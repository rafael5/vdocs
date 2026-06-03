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

import re
from dataclasses import dataclass

from vdocs.kernel.markdown import iter_headings

PASS = "PASS"
REVIEW = "REVIEW"
QUARANTINE = "QUARANTINE"

# A content section needs at least this many substantive word tokens to stand alone when retrieved.
# A calibration target (fidelity-framework §9), not a magic constant — tune against the golden set.
_MIN_TOKENS = 8

# Recognition patterns (see module docstring for why they live here, not imported from `normalize`):
# a link/image whose target points at a sidecar or single-sourced store ⇒ content was relocated,
# not lost; the round-trip back-link is pure navigation furniture, never substance.
_REFERENT_RE = re.compile(r"\]\([^)]*(?:_shared/|tables/|assets/|\.csv)[^)]*\)")
_NAV_RE = re.compile(r"↑\s*Back to Contents", re.IGNORECASE)
_LINK_LABEL_RE = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")  # [label](t) -> label ; ![alt](t) -> alt
_WORD_RE = re.compile(r"\w+")


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


def _audit_body(body_lines: list[str]) -> tuple[bool, int]:
    """``(has_referent, substantive_tokens)`` for one section body.

    Blank and navigation lines never count; a line pointing at relocated content marks the chunk as
    having a referent (and its short pointer label adds no substance); everything else contributes
    its visible word tokens (link syntax reduced to its label)."""
    has_referent = False
    tokens = 0
    for line in body_lines:
        s = line.strip()
        if not s or _NAV_RE.search(s):
            continue
        if _REFERENT_RE.search(s):
            has_referent = True
            continue  # a relocation pointer is not substance — its content lives in the referent
        tokens += len(_WORD_RE.findall(_LINK_LABEL_RE.sub(r"\1", s)))
    return has_referent, tokens


def audit_chunks(body: str, *, min_tokens: int = _MIN_TOKENS) -> list[ChunkAudit]:
    """Audit every leaf content section of ``body`` (containers excluded)."""
    audits: list[ChunkAudit] = []
    for level, title, seg, is_container in _segments(body):
        if is_container:
            continue
        has_referent, tokens = _audit_body(seg)
        if tokens >= min_tokens:
            classification = "ok"
        elif has_referent:
            classification = "stub"
        else:
            classification = "hollow"
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
