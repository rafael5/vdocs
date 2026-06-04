"""Pure over-strip guardrail — the search-corpus enforcement of the §6.5 optimum (zero I/O).

Condensation (boilerplate→reference, dead phrases→delete, scaffold→strip, big tables→CSV sidecar)
raises a chunk's signal-to-noise — but only up to a point. Past the optimum a section is stripped so
bare it no longer stands alone: retrieved in isolation it is an unanchored fragment that *hurts*
recall (vdocs-design §6.5; fidelity-framework §10.5). "Subtract more" is therefore not monotonically
better — the curve peaks then falls. This module measures where a document sits on that curve.

The crux is distinguishing two outcomes that both leave a chunk short on prose:

* **relocated** — the content moved to a *referent* the body still points at (a ``_shared/``
  boilerplate link, a ``tables/*.csv`` stub, an ``assets/`` image). Nothing is lost; the fidelity
  scorer dereferences it before recall scoring (fidelity-framework §4). This is by-design
  decomposition and must **never** be penalised — a ``stub`` chunk.
* **hollow** — the chunk is reduced to a bare heading (plus navigation furniture) with *no* referent
  and below the substantive-token floor. That is the over-strip defect: a content section promising
  meaning with none beneath it. It will embed as essentially just its title and pollute the search
  space.

The over-strip rate is hollow content chunks ÷ content chunks. Container headings (those whose
substance lives in subsections) are excluded from the denominator. Like ``compliance_pure``, this is
a **T-only**, deterministic check (no source ``S`` needed): a hollow content chunk is self-evidently
a defect on the normalized body alone. The recognition patterns mirror the markers ``normalize``
emits but are duplicated here deliberately, so the scorer never imports the stage it audits
(independent-reference principle, fidelity-framework §2.2 / vdocs-design §9.2).
"""

from __future__ import annotations

from dataclasses import dataclass

from vdocs.kernel.markdown import (
    MIN_SUBSTANTIVE_TOKENS,
    classify_section,
    iter_headings,
    substantive_tokens,
)

PASS = "PASS"
REVIEW = "REVIEW"
QUARANTINE = "QUARANTINE"

# The substantive-content floor + the "is this body substantive" measure are shared with the
# `index` chunker via the kernel (§9.2), so the over-strip gate and the chunker agree on "hollow".
# The scorer still never imports the stage it audits (`normalize`/`index`) — the kernel is neutral
# infrastructure (independent-reference principle, FF §2.2). `_MIN_TOKENS` kept as a local alias.
_MIN_TOKENS = MIN_SUBSTANTIVE_TOKENS


@dataclass(frozen=True)
class ChunkAudit:
    """The over-strip audit of one content section (heading + its body up to the next heading)."""

    title: str
    level: int
    substantive_tokens: int
    has_referent: bool  # body still points at relocated content (boilerplate/CSV/asset)
    classification: str  # "ok" | "stub" (relocated, recoverable) | "hollow" (over-stripped defect)


@dataclass(frozen=True)
class OverStripVerdict:
    """Document-level over-strip verdict (fidelity-framework §10.5)."""

    score: float  # 1 - over_strip_rate
    verdict: str  # PASS | REVIEW | QUARANTINE
    content_chunks: int  # leaf content sections audited (containers excluded)
    hollow: tuple[str, ...]  # titles of over-stripped chunks
    stubs: tuple[str, ...]  # titles of by-design referent stubs (reported, not penalised)
    over_strip_rate: float


def _segments(body: str) -> list[tuple[int, str, list[str], bool]]:
    """``(level, title, body_lines, is_container)`` per H2+ heading.

    A heading is a *container* when the next heading is strictly deeper — its substance lives in its
    subsections, so judging its own bareness would be a false positive; containers are excluded."""
    lines = body.split("\n")
    heads = [(i, lvl, txt.strip()) for i, lvl, txt in iter_headings(body) if lvl >= 2]
    out: list[tuple[int, str, list[str], bool]] = []
    for k, (idx, lvl, txt) in enumerate(heads):
        nxt = heads[k + 1] if k + 1 < len(heads) else None
        end = nxt[0] if nxt is not None else len(lines)
        is_container = nxt is not None and nxt[1] > lvl
        out.append((lvl, txt, lines[idx + 1 : end], is_container))
    return out


def audit_chunks(body: str, *, min_tokens: int = _MIN_TOKENS) -> list[ChunkAudit]:
    """Audit every leaf content section of ``body`` (containers excluded)."""
    audits: list[ChunkAudit] = []
    for level, title, seg, is_container in _segments(body):
        if is_container:
            continue
        has_referent, tokens = substantive_tokens(seg)
        classification = classify_section(
            is_container=False, has_referent=has_referent, tokens=tokens, min_tokens=min_tokens
        )
        audits.append(ChunkAudit(title, level, tokens, has_referent, classification))
    return audits


def score_over_strip(
    body: str,
    *,
    min_tokens: int = _MIN_TOKENS,
    pass_at: float = 1.0,
    quarantine_at: float = 0.5,
) -> OverStripVerdict:
    """Score ``body`` on the over-strip guardrail (fidelity-framework §10.5).

    ``score`` = 1 - (hollow chunks ÷ content chunks). PASS only when **no** content chunk is hollow
    (an over-stripped section is never silently faithful); REVIEW down to ``quarantine_at``;
    QUARANTINE when most of the body is hollow. A doc with no content sections scores PASS."""
    audits = audit_chunks(body, min_tokens=min_tokens)
    n = len(audits)
    hollow = tuple(a.title for a in audits if a.classification == "hollow")
    stubs = tuple(a.title for a in audits if a.classification == "stub")
    rate = 0.0 if n == 0 else len(hollow) / n
    score = 1.0 - rate
    if score >= pass_at:
        verdict = PASS
    elif score >= quarantine_at:
        verdict = REVIEW
    else:
        verdict = QUARANTINE
    return OverStripVerdict(
        score=score,
        verdict=verdict,
        content_chunks=n,
        hollow=hollow,
        stubs=stubs,
        over_strip_rate=rate,
    )


def blocks_publish(verdict: str, *, signed_off: bool = False) -> bool:
    """The `validate` hard-gate rule (§8), shared with `compliance_pure`: QUARANTINE always blocks;
    REVIEW blocks unless a human signed off; PASS never blocks."""
    if verdict == QUARANTINE:
        return True
    if verdict == REVIEW:
        return not signed_off
    return False
