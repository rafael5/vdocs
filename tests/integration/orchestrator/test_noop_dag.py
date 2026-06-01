"""The Phase-1 proof: a no-op two-stage DAG exercising the full spine (design §17 step 1).

alpha (requires external `vdl`, produces alpha.out) → beta (requires alpha.out, produces
beta.out). Verifies preflight → run → postflight, the completion record, and skip/force —
green end to end, with no real pipeline stage involved.
"""

import pytest

from vdocs.contracts.registry import VDL
from vdocs.kernel import cas
from vdocs.models.artifact import ArtifactContract, Kind, StorageClass
from vdocs.models.stage import Decision, Idempotency, RunResult
from vdocs.orchestrator.engine import Orchestrator, OrchestratorError
from vdocs.orchestrator.stage import Stage, StageContext

ALPHA_OUT = ArtifactContract(
    key="alpha.out",
    kind=Kind.FILE,
    storage_class=StorageClass.TEXT_VERSIONED,
    produced_by="alpha",
    relpath="alpha.out",
)
BETA_OUT = ArtifactContract(
    key="beta.out",
    kind=Kind.FILE,
    storage_class=StorageClass.TEXT_VERSIONED,
    produced_by="beta",
    relpath="beta.out",
)


class Alpha(Stage):
    name = "alpha"
    description = "no-op producer seeded by the external source"
    requires = [VDL]
    produces = [ALPHA_OUT]
    idempotency = Idempotency.SKIP_IF_UNCHANGED

    def __init__(self) -> None:
        self.run_count = 0

    def run(self, ctx: StageContext, force: bool) -> RunResult:
        self.run_count += 1
        cas.atomic_write(ALPHA_OUT.locate(ctx.cfg).path, b"alpha-payload")
        return RunResult(counts={"processed": 1})


class Beta(Stage):
    name = "beta"
    description = "no-op consumer of alpha.out"
    requires = [ALPHA_OUT]
    produces = [BETA_OUT]
    idempotency = Idempotency.SKIP_IF_UNCHANGED

    def __init__(self) -> None:
        self.run_count = 0

    def run(self, ctx: StageContext, force: bool) -> RunResult:
        self.run_count += 1
        src = ALPHA_OUT.locate(ctx.cfg).path.read_bytes()
        cas.atomic_write(BETA_OUT.locate(ctx.cfg).path, src + b"+beta")
        return RunResult(counts={"processed": 1})


def test_fresh_run_executes_both_and_records_ok(ctx):
    alpha, beta = Alpha(), Beta()
    orch = Orchestrator([beta, alpha])  # deliberately out of order — topo sort fixes it

    results = orch.run(ctx)

    assert [r.stage for r in results] == ["alpha", "beta"]  # topological order
    assert all(r.status == "ok" for r in results)
    assert alpha.run_count == 1 and beta.run_count == 1
    # artifacts exist with the expected chained content
    assert ALPHA_OUT.locate(ctx.cfg).path.read_bytes() == b"alpha-payload"
    assert BETA_OUT.locate(ctx.cfg).path.read_bytes() == b"alpha-payload+beta"
    # completion records carry fingerprints of the produced artifacts
    alpha_rec = ctx.state.get("alpha")
    assert "alpha.out" in alpha_rec.outputs_fp
    beta_rec = ctx.state.get("beta")
    # beta's recorded input fingerprint matches alpha's recorded output fingerprint
    assert beta_rec.inputs_fp["alpha.out"] == alpha_rec.outputs_fp["alpha.out"]


def test_rerun_skips_when_inputs_unchanged(ctx):
    alpha, beta = Alpha(), Beta()
    orch = Orchestrator([alpha, beta])

    orch.run(ctx)
    second = orch.run(ctx)

    assert second == [None, None]  # both skipped
    assert alpha.run_count == 1 and beta.run_count == 1  # no re-execution


def test_force_reruns_everything(ctx):
    alpha, beta = Alpha(), Beta()
    orch = Orchestrator([alpha, beta])

    orch.run(ctx)
    forced = orch.run(ctx, force=True)

    assert all(r is not None and r.status == "ok" for r in forced)
    assert alpha.run_count == 2 and beta.run_count == 2


def test_missing_prerequisite_fails_with_remediation(ctx):
    # beta alone, with no alpha output present
    beta = Beta()
    pf = beta.preflight(ctx, force=False)
    assert pf.decision is Decision.FAIL
    assert pf.remediation == "Run: vdocs alpha"


def test_stale_upstream_output_is_detected(ctx):
    alpha, beta = Alpha(), Beta()
    Orchestrator([alpha, beta]).run(ctx)
    # mutate alpha.out *behind the orchestrator's back* — fingerprint no longer matches
    # the value alpha recorded in its completion record.
    cas.atomic_write(ALPHA_OUT.locate(ctx.cfg).path, b"tampered")
    pf = beta.preflight(ctx, force=False)
    assert pf.decision is Decision.FAIL
    assert "changed since alpha" in pf.reason
    assert pf.remediation == "re-run alpha"


def test_only_runs_single_stage(ctx):
    alpha, beta = Alpha(), Beta()
    orch = Orchestrator([alpha, beta])
    results = orch.run(ctx, only="alpha")
    assert [r.stage for r in results] == ["alpha"]
    assert beta.run_count == 0


def test_from_and_to_slice_the_order(ctx):
    alpha, beta = Alpha(), Beta()
    orch = Orchestrator([alpha, beta])
    orch.run(ctx, to="alpha")  # only alpha
    assert alpha.run_count == 1 and beta.run_count == 0
    orch.run(ctx, from_="beta")  # only beta (alpha's output now present)
    assert beta.run_count == 1


def test_duplicate_stage_names_rejected():
    with pytest.raises(OrchestratorError):
        Orchestrator([Alpha(), Alpha()])


def test_unknown_stage_selection_rejected(ctx):
    orch = Orchestrator([Alpha(), Beta()])
    with pytest.raises(OrchestratorError):
        orch.run(ctx, only="ghost")


def test_cycle_is_detected():
    a_out = ArtifactContract(
        key="cyc.a", kind=Kind.FILE, storage_class=StorageClass.STATE, produced_by="ca", relpath="a"
    )
    b_out = ArtifactContract(
        key="cyc.b", kind=Kind.FILE, storage_class=StorageClass.STATE, produced_by="cb", relpath="b"
    )

    class CA(Stage):
        name = "ca"
        requires = [b_out]
        produces = [a_out]

        def run(self, ctx, force):  # pragma: no cover - never reached
            return RunResult()

    class CB(Stage):
        name = "cb"
        requires = [a_out]
        produces = [b_out]

        def run(self, ctx, force):  # pragma: no cover - never reached
            return RunResult()

    with pytest.raises(OrchestratorError):
        Orchestrator([CA(), CB()]).order()
