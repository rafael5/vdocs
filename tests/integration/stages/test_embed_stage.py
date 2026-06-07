"""embed integration — chunks → vectors.db, and the graceful skip when fastembed is absent.

`embed` is the Phase-6 semantic stage; its real backend (`fastembed`) is an optional runtime dep.
When it isn't installed, the stage must **skip** (a no-op, semantic stays off) rather than fail —
so a `vdocs run` slice that crosses `embed` isn't blocked by the not-yet-enabled stage (D3, §14.6).
With an injected embedder (the test/fake path) it runs regardless.
"""

from __future__ import annotations

import pytest

from vdocs.contracts.registry import INDEX_CHUNKS
from vdocs.kernel import db
from vdocs.models.stage import Decision, StageRun
from vdocs.orchestrator.engine import Orchestrator
from vdocs.stages.embed import stage as embed_stage
from vdocs.stages.embed.stage import Embedder, EmbedStage


def _seed_chunks(ctx):
    conn = db.connect(ctx.cfg.index_db)
    conn.executescript("CREATE TABLE chunks (chunk_id TEXT PRIMARY KEY, text TEXT)")
    conn.executemany(
        "INSERT INTO chunks VALUES (?, ?)",
        [("d/a", "alpha text"), ("d/b", "beta text")],
    )
    conn.commit()
    conn.close()
    ctx.state.record(
        StageRun(
            stage="index",
            scope="",
            status="ok",
            started_at="t",
            finished_at="t",
            inputs_fp={},
            outputs_fp={INDEX_CHUNKS.key: INDEX_CHUNKS.fingerprint(ctx.cfg)},
            counts={},
            contract_ver=1,
            tool_ver=ctx.cfg.tool_ver,
        )  # fmt: skip
    )


def test_embed_skips_when_fastembed_absent(ctx, monkeypatch):
    # the real default backend is selected (no injected embedder) but fastembed isn't installed
    monkeypatch.setattr(embed_stage, "_fastembed_available", lambda: False)
    stage = EmbedStage()
    pf = stage.preflight(ctx, force=False)
    assert pf.decision is Decision.SKIP
    assert "fastembed" in pf.reason.lower()
    # and the orchestrator treats it as a benign skip (None result), writing no vectors.db
    (result,) = Orchestrator([stage]).run(ctx)
    assert result is None
    assert not ctx.cfg.vectors_db.exists()


def test_embed_skips_even_when_forced_if_fastembed_absent(ctx, monkeypatch):
    # a missing optional dependency is not something --force can satisfy
    monkeypatch.setattr(embed_stage, "_fastembed_available", lambda: False)
    assert EmbedStage().preflight(ctx, force=True).decision is Decision.SKIP


def test_embed_runs_with_injected_embedder(ctx):
    # an injected embedder bypasses the fastembed check and embeds the chunks into vectors.db
    _seed_chunks(ctx)
    fake = Embedder("fake-model", "0", lambda texts: [[0.1, 0.2, 0.3] for _ in texts])
    (result,) = Orchestrator([EmbedStage(embedder=fake)]).run(ctx)
    assert result.status == "ok"
    assert result.counts == {"chunks": 2, "dim": 3}
    assert ctx.cfg.vectors_db.exists()
    vconn = db.connect(ctx.cfg.vectors_db, read_only=True)
    try:
        model = vconn.execute("SELECT model, version, dim FROM embedding_model").fetchone()
        # vec_chunks is a vec0 virtual table (needs the sqlite-vec extension to query its rows);
        # its presence in the schema is enough here — the dim/chunk counts come from the result.
        has_vec = vconn.execute(
            "SELECT count(*) FROM sqlite_master WHERE name='vec_chunks'"
        ).fetchone()[0]
    finally:
        vconn.close()
    assert tuple(model) == ("fake-model", "0", 3)
    assert has_vec == 1


def test_embed_rejects_chunk_over_token_budget(ctx):
    # A1 gate: a chunk that would exceed the model's token budget must fail the build (silent
    # truncation at embed time would leave a hole in the vector index), naming the offender.
    conn = db.connect(ctx.cfg.index_db)
    conn.executescript("CREATE TABLE chunks (chunk_id TEXT PRIMARY KEY, text TEXT)")
    conn.executemany(
        "INSERT INTO chunks VALUES (?, ?)",
        [("d/ok", "small"), ("d/huge", "x" * 100_000)],
    )
    conn.commit()
    conn.close()
    ctx.state.record(
        StageRun(
            stage="index",
            scope="",
            status="ok",
            started_at="t",
            finished_at="t",
            inputs_fp={},
            outputs_fp={INDEX_CHUNKS.key: INDEX_CHUNKS.fingerprint(ctx.cfg)},
            counts={},
            contract_ver=1,
            tool_ver=ctx.cfg.tool_ver,
        )  # fmt: skip
    )
    tiny_budget = Embedder("fake", "0", lambda texts: [[0.0] for _ in texts], max_tokens=64)
    with pytest.raises(ValueError, match="d/huge"):
        Orchestrator([EmbedStage(embedder=tiny_budget)]).run(ctx)
    assert not ctx.cfg.vectors_db.exists()
