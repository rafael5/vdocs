"""Pure template-compliance oracle — the computable core of the §9.8 compliance check (zero I/O).

A retained ``(doc_type, era)`` template schema is an expectation *independent of both the source
and the converter*, which makes scoring a document against it a high-confidence oracle (it satisfies
the fidelity framework's "independent reference" principle). §9.8 names two distinct verdicts, and
both reduce to the same matcher — expected sections vs. observed section titles:

1. **Extraction self-validation** — does the *body* conform to its own ``(doc_type, era)`` template?
   A required section the template guarantees but the body lacks is a high-confidence signal that
   extraction/refinement dropped something, caught without consulting the source.
2. **Modernization / source-drift** — does the *era-template* conform to the **canonical** doc_type
   schema? Many older guides will not — a source-quality signal, not a migration defect.

`discover` induces the schemas (`TemplateSection`, with a numbering-tolerant ``title_pattern``);
curation approves them; the **fidelity** stage (Phase 5) loads the curated schema and wires these
verdicts into `validate`'s hard gate. This module is that gate's pure, testable kernel — the
``stage.py`` driver lands with Phase 5 (§17). It is decoupled from `discover` (it takes plain
:class:`ExpectedSection` rows, not the `discover` model) so neither stage imports the other.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from vdocs.kernel.markdown import iter_headings

PASS = "PASS"
REVIEW = "REVIEW"
QUARANTINE = "QUARANTINE"


@dataclass(frozen=True)
class ExpectedSection:
    """One expected section of a template schema — the compliance matcher's input (§9.8).

    ``title_pattern`` is the regex `discover` induces (numbering-tolerant, case-insensitive); only
    ``required`` sections drive the score (optional sections never penalise a document)."""

    title: str
    title_pattern: str
    required: bool


@dataclass(frozen=True)
class ComplianceVerdict:
    """The scored conformance of an observed structure to an expected schema (§9.8)."""

    score: float  # present_required / expected_required (1.0 when nothing is required)
    verdict: str  # PASS | REVIEW | QUARANTINE
    expected_required: int
    present_required: int
    missing_required: tuple[str, ...]  # required section titles with no matching heading/title
    matched: tuple[str, ...]  # required section titles that were found


def _heading_titles(body: str) -> list[str]:
    """The body's section-heading texts (H2+; H1 is the doc title) — what the schema is matched
    against (fence-/Contents-aware via the shared ``kernel.markdown.iter_headings``, §9.2)."""
    return [text.strip() for _, level, text in iter_headings(body) if level >= 2]


def _score(
    titles: Sequence[str],
    sections: Sequence[ExpectedSection],
    *,
    pass_at: float,
    quarantine_at: float,
) -> ComplianceVerdict:
    required = [s for s in sections if s.required]
    present: list[str] = []
    missing: list[str] = []
    for s in required:
        rx = re.compile(s.title_pattern)
        (present if any(rx.match(t) for t in titles) else missing).append(s.title)
    n = len(required)
    score = 1.0 if n == 0 else len(present) / n
    if score >= pass_at:
        verdict = PASS
    elif score >= quarantine_at:
        verdict = REVIEW
    else:
        verdict = QUARANTINE
    return ComplianceVerdict(
        score=score,
        verdict=verdict,
        expected_required=n,
        present_required=len(present),
        missing_required=tuple(missing),
        matched=tuple(present),
    )


def score_extraction_compliance(
    body: str,
    sections: Sequence[ExpectedSection],
    *,
    pass_at: float = 1.0,
    quarantine_at: float = 0.5,
) -> ComplianceVerdict:
    """Verdict 1 (§9.8): does ``body`` conform to its own ``(doc_type, era)`` template schema?

    PASS only when *every* required section is present (a missing guaranteed section is a likely
    extraction bug); REVIEW down to ``quarantine_at`` coverage; QUARANTINE below it."""
    return _score(_heading_titles(body), sections, pass_at=pass_at, quarantine_at=quarantine_at)


def score_schema_drift(
    era_sections: Sequence[ExpectedSection],
    canonical_sections: Sequence[ExpectedSection],
    *,
    pass_at: float = 1.0,
    quarantine_at: float = 0.5,
) -> ComplianceVerdict:
    """Verdict 2 (§9.8): does the era-template conform to the **canonical** doc_type schema?

    A source-drift signal (structural divergence across decades), measured by treating the
    era-template's own section titles as the observed set scored against the canonical schema."""
    titles = [s.title for s in era_sections]
    return _score(titles, canonical_sections, pass_at=pass_at, quarantine_at=quarantine_at)


def blocks_publish(verdict: str, *, signed_off: bool = False) -> bool:
    """The `validate` hard-gate rule (§8): a document may publish as faithful only if PASS, or
    REVIEW with a recorded human sign-off; QUARANTINE always blocks."""
    if verdict == QUARANTINE:
        return True
    if verdict == REVIEW:
        return not signed_off
    return False
