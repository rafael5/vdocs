"""Pure pattern miners for `discover` — propose candidates, mutate nothing (§9.6).

`discover` is inductive and corpus-global: it reads the converted bodies and *proposes*
candidate patterns (with evidence + a disposition + a confidence grade) to ``reports/patterns``.
A separate **curation gate** promotes high-confidence candidates into the version-controlled
``registries/``; only then does `normalize` subtract them. These functions are the miners —
pure functions of ``{doc_id: markdown}`` in, candidates out. The clustering/shingling
primitives they could build on live once in ``kernel/discovery`` (tenet #4).
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from math import ceil

from pydantic import BaseModel, Field

from vdocs.kernel import discovery as kd
from vdocs.kernel.markdown import is_markdown_artifact, iter_headings
from vdocs.kernel.text import block_key as block_key  # shared block identity (§9.2); re-exported
from vdocs.kernel.text import decade_bucket, slugify

_WS = re.compile(r"\s+")
_BLOCK_SPLIT = re.compile(r"\n\s*\n")
# `#+` (not `#{1,6}`): a recurring block that opens with an oversized heading is still template
# scaffold — the canonical heading resolution shared across the markdown stages (kernel.markdown).
_HEADING = re.compile(r"^#+\s")
_BARE_MARKER_RE = re.compile(r"^[ \t]*(?:\d+\.|[-*])[ \t]*$", re.MULTILINE)
_ACRONYM = re.compile(r"\b[A-Z][A-Z0-9]{1,7}\b")
_SAMPLE = 5  # how many example doc_ids to carry as evidence
_MAX_VARIANTS = 8  # styling variants carried as canonicalization evidence

# --- structural-convention detection (registries/structures, §9.7 CANONICALIZE) ---
# A callout/admonition line: an optional bold wrapper around a known label, then a colon — the
# real corpus styles "Note" a dozen ways (**Note:, NOTE:, **Note** :, Note:); all canonicalize
# to one GFM alert. Labels that map to a GitHub alert use `> [!LABEL]`; the rest a bold blockquote.
_CALLOUT_RE = re.compile(
    r"^[ \t]*\**[ \t]*(note|caution|warning|important|tip|example|reminder)\b\**[ \t]*\**[ \t]*:",
    re.IGNORECASE | re.MULTILINE,
)
_GFM_ALERTS = frozenset({"note", "tip", "important", "warning", "caution"})
_TOC_RE = re.compile(
    r"^#{1,3}[ \t]+(?:table of contents|contents)[ \t]*$", re.IGNORECASE | re.MULTILINE
)
_REVTABLE_RE = re.compile(
    r"^#{1,3}[ \t]+(?:revision history|revisions)[ \t]*$", re.IGNORECASE | re.MULTILINE
)

# --- (doc_type, era) template induction (§9.8 / ADR-018,019) ---
# era comes from the title-page publication date, bucketed by decade (the shared kernel helper
# `decade_bucket` — also used by `normalize` template matching). The title-page window is the front
# matter; missing date yields "unknown".
_TITLE_PAGE_LINES = 40  # the title-page window (front matter) scanned for a publication date

# common all-caps English/header words that are not glossary terms (real-corpus noise: the
# acronym shape over-matches NO/YES/TO/… and form-field labels). Curation can still add real ones.
_GLOSSARY_STOPWORDS = frozenset(
    {
        "A", "AN", "AND", "ARE", "AS", "AT", "BE", "BY", "FOR", "IF", "IN", "IS", "IT", "NO",
        "NOT", "OF", "ON", "OR", "TO", "THE", "YES", "ALL", "ANY", "NEW", "OLD", "SEE", "USE",
        "ADD", "SET", "GET", "MAY", "CAN", "WILL", "FROM", "WITH", "THIS", "THAT", "NAME", "NOTE",
        "DATE", "PAGE", "TIME", "TYPE", "ITEM", "STEP", "TRUE", "FALSE", "REDACTED", "TBD", "NA",
    }
)  # fmt: skip


class PatternCandidate(BaseModel):
    """One proposed pattern: which registry, how to dispose of it, and the evidence for it."""

    registry: str  # boilerplate | phrases | glossary
    disposition: str  # REFERENCE | DELETE | PROMOTE (§9.6)
    key: str  # the identity used by `normalize` (normalised block / term)
    text: str  # a representative original spelling
    doc_count: int  # how many distinct documents it appears in
    sample_doc_ids: list[str] = Field(default_factory=list)
    grade: str  # auto | review (the curation-gate hint)


class RoutingCandidate(BaseModel):
    """A convert-quality verdict proposing a different converter for one document (§9.6,
    ADR-010 ``registries/converter-routing``). Some VA DOCX wrap their lists in Word
    ``[[…]](#_Toc…)`` cross-reference fields; Pandoc detaches each marker from its content,
    **exploding lists into thousands of bare markers** (a marker alone on a line). Docling
    reconstructs the lists cleanly (verified on ``cprsguium``: 3,058 bare markers → 0; proper
    list items 332 → 3,230). This flags such docs as Docling ROUTE candidates with the evidence."""

    doc_id: str  # the bundle path <app>/<slug>
    suggested_converter: str  # docling
    reason: str
    xref_wraps: int  # Word `[[…]]` cross-ref wraps in the Pandoc output (the strong trigger)
    bare_markers: int  # list markers alone on a line — the explosion Docling fixes


class StructureCandidate(BaseModel):
    """A recurring **structural convention** → ``registries/structures`` (CANONICALIZE, §9.7).

    The same structural intent is rendered many ways across the corpus — the "Note" callout
    appears as ``**Note:``, ``NOTE:``, ``**Note** :`` …; the contents heading as
    ``# Table of Contents`` / ``# Contents`` at varying levels. Each is one *convention* with many
    source ``variants`` that `normalize` should rewrite to one ``canonical_form`` (standard GFM)."""

    convention: str  # callout | toc | revision-table
    disposition: str = "CANONICALIZE"  # §9.7 structures disposition (fixed)
    key: str  # convention id, e.g. "callout:note", "toc:contents", "revision-table"
    canonical_form: str  # the standard GFM form to rewrite to (the curation target)
    variants: list[str] = Field(default_factory=list)  # distinct source stylings observed
    doc_count: int  # documents exhibiting the convention
    sample_doc_ids: list[str] = Field(default_factory=list)
    grade: str  # auto | review (the curation-gate hint)


class TemplateSection(BaseModel):
    """One row of a template's retained **computable** structural schema (§9.8): an expected
    section, rich enough to be a validation oracle (the template-compliance check) and a reuse
    asset, not just a strippable title."""

    section_id: str  # slug of the consensus title — the stable section identity
    title: str  # the consensus (most common) heading title
    title_pattern: str  # a regex matching the section's title across docs (numbering-tolerant)
    level: int  # the modal heading level (1–6, or >6 for oversized ATX)
    required: bool  # present in ≥ REQUIRED_RATIO of cluster members (§9.8 — not "every member")
    repeatable: bool  # the section legitimately recurs within a doc (e.g. per-patch subsections)
    semantic_role: str | None  # the section's role (orientation/installation/…), null if unknown
    toc_level: bool  # whether it belongs in the regenerated TOC (level ≤ 3, §6.7)


class TemplateCandidate(BaseModel):
    """An induced per-``(doc_type, era)`` template (§9.8/ADR-018): the scaffold each manual of a
    type+era was poured into. Disposition **STRIP** — the literal scaffold leaves the body and a
    ``template_id`` is stamped — but the ordered structural ``schema`` is **RETAINED** (an asset,
    not just noise: the validation oracle + reuse source). Proposal only; curation approves it."""

    template_id: str  # "<doc_type>:<era>:<scaffold-fp8>" — stable identity stamped onto bodies
    doc_type: str  # the catalog doc_code (UM/TM/IG/…)
    era: str  # decade bucket of the title-page date (e.g. "2010s") or "unknown"
    disposition: str = "STRIP"  # §9.7 templates disposition (STRIP body + stamp + RETAIN schema)
    sections: list[TemplateSection] = Field(default_factory=list)  # the retained structural schema
    doc_count: int  # cluster size (docs sharing this scaffold)
    sample_doc_ids: list[str] = Field(default_factory=list)
    grade: str  # auto | review (the curation-gate hint)


class PatternReport(BaseModel):
    """The ``reports/patterns`` artifact: candidate patterns, pre-curation. ``blocks`` holds the
    recurring-block candidates (each tagged ``registry`` = templates | phrases | boilerplate);
    ``converter_routing`` holds per-document convert-quality routing candidates; ``structures``
    holds recurring structural-convention candidates; ``templates`` holds the induced
    ``(doc_type, era)`` template candidates with their retained schemas (§9.8)."""

    blocks: list[PatternCandidate] = Field(default_factory=list)
    glossary: list[PatternCandidate] = Field(default_factory=list)
    converter_routing: list[RoutingCandidate] = Field(default_factory=list)
    structures: list[StructureCandidate] = Field(default_factory=list)
    templates: list[TemplateCandidate] = Field(default_factory=list)


def split_blocks(markdown: str) -> list[str]:
    """Split a body into blocks on blank lines; trimmed, non-empty (paragraph grain).

    A block whose lines are *entirely* markdown artifacts — nav/TOC links, ``<img>`` figure tags,
    table-CSV markers (``kernel.markdown.is_markdown_artifact``, §9.2) — is dropped, so that
    structural furniture never surfaces as "boilerplate" (the dominant noise the spike found: a
    `[↑ Back to Contents](#contents)` line present in every DIBR doc). Headings and prose are kept,
    including a paragraph that merely *contains* an inline link (block grain is preserved — a block
    is dropped only when every one of its lines is an artifact)."""
    blocks: list[str] = []
    for raw in _BLOCK_SPLIT.split(markdown):
        b = raw.strip()
        if not b:
            continue
        lines = [ln for ln in b.splitlines() if ln.strip()]
        # drop if every line is an artifact, or the whole block collapses to a single artifact
        # (a multi-line ``<img …>`` tag spread across lines) — handles both grains.
        if all(is_markdown_artifact(ln) for ln in lines) or is_markdown_artifact(" ".join(lines)):
            continue
        blocks.append(b)
    return blocks


def mine_recurring_blocks(
    docs: dict[str, str],
    *,
    min_docs: int = 3,
    auto_docs: int = 10,
    phrase_max_len: int = 60,
    near_dup_threshold: float = 0.8,
) -> list[PatternCandidate]:
    """Blocks recurring across ≥ ``min_docs`` documents → candidates.

    Disposition (the curation hint; §9.6) by block shape:
      * a **heading** (``# …``) is template scaffold → ``templates`` (RETAIN — *never* deleted);
      * a short single-line non-heading is paper-era furniture → ``phrases`` (DELETE);
      * a longer block is meaningful-but-duplicated → ``boilerplate`` (REFERENCE).
    Frequent ones (≥ ``auto_docs``) grade ``auto``, the rest ``review`` — except DELETE proposals
    are always ``review`` (deleting content is never auto-approved on frequency alone).

    Exact whitespace-collapsed equality (``block_key``) is the cheap pre-bucket. On top of it the
    **boilerplate** path runs MinHash/Jaccard near-duplicate clustering (``kernel/discovery``) so
    blocks that drift by a word or two across docs cluster into one candidate whose ``doc_count``
    is the union — boilerplate is rarely byte-identical corpus-wide (§9.6 step 1). Headings
    (templates) and short phrases stay exact-keyed: merging distinct headings or furniture would
    blur identities the curation gate needs sharp."""
    key_docs: dict[str, set[str]] = defaultdict(set)
    key_text: dict[str, str] = {}
    for doc_id, md in docs.items():
        for k, original in {block_key(b): b for b in split_blocks(md)}.items():
            key_docs[k].add(doc_id)
            key_text.setdefault(k, original)

    boiler_keys: list[str] = []
    candidates: list[PatternCandidate] = []
    for k in key_docs:
        registry, disposition = _classify_block(key_text[k], phrase_max_len)
        if registry == "boilerplate":
            boiler_keys.append(k)  # deferred — clustered below across near-dup spellings
            continue
        if len(key_docs[k]) >= min_docs:
            candidates.append(
                _block_candidate(registry, disposition, k, key_text[k], key_docs[k], auto_docs)
            )

    candidates.extend(
        _cluster_boilerplate(
            boiler_keys, key_docs, key_text, min_docs, auto_docs, near_dup_threshold
        )
    )
    candidates.sort(key=lambda c: (-c.doc_count, c.key))
    return candidates


def _block_candidate(
    registry: str, disposition: str, key: str, text: str, docs: set[str], auto_docs: int
) -> PatternCandidate:
    frequent = len(docs) >= auto_docs
    return PatternCandidate(
        registry=registry,
        disposition=disposition,
        key=key,
        text=text,
        doc_count=len(docs),
        sample_doc_ids=sorted(docs)[:_SAMPLE],
        # never auto-approve a deletion on frequency alone (a heading recurs too)
        grade="auto" if frequent and disposition != "DELETE" else "review",
    )


def _cluster_boilerplate(
    keys: list[str],
    key_docs: dict[str, set[str]],
    key_text: dict[str, str],
    min_docs: int,
    auto_docs: int,
    threshold: float,
) -> list[PatternCandidate]:
    """Near-dup cluster the boilerplate-shaped exact buckets, one candidate per cluster.

    The cluster's identity is its dominant member (most docs, then lexical) and its ``doc_count``
    is the union of every near-identical spelling's documents — so spellings that each fall below
    ``min_docs`` can still qualify together."""
    if not keys:
        return []
    keys = sorted(keys)  # deterministic signature order → deterministic cluster ids
    signatures = [kd.minhash_signature(kd.shingles(key_text[k])) for k in keys]
    out: list[PatternCandidate] = []
    for cluster in kd.cluster_near_duplicates(signatures, threshold=threshold):
        members = [keys[i] for i in cluster]
        union: set[str] = set().union(*(key_docs[m] for m in members))
        if len(union) < min_docs:
            continue
        rep = max(members, key=lambda m: (len(key_docs[m]), m))  # dominant spelling
        out.append(
            _block_candidate("boilerplate", "REFERENCE", rep, key_text[rep], union, auto_docs)
        )
    return out


def _classify_block(text: str, phrase_max_len: int) -> tuple[str, str]:
    """(registry, disposition) for a recurring block by its shape (§9.6 families)."""
    if _HEADING.match(text):
        return "templates", "RETAIN"  # structural scaffold — kept, stamped, never deleted
    if "\n" not in text and len(text) <= phrase_max_len:
        return "phrases", "DELETE"  # short paper-era furniture
    return "boilerplate", "REFERENCE"  # meaningful, duplicated → single-source


def mine_glossary(docs: dict[str, str], *, min_docs: int = 3) -> list[PatternCandidate]:
    """Acronyms (``[A-Z][A-Z0-9]{1,7}``) appearing in ≥ ``min_docs`` docs → glossary candidates
    (PROMOTE). Always ``review`` — defining an acronym is a human judgement."""
    term_docs: dict[str, set[str]] = defaultdict(set)
    for doc_id, md in docs.items():
        for term in set(_ACRONYM.findall(md)):
            if term not in _GLOSSARY_STOPWORDS:
                term_docs[term].add(doc_id)
    out = [
        PatternCandidate(
            registry="glossary",
            disposition="PROMOTE",
            key=term,
            text=term,
            doc_count=len(ds),
            sample_doc_ids=sorted(ds)[:_SAMPLE],
            grade="review",
        )
        for term, ds in term_docs.items()
        if len(ds) >= min_docs
    ]
    out.sort(key=lambda c: (-c.doc_count, c.key))
    return out


def _callout_canonical_form(label: str) -> str:
    """The standard GFM target for a callout label: a GitHub alert if supported, else a
    bold blockquote (so non-alert labels like Example/Reminder still canonicalize uniformly)."""
    if label in _GFM_ALERTS:
        return f"> [!{label.upper()}]"
    return f"> **{label.capitalize()}:**"


def mine_structures(
    docs: dict[str, str], *, min_docs: int = 3, auto_docs: int = 10
) -> list[StructureCandidate]:
    """Recurring structural conventions across the corpus → ``structures`` candidates (§9.7).

    Three convention families, all CANONICALIZE-to-GFM: **callout/admonition** styling (the same
    label rendered many ways — the strong signal), the **contents** heading shape, and the
    **revision-history** heading shape. Each carries the distinct source ``variants`` as the
    canonicalization evidence. Frequent (≥ ``auto_docs``) → ``auto``, else ``review``; mutates
    nothing (proposals only)."""
    callout_docs: dict[str, set[str]] = defaultdict(set)
    callout_variants: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    convention_docs: dict[str, set[str]] = defaultdict(set)
    convention_variants: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for doc_id, md in docs.items():
        for m in _CALLOUT_RE.finditer(md):
            label = m.group(1).lower()
            callout_docs[label].add(doc_id)
            callout_variants[label][_WS.sub(" ", m.group(0).strip())] += 1
        for conv, rx in (("toc:contents", _TOC_RE), ("revision-table", _REVTABLE_RE)):
            hits = rx.findall(md)
            if hits:
                convention_docs[conv].add(doc_id)
                for h in hits:
                    convention_variants[conv][_WS.sub(" ", h.strip())] += 1

    out: list[StructureCandidate] = []
    for label, ds in callout_docs.items():
        if len(ds) < min_docs:
            continue
        out.append(
            _structure_candidate(
                "callout",
                f"callout:{label}",
                _callout_canonical_form(label),
                callout_variants[label],
                ds,
                auto_docs,
            )
        )
    canonical = {"toc:contents": "## Contents", "revision-table": "## Revision History"}
    for conv, ds in convention_docs.items():
        if len(ds) < min_docs:
            continue
        kind = "toc" if conv.startswith("toc") else "revision-table"
        out.append(
            _structure_candidate(
                kind, conv, canonical[conv], convention_variants[conv], ds, auto_docs
            )
        )
    out.sort(key=lambda c: (-c.doc_count, c.key))
    return out


def _structure_candidate(
    convention: str,
    key: str,
    canonical_form: str,
    variant_counts: dict[str, int],
    docs: set[str],
    auto_docs: int,
) -> StructureCandidate:
    variants = sorted(variant_counts, key=lambda v: (-variant_counts[v], v))[:_MAX_VARIANTS]
    return StructureCandidate(
        convention=convention,
        key=key,
        canonical_form=canonical_form,
        variants=variants,
        doc_count=len(docs),
        sample_doc_ids=sorted(docs)[:_SAMPLE],
        grade="auto" if len(docs) >= auto_docs else "review",
    )


def extract_era(body: str, *, head_lines: int = _TITLE_PAGE_LINES) -> str:
    """Decade bucket of the title-page publication date, or ``"unknown"`` (§9.8).

    Scans only the title-page window (front matter) for the first ``Month YYYY`` — the date the
    author printed on the cover, which (unlike the DOCX re-export timestamp) tracks the real era.
    Delegates to the shared ``kernel/text.decade_bucket`` (§9.2 — also used by `normalize`)."""
    return decade_bucket(body, max_lines=head_lines)


def parse_scaffold(body: str) -> list[tuple[int, str]]:
    """Ordered ``(level, title)`` of the body's section headings — the structural scaffold.

    H1 is excluded: it is the document title, not a reusable section of the template scaffold.
    Fence- + Contents-aware via the shared ``kernel.markdown.iter_headings`` (§9.2), recognizing
    ``#+`` headings (>6 levels) uniformly with the other markdown stages."""
    return [(level, text.strip()) for _, level, text in iter_headings(body) if level >= 2]


def _slug(title: str) -> str:
    # the shared GitHub-anchor rule (§9.2/D3): a section's slug now MATCHES the anchor `normalize`
    # emits for the same heading, so `index` can join a discovered section to its published heading.
    return slugify(title, fallback="section")


# --- §9.8 computable schema: title-pattern induction + semantic-role labelling ---
# A leading section number (`1.`, `1.2.3`, `1`, with optional trailing dot) — stripped to align
# `1. Introduction` / `1 Introduction` / `Introduction` into one section (the heterogeneous-type
# alignment win, spike §5). The *generated* title_pattern makes that prefix optional so the regex
# still matches every numbered or unnumbered spelling.
_NUMBERING_RE = re.compile(r"^\s*\d+(?:\.\d+)*\.?\s+")
_NUMBER_PREFIX = r"(?:\d+(?:\.\d+)*\.?\s+)?"

# Section title → semantic role (§9.8). A *proposal-time* hint only: `discover` proposes, curation
# confirms/edits it via the `registries/` PR (so a coarse heuristic is safe — it never mutates a
# body, and unknown titles stay null rather than being guessed). Substrings are checked in order;
# the first match wins, so the more specific labels (back-out, installation) precede the general.
_ROLE_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("glossary", "glossary"),
    ("acronym", "glossary"),
    ("revision history", "revision-history"),
    ("back-out", "back-out"),
    ("back out", "back-out"),
    ("rollback", "back-out"),
    ("roll back", "back-out"),
    ("install", "installation"),
    ("deployment", "installation"),
    ("troubleshoot", "troubleshooting"),
    ("introduction", "orientation"),
    ("overview", "orientation"),
    ("orientation", "orientation"),
    ("purpose", "orientation"),
    ("scope", "orientation"),
    ("getting started", "orientation"),
)

# `required`/admission policy (§9.8). The spike's exact-anchor method found real DIBR sections at
# 60–94% coverage, never a clean 100%, so "required = present in *every* member" understates the
# template. We use a ratio: a section is RETAINED when it covers ≥ ADMIT_RATIO of the cluster (with
# an absolute floor of 2 docs, so a lone heading is never template structure) and marked REQUIRED
# when it covers ≥ REQUIRED_RATIO. The gap [ADMIT_RATIO, REQUIRED_RATIO) is the optional tier —
# sections that genuinely belong to the template but not to every instance.
_ADMIT_RATIO = 0.25
_REQUIRED_RATIO = 0.5


def _strip_numbering(title: str) -> str:
    """Drop a leading section number (``1.``/``1.2.3``/``1``) so numbered and unnumbered spellings
    of the same heading align to one section key (§9.8)."""
    return _NUMBERING_RE.sub("", title).strip()


def _core_key(title: str) -> str:
    """Numbering-stripped, lowercased, ws-collapsed section identity for clustering titles."""
    return " ".join(_strip_numbering(title).lower().split())


def induce_title_pattern(variants: Sequence[str]) -> str:
    """A regex matching every observed spelling of one section's title (§9.8).

    The spellings are aligned by stripping any leading section number; the generated pattern makes
    that number prefix optional (so ``Introduction`` and ``1. Introduction`` both match) and is
    case-insensitive. Distinct cores (genuinely different wordings clustered together) become an
    alternation, so the pattern still matches each spelling it was induced from."""
    cores: dict[str, str] = {}  # lowercased core → representative display spelling
    has_numbering = False
    for v in variants:
        if _NUMBERING_RE.match(v):
            has_numbering = True
        core = _strip_numbering(v)
        cores.setdefault(core.lower(), core)
    prefix = _NUMBER_PREFIX if has_numbering else ""
    if len(cores) == 1:
        body = re.escape(next(iter(cores.values())))
    else:
        body = "(?:" + "|".join(re.escape(c) for _, c in sorted(cores.items())) + ")"
    return f"(?i)^{prefix}{body}$"


def infer_semantic_role(title: str) -> str | None:
    """The section's semantic role where inferable (orientation/installation/back-out/…), else
    ``None`` — a curation-overridable proposal hint, never a guess (§9.8)."""
    t = " ".join(title.lower().split())
    for keyword, role in _ROLE_KEYWORDS:
        if keyword in t:
            return role
    return None


def mine_templates(
    docs: dict[str, str],
    doc_types: dict[str, str],
    *,
    min_docs: int = 3,
    auto_docs: int = 10,
    scaffold_threshold: float = 0.6,
) -> list[TemplateCandidate]:
    """Induce per-``(doc_type, era)`` template candidates by structural clustering (§9.8/ADR-018).

    Bucket bodies by ``(doc_type, era)`` — ``doc_type`` from the curated catalog (``doc_types``
    map; bodies with no known type are skipped), ``era`` from the title-page date — then near-dup
    cluster each bucket by heading scaffold (``kernel/discovery``). Each cluster of ≥ ``min_docs``
    becomes one template with a stamped ``template_id`` and a **retained** consensus structural
    schema. Proposals only — mutates nothing."""
    buckets: dict[tuple[str, str], list[tuple[str, list[tuple[int, str]]]]] = defaultdict(list)
    for doc_id, md in docs.items():
        dt = doc_types.get(doc_id)
        if not dt:
            continue
        buckets[(dt, extract_era(md))].append((doc_id, parse_scaffold(md)))

    out: list[TemplateCandidate] = []
    for (dt, era), members in buckets.items():
        if len(members) < min_docs:
            continue
        # cluster on numbering-stripped titles so `1. Introduction` and `Introduction` align — the
        # same key the consensus schema uses (the heterogeneous-type alignment win, §9.8 / spike §5)
        sigs = [
            kd.minhash_signature(kd.scaffold_shingles([_strip_numbering(t) for _, t in sc]))
            for _, sc in members
        ]
        for cluster in kd.cluster_near_duplicates(sigs, threshold=scaffold_threshold):
            picked = [members[i] for i in cluster]
            if len(picked) < min_docs:
                continue
            sections = _consensus_schema(picked)
            fp = kd.structural_fingerprint([s.title for s in sections])
            out.append(
                TemplateCandidate(
                    template_id=f"{dt}:{era}:{fp[:8]}",
                    doc_type=dt,
                    era=era,
                    sections=sections,
                    doc_count=len(picked),
                    sample_doc_ids=sorted(d for d, _ in picked)[:_SAMPLE],
                    grade="auto" if len(picked) >= auto_docs else "review",
                )
            )
    out.sort(key=lambda t: (-t.doc_count, t.template_id))
    return out


@dataclass
class _SectionAgg:
    """Per-section accumulator while building a cluster's consensus schema."""

    title: str  # first-seen display spelling (the consensus title is the most common variant)
    count: int = 0  # member docs containing this section
    levels: Counter[int] = field(default_factory=Counter)
    positions: list[int] = field(default_factory=list)
    variants: Counter[str] = field(default_factory=Counter)  # every display spelling seen
    repeats_in_doc: int = 0  # member docs where this section appears more than once


def _consensus_schema(
    members: list[tuple[str, list[tuple[int, str]]]],
    *,
    admit_ratio: float = _ADMIT_RATIO,
    required_ratio: float = _REQUIRED_RATIO,
) -> list[TemplateSection]:
    """The retained computable schema for a scaffold cluster (§9.8).

    Sections are keyed by numbering-stripped title (so ``1. Introduction`` and ``Introduction``
    align), ordered by mean position, and admitted when they cover ≥ ``admit_ratio`` of members
    (absolute floor 2); each is marked ``required`` at ≥ ``required_ratio`` coverage, ``repeatable``
    when it recurs within any member, carries a numbering-tolerant ``title_pattern`` induced from
    its observed spellings, and an inferred ``semantic_role`` (null when unknown)."""
    size = len(members)
    agg: dict[str, _SectionAgg] = {}
    for _, scaffold in members:
        seen: set[str] = set()
        per_doc: Counter[str] = Counter()
        for pos, (level, title) in enumerate(scaffold):
            key = _core_key(title)
            per_doc[key] += 1
            row = agg.setdefault(key, _SectionAgg(title=title))
            row.variants[title] += 1
            if key in seen:  # count docs / levels / position once per document
                continue
            seen.add(key)
            row.count += 1
            row.levels[level] += 1
            row.positions.append(pos)
        for key, n in per_doc.items():
            if n > 1:
                agg[key].repeats_in_doc += 1
    admit_floor = max(2, ceil(admit_ratio * size))
    required_floor = required_ratio * size
    rows = sorted(
        (r for r in agg.values() if r.count >= admit_floor),
        key=lambda r: sum(r.positions) / len(r.positions),
    )
    out: list[TemplateSection] = []
    for r in rows:
        consensus_title = r.variants.most_common(1)[0][0]
        level = r.levels.most_common(1)[0][0]
        out.append(
            TemplateSection(
                section_id=_slug(consensus_title),
                title=consensus_title,
                title_pattern=induce_title_pattern(list(r.variants)),
                level=level,
                required=r.count >= required_floor,
                repeatable=r.repeats_in_doc > 0,
                semantic_role=infer_semantic_role(consensus_title),
                toc_level=level <= 3,
            )
        )
    return out


def count_bare_markers(body: str) -> int:
    """List markers alone on a line (``- ``/``* ``/``N.`` with no content) — Pandoc's explosion
    of Word ``[[…]]`` cross-reference fields, which Docling reconstructs into real list items."""
    return len(_BARE_MARKER_RE.findall(body))


def count_xref_wraps(body: str) -> int:
    """Word ``[[…]]`` cross-reference field wraps surviving in the Pandoc markdown."""
    return body.count("[[")


def mine_converter_routing(
    docs: dict[str, str], *, min_xref_wraps: int = 50
) -> list[RoutingCandidate]:
    """Flag documents whose Pandoc output carries a heavy Word ``[[…]]`` cross-reference
    explosion (≥ ``min_xref_wraps``) — the list-shredding pathology Docling fixes cleanly
    (§9.6, ADR-010). Evidence: cross-ref wraps + the bare-marker count. Sorted worst-first.

    This is v1's signal, not heading count: ``cprsguium`` has 573 headings *and* 3,058 bare
    markers — measuring headings misses exactly the doc Docling helps."""
    out: list[RoutingCandidate] = []
    for doc_id, body in docs.items():
        xref = count_xref_wraps(body)
        if xref >= min_xref_wraps:
            bare = count_bare_markers(body)
            out.append(
                RoutingCandidate(
                    doc_id=doc_id,
                    suggested_converter="docling",
                    reason=f"{xref} Word cross-ref wraps explode lists into {bare} bare markers",
                    xref_wraps=xref,
                    bare_markers=bare,
                )
            )
    out.sort(key=lambda c: -c.xref_wraps)
    return out
