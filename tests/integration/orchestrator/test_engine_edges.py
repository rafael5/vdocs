"""Edge-case coverage for the spine: gating branches the happy path doesn't exercise."""

import pytest

from vdocs.contracts.registry import VDL
from vdocs.kernel import cas
from vdocs.models.artifact import ArtifactContract, Kind, StorageClass
from vdocs.models.stage import Decision, Idempotency, RunResult
from vdocs.orchestrator.engine import Orchestrator, StageFailed
from vdocs.orchestrator.stage import PostflightError, Stage, _utc_now


def _file(key, producer=None):
    return ArtifactContract(
        key=key,
        kind=Kind.FILE,
        storage_class=StorageClass.TEXT_VERSIONED,
        produced_by=producer,
        relpath=f"{key}.bin",
    )


OUT = _file("solo")
DEP = _file("dep", producer="producer")


def test_default_clock_returns_iso_timestamp(ctx):
    # _utc_now is the default StageContext clock; exercise it directly.
    assert _utc_now().startswith("20")
    assert ctx.clock()  # injected clock still works


def test_optional_missing_input_warns_and_proceeds(ctx):
    optional = ArtifactContract(
        key="opt",
        kind=Kind.FILE,
        storage_class=StorageClass.TEXT_VERSIONED,
        produced_by="upstream",
        optional=True,
        relpath="opt.bin",
    )

    class S(Stage):
        name = "s"
        requires = [optional]
        produces = [OUT]
        idempotency = Idempotency.SKIP_IF_UNCHANGED

        def run(self, ctx, force):
            cas.atomic_write(OUT.locate(ctx.cfg).path, b"x")
            return RunResult()

    pf = S().preflight(ctx, force=False)
    assert pf.decision is Decision.PROCEED  # missing optional → WARN, not FAIL


def test_upstream_present_on_disk_but_no_ok_record_fails(ctx):
    # The dependency file exists, but its producer never wrote an ok stage_run.
    cas.atomic_write(DEP.locate(ctx.cfg).path, b"orphan")

    class Consumer(Stage):
        name = "consumer"
        requires = [DEP]
        produces = [_file("consumed", producer="consumer")]

        def run(self, ctx, force):  # pragma: no cover - preflight fails first
            return RunResult()

    pf = Consumer().preflight(ctx, force=False)
    assert pf.decision is Decision.FAIL
    assert "has not completed ok" in pf.reason
    assert pf.remediation == "Run: vdocs producer"


def test_force_only_stage_skips_without_force(ctx):
    class Net(Stage):
        name = "net"
        requires = [VDL]
        produces = [OUT]
        idempotency = Idempotency.FORCE_ONLY

        def run(self, ctx, force):  # pragma: no cover - skipped without force
            return RunResult()

    pf = Net().preflight(ctx, force=False)
    assert pf.decision is Decision.SKIP
    assert "force-only" in pf.reason


def test_always_rerun_proceeds_without_force(ctx):
    runs = []

    class Always(Stage):
        name = "always"
        requires = [VDL]
        produces = [OUT]
        idempotency = Idempotency.ALWAYS_RERUN

        def run(self, ctx, force):
            runs.append(1)
            cas.atomic_write(OUT.locate(ctx.cfg).path, b"x")
            return RunResult()

    orch = Orchestrator([Always()])
    orch.run(ctx)
    orch.run(ctx)  # no force, but ALWAYS_RERUN → runs again
    assert len(runs) == 2


def test_postflight_fails_when_output_not_produced(ctx):
    class Lazy(Stage):
        name = "lazy"
        requires = [VDL]
        produces = [OUT]

        def run(self, ctx, force):
            return RunResult()  # writes nothing — postflight must catch it

    with pytest.raises(PostflightError):
        Orchestrator([Lazy()]).run(ctx)
    rec = ctx.state.get("lazy")
    assert rec is not None and rec.status == "failed"


def test_postflight_deep_gate_failure_blocks(ctx):
    class Gated(Stage):
        name = "gated"
        requires = [VDL]
        produces = [OUT]

        def run(self, ctx, force):
            cas.atomic_write(OUT.locate(ctx.cfg).path, b"x")
            return RunResult()

        def deep_gate(self, ctx):
            from vdocs.models.stage import PostflightResult

            return PostflightResult(ok=False, reason="synthetic gate failure")

    with pytest.raises(PostflightError):
        Orchestrator([Gated()]).run(ctx)
    assert ctx.state.get("gated").status == "failed"


def test_orchestrator_run_raises_stage_failed_with_remediation(ctx):
    # A consumer whose required input is simply absent → run() surfaces StageFailed.
    class Consumer(Stage):
        name = "beta"
        requires = [DEP]
        produces = [_file("c", producer="beta")]

        def run(self, ctx, force):  # pragma: no cover - preflight fails first
            return RunResult()

    with pytest.raises(StageFailed) as exc:
        Orchestrator([Consumer()]).run(ctx)
    assert exc.value.remediation == "Run: vdocs producer"
    assert "producer" in str(exc.value)
