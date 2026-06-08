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
    """An injected embedding backend: its model id+version (cheap, for the fingerprint), the model's
    ``max_tokens`` context budget (the A1 no-truncation gate, §9a), and a batch ``embed`` callable
    text→vectors (the heavy part, loaded lazily by the real default)."""

    model: str
    version: str
    embed: Callable[[list[str]], list[list[float]]]
    max_tokens: int = 8192


def _default_embedder() -> Embedder:
    """The real backend: fastembed's ``nomic-ai/nomic-embed-text-v1.5`` (768-dim, **8192-token**
    context — C1).

    A1 chose **bge-m3** for its 8k context, but fastembed's dense ``TextEmbedding`` API does not
    serve bge-m3 (only via sentence-transformers/FlagEmbedding). nomic-embed-text-v1.5 is the
    fastembed-native long-context (8k) embedder — same no-truncation property (the largest golden
    chunk ~5.7k tokens « 8192), keeping the planned `uv add fastembed` toolchain. It requires a
    **task prefix** on every input: the corpus side here uses ``search_document:`` (the query side
    uses ``search_query:``, C2). The id+version+budget are static (cheap fingerprint); the model
    loads lazily on first ``embed`` — a runtime dep, not a `make check` dependency."""
    state: dict = {}

    def embed(texts: list[str]) -> list[list[float]]:  # pragma: no cover - real backend
        model = state.get("model")
        if model is None:
            from fastembed import TextEmbedding

            model = state["model"] = TextEmbedding("nomic-ai/nomic-embed-text-v1.5")
        prefixed = [f"search_document: {t}" for t in texts]
        return [[float(x) for x in v] for v in model.embed(prefixed)]

    return Embedder("nomic-ai/nomic-embed-text-v1.5", "1.5", embed, max_tokens=8192)


class EmbedStage(Stage):
    name = "embed"
    description = "embed searchable chunks → vectors.db (sqlite-vec ANN) for semantic search"
    requires = [INDEX_CHUNKS]
    produces = [VECTORS_DB]
    idempotency = Idempotency.SKIP_IF_UNCHANGED

    def __init__(
        self,
        embedder: Embedder | None = None,
        *,
        max_batch_tokens: int = 8192,
        max_batch_items: int = 64,
    ) -> None:
        self._embedder = embedder  # None → the real fastembed default (lazy)
        # Bound each embed batch by its *padded* footprint (items × longest member), not a fixed
        # count — a fixed 256-item batch OOMs on long 8k-context chunks (see token_batched / the C1
        # OOM fix). 8192 padded tokens keeps peak activation memory to ~1 GB for the corpus (max
        # chunk ~2.5k tokens) and ~3 GB for a lone worst-case 8k chunk.
        self._max_batch_tokens = max_batch_tokens
        self._max_batch_items = max_batch_items

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
        # A2a: embed the *contextual* text (body + `«doc_title › section_path»` header), not the
        # bare body — the stored/cited chunk and the FTS row stay clean.
        ids, texts = _read_chunks(ctx.cfg.index_db)
        # A1 gate (§9a): refuse to build a vectors.db with silently-truncated chunks. Cheap
        # conservative estimate — runs before the model loads, so a sizing mismatch fails fast.
        ep.assert_within_budget(ids, texts, max_tokens=emb.max_tokens)
        # Stream batch-by-batch into vectors.db (no list of every vector held at once): the embedder
        # is fed token-budgeted batches and each batch's vectors are written as it returns.
        batches = (
            emb.embed(batch)
            for batch in ep.token_batched(
                texts, max_padded_tokens=self._max_batch_tokens, max_items=self._max_batch_items
            )
        )
        dim = _build_vectors_db(ctx.cfg.vectors_db, emb, ids, batches)
        # counts are ints (§7.2); the model id+version are persisted in vectors.db:embedding_model
        return RunResult(counts={"chunks": len(ids), "dim": dim})


def _read_chunks(index_db) -> tuple[list[str], list[str]]:  # type: ignore[no-untyped-def]
    """`(chunk_ids, embed_texts)` for every chunk, ordered by id (deterministic build).

    The text is the **contextual** embed text (A2a, §9b): the chunk body prefixed with a
    `«doc_title › section_path»` breadcrumb resolved by joining `doc_sections`/`documents`. The
    chunk body in `chunks.text` and the FTS row stay clean — only what the embedder sees is
    decorated.

    A3 (§8.3): **`stub` sections are excluded** — a pointer-only chunk ("[see boilerplate]") embeds
    to nothing useful, so it stays lexically findable in FTS but never enters the semantic surface.
    `vectors.db` therefore holds fewer chunks than `index.db:chunks` by the stub count."""
    conn = db.connect(index_db, read_only=True)
    try:
        rows = conn.execute(
            "SELECT c.chunk_id, d.title, s.section_path, c.text "
            "FROM chunks c "
            "JOIN doc_sections s ON s.section_id = c.section_id "
            "JOIN documents d ON d.doc_key = c.doc_key "
            "WHERE s.kind != 'stub' "
            "ORDER BY c.chunk_id"
        ).fetchall()
    finally:
        conn.close()
    ids = [r[0] for r in rows]
    texts = [ep.contextual_embed_text(r[1] or "", r[2] or "", r[3]) for r in rows]
    return ids, texts


def _build_vectors_db(vectors_db, emb: Embedder, ids, vector_batches) -> int:  # type: ignore[no-untyped-def]
    """Build `vectors.db` atomically (temp + ``os.replace``): the `embedding_model` meta row + a
    sqlite-vec ``vec0`` ANN table keyed by `chunk_id`. Returns the embedding ``dim``.

    Streams ``vector_batches`` (an iterable of per-batch vector lists, in `ids` order) into the
    table as they arrive — never materializing every vector at once. The ``vec0`` table needs the
    dim up front, so it is created from the first batch; the `embedding_model` row is written at the
    end with the final dim. An empty corpus (no batches) ⇒ meta only, dim 0, no vec table (semantic
    search stays off)."""
    vectors_db.parent.mkdir(parents=True, exist_ok=True)
    tmp = vectors_db.parent / f".{vectors_db.name}.tmp"
    for p in (tmp, tmp.with_name(tmp.name + "-wal"), tmp.with_name(tmp.name + "-shm")):
        p.unlink(missing_ok=True)
    conn = sqlite3.connect(tmp)
    try:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        id_iter = iter(ids)
        dim = 0
        for vectors in vector_batches:
            bdim = ep.uniform_dim(vectors)
            if dim == 0:
                dim = bdim
                conn.execute(
                    f"CREATE VIRTUAL TABLE vec_chunks USING vec0("
                    f"chunk_id TEXT PRIMARY KEY, embedding float[{dim}])"
                )
            elif bdim != dim:
                raise ValueError(f"embedder returned non-uniform dims: {sorted({dim, bdim})}")
            conn.executemany(
                "INSERT INTO vec_chunks(chunk_id, embedding) VALUES (?, ?)",
                [(next(id_iter), sqlite_vec.serialize_float32(list(v))) for v in vectors],
            )
        conn.execute("CREATE TABLE embedding_model (model TEXT, version TEXT, dim INTEGER)")
        conn.execute("INSERT INTO embedding_model VALUES (?, ?, ?)", (emb.model, emb.version, dim))
        conn.commit()
    finally:
        conn.close()
    os.replace(tmp, vectors_db)
    return dim
