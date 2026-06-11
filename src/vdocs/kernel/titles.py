"""Title de-noising — the clean display name (version/patch stripped) for a document.

The single home of the title-normalization rules (see
``docs/title-normalization-proposal.md``). A gold document title embeds version
and patch tokens that bury the application name and vary per app — yet that
information is already parsed into the ``version``/``patch_id`` fields. This
strips it from the *display* title so the application/product name leads.

Pure: no I/O, no logging. The ``index`` stage applies it when building the
``documents`` rows (clean ``title`` + preserved raw ``title_source``), passing
the application's canonical ``app_name`` so a title that was *only* a patch
token + a doc-type label (e.g. a "Change Pages" addendum) still names its app.

Design rule (precision): ``Version``/``Release`` are removed **only when
followed by a number**, so plain-word senses ("GUI Version", "Release Notes")
survive untouched.
"""

from __future__ import annotations

import re

__all__ = ["clean_title"]

# Strip rules, applied in order. Each removes one class of version/patch noise.
_STRIP: tuple[re.Pattern[str], ...] = (
    re.compile(r"\s*\(\s*updated[^)]*\)", re.I),  # (Updated PSN*4.0*575)
    re.compile(r"\s*\([A-Z][A-Z0-9]*\*[\d.*]+\)"),  # (GMRC*3.0*189)
    re.compile(r"\b[A-Z][A-Z0-9]+\*\d+(?:\.\d+)*(?:\*\d+)?"),  # PSO*7.0*123 / IB*2
    re.compile(r"\b[A-Z]{2,}\s+\d+\.\d+\s+\d+\b"),  # SD 5.3 574
    re.compile(r"\b(?:version|release|rel\.?|ver\.?)[\s.]*\d+(?:\.\d+)*[A-Za-z]?\b", re.I),
    re.compile(r"\bv\.?\s*\d+(?:\.\d+)+\b", re.I),  # v1.5 / V. 1.6
    re.compile(r"\b\d+\.\d+(?:\.\d+)*\b"),  # bare dotted version (VSE 1.7.2.1)
    re.compile(r"\b\d+\.\d+\*\d+\b"),  # orphan 1.6*14
    re.compile(r"\*\d+\b"),  # orphan *14
)

_EMPTY_PARENS = re.compile(r"\(\s*\)")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([:,])")
_MULTISPACE = re.compile(r"\s{2,}")
_TRAILING_PUNCT = re.compile(r"\s*[:\-–]\s*$")
_LEADING_JUNK = re.compile(r"^[\s:\-–,]+")

# doc-type / role label words — used to detect a title that, once de-noised, is
# only a label (no product name) and so needs the app-name fallback.
_LABEL = re.compile(
    r"\b(user|technical|installation|developer'?s?|security|supervisor'?s?|programmer'?s?"
    r"|nurse'?s?|inspector'?s?|clinical coordinator|manual|guide|guides|handbook|reference"
    r"|card|notes|addendum|supplement|update|page|pages|change|menu|gui)\b",
    re.I,
)
_NON_ALNUM = re.compile(r"[^A-Za-z0-9]")


def clean_title(raw: str, app_name: str = "") -> str:
    """Return the display title for ``raw`` with version/patch tokens removed.

    If the result is only a doc-type label (no product name — e.g. a title that
    was just ``PSJ*5*279 Nurse's User Manual Change Pages``), it is prefixed with
    ``app_name``. A fully-collapsed result falls back to ``app_name`` (or the
    trimmed raw if no app name is known).
    """
    s = _denoise(raw)
    if not s:
        return app_name or (raw or "").strip()
    if app_name and _label_only(s):
        return f"{app_name} — {s}"
    return s


def _denoise(raw: str) -> str:
    """Strip version/patch tokens and tidy — the de-noised title, no name fallback."""
    s = raw or ""
    for rx in _STRIP:
        s = rx.sub(" ", s)
    return _tidy(s)


# ── abbreviation-first display title (product-prefixed) ─────────────────────

_DOCKIND = re.compile(
    r"\b(user|technical|installation|deployment|security|supervisor|manager|pharmacist|"
    r"technician|nurse|inspector|programmer|clinician|developer|manual|guide|guides|handbook|"
    r"reference|card|notes|addendum|supplement|appendix|specification|spec|overview|setup|"
    r"training|getting|quick|release|change|package|menu|module)\b",
    re.I,
)
_LEAD_PARENS = re.compile(r"^\s*\([^)]*\)")  # a leftover "(ABBR)" right after a stripped name


def _starts_with(text: str, prefix: str) -> bool:
    """Case-insensitive prefix match at a word boundary (so 'RA' ≠ 'Radiology')."""
    if not prefix or len(text) < len(prefix):
        return False
    if text[: len(prefix)].lower() != prefix.lower():
        return False
    rest = text[len(prefix) :]
    return rest == "" or not rest[0].isalnum()


def _heuristic_lead(t: str) -> str:
    """The product/app name a title leads with = its text before the first doc-kind word."""
    m = _DOCKIND.search(t)
    return (t[: m.start()] if m else t).strip(" -–:/")


def _strip_domain_prefix(name: str) -> str:
    """Drop a leading 'Pharmacy: ' / 'CPRS: ' / 'Registry: ' qualifier from a name."""
    return name.split(": ", 1)[1] if ": " in name else name


def display_title(
    raw: str, app_code: str, app_name: str, products: list[dict]
) -> tuple[str, str, str]:
    """Build the abbreviation-first display title for a document.

    Returns ``(title, product_abbr, product_full)`` where ``title`` is
    ``"<ABBR> — <distinguishing suffix>"`` (version/patch removed, the product
    name replaced by its dense abbreviation so titles cluster and sort by
    product). ``products`` is the registry entry list for ``app_code`` ([] if
    none → defaults to the application's own name/code).
    """
    t = _denoise(raw)
    abbr = full = ""
    matched = ""
    # 1) registry product whose longest match-alias is a word-boundary prefix
    for p in products:
        for alias in p["match"]:
            if _starts_with(t, alias) and len(alias) > len(matched):
                abbr, full, matched = p["abbr"], p["full"], alias
    # 2) default: the application itself
    if not abbr:
        abbr = app_code
        full = app_name or app_code
        for cand in sorted({app_name, _strip_domain_prefix(app_name)}, key=len, reverse=True):
            if cand and _starts_with(t, cand):
                matched = cand
                break
        else:
            matched = _heuristic_lead(t)
    # 3) suffix = the title minus the matched product/app name, de-chromed
    rest = t[len(matched) :] if matched and _starts_with(t, matched) else t
    rest = _LEAD_PARENS.sub("", rest)
    suffix = rest.strip(" -–:,/")
    title = f"{abbr} — {suffix}" if suffix else abbr
    return title, abbr, full


def _tidy(s: str) -> str:
    s = _EMPTY_PARENS.sub("", s)
    s = _SPACE_BEFORE_PUNCT.sub(r"\1", s)
    s = _MULTISPACE.sub(" ", s)
    s = _TRAILING_PUNCT.sub("", s)
    s = _LEADING_JUNK.sub("", s)
    return s.strip()


def _label_only(s: str) -> bool:
    """True when ``s`` has no real name residue after removing doc-type labels."""
    return len(_NON_ALNUM.sub("", _LABEL.sub("", s))) < 3
