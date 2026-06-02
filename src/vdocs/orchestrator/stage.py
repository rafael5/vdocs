"""The Stage abstraction and the generic preflight/postflight engine (§7.1, §7.3).

The §7.3 preflight/postflight algorithms live here **once** as concrete methods on the
``Stage`` base class — every stage inherits the identical logic and overrides only
``run`` (and optionally ``deep_gate``). This is the anti-duplication rule (§9.2) applied
to orchestration: there is no second code path, and no stage re-implements gating.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

import structlog

from vdocs.config import Settings
from vdocs.models.artifact import ArtifactContract
from vdocs.models.stage import (
    Idempotency,
    PostflightResult,
    PreflightResult,
    RunResult,
    StageRun,
)
from vdocs.orchestrator.state import StateStore

log = structlog.get_logger(__name__)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class StageContext:
    """Everything a stage needs at runtime — resolved config + state, no globals (§9.1)."""

    cfg: Settings
    state: StateStore
    scope: str = ""
    verify: bool = False
    clock: Callable[[], str] = field(default=_utc_now)


class PostflightError(RuntimeError):
    """Raised when a stage's outputs fail validation or the deep gate (§7.3)."""


class Stage(ABC):
    """One node of the pipeline DAG: a pure transform from ``requires`` to ``produces``."""

    name: str
    description: str = ""
    requires: list[ArtifactContract] = []
    produces: list[ArtifactContract] = []
    idempotency: Idempotency = Idempotency.SKIP_IF_UNCHANGED
    contract_ver: int = 1

    # --- the work (the only thing a concrete stage must implement) ---
    @abstractmethod
    def run(self, ctx: StageContext, force: bool) -> RunResult:
        """Do the transform. Write to a temp location and atomic-swap on success (§7.4)."""

    def deep_gate(self, ctx: StageContext) -> PostflightResult:
        """Stage-specific output gate; default passes. ``validate`` overrides this (§7.3)."""
        return PostflightResult(ok=True)

    def extra_input_fps(self, ctx: StageContext) -> dict[str, str]:
        """Stage-specific contributions to the input fingerprint, beyond the ``requires``
        contracts (§7.3). The default is none; ``fetch`` overrides it to fold its resolved
        selection into ``inputs_fp`` so the selection participates in ``SKIP_IF_UNCHANGED``
        (§5.6). Keys must not collide with any ``requires`` artifact key."""
        return {}

    # --- generic preflight (§7.3) ---
    def preflight(self, ctx: StageContext, force: bool) -> PreflightResult:
        cfg = ctx.cfg
        # 1. Every required input must be present & usable (or a loud-WARN if optional).
        for c in self.requires:
            res = c.validate(cfg)
            if not res.ok:
                if c.optional:
                    log.warning(
                        "optional-input-missing", stage=self.name, artifact=c.key, detail=res.detail
                    )
                    continue
                remediation = f"Run: vdocs {c.produced_by}" if c.produced_by else f"Provide {c.key}"
                return PreflightResult.fail(
                    f"required input {c.key} is not usable: {res.detail}",
                    remediation=remediation,
                )
        # 2. Internal upstreams must have completed ok and not drifted since (§7.3).
        for c in self.requires:
            if c.produced_by is None or not c.validate(cfg).ok:
                continue
            up = ctx.state.get(c.produced_by, ctx.scope)
            if up is None or up.status != "ok":
                return PreflightResult.fail(
                    f"upstream {c.produced_by} has not completed ok for scope {ctx.scope!r}",
                    remediation=f"Run: vdocs {c.produced_by}",
                )
            if up.outputs_fp.get(c.key) != c.fingerprint(cfg, verify=ctx.verify):
                return PreflightResult.fail(
                    f"{c.key} changed since {c.produced_by} produced it",
                    remediation=f"re-run {c.produced_by}",
                )
        # 3 & 4. Skip decision.
        if force or self.idempotency == Idempotency.ALWAYS_RERUN:
            return PreflightResult.proceed()
        if self.idempotency == Idempotency.FORCE_ONLY:
            return PreflightResult.skip("force-only stage; not forced")
        prior = ctx.state.get(self.name, ctx.scope)
        if prior is not None and prior.status == "ok":
            # Optional outputs may legitimately be absent (e.g. a doc with no images → empty
            # asset CAS); they don't gate the skip decision.
            produces_ok = all(p.validate(cfg).ok for p in self.produces if not p.optional)
            # A produces[] shape change is signalled by a contract_ver bump; it must re-run
            # even when inputs are unchanged (§7.3 step 2; design.md:786).
            same_contract = prior.contract_ver == self.contract_ver
            if same_contract and prior.inputs_fp == self._input_fps(ctx) and produces_ok:
                return PreflightResult.skip("inputs unchanged")
        return PreflightResult.proceed()

    # --- generic postflight (§7.3) ---
    def postflight(self, ctx: StageContext, run: RunResult, started_at: str) -> StageRun:
        cfg = ctx.cfg
        finished_at = ctx.clock()
        inputs_fp = self._input_fps(ctx)
        # Required outputs must validate; optional outputs that are absent/empty don't fail
        # the gate (but if present they're fingerprinted below).
        invalid = [p.key for p in self.produces if not p.optional and not p.validate(cfg).ok]
        gate = self.deep_gate(ctx)
        if invalid or not gate.ok:
            self._write(ctx, "failed", started_at, finished_at, inputs_fp, {}, run.counts)
            reason = f"invalid outputs {invalid}" if invalid else gate.reason
            raise PostflightError(f"{self.name} postflight failed: {reason}")
        outputs_fp = {
            p.key: p.fingerprint(cfg, verify=ctx.verify)
            for p in self.produces
            if p.validate(cfg).ok
        }
        return self._write(ctx, "ok", started_at, finished_at, inputs_fp, outputs_fp, run.counts)

    # --- helpers ---
    def _input_fps(self, ctx: StageContext) -> dict[str, str]:
        fps: dict[str, str] = {}
        for c in self.requires:
            if not c.validate(ctx.cfg).ok:
                continue
            fps[c.key] = c.fingerprint(ctx.cfg, verify=ctx.verify)
            # Fold each internal upstream's contract_ver into this stage's input identity:
            # a produces[] shape bump that the cheap fingerprint can't see (e.g. a new SQLite
            # column) still changes inputs_fp here, so the consumer re-runs (§7.3 step 2).
            if c.produced_by is not None:
                up = ctx.state.get(c.produced_by, ctx.scope)
                if up is not None and up.status == "ok":
                    fps[f"{c.key}#contract_ver"] = str(up.contract_ver)
        extra = self.extra_input_fps(ctx)
        clash = extra.keys() & fps.keys()
        if clash:
            raise ValueError(
                f"{self.name}.extra_input_fps keys collide with input fingerprint keys: "
                f"{sorted(clash)}"
            )
        fps.update(extra)
        return fps

    def _write(
        self,
        ctx: StageContext,
        status: str,
        started_at: str,
        finished_at: str,
        inputs_fp: dict[str, str],
        outputs_fp: dict[str, str],
        counts: dict[str, int],
    ) -> StageRun:
        run = StageRun(
            stage=self.name,
            scope=ctx.scope,
            status=status,  # type: ignore[arg-type]
            started_at=started_at,
            finished_at=finished_at,
            inputs_fp=inputs_fp,
            outputs_fp=outputs_fp,
            counts=counts,
            contract_ver=self.contract_ver,
            tool_ver=ctx.cfg.tool_ver,
        )
        ctx.state.record(run)
        return run
