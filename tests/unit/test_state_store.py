"""Unit tests for the StateStore — the stage_runs completion-record store (§7.2)."""

from vdocs.models.stage import StageRun
from vdocs.orchestrator.state import StateStore


def _run(stage: str, status: str = "ok", scope: str = "") -> StageRun:
    return StageRun(
        stage=stage,
        scope=scope,
        status=status,  # type: ignore[arg-type]
        started_at="2026-06-01T00:00:00Z",
        finished_at="2026-06-01T00:00:01Z",
        inputs_fp={"vdl": "external:vdl"},
        outputs_fp={f"{stage}.out": "abc"},
        counts={"processed": 1},
        contract_ver=1,
        tool_ver="0.1.0",
    )


def test_record_then_get_round_trips(tmp_path):
    store = StateStore.open(tmp_path / "state.db")
    try:
        store.record(_run("alpha"))
        got = store.get("alpha")
        assert got is not None
        assert got.status == "ok"
        assert got.outputs_fp == {"alpha.out": "abc"}
        assert got.counts == {"processed": 1}
    finally:
        store.close()


def test_get_missing_returns_none(tmp_path):
    store = StateStore.open(tmp_path / "state.db")
    try:
        assert store.get("nope") is None
    finally:
        store.close()


def test_record_is_upsert_by_stage_and_scope(tmp_path):
    store = StateStore.open(tmp_path / "state.db")
    try:
        store.record(_run("alpha", status="failed"))
        store.record(_run("alpha", status="ok"))
        got = store.get("alpha")
        assert got is not None and got.status == "ok"
    finally:
        store.close()


def test_scope_is_part_of_the_key(tmp_path):
    store = StateStore.open(tmp_path / "state.db")
    try:
        store.record(_run("enrich", scope="LR"))
        store.record(_run("enrich", scope="PSO"))
        assert store.get("enrich", scope="LR") is not None
        assert store.get("enrich", scope="PSO") is not None
        assert store.get("enrich", scope="") is None
    finally:
        store.close()


def test_persists_across_reopen(tmp_path):
    path = tmp_path / "state.db"
    s1 = StateStore.open(path)
    s1.record(_run("alpha"))
    s1.close()
    s2 = StateStore.open(path)
    try:
        assert s2.get("alpha") is not None
    finally:
        s2.close()
