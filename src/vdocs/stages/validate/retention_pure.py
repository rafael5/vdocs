"""Pure content-retention gate — the rule that finally decides what ships (P3.3, audit R‑5/[S8]).

`normalize` has scored every document's content retention since Phase 3, and
``normalize.retention_pure.blocks_publish`` has encoded the rule the whole time — but nothing
called it. The verdict landed in ``flags.yaml`` as a string and QUARANTINE documents flowed into
gold under a green pipeline. This module is the consumer side: given each **gold anchor bundle's**
recorded verdict (from the ``capture.yaml`` that travels with it, covered by ``bundle.yaml``'s
signed manifest) plus the curated sign-off registry, decide what blocks.

The rule itself is not re-implemented here — ``blocks_publish`` remains its one definition (§9.2).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from vdocs.stages.normalize.retention_pure import QUARANTINE, REVIEW, blocks_publish

#: an over-stripped document — never excusable by a sign-off
QUARANTINED = "retention-quarantine"
#: a partial loss awaiting a human judgement that has not been recorded
REVIEW_UNSIGNED = "retention-review-unsigned"
#: a gold bundle carrying no retention record at all — UNKNOWN, never PASS
UNSCORED = "retention-unscored"
#: a sign-off for a document that no longer needs one — reported, never blocking
SIGNOFF_STALE = "retention-signoff-stale"


@dataclass(frozen=True)
class RetentionFinding:
    """One retention verdict the gate has something to say about."""

    kind: str
    doc_id: str
    detail: str
    blocking: bool


def gate_retention(
    scored: Iterable[tuple[str, str, float | None]],
    *,
    signed_off: frozenset[str],
) -> list[RetentionFinding]:
    """Findings for every gold bundle whose recorded retention verdict blocks (or is missing).

    ``scored`` is ``(doc_id, verdict, retention)`` per gold anchor bundle; ``signed_off`` is the
    curated ``registries/retention-signoff.yaml`` doc_id set. Findings are returned in doc_id order
    so the report is diffable across runs.

    Three block: **QUARANTINE** (always — a gutted document is not a judgement call, so a sign-off
    cannot excuse it), **REVIEW without a sign-off**, and **an unscored bundle** (a bundle that was
    never scored has not been cleared; treating "no record" as PASS is the fail-open shape this
    gate exists to remove). A sign-off covering a document that now passes is reported as *stale*
    but never blocks — a stale excuse is registry hygiene, not a corpus defect.
    """
    rows = list(scored)  # may be a generator; the stale-sign-off pass needs a second look
    findings: list[RetentionFinding] = []
    for doc_id, verdict, retention in rows:
        pct = "unknown" if retention is None else f"{retention:.2f}"
        if not verdict:
            findings.append(
                RetentionFinding(
                    UNSCORED,
                    doc_id,
                    "gold bundle carries no capture.yaml retention block — re-run normalize",
                    True,
                )
            )
        elif verdict == QUARANTINE:
            findings.append(
                RetentionFinding(
                    QUARANTINED,
                    doc_id,
                    f"retention {pct} — over-stripped; a sign-off cannot excuse QUARANTINE",
                    True,
                )
            )
        elif verdict == REVIEW and blocks_publish(REVIEW, signed_off=doc_id in signed_off):
            findings.append(
                RetentionFinding(
                    REVIEW_UNSIGNED,
                    doc_id,
                    f"retention {pct} — needs a reason in registries/retention-signoff.yaml",
                    True,
                )
            )
    # A sign-off earns its keep only while the document it names still needs one.
    covered = {
        doc_id for doc_id, verdict, _ in rows if verdict in (REVIEW, QUARANTINE) or not verdict
    }
    for doc_id in sorted(signed_off - covered):
        findings.append(
            RetentionFinding(
                SIGNOFF_STALE,
                doc_id,
                "sign-off for a document that no longer needs one — drop the registry entry",
                False,
            )
        )
    return sorted(findings, key=lambda f: (f.doc_id, f.kind))


__all__ = [
    "QUARANTINED",
    "REVIEW_UNSIGNED",
    "RetentionFinding",
    "SIGNOFF_STALE",
    "UNSCORED",
    "gate_retention",
]
