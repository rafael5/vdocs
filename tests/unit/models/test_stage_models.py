"""Unit tests for models.stage — decision/result types + the completion record (§7.1, §7.2)."""

import pytest
from pydantic import ValidationError

from vdocs.models.stage import (
    Decision,
    Idempotency,
    PostflightResult,
    PreflightResult,
    RunResult,
    StageRun,
)


def test_idempotency_members():
    assert {i.value for i in Idempotency} == {"skip_if_unchanged", "always_rerun", "force_only"}


def test_preflight_constructors():
    assert PreflightResult.proceed().decision is Decision.PROCEED
    skip = PreflightResult.skip("unchanged")
    assert skip.decision is Decision.SKIP and skip.reason == "unchanged"
    fail = PreflightResult.fail("missing input", remediation="Run: vdocs crawl")
    assert fail.decision is Decision.FAIL
    assert fail.remediation == "Run: vdocs crawl"


def test_run_result_defaults_to_empty_counts():
    assert RunResult().counts == {}
    assert RunResult(counts={"processed": 3}).counts == {"processed": 3}


def test_postflight_result():
    assert PostflightResult(ok=True).ok is True
    assert PostflightResult(ok=False, reason="bad output").reason == "bad output"


def test_stage_run_round_trips():
    run = StageRun(
        stage="alpha",
        status="ok",
        started_at="2026-06-01T00:00:00Z",
        finished_at="2026-06-01T00:00:01Z",
        inputs_fp={"vdl": "external:vdl"},
        outputs_fp={"alpha.out": "deadbeef"},
        counts={"processed": 1},
        contract_ver=1,
        tool_ver="0.1.0",
    )
    again = StageRun.model_validate(run.model_dump())
    assert again == run
    assert again.scope == ""  # default scope is whole-corpus


def test_stage_run_rejects_bad_status():
    with pytest.raises(ValidationError):
        StageRun(
            stage="alpha",
            status="weird",
            started_at="t",
            finished_at="t",
            inputs_fp={},
            outputs_fp={},
            counts={},
            contract_ver=1,
            tool_ver="0.1.0",
        )
