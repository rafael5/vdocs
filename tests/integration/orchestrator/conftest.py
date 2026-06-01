"""Shared fixtures for orchestrator integration tests."""

import itertools

import pytest

from vdocs.config import Settings
from vdocs.orchestrator.stage import StageContext
from vdocs.orchestrator.state import StateStore


@pytest.fixture
def ctx(tmp_path):
    """A StageContext with a monotonic injected clock (deterministic timestamps)."""
    counter = itertools.count()
    cfg = Settings(data_dir=tmp_path)
    cfg.lake.mkdir(parents=True, exist_ok=True)
    store = StateStore.open(cfg.state_db)
    context = StageContext(
        cfg=cfg,
        state=store,
        clock=lambda: f"2026-06-01T00:00:{next(counter):02d}Z",
    )
    yield context
    store.close()
