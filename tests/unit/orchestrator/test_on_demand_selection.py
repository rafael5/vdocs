"""On-demand stages are off the default path but still runnable by name (PM.3b).

A stage whose output no other stage consumes should not be paid for on every rebuild. `discover`
is the case that forced the rule: it mines ~81,500 pattern *proposals* nobody consumes (nothing
`requires` its contract), and the PM.1 sample measured the whole approvable furniture fraction at
~0.07% of the corpus. Rather than special-case it, the orchestrator gains a generic selection
flag — `Stage.on_demand` — so range selections (a full build, `--from`/`--to`) skip it while
`--only <name>` still runs it. The stage stays registered, so the DAG order is unchanged.
"""

from vdocs.models.artifact import ArtifactContract, Kind, StorageClass
from vdocs.models.stage import RunResult
from vdocs.orchestrator.engine import Orchestrator
from vdocs.orchestrator.stage import Stage, StageContext

A_OUT = ArtifactContract(
    key="a.out",
    kind=Kind.FILE,
    storage_class=StorageClass.TEXT_VERSIONED,
    produced_by="a",
    relpath="a.out",
)


class _A(Stage):
    name = "a"
    produces = [A_OUT]

    def run(self, ctx: StageContext, force: bool) -> RunResult:  # pragma: no cover - not driven
        return RunResult(counts={})


class _Sidecar(Stage):
    """Consumes `a.out`, produces something nobody reads — the `discover` shape."""

    name = "sidecar"
    requires = [A_OUT]
    on_demand = True

    def run(self, ctx: StageContext, force: bool) -> RunResult:  # pragma: no cover - not driven
        return RunResult(counts={})


class _B(Stage):
    name = "b"
    requires = [A_OUT]

    def run(self, ctx: StageContext, force: bool) -> RunResult:  # pragma: no cover - not driven
        return RunResult(counts={})


def _orch() -> Orchestrator:
    return Orchestrator([_A(), _Sidecar(), _B()])


def test_on_demand_stage_is_registered_and_ordered() -> None:
    """It stays a DAG node — only its *selection* changes, so `--only` can still find it."""
    assert [s.name for s in _orch().order()] == ["a", "b", "sidecar"]


def test_default_selection_skips_the_on_demand_stage() -> None:
    assert [s.name for s in _orch()._select(None, None, None)] == ["a", "b"]


def test_range_selection_skips_the_on_demand_stage() -> None:
    """A full build drives `--from`/`--to`; spanning an on-demand stage must not pull it in."""
    assert [s.name for s in _orch()._select("a", "sidecar", None)] == ["a", "b"]


def test_only_still_runs_the_on_demand_stage() -> None:
    assert [s.name for s in _orch()._select(None, None, "sidecar")] == ["sidecar"]


def test_stages_are_on_the_default_path_unless_they_opt_out() -> None:
    assert Stage.on_demand is False
