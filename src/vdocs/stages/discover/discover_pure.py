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
from collections import defaultdict

from pydantic import BaseModel, Field

_WS = re.compile(r"\s+")
_BLOCK_SPLIT = re.compile(r"\n\s*\n")
_HEADING = re.compile(r"^#{1,6}\s")
_HEADING_LINE = re.compile(r"^#{1,6} ", re.MULTILINE)
_ACRONYM = re.compile(r"\b[A-Z][A-Z0-9]{1,7}\b")
_SAMPLE = 5  # how many example doc_ids to carry as evidence

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
    ADR-010 ``registries/converter-routing``). Pandoc occasionally yields a *bare-marker
    explosion* — a long body with no recovered heading structure — which Docling handles
    better; this flags such docs as ROUTE candidates with the evidence."""

    doc_id: str  # the bundle path <app>/<slug>
    suggested_converter: str  # docling
    reason: str
    words: int
    headings: int


class PatternReport(BaseModel):
    """The ``reports/patterns`` artifact: candidate patterns, pre-curation. ``blocks`` holds the
    recurring-block candidates (each tagged ``registry`` = templates | phrases | boilerplate);
    ``converter_routing`` holds per-document convert-quality routing candidates."""

    blocks: list[PatternCandidate] = Field(default_factory=list)
    glossary: list[PatternCandidate] = Field(default_factory=list)
    converter_routing: list[RoutingCandidate] = Field(default_factory=list)


def split_blocks(markdown: str) -> list[str]:
    """Split a body into blocks on blank lines; trimmed, non-empty (paragraph grain)."""
    return [b.strip() for b in _BLOCK_SPLIT.split(markdown) if b.strip()]


def block_key(block: str) -> str:
    """Identity for a block: lowercased, whitespace-collapsed (so trivial spacing diffs match)."""
    return _WS.sub(" ", block.strip().lower())


def mine_recurring_blocks(
    docs: dict[str, str],
    *,
    min_docs: int = 3,
    auto_docs: int = 10,
    phrase_max_len: int = 60,
) -> list[PatternCandidate]:
    """Blocks recurring across ≥ ``min_docs`` documents → candidates.

    Disposition (the curation hint; §9.6) by block shape:
      * a **heading** (``# …``) is template scaffold → ``templates`` (RETAIN — *never* deleted);
      * a short single-line non-heading is paper-era furniture → ``phrases`` (DELETE);
      * a longer block is meaningful-but-duplicated → ``boilerplate`` (REFERENCE).
    Frequent ones (≥ ``auto_docs``) grade ``auto``, the rest ``review`` — except DELETE proposals
    are always ``review`` (deleting content is never auto-approved on frequency alone)."""
    key_docs: dict[str, set[str]] = defaultdict(set)
    key_text: dict[str, str] = {}
    for doc_id, md in docs.items():
        for k, original in {block_key(b): b for b in split_blocks(md)}.items():
            key_docs[k].add(doc_id)
            key_text.setdefault(k, original)

    candidates: list[PatternCandidate] = []
    for k, ds in key_docs.items():
        if len(ds) < min_docs:
            continue
        text = key_text[k]
        registry, disposition = _classify_block(text, phrase_max_len)
        frequent = len(ds) >= auto_docs
        candidates.append(
            PatternCandidate(
                registry=registry,
                disposition=disposition,
                key=k,
                text=text,
                doc_count=len(ds),
                sample_doc_ids=sorted(ds)[:_SAMPLE],
                # never auto-approve a deletion on frequency alone (a heading recurs too)
                grade="auto" if frequent and disposition != "DELETE" else "review",
            )
        )
    candidates.sort(key=lambda c: (-c.doc_count, c.key))
    return candidates


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


def count_headings(body: str) -> int:
    """Number of ATX markdown headings (``# ``…``###### ``) in a body — the recovered structure."""
    return len(_HEADING_LINE.findall(body))


def mine_converter_routing(docs: dict[str, str], *, min_words: int = 400) -> list[RoutingCandidate]:
    """Flag substantial documents that Pandoc converted with **no heading structure** (a
    bare-marker explosion) as candidates to re-convert with Docling (§9.6, ADR-010). Evidence:
    word count + heading count. Sorted worst-first (most words, structure lost)."""
    out: list[RoutingCandidate] = []
    for doc_id, body in docs.items():
        words = len(body.split())
        headings = count_headings(body)
        if words >= min_words and headings == 0:
            out.append(
                RoutingCandidate(
                    doc_id=doc_id,
                    suggested_converter="docling",
                    reason=f"no headings recovered in a {words}-word document (structure lost)",
                    words=words,
                    headings=headings,
                )
            )
    out.sort(key=lambda c: -c.words)
    return out
