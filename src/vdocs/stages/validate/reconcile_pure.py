"""Pure corpus-level sidecar reconciliation — the validate count-reconciliation gate (§5.2, FF C2).

`normalize` emits per-sidecar counts (``state.db:stage_runs[normalize].counts``) and a per-bundle
``capture.yaml``; until the validate gate nothing consumed them. This module reconciles them into
typed findings:

  * **absent-unexpected** — a ``capture.yaml`` records a per-document silent miss (Step 1's signal,
    ``capture_pure``), aggregated here so the gate can fail on it;
  * **corpus-zero** — an expected-nonzero sidecar class is zero across a *large* corpus (the §5.2
    "zero ``tables/*.csv`` corpus-wide ⇒ table extraction silently broke" whole-detector failure);
    gated on a corpus-size floor so a small selection that legitimately has none is not flagged;
  * **count-drop** — a sidecar count fell vs. the *prior* validate run over a same-or-larger
    document set (a regression with no matching shrink in the corpus).

These are the corpus-level net that complements ``capture_pure``'s per-document net: the residue
scan catches a single doc's miss; this catches whole-detector failures and cross-run regressions no
per-document score can see. Pure: plain values in, findings out; the driver reads the tree + state.
"""

from __future__ import annotations

from dataclasses import dataclass

ABSENT_UNEXPECTED = "absent-unexpected"
CORPUS_ZERO = "corpus-zero"
COUNT_DROP = "count-drop"

# Sidecar count keys (in stage_runs[normalize].counts) expected nonzero on a large real corpus.
# refs: every document with headings mints anchors; tables: a large technical-manual corpus always
# carries qualifying data tables (the §5.2 example). Both are checked only above ``corpus_min``.
_EXPECT_NONZERO = ("refs_sidecars", "tables_sidecars")
# Count keys watched for a cross-run drop: the expected-nonzero kinds + the variable-but-tracked.
_DROP_WATCHED = (*_EXPECT_NONZERO, "revision_sidecars", "toc_sidecars", "capture_sidecars")


@dataclass(frozen=True)
class ReconcileFinding:
    """One corpus-reconciliation finding: its class, the sidecar/count key, and a human detail."""

    kind: str  # ABSENT_UNEXPECTED | CORPUS_ZERO | COUNT_DROP
    sidecar: str
    detail: str


def reconcile(
    *,
    manifests: list[dict],
    current_counts: dict[str, int],
    prior_counts: dict[str, int] | None,
    corpus_min: int,
    expect_nonzero: tuple[str, ...] = _EXPECT_NONZERO,
) -> list[ReconcileFinding]:
    """Reconcile the capture manifests + emitted counts against expectation + the prior run."""
    findings: list[ReconcileFinding] = []
    documents = int(current_counts.get("documents", 0))

    # 1. per-document absent-unexpected — a residue-caught silent miss (capture_pure, Step 1)
    for m in manifests:
        doc = str(m.get("doc_id", ""))
        for kind, entry in (m.get("captures") or {}).items():
            if entry.get("outcome") == ABSENT_UNEXPECTED:
                findings.append(
                    ReconcileFinding(
                        ABSENT_UNEXPECTED, kind, f"{doc}: {kind} absent but residue scan saw it"
                    )
                )

    # 2. corpus-zero — an expected-nonzero class is zero across a large corpus (§5.2)
    if documents >= corpus_min:
        for key in expect_nonzero:
            if int(current_counts.get(key, 0)) == 0:
                findings.append(
                    ReconcileFinding(
                        CORPUS_ZERO,
                        key,
                        f"{key}=0 across {documents} documents — likely a whole-detector failure",
                    )
                )

    # 3. count-drop — a count fell vs. the prior run over a same-or-larger document set
    if prior_counts is not None and documents >= int(prior_counts.get("documents", 0)):
        for key in _DROP_WATCHED:
            cur, prev = int(current_counts.get(key, 0)), int(prior_counts.get(key, 0))
            if cur < prev:
                findings.append(
                    ReconcileFinding(
                        COUNT_DROP,
                        key,
                        f"{key} dropped {prev}→{cur} (documents {documents} ≥ "
                        f"prior {int(prior_counts.get('documents', 0))} — not a smaller selection)",
                    )
                )
    return findings
