"""Pure inventory-enrichment engine — the 5 passes + system classification (Phase C, §4).

A faithful port of the v1 ``enrich_inventory.py`` + ``classify_vista_type.py`` logic, made
pure: every function takes plain values (row dicts + the loaded :class:`Registries`) and
returns plain values — no I/O, no globals, no network, no time. The thin ``catalog`` stage
driver supplies the raw rows (flattened from ``catalog.raw``) and the registries, then
serializes the result.

Order is load-bearing (§4): pass 1 (per-row identity/parse) → pass 2 (corpus-global noise,
companion pairing, package canon, derived keys) → pass 3 (group-key peer inference) →
pass 4 (manual overrides) → pass 5 (canonical labels) → system classification. The
``anchor_key`` (``app:pkg:doc_code``, version-free) is a vdocs addition beyond v1 (§9.4),
consumed downstream by ``consolidate``.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import PurePosixPath
from urllib.parse import urlparse

from vdocs.kernel.ids import anchor_key
from vdocs.kernel.text import month_year_iso, repair_mojibake
from vdocs.stages.catalog.registries import (
    AppSpecificMap,
    DocTypePattern,
    Registries,
    SuffixMap,
    TypoCorrection,
)

CompiledPatterns = list[tuple[re.Pattern[str], str, str]]

# --- patch-identity regexes (§6.2, verbatim from v1) -----------------------
PATCH_A = re.compile(
    r"^(?:[A-Za-z ]+\s)?([A-Z][A-Z0-9]+)\*([\d]+(?:\.[\d]+)?)\*(\d+)(?:/\d+)*\s*(.*)",
    re.DOTALL,
)
PATCH_FULL = re.compile(
    r"^(?:[A-Za-z ]+\s)?([A-Z][A-Z0-9]+\*[\d.]+\*\d+(?:/[A-Z][A-Z0-9]+\*[\d.]+\*\d+)*)",
    re.DOTALL,
)
MULTI_NS_RE = re.compile(r"[A-Z][A-Z0-9]+\*[\d.]+\*\d+/[A-Z][A-Z0-9]+\*")
PATCH_B = re.compile(
    r"(?:[Vv]ersion\s+|[Vv](?=\d)|Release\s+)(\d+(?:\.\d+)*)|\b(\d+\.\d+(?:\.\d+)?)\b"
)
FNAME_VER = re.compile(r"^[a-z0-9]+_(\d+)_(\d+)", re.IGNORECASE)
FNAME_PATCH = re.compile(r"_p?(\d{3,5})_", re.IGNORECASE)
ABBR_RE = re.compile(r"\s*\(([A-Z0-9/+\-]{1,10})\)\s*$")
_SLUG_SUFFIX_RE = re.compile(r"[_\-]([a-z]{2,8})$", re.IGNORECASE)
_SLUG_NON_ALNUM = re.compile(r"[^a-z0-9]+")

# Catalog dates are a strict ``MON YYYY`` *field* (not free text), so the recognised shape is
# anchored to exactly three month-letters + a year; the month→number mapping itself is the shared
# kernel table (§9.2 — one month table for the corpus), applied via ``month_year_iso``.
_DATE_RE = re.compile(r"^[A-Za-z]{3}\s+\d{4}$")

# doc_subject cleaning artifacts
_BARE_YEAR_RE = re.compile(r"^\d{4}$")
_BARE_VERSION_RE = re.compile(r"^[\d.]+$")
_BARE_PUNCT_RE = re.compile(r"^[*\s,\-]+$")
_PATCH_ARTIFACT_RE = re.compile(r"^\*\d+")
_PATCH_ID_RE = re.compile(r"^[A-Z][A-Z0-9]+\*[\d.]+\*\d+(?:/[A-Z][A-Z0-9]+\*[\d.]+\*\d+)*$")
_DIBR_PHRASE_RE = re.compile(
    r"Deployment[,\s]+Installation[,\s]+Back.?Out[,\s]+and[,\s]+Rollback\s*Guide?", re.IGNORECASE
)
_VBA_TITLE_RE = re.compile(r"^\d{2}[–\-]\d+")
_VBA_FNAME_RE = re.compile(r"^(?:VBA|SF)\d", re.IGNORECASE)
_VBA_SUBJ_RE = re.compile(r"^[\d–\-]+\s*[–\-—]\s*")


# --- text fixers (§4.1, §9.3) ----------------------------------------------
def fix_mojibake(text: str) -> str:
    """Repair encoding artifacts via the shared kernel fixer (§9.2). Idempotent."""
    if not text:
        return ""
    return repair_mojibake(text)


def apply_typo_corrections(
    text: str, field: str, corrections: tuple[TypoCorrection, ...]
) -> tuple[str, list[str]]:
    """Apply each correction whose ``fields`` include ``field``; return (text, replaced_sources)."""
    if not text:
        return "", []
    aliases: list[str] = []
    out = text
    for c in corrections:
        if field in c.fields and c.source in out:
            out = out.replace(c.source, c.corrected)
            aliases.append(c.source)
    return out, aliases


# --- small derivations (§4.2) ----------------------------------------------
def normalize_date(raw: str) -> str:
    """'DEC 2019' → '2019-12'; unchanged if unrecognised. The strict ``MON YYYY`` field shape is
    catalog-local; the month→number conversion is the shared ``month_year_iso`` (§9.2)."""
    if not raw:
        return ""
    if _DATE_RE.match(raw.strip()) and (iso := month_year_iso(raw.strip())):
        return iso
    return raw


def split_patch_ver(ver: str) -> tuple[str, str]:
    """(major, minor) as int-strings; minor 0 when major-only; ('','') if non-numeric."""
    if not ver:
        return "", ""
    parts = ver.split(".")
    try:
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
        return str(major), str(minor)
    except ValueError:
        return "", ""


def classify_noise(url: str, vba_hosts: frozenset[str]) -> str:
    """noise_type for a shared (repeated) URL: vba_form | va_ref | '' (within VDL)."""
    p = urlparse(url)
    if p.netloc.lower() in vba_hosts:
        return "vba_form"
    if "/vdl/" not in p.path:
        return "va_ref"
    return ""


def make_doc_slug(doc_filename: str) -> str:
    """Filesystem-path slug for a document's bundle: lowercased stem, **every** non-alnum run → '_',
    trimmed. PDF/DOCX pairs share it.

    Deliberately NOT ``kernel.text.slugify`` (the GitHub-anchor rule): this is a path-safety
    transform that *collapses* punctuation rather than dropping it, so a filename version like
    ``DG_5.3`` becomes ``dg_5_3`` (the ``.`` is a separator here, not deleted as in an anchor).
    Different purpose, different rule — kept local to ``catalog`` (its only consumer), not a §9.2
    duplicate of the anchor slug."""
    stem = PurePosixPath(doc_filename).stem
    return _SLUG_NON_ALNUM.sub("_", stem.lower()).strip("_")


# --- doc-type classification (§4.1, §6.3-6.4) ------------------------------
def compile_doc_types(patterns: tuple[DocTypePattern, ...]) -> CompiledPatterns:
    """Pre-compile the ordered title-classifier rules (most-specific first)."""
    return [(re.compile(p.pattern, re.IGNORECASE), p.code, p.label) for p in patterns]


def classify_doc_type(text: str, compiled: CompiledPatterns) -> tuple[str, str]:
    """First matching (code, label) for ``text``, or ('', '')."""
    for pattern, code, label in compiled:
        if pattern.search(text):
            return code, label
    return "", ""


def classify_by_filename(
    doc_slug: str, app_abbrev: str, suffix_map: SuffixMap, app_specific: AppSpecificMap
) -> tuple[str, str]:
    """Filename-suffix fallback (title takes precedence). App-specific overrides win."""
    stem = PurePosixPath(doc_slug).stem
    m = _SLUG_SUFFIX_RE.search(stem)
    if not m:
        return "", ""
    suf = m.group(1).lower()
    if (override := app_specific.get((app_abbrev, suf))) is not None:
        return override
    return suffix_map.get(suf, ("", ""))


def extract_subject(title: str, patch_prefix: str, doc_label: str) -> str:
    """Strip patch prefix + doc-label + residual DIBR phrase; trim edge punctuation."""
    remainder = title
    if patch_prefix:
        remainder = remainder[len(patch_prefix) :].strip()
    if doc_label:
        remainder = re.sub(re.escape(doc_label), "", remainder, flags=re.IGNORECASE).strip()
    remainder = _DIBR_PHRASE_RE.sub("", remainder).strip()
    remainder = re.sub(r"^[\s\-–—:,]+|[\s\-–—:,]+$", "", remainder)
    return remainder


def clean_doc_subject(subject: str, app_abbrev: str, doc_title: str, doc_label: str) -> str:
    """Clear redundant/artefact subjects; keep genuine qualifiers (§4.2 step 3)."""
    if not subject:
        return ""
    s = subject.strip()
    if not s:
        return ""
    if app_abbrev and s.upper() == app_abbrev.upper():
        return ""
    if s == doc_title:
        return ""
    if doc_label and s == doc_label:
        return ""
    if s.startswith("/"):
        return ""
    if _BARE_YEAR_RE.match(s) or _BARE_VERSION_RE.match(s) or _BARE_PUNCT_RE.match(s):
        return ""
    if _PATCH_ARTIFACT_RE.match(s) or _PATCH_ID_RE.match(s):
        return ""
    if len(s) <= 2 and not any(c.isalpha() for c in s):
        return ""
    return s


# --- pass 1: per-row patch identity + doc type + subject (§4.1) ------------
def parse_row(
    row: dict, compiled: CompiledPatterns, suffix_map: SuffixMap, app_specific: AppSpecificMap
) -> dict:
    """The heart: derive patch identity, doc-type, subject for one row."""
    title = row["doc_title"].strip()
    doc_filename = row["doc_filename"].strip()
    app_code = row.get("app_name_abbrev", "").strip() or (
        m.group(1) if (m := ABBR_RE.search(row.get("app_name_full", ""))) else ""
    )

    pkg_ns = patch_ver = patch_num = doc_code = doc_label = doc_subj = patch_id_full = ""
    multi_ns = "0"

    if MULTI_NS_RE.search(title):
        multi_ns = "1"
        if (mf := PATCH_FULL.match(title)) is not None:
            patch_id_full = mf.group(1)

    m = PATCH_A.match(title)
    if m:
        pkg_ns = m.group(1)
        patch_ver = m.group(2)
        patch_num = str(int(m.group(3)))
        remainder = m.group(4).strip()
        doc_code, doc_label = classify_doc_type(remainder, compiled)
        if not doc_code:
            doc_code, doc_label = classify_by_filename(
                doc_filename, app_code, suffix_map, app_specific
            )
        doc_subj = extract_subject(remainder, "", doc_label)
    else:
        m_ver = PATCH_B.search(title)
        if m_ver:
            patch_ver = m_ver.group(1) or m_ver.group(2)
            pkg_ns = app_code
            remainder_b = title[m_ver.end() :].strip()
        else:
            remainder_b = title
            if (m_fn := FNAME_VER.match(doc_filename.lower())) is not None:
                patch_ver = f"{m_fn.group(1)}.{m_fn.group(2)}"
                pkg_ns = app_code
        if not patch_num and (m_fp := FNAME_PATCH.search(doc_filename)) is not None:
            patch_num = str(int(m_fp.group(1)))
        doc_code, doc_label = classify_doc_type(title, compiled)
        if not doc_code:
            doc_code, doc_label = classify_by_filename(
                doc_filename, app_code, suffix_map, app_specific
            )
        doc_subj = extract_subject(remainder_b, "", doc_label)

    if _VBA_TITLE_RE.match(title) or _VBA_FNAME_RE.match(doc_filename):
        doc_code = "FORM"
        doc_label = "VBA Form"
        doc_subj = _VBA_SUBJ_RE.sub("", title).strip()
        pkg_ns = patch_ver = patch_num = ""

    return {
        "pkg_ns": pkg_ns,
        "patch_ver": patch_ver,
        "patch_num": patch_num,
        "doc_code": doc_code,
        "doc_label": doc_label,
        "doc_subject": doc_subj,
        "patch_id_full": patch_id_full,
        "multi_ns": multi_ns,
    }


# --- canonical label (§4.5) ------------------------------------------------
def apply_canonical_label(doc_code: str, current: str, labels: dict[str, str]) -> tuple[str, str]:
    """Collapse label drift: (canonical, subtitle); subtitle keeps the divergent original."""
    if not doc_code or doc_code not in labels:
        return current, ""
    canonical = labels[doc_code]
    if current and current != canonical:
        return canonical, current
    return canonical, ""


# --- system classification (Stage C, §4.6) ---------------------------------
def classify_system(abbrev: str, reg: Registries) -> tuple[str, bool]:
    """(system_type, cots_dependent) by app abbrev; 'unclassified' if unmapped."""
    return reg.system_type.get(abbrev, "unclassified"), abbrev in reg.cots_dependency


# --- the full pipeline -----------------------------------------------------
def enrich_rows(rows: list[dict], reg: Registries) -> list[dict]:
    """Run passes 1-5 + system classification over raw rows; return enriched rows.

    Each input row carries the raw crawl fields (doc_title, filename, file_ext, app_name,
    section_name, app_status, decommission_date, doc_url, app_url). Returns new dicts with
    the full enriched field set (§5) including ``anchor_key`` (vdocs addition).
    """
    compiled = compile_doc_types(reg.doc_type_patterns)

    # --- Pass 1: per-row rename, repair, parse ---
    enriched: list[dict] = []
    for raw in rows:
        row = dict(raw)
        row["doc_filename"] = row.pop("filename", row.get("doc_filename", ""))
        row["doc_file_ext"] = row.pop("file_ext", row.get("doc_file_ext", ""))
        for f in ("doc_title", "doc_subject", "app_name"):
            if f in row:
                row[f] = fix_mojibake(row[f])
        m = ABBR_RE.search(row.get("app_name", ""))
        row["app_name_abbrev"] = m.group(1) if m else ""
        if m:
            row["app_name"] = ABBR_RE.sub("", row["app_name"]).strip()
        row["app_name_full"] = row.pop("app_name", "")
        aliases: list[str] = []
        for f in ("doc_title", "doc_subject", "app_name_full"):
            if f in row:
                row[f], a = apply_typo_corrections(row[f], f, reg.typo_corrections)
                aliases.extend(a)
        parsed = parse_row(row, compiled, reg.slug_suffix_map, reg.app_specific_suffix)
        parsed["doc_search_aliases"] = "|".join(dict.fromkeys(aliases))
        enriched.append({**row, **parsed})

    # --- Pass 2 setup: corpus-global structures ---
    url_counts = Counter(r["doc_url"] for r in enriched)
    shared_urls = {u for u, c in url_counts.items() if c > 1}
    base_to_urls: dict[str, dict[str, str]] = defaultdict(dict)
    for r in enriched:
        base, ext = _split_url_ext(r["doc_url"])
        base_to_urls[base][ext] = r["doc_url"]

    # --- Pass 2: per-row global enrichment ---
    for row in enriched:
        if not row["app_name_abbrev"]:
            row["app_name_abbrev"] = (
                reg.abbrev_fallback.get(row["app_name_full"], "") or row["pkg_ns"]
            )
        entry = reg.packages.get(row["app_name_abbrev"])
        if entry is not None:
            original = row["app_name_full"]
            row["app_name_full"] = entry.canonical_name
            row["doc_subject_raw"] = original if original != entry.canonical_name else ""
            if not row["pkg_ns"] and entry.pkg_ns:
                row["pkg_ns"] = entry.pkg_ns
            row["canonical_pkg"] = entry.canonical_pkg
        else:
            row["doc_subject_raw"] = ""
            row["canonical_pkg"] = row["app_name_abbrev"]

        row["doc_subject"] = clean_doc_subject(
            row.get("doc_subject", ""), row["app_name_abbrev"], row["doc_title"], row["doc_label"]
        )
        row["section_code"] = reg.section_code.get(row["section_name"], "")
        row["decommission_date"] = normalize_date(row.get("decommission_date", ""))
        row["patch_ver_major"], row["patch_ver_minor"] = split_patch_ver(row["patch_ver"])

        has_ver, has_num = bool(row["patch_ver"]), bool(row["patch_num"])
        row["doc_layer"] = "anchor" if has_ver and not has_num else "patch" if has_num else "plain"

        ns, ver, num = row["pkg_ns"], row["patch_ver"], row["patch_num"]
        if ns and ver and num:
            row["patch_id"] = f"{ns}*{ver}*{num}"
        elif ns and ver:
            row["patch_id"] = f"{ns}*{ver}"
        else:
            row["patch_id"] = ""
        row["doc_format"] = row["doc_file_ext"].lstrip(".") if row["doc_file_ext"] else ""
        abbrev = row["app_name_abbrev"]
        row["group_key"] = (
            f"{abbrev}:{row['pkg_ns']}:{row['patch_ver']}" if row["patch_ver"] else ""
        )
        row["noise_type"] = (
            classify_noise(row["doc_url"], reg.vba_form_hosts)
            if row["doc_url"] in shared_urls
            else ""
        )
        base, ext = _split_url_ext(row["doc_url"])
        row["companion_url"] = next(
            (u for e, u in base_to_urls.get(base, {}).items() if e != ext), ""
        )
        row["doc_slug"] = make_doc_slug(row["doc_filename"])
        # github columns: blank unless a url_map is supplied (not wired in vdocs yet)
        row["github_md_url"] = ""
        row["github_md_raw_url"] = ""

    # --- Pass 3: group_key peer inference ---
    by_group: dict[str, list[dict]] = defaultdict(list)
    for row in enriched:
        if row["group_key"] and not row["noise_type"]:
            by_group[row["group_key"]].append(row)
    for row in enriched:
        if row["doc_code"] or row["noise_type"] or not row["group_key"]:
            continue
        peers = [
            p["doc_code"]
            for p in by_group[row["group_key"]]
            if p["doc_code"] and p["doc_slug"] != row["doc_slug"]
        ]
        if peers and len(set(peers)) == 1:
            row["doc_code"] = peers[0]
            row["doc_label"] = next(
                p["doc_label"] for p in by_group[row["group_key"]] if p["doc_code"] == peers[0]
            )

    # --- Pass 4: manual overrides ---
    for row in enriched:
        slug = row["doc_slug"]
        if slug in reg.manual_noise:
            row["noise_type"] = "test_document"
            row["doc_code"] = ""
            row["doc_label"] = ""
        elif slug in reg.manual_overrides:
            row["doc_code"], row["doc_label"] = reg.manual_overrides[slug]

    # --- Pass 5: canonical label + doc_labelling + anchor_key + system class ---
    for row in enriched:
        row["doc_label"], row["doc_subtitle"] = apply_canonical_label(
            row["doc_code"], row["doc_label"], reg.doc_labels
        )
        row["doc_labelling"] = "manual" if row["doc_slug"] in reg.manual_slugs else "code"
        row["anchor_key"] = anchor_key(row["app_name_abbrev"], row["pkg_ns"], row["doc_code"])
        row["system_type"], row["cots_dependent"] = classify_system(row["app_name_abbrev"], reg)

    return enriched


def _split_url_ext(url: str) -> tuple[str, str]:
    """(base, '.ext-lowercased') split on the last path segment's dot; ('url','') if none."""
    last = url.split("/")[-1]
    if "." in last:
        return url.rsplit(".", 1)[0], "." + url.rsplit(".", 1)[1].lower()
    return url, ""
