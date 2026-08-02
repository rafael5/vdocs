"""The `doctor` stage — the corpus-soundness gate, wired into the DAG as its terminal node.

The 20 checks (coverage floors, anchor integrity + coverage, the entity-quarantine cascade, the
SKL-projection wipe detector, gate fidelity, latest-only FTS, vocab closure, and read-contract
verbatim verification) already existed and already passed — but they ran only under ``build`` or
by hand, so a pipeline driven with ``vdocs run`` could finish green over a RED-able ``index.db``
and nobody asked (audit R‑6 / [S18]; the org's CI-audit F‑27 class: *a gate that works is not a
gate that is enforced*). This stage is the placement fix, and it is deliberately **thin**:

- the checks are NOT forked — :func:`vdocs.server.doctor.diagnose_lake` is the one diagnosis
  path, shared with the ``vdocs doctor`` command;
- the ``CONTRACT_MANIFEST`` edge is what sorts it after ``manifest``, making it terminal — so a
  run that reaches the manifest reaches the gate (in particular the ``index --force``-after-
  ``merge`` case the "SKL projections" check exists for);
- ``ALWAYS_RERUN``: a gate re-checks every time, like ``validate``;
- RED ⇒ ``deep_gate`` fails ⇒ ``PostflightError`` ⇒ non-zero exit through the existing
  stop-on-first-error contract. WARN and BY-DESIGN never fail — F6 in ``doctor.verdict()`` is
  deliberate (an expected gap is not a defect), and WARNs surface as run warnings instead.

Its output, ``reports/doctor/doctor.json``, makes the verdict a **computable artifact** (the §5
ledger's 17th node) rather than stdout a human read.
"""

from __future__ import annotations

import json

import structlog

from vdocs.contracts.registry import (
    CONTRACT_MANIFEST,
    DOCTOR_REPORT,
    INDEX_DOCUMENTS,
    REGISTRIES,
    RELATIONS,
)
from vdocs.kernel import cas
from vdocs.models.stage import Idempotency, PostflightResult, RunResult
from vdocs.orchestrator.stage import Stage, StageContext
from vdocs.server import doctor as doc
from vdocs.stages.doctor import doctor_pure as dp

log = structlog.get_logger(__name__)


class DoctorStage(Stage):
    name = "doctor"
    description = "corpus-soundness gate: 20 checks over index.db → GOLD LIBRARY GREEN|RED"
    # CONTRACT_MANIFEST (produced by `manifest`) is the edge that makes this terminal; the two
    # index.db tables are the substrate the checks actually read. REGISTRIES carries the policy
    # the verdict is measured against (doctor-policy / the gate keep-set / entity-quality), so it
    # is a real input edge, not a file read behind the DAG's back.
    requires = [INDEX_DOCUMENTS, RELATIONS, CONTRACT_MANIFEST, REGISTRIES]
    produces = [DOCTOR_REPORT]
    idempotency = Idempotency.ALWAYS_RERUN
    # F4: `vdocs doctor` must diagnose a present, valid index.db even with no state.db run
    # records (a wiped state must not make the gate unrunnable). Drift is still checked when a
    # record does exist.
    requires_upstream_record = False

    def __init__(self) -> None:
        self._verdict = "GREEN"
        self._failures: list[str] = []

    def run(self, ctx: StageContext, force: bool) -> RunResult:
        report = doc.diagnose_lake(ctx.cfg)
        self._verdict = report.verdict()
        self._failures = [f"{c.name}: {c.detail}" for c in report.failures()]

        payload = dp.report_payload(report, tool_ver=ctx.cfg.tool_ver, generated_at=ctx.clock())
        cas.atomic_write(
            ctx.cfg.doctor_report,
            (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode(
                "utf-8"
            ),
        )
        if self._verdict == "RED":
            log.warning("doctor-red", failures=self._failures)
        counts = dp.health_counts(report)
        return RunResult(
            counts={"gold_documents": report.gold_count, **counts},
            # WARN/BY-DESIGN never block (F6) — but they are surfaced, never swallowed.
            warnings=[
                f"{c.name}: {c.detail}" for c in report.checks if c.health is doc.Health.WARN
            ],
        )

    def deep_gate(self, ctx: StageContext) -> PostflightResult:
        """The gate the audit found un-enforced: a RED corpus stops the run (non-zero exit)."""
        if self._verdict == "RED":
            return PostflightResult(
                ok=False,
                reason=(
                    f"GOLD LIBRARY: RED — {len(self._failures)} failing check(s): "
                    + "; ".join(self._failures)
                ),
            )
        return PostflightResult(ok=True)
