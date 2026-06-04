"""The `manifest` stage — consolidated + index.db → corpus-manifest.json + discovery.json (§14.4).

The agent front door: corpus counts, the stable-ID scheme, and the MCP capability manifest,
assembled from the derived stores. Per D3, **`vectors.db` is an optional input** (produced by
`embed` in Phase 6): built now against `consolidated` + `index.db` alone it omits the embedding
model id+version and marks semantic search **unavailable**; a Phase-6 re-run once `vectors.db`
exists fills the fields and flips the capability on (the "optional produces don't gate" rule, as
`convert`'s `assets`).
"""

from __future__ import annotations

import json

import structlog

from vdocs.contracts.registry import (
    CONSOLIDATED,
    CORPUS_MANIFEST,
    DISCOVERY_JSON,
    INDEX_DOCUMENTS,
    INDEX_ENTITIES,
    RELATIONS,
)
from vdocs.kernel import cas, db
from vdocs.models.stage import Idempotency, RunResult
from vdocs.orchestrator.stage import Stage, StageContext
from vdocs.stages.manifest import manifest_pure as mp

log = structlog.get_logger(__name__)


class ManifestStage(Stage):
    name = "manifest"
    description = "assemble corpus-manifest.json + discovery.json (the MCP front door)"
    requires = [CONSOLIDATED, INDEX_DOCUMENTS, INDEX_ENTITIES, RELATIONS]
    produces = [CORPUS_MANIFEST, DISCOVERY_JSON]
    idempotency = Idempotency.SKIP_IF_UNCHANGED

    def run(self, ctx: StageContext, force: bool) -> RunResult:
        cfg = ctx.cfg
        counts = _gather_counts(cfg.index_db)
        # D3: vectors.db is optional (Phase 6). Absent ⇒ no embedding info ⇒ semantic unavailable.
        embedding = _read_embedding(cfg.vectors_db)
        generated_at = ctx.clock()

        manifest = mp.corpus_manifest(
            counts, tool_ver=cfg.tool_ver, generated_at=generated_at, embedding=embedding
        )
        discovery = mp.discovery_descriptor(counts, tool_ver=cfg.tool_ver, embedding=embedding)
        cas.atomic_write(cfg.corpus_manifest, _dumps(manifest))
        cas.atomic_write(cfg.discovery_json, _dumps(discovery))
        return RunResult(
            counts={
                "documents": counts["documents"],
                "version_groups": counts["version_groups"],
                "entities": counts["entities"],
                "relations": counts["relations"],
                "semantic_available": int(embedding is not None),
            }
        )


def _dumps(obj) -> bytes:  # type: ignore[no-untyped-def]
    """Deterministic JSON bytes (sorted keys) so a no-op re-run is byte-identical (content-skip)."""
    return (json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _gather_counts(index_db):  # type: ignore[no-untyped-def]
    """Corpus counts off the derived index — documents/sections/entities/relations + breakdowns."""
    conn = db.connect(index_db, read_only=True)
    try:
        one = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
        return {
            "documents": one("SELECT count(*) FROM documents"),
            "documents_latest": one("SELECT count(*) FROM documents WHERE is_latest=1"),
            # each version group has exactly one is_latest anchor → latest count == group count
            "version_groups": one("SELECT count(*) FROM documents WHERE is_latest=1"),
            "sections": one("SELECT count(*) FROM doc_sections"),
            # the search surface is the chunks table (containers + hollow excluded, oversized split)
            "sections_searchable": one("SELECT count(*) FROM chunks"),
            "entities": one("SELECT count(*) FROM entities"),
            "entities_by_type": dict(
                conn.execute("SELECT type, count(*) FROM entities GROUP BY type").fetchall()
            ),
            "relations": one("SELECT count(*) FROM relations"),
            "relations_by_type": dict(
                conn.execute("SELECT rel, count(*) FROM relations GROUP BY rel").fetchall()
            ),
        }
    finally:
        conn.close()


def _read_embedding(vectors_db):  # type: ignore[no-untyped-def]
    """The embedding-model id+version from `vectors.db`, or ``None`` when it doesn't exist yet (D3 —
    `embed` is Phase 6). Phase 4 always returns ``None`` (semantic search unavailable)."""
    if not vectors_db.exists():
        return None
    conn = db.connect(vectors_db, read_only=True)
    try:
        row = conn.execute("SELECT model, version, dim FROM embedding_model LIMIT 1").fetchone()
    except Exception:  # noqa: BLE001 — a vectors.db without the meta table ⇒ treat as unavailable
        return None
    finally:
        conn.close()
    return {"model": row[0], "version": row[1], "dim": row[2]} if row else None
