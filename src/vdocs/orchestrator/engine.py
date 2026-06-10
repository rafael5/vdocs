"""The generic DAG runner (§7.5).

Topologically sorts stages from their ``requires``/``produces`` graph — the §8 table
*is* the graph — and drives each through the identical ``preflight → run → postflight``
sequence, stopping on the first hard failure. There is no hand-maintained ordered stage
list anywhere (tenet #8).
"""

from __future__ import annotations

from collections.abc import Callable

import structlog

from vdocs.models.stage import Decision, StageRun
from vdocs.orchestrator.report import RunReporter, Status
from vdocs.orchestrator.stage import PostflightError, Stage, StageContext

log = structlog.get_logger(__name__)


def _progress_sink(rep: RunReporter, index: int, total: int, name: str) -> Callable[[str], None]:
    """A per-stage heartbeat callable bound to the reporter (so a long stage shows progress)."""

    def progress(message: str) -> None:
        rep.stage_progress(index, total, name, message)

    return progress


class OrchestratorError(RuntimeError):
    """Structural problem with the DAG (duplicate names, cycle, unknown stage)."""


class StageFailed(RuntimeError):
    """A stage's preflight returned FAIL — carries the remediation hint (tenet #7)."""

    def __init__(self, stage: str, reason: str, remediation: str) -> None:
        self.stage = stage
        self.reason = reason
        self.remediation = remediation
        msg = f"{stage}: {reason}"
        if remediation:
            msg += f"  →  {remediation}"
        super().__init__(msg)


class Orchestrator:
    """Holds the stage set, derives execution order, and runs the pipeline."""

    def __init__(self, stages: list[Stage]) -> None:
        names = [s.name for s in stages]
        if len(names) != len(set(names)):
            raise OrchestratorError("duplicate stage names in DAG")
        self._stages = {s.name: s for s in stages}

    def order(self) -> list[Stage]:
        """Kahn topological sort; deterministic (ties broken by stage name)."""
        # deps[consumer] = set of producer stages it depends on (both in this DAG).
        deps: dict[str, set[str]] = {name: set() for name in self._stages}
        for stage in self._stages.values():
            for c in stage.requires:
                if c.produced_by in self._stages and c.produced_by != stage.name:
                    deps[stage.name].add(c.produced_by)
        ordered: list[Stage] = []
        resolved: set[str] = set()
        remaining = set(self._stages)
        while remaining:
            ready = sorted(n for n in remaining if deps[n] <= resolved)
            if not ready:
                raise OrchestratorError(f"cycle detected among stages: {sorted(remaining)}")
            for name in ready:
                ordered.append(self._stages[name])
                resolved.add(name)
                remaining.discard(name)
        return ordered

    def _select(
        self,
        from_: str | None,
        to: str | None,
        only: str | None,
    ) -> list[Stage]:
        order = self.order()
        for name in (from_, to, only):
            if name is not None and name not in self._stages:
                raise OrchestratorError(f"unknown stage {name!r}")
        if only is not None:
            return [self._stages[only]]
        names = [s.name for s in order]
        start = names.index(from_) if from_ else 0
        end = names.index(to) + 1 if to else len(names)
        return order[start:end]

    def run(
        self,
        ctx: StageContext,
        *,
        from_: str | None = None,
        to: str | None = None,
        only: str | None = None,
        force: bool = False,
        reporter: RunReporter | None = None,
    ) -> list[StageRun | None]:
        """Run the selected stages in order. Returns a StageRun per stage (None if skipped).

        ``reporter`` (optional) receives a per-stage outcome so the operator gets a GREEN/WARN/ERROR
        summary + exit code; failures are reported **before** the exception re-raises (so the run
        summary is complete even when a stage stops the run), and the original exception type
        (``StageFailed`` / ``PostflightError``) still propagates for the stop-on-first-error
        contract."""
        rep = reporter or RunReporter(echo=lambda _s: None)
        results: list[StageRun | None] = []
        selected = self._select(from_, to, only)
        total = len(selected)
        for i, stage in enumerate(selected, 1):
            rep.stage_start(i, total, stage.name, stage.description)
            pf = stage.preflight(ctx, force)
            if pf.decision is Decision.FAIL:
                log.error("stage-preflight-failed", stage=stage.name, reason=pf.reason)
                rep.stage_error(i, total, stage.name, pf.reason, pf.remediation)
                raise StageFailed(stage.name, pf.reason, pf.remediation)
            if pf.decision is Decision.SKIP:
                log.info("stage-skipped", stage=stage.name, reason=pf.reason)
                rep.stage_skipped(i, total, stage.name, pf.reason)
                results.append(None)
                continue
            started_at = ctx.clock()
            t0 = ctx.mono()
            ctx.progress = _progress_sink(rep, i, total, stage.name)
            try:
                run = stage.run(ctx, force)
                sr = stage.postflight(ctx, run, started_at)
            except PostflightError as exc:
                log.error("stage-postflight-failed", stage=stage.name, reason=str(exc))
                rep.stage_error(i, total, stage.name, str(exc), "")
                raise
            elapsed = ctx.mono() - t0
            status = Status.WARN if run.warnings else Status.GREEN
            rep.stage_done(i, total, stage.name, status, sr.counts, run.warnings, elapsed)
            log.info("stage-ok", stage=stage.name, counts=sr.counts)
            results.append(sr)
        return results


__all__ = ["Orchestrator", "OrchestratorError", "StageFailed"]
