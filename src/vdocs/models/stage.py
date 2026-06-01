"""Stage decision/result types and the completion record (§7.1, §7.2).

These are the boundary types the orchestrator exchanges with stages and persists to
``state.db``. ``StageRun`` is the completion record — one row per ``(stage, scope)``;
``status='ok'`` is reachable only by passing postflight, and it is the inter-stage
contract surface the next stage's preflight reads.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class Idempotency(StrEnum):
    """How a stage decides whether a re-run is needed (§7.1)."""

    SKIP_IF_UNCHANGED = "skip_if_unchanged"
    ALWAYS_RERUN = "always_rerun"
    FORCE_ONLY = "force_only"


class Decision(StrEnum):
    """The outcome of preflight (§7.3)."""

    PROCEED = "proceed"
    SKIP = "skip"
    FAIL = "fail"


class PreflightResult(BaseModel):
    """Preflight verdict, with a remediation hint on failure (tenet #7)."""

    model_config = {"frozen": True}

    decision: Decision
    reason: str = ""
    remediation: str = ""

    @classmethod
    def proceed(cls) -> PreflightResult:
        return cls(decision=Decision.PROCEED)

    @classmethod
    def skip(cls, reason: str) -> PreflightResult:
        return cls(decision=Decision.SKIP, reason=reason)

    @classmethod
    def fail(cls, reason: str, *, remediation: str = "") -> PreflightResult:
        return cls(decision=Decision.FAIL, reason=reason, remediation=remediation)


class RunResult(BaseModel):
    """What a stage's ``run`` reports — counts of work done (§7.2 ``counts``)."""

    counts: dict[str, int] = Field(default_factory=dict)


class PostflightResult(BaseModel):
    """Postflight verdict: did ``produces[]`` validate / did the deep gate pass."""

    model_config = {"frozen": True}

    ok: bool
    reason: str = ""


class StageRun(BaseModel):
    """The completion record persisted to ``state.db:stage_runs`` (§7.2)."""

    stage: str
    scope: str = ""
    status: Literal["ok", "failed"]
    started_at: str
    finished_at: str
    inputs_fp: dict[str, str]
    outputs_fp: dict[str, str]
    counts: dict[str, int]
    contract_ver: int
    tool_ver: str
