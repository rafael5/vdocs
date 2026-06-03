"""The `validate` stage — the sidecar-verification HARD GATE (Steps 2-3; §8, FF C2/C5).

This is the first slice of the §8 ``validate`` gate (the broader S→T fidelity verdict, schema, and
ID/vector integrity land later and feed the *same* gate). It consumes the signals `normalize`
already records but nothing read — the per-bundle ``capture.yaml`` typed capture-attempt records
(§6.4) and the ``refs.yaml`` outbound cross-ref maps (§6.7) — and **fails loudly** on:

  1. **typed absence** (Step 1) — any per-document ``absent-unexpected`` capture outcome;
  2. **count reconciliation** (Step 2, §5.2) — an expected-nonzero sidecar class zero across a
     large corpus, or a count that dropped vs. the prior run over a same-or-larger document set
     (the emitted ``stage_runs[normalize].counts`` finally consumed; the prior validate report is
     the cross-run baseline);
  3. **ref resolution** (Step 3, §5.5) — any **severed** outbound ref (a target slug no heading
     carries — the DITA severed-conref class, hard floor zero); ``UNRESOLVED`` bookmarks are the
     already-flagged class, bounded by the C5 cross-ref dead-anchor rate.

It always (re)writes ``reports/validation/verification.json`` (the findings + the count baseline)
and sets its own ``ok`` via the deep gate. ``ALWAYS_RERUN`` — a gate re-checks every time. Pure
logic lives in ``reconcile_pure``/``refs_pure``; this driver is thin I/O (reads the tree + state,
writes the report). The pure cores are written to be reused by the full ``fidelity`` stage later.
"""

from __future__ import annotations

import json

import structlog
import yaml

from vdocs.contracts.registry import TEXT_NORMALIZED, VALIDATION_REPORT
from vdocs.kernel import cas
from vdocs.models.stage import Idempotency, PostflightResult, RunResult
from vdocs.orchestrator.stage import Stage, StageContext
from vdocs.stages.validate import reconcile_pure as rc
from vdocs.stages.validate import refs_pure as rp

log = structlog.get_logger(__name__)

# The corpus-size floor below which a zero expected-nonzero count is not treated as a whole-detector
# failure (a small selection may legitimately carry none) — §5.2 / reconcile_pure.
CORPUS_MIN = 50
# The C5 cross-ref dead-anchor rate floor: UNRESOLVED (unmapped) bookmarks below this share are the
# already-flagged class, not a blocking regression (severed refs always block, floor 0).
UNMAPPED_RATE_FLOOR = 0.02


class ValidateStage(Stage):
    name = "validate"
    description = "sidecar-verification hard gate: typed absence + count reconcile + ref resolution"
    requires = [TEXT_NORMALIZED]
    produces = [VALIDATION_REPORT]
    idempotency = Idempotency.ALWAYS_RERUN

    def __init__(self) -> None:
        self._blocking = False
        self._reason = ""

    def run(self, ctx: StageContext, force: bool) -> RunResult:
        normalized_root = ctx.cfg.silver_normalized

        prior_counts = _read_prior_counts(ctx.cfg.validation_report)
        current_counts = _normalize_counts(ctx)

        manifests: list[dict] = []
        ref_findings: list[rp.RefFinding] = []
        outbound_total = 0
        for body_path in sorted(normalized_root.rglob("body.md")):
            bundle = body_path.parent
            capture = _load_yaml(bundle / "capture.yaml")
            if capture:
                manifests.append(capture)
            refs = _load_yaml(bundle / "refs.yaml")
            if refs:
                outbound_total += len(refs.get("outbound") or {})
                ref_findings.extend(rp.resolve_refs(refs))

        reconcile_findings = rc.reconcile(
            manifests=manifests,
            current_counts=current_counts,
            prior_counts=prior_counts,
            corpus_min=CORPUS_MIN,
        )
        severed = [f for f in ref_findings if f.kind == rp.SEVERED]
        unmapped = [f for f in ref_findings if f.kind == rp.UNMAPPED]
        unmapped_rate = (len(unmapped) / outbound_total) if outbound_total else 0.0

        blocked_by: list[str] = []
        if reconcile_findings:
            blocked_by.append(f"{len(reconcile_findings)} reconciliation finding(s)")
        if severed:
            blocked_by.append(f"{len(severed)} severed cross-ref(s)")
        if unmapped_rate > UNMAPPED_RATE_FLOOR:
            blocked_by.append(
                f"unmapped cross-ref rate {unmapped_rate:.3f} > {UNMAPPED_RATE_FLOOR}"
            )
        self._blocking = bool(blocked_by)
        self._reason = "; ".join(blocked_by)

        documents = int(current_counts.get("documents", len(manifests)))
        report: dict[str, object] = {
            "blocking": self._blocking,
            "blocked_by": blocked_by,
            "documents": documents,
            "counts": current_counts,  # the cross-run baseline for the next run's drop check
            "reconcile_findings": [
                {"kind": f.kind, "sidecar": f.sidecar, "detail": f.detail}
                for f in reconcile_findings
            ],
            "ref_findings": {
                "severed": [_ref_dict(f) for f in severed],
                "unmapped": [_ref_dict(f) for f in unmapped],
                "outbound_total": outbound_total,
                "unmapped_rate": round(unmapped_rate, 4),
            },
        }
        cas.atomic_write(
            ctx.cfg.validation_report,
            (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )
        if self._blocking:
            log.warning("validate-gate-blocking", reason=self._reason)
        return RunResult(
            counts={
                "documents": documents,
                "reconcile_findings": len(reconcile_findings),
                "severed_refs": len(severed),
                "unmapped_refs": len(unmapped),
                "blocking": int(self._blocking),
            }
        )

    def deep_gate(self, ctx: StageContext) -> PostflightResult:
        """The HARD GATE: fail (blocking publish) when any verification finding fired (§8)."""
        if self._blocking:
            return PostflightResult(ok=False, reason=f"sidecar verification failed: {self._reason}")
        return PostflightResult(ok=True)


def _ref_dict(f: rp.RefFinding) -> dict:
    return {"doc_id": f.doc_id, "bookmark": f.bookmark, "target": f.target, "kind": f.kind}


def _load_yaml(path):  # type: ignore[no-untyped-def]
    """Load a sidecar YAML mapping, or ``None`` if absent/empty (defensive — a bad bundle is skipped
    by the count reconciliation rather than crashing the gate)."""
    if not path.is_file():
        return None
    return yaml.safe_load(path.read_text(encoding="utf-8")) or None


def _read_prior_counts(path):  # type: ignore[no-untyped-def]
    """The prior validate run's recorded counts (the §5.2 cross-run drop baseline), or ``None``."""
    if not path.is_file():
        return None
    try:
        return dict(json.loads(path.read_text(encoding="utf-8")).get("counts") or {})
    except (ValueError, AttributeError):
        return None


def _normalize_counts(ctx: StageContext) -> dict[str, int]:
    """The emitted ``stage_runs[normalize].counts`` — the per-sidecar aggregates §5.2 reconciles
    (the artifact nothing consumed until this gate). Empty if normalize has no recorded run."""
    run = ctx.state.get("normalize", ctx.scope)
    return dict(run.counts) if run is not None else {}
