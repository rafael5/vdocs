"""The `embed` stage — index.db chunks → vectors.db (semantic search surface, §14.6).

Embeds the **searchable, is_latest** chunks (`index.db:chunks`, the A1 retrieval units — containers
and hollow sections already excluded, oversized already split) into `vectors.db`: a sqlite-vec
``vec0`` ANN index keyed by `chunk_id`, plus an `embedding_model` meta row (model/version/dim) that
`manifest` reads to flip semantic search **on** (D3).

The embedding model is an **injected backend** (`Embedder`) — like `convert`'s Pandoc/Docling — so
the stage is fully tested with a fake embedder (no model download in the test path) and the real
model is a lazy default exercised by `vdocs embed`. The model id+version enter the input fingerprint
(`extra_input_fps`), so swapping the model re-embeds; an unchanged model + unchanged chunks skip.
"""

from __future__ import annotations

import importlib.util
import os
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

import sqlite_vec
import structlog

from vdocs.contracts.registry import INDEX_CHUNKS, VECTORS_DB
from vdocs.kernel import db
from vdocs.models.stage import Idempotency, PreflightResult, RunResult
from vdocs.orchestrator.stage import Stage, StageContext
from vdocs.stages.embed import embed_pure as ep

log = structlog.get_logger(__name__)


def _fastembed_available() -> bool:
    """Whether the optional Phase-6 embedding backend (`fastembed`) is importable. Kept as a
    module-level function so the graceful-skip decision is trivially testable."""
    return importlib.util.find_spec("fastembed") is not None


@dataclass(frozen=True)
class Embedder:
    """An injected embedding backend: its model id+version (cheap, for the fingerprint) and a
    batch ``embed`` callable text→vectors (the heavy part, loaded lazily by the real default)."""

    model: str
    version: str
    embed: Callable[[list[str]], list[list[float]]]


def _default_embedder() -> Embedder:
    """The real backend: fastembed's ``BAAI/bge-small-en-v1.5`` (384-dim). The model id+version are
    static (so the fingerprint is cheap); the model itself loads lazily on the first ``embed``
    call — a Phase-6 runtime dep (``uv add fastembed``), not a test/`make check` dependency."""
    state: dict = {}

    def embed(texts: list[str]) -> list[list[float]]:  # pragma: no cover - real backend
        model = state.get("model")
        if model is None:
            from fastembed import TextEmbedding

            model = state["model"] = TextEmbedding("BAAI/bge-small-en-v1.5")
        return [[float(x) for x in v] for v in model.embed(texts)]

    return Embedder("BAAI/bge-small-en-v1.5", "1.5", embed)


class EmbedStage(Stage):
    name = "embed"
    description = "embed searchable chunks → vectors.db (sqlite-vec ANN) for semantic search"
    requires = [INDEX_CHUNKS]
    produces = [VECTORS_DB]
    idempotency = Idempotency.SKIP_IF_UNCHANGED

    def __init__(self, embedder: Embedder | None = None, *, batch_size: int = 256) -> None:
        self._embedder = embedder  # None → the real fastembed default (lazy)
        self._batch = batch_size

    def _emb(self) -> Embedder:
        return self._embedder or _default_embedder()

    def preflight(self, ctx: StageContext, force: bool) -> PreflightResult:
        # D3: semantic embedding is optional. If the real backend would be used but `fastembed`
        # isn't installed, skip gracefully (no-op, semantic stays off) rather than failing the run —
        # so a `vdocs run` slice that crosses `embed` isn't blocked by the not-yet-enabled stage.
        # An injected embedder (tests / a custom backend) bypasses this and runs normally.
        if self._embedder is None and not _fastembed_available():
            return PreflightResult.skip(
                "fastembed not installed; semantic embedding unavailable "
                "(run `uv add fastembed` to enable)"
            )
        return super().preflight(ctx, force)

    def extra_input_fps(self, ctx: StageContext) -> dict[str, str]:
        e = self._emb()  # cheap: the default sets id+version without loading the model
        return {"embed_model": f"{e.model}:{e.version}"}

    def run(self, ctx: StageContext, force: bool) -> RunResult:
        emb = self._emb()
        ids, texts = _read_chunks(ctx.cfg.index_db)
        vectors: list[list[float]] = []
        for batch in ep.batched(texts, self._batch):
            vectors.extend(emb.embed(batch))
        dim = ep.uniform_dim(vectors) if vectors else 0
        _build_vectors_db(ctx.cfg.vectors_db, emb, dim, ids, vectors)
        # counts are ints (§7.2); the model id+version are persisted in vectors.db:embedding_model
        return RunResult(counts={"chunks": len(ids), "dim": dim})


def _read_chunks(index_db) -> tuple[list[str], list[str]]:  # type: ignore[no-untyped-def]
    """`(chunk_ids, texts)` for every chunk, ordered by id (deterministic build)."""
    conn = db.connect(index_db, read_only=True)
    try:
        rows = conn.execute("SELECT chunk_id, text FROM chunks ORDER BY chunk_id").fetchall()
    finally:
        conn.close()
    return [r[0] for r in rows], [r[1] for r in rows]


def _build_vectors_db(vectors_db, emb: Embedder, dim: int, ids, vectors) -> None:  # type: ignore[no-untyped-def]
    """Build `vectors.db` atomically (temp + ``os.replace``): the `embedding_model` meta row + a
    sqlite-vec ``vec0`` ANN table keyed by `chunk_id`. dim 0 (empty corpus) ⇒ meta only, no vec."""
    vectors_db.parent.mkdir(parents=True, exist_ok=True)
    tmp = vectors_db.parent / f".{vectors_db.name}.tmp"
    for p in (tmp, tmp.with_name(tmp.name + "-wal"), tmp.with_name(tmp.name + "-shm")):
        p.unlink(missing_ok=True)
    conn = sqlite3.connect(tmp)
    try:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        conn.execute("CREATE TABLE embedding_model (model TEXT, version TEXT, dim INTEGER)")
        conn.execute("INSERT INTO embedding_model VALUES (?, ?, ?)", (emb.model, emb.version, dim))
        if dim > 0:
            conn.execute(
                f"CREATE VIRTUAL TABLE vec_chunks USING vec0("
                f"chunk_id TEXT PRIMARY KEY, embedding float[{dim}])"
            )
            conn.executemany(
                "INSERT INTO vec_chunks(chunk_id, embedding) VALUES (?, ?)",
                [(cid, sqlite_vec.serialize_float32(list(v))) for cid, v in zip(ids, vectors)],
            )
        conn.commit()
    finally:
        conn.close()
    os.replace(tmp, vectors_db)
