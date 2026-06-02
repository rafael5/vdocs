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
_ACRONYM = re.compile(r"\b[A-Z][A-Z0-9]{1,7}\b")
_SAMPLE = 5  # how many example doc_ids to carry as evidence


class PatternCandidate(BaseModel):
    """One proposed pattern: which registry, how to dispose of it, and the evidence for it."""

    registry: str  # boilerplate | phrases | glossary
    disposition: str  # REFERENCE | DELETE | PROMOTE (§9.6)
    key: str  # the identity used by `normalize` (normalised block / term)
    text: str  # a representative original spelling
    doc_count: int  # how many distinct documents it appears in
    sample_doc_ids: list[str] = Field(default_factory=list)
    grade: str  # auto | review (the curation-gate hint)


class PatternReport(BaseModel):
    """The ``reports/patterns`` artifact: candidate patterns by family, pre-curation."""

    boilerplate: list[PatternCandidate] = Field(default_factory=list)
    glossary: list[PatternCandidate] = Field(default_factory=list)


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

    A short single-line block reads as paper-era furniture → ``phrases`` (DELETE); a longer
    block is meaningful-but-duplicated → ``boilerplate`` (REFERENCE). Frequent ones (≥
    ``auto_docs``) are graded ``auto`` (curation may auto-approve), the rest ``review``."""
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
        is_phrase = "\n" not in text and len(text) <= phrase_max_len
        candidates.append(
            PatternCandidate(
                registry="phrases" if is_phrase else "boilerplate",
                disposition="DELETE" if is_phrase else "REFERENCE",
                key=k,
                text=text,
                doc_count=len(ds),
                sample_doc_ids=sorted(ds)[:_SAMPLE],
                grade="auto" if len(ds) >= auto_docs else "review",
            )
        )
    candidates.sort(key=lambda c: (-c.doc_count, c.key))
    return candidates


def mine_glossary(docs: dict[str, str], *, min_docs: int = 3) -> list[PatternCandidate]:
    """Acronyms (``[A-Z][A-Z0-9]{1,7}``) appearing in ≥ ``min_docs`` docs → glossary candidates
    (PROMOTE). Always ``review`` — defining an acronym is a human judgement."""
    term_docs: dict[str, set[str]] = defaultdict(set)
    for doc_id, md in docs.items():
        for term in set(_ACRONYM.findall(md)):
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
