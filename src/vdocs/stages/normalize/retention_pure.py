"""Pure content-retention guardrail — did ``normalize`` keep (or relocate) the body it was given?

The ``normalize`` content-retention gate: compares the normalized output against the enriched
input so a body deleted whole is caught — a catastrophic drop (e.g. a legacy-TOC strip that ran
past the TOC into the body, vdocs-design §6.7) shows up as near-zero retention and blocks the doc
before it reaches the corpus.

Words **relocated** to a referent the body still points at (an extracted ``tables/*.csv`` sidecar)
count as retained, so legitimately table-heavy docs (a Technical Manual whose option tables move to
CSV) are never penalised. Deterministic; no source ``S`` beyond the two word counts the stage
already has.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

PASS = "PASS"
REVIEW = "REVIEW"
QUARANTINE = "QUARANTINE"


@dataclass(frozen=True)
class RetentionVerdict:
    """Document-level content-retention verdict."""

    retention: float  # (normalized_body + relocated) ÷ enriched, capped at 1
    verdict: str  # PASS | REVIEW | QUARANTINE
    enriched_words: int
    kept_words: int  # normalized body words + relocated (table CSV) words


def score_retention(
    enriched_words: int,
    normalized_words: int,
    relocated_words: int = 0,
    *,
    pass_at: float = 0.8,
    quarantine_at: float = 0.5,
) -> RetentionVerdict:
    """Score how much of the enriched body survived normalize.

    ``retention = (normalized_words + relocated_words) / enriched_words`` (capped at 1). PASS at or
    above ``pass_at``; REVIEW down to ``quarantine_at``; QUARANTINE below. A doc with a trivial
    enriched body (nothing to lose) scores PASS."""
    kept = normalized_words + relocated_words
    retention = 1.0 if enriched_words <= 0 else min(1.0, kept / enriched_words)
    if retention >= pass_at:
        verdict = PASS
    elif retention >= quarantine_at:
        verdict = REVIEW
    else:
        verdict = QUARANTINE
    return RetentionVerdict(retention, verdict, enriched_words, kept)


def relocated_word_count(
    *,
    legacy_toc: Sequence[Mapping[str, object]] = (),
    boilerplate_keys: Sequence[str] = (),
) -> int:
    """Words that LEFT the body inside the retention window but were **relocated** to a referent
    the body still points at — the ``relocated_words`` credit for :func:`score_retention`.

    Only in-window relocations may be counted. ``normalize`` takes its retention baseline *after*
    lifting the revision apparatus and the qualifying tables (``stage.py``: ``pre_norm_words``),
    so those words are **already absent from the denominator**; crediting them would raise the
    numerator against a denominator that never counted them and inflate the score — measured
    2026-08-01 on the live lake: it turns a document that truly retained 57% into a PASS at 0.87.
    What ``normalize_body`` itself relocates is:

    * the **legacy in-body TOC** → ``toc.yaml`` (each entry's title + its printed page number,
      captured verbatim before the strip, §6.7);
    * curated **boilerplate** → a REFERENCE link to ``gold/_shared/boilerplate/<id>.md`` (§9.6);
      the registry ``key`` is the whitespace-collapsed block it replaced, so its length is the
      block's length.
    """
    words = 0
    for entry in legacy_toc:
        words += len(str(entry.get("title", "")).split())
        if str(entry.get("page", "")).strip():
            words += 1  # the printed page number left the body with its entry
    words += sum(len(key.split()) for key in boilerplate_keys)
    return words


def blocks_publish(verdict: str, *, signed_off: bool = False) -> bool:
    """The content-retention hard-gate rule (§8): QUARANTINE always blocks; REVIEW blocks unless a
    human signed off; PASS never blocks."""
    if verdict == QUARANTINE:
        return True
    if verdict == REVIEW:
        return not signed_off
    return False
