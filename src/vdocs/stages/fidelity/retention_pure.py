"""Pure content-retention guardrail — did ``normalize`` keep (or relocate) the body it was given?

Orthogonal to the over-strip gate (``overstrip_pure``), which measures bareness *within* the
sections that remain and is **blind to a body deleted whole**: a fully gutted doc has zero content
sections, so its over-strip rate is ``0/0`` → PASS. This gate instead compares the normalized output
against the enriched input — a catastrophic drop (e.g. a legacy-TOC strip that ran past the TOC into
the body, vdocs-design §6.7) shows up as near-zero retention.

Words **relocated** to a referent the body still points at (an extracted ``tables/*.csv`` sidecar)
count as retained, so legitimately table-heavy docs (a Technical Manual whose option tables move to
CSV) are never penalised — the same relocated-vs-lost distinction ``overstrip_pure`` draws for
stubs. Deterministic; no source ``S`` beyond the two word counts the stage already has.
"""

from __future__ import annotations

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


def blocks_publish(verdict: str, *, signed_off: bool = False) -> bool:
    """The `validate` hard-gate rule (§8), shared with the other fidelity guardrails: QUARANTINE
    always blocks; REVIEW blocks unless a human signed off; PASS never blocks."""
    if verdict == QUARANTINE:
        return True
    if verdict == REVIEW:
        return not signed_off
    return False
