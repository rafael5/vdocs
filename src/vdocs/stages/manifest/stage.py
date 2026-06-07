"""The `manifest` stage — consolidated + index.db → corpus-manifest.json + discovery.json (§14.4).

The agent front door: corpus counts, the stable-ID scheme, and the MCP capability manifest,
assembled from the derived stores. Per D3, **`vectors.db` is an optional input** (produced by
`embed` in Phase 6): built now against `consolidated` + `index.db` alone it omits the embedding
model id+version and marks semantic search **unavailable**; a Phase-6 re-run once `vectors.db`
exists fills the fields and flips the capability on (the "optional produces don't gate" rule, as
`convert`'s `assets`).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import structlog

from vdocs.contracts.registry import (
    AI_MANIFEST,
    CONSOLIDATED,
    CORPUS_CARD,
    CORPUS_MANIFEST,
    DISCOVERY_JSON,
    INDEX_DOCUMENTS,
    INDEX_ENTITIES,
    REGISTRIES,
    RELATIONS,
)
from vdocs.kernel import cas, db
from vdocs.kernel import registry as kregistry
from vdocs.models.stage import Idempotency, RunResult
from vdocs.orchestrator.stage import Stage, StageContext
from vdocs.stages.manifest import manifest_pure as mp

log = structlog.get_logger(__name__)


class ManifestStage(Stage):
    name = "manifest"
    description = "assemble corpus-manifest.json + discovery.json + the AI corpus card"
    requires = [CONSOLIDATED, INDEX_DOCUMENTS, INDEX_ENTITIES, RELATIONS, REGISTRIES]
    produces = [CORPUS_MANIFEST, DISCOVERY_JSON, AI_MANIFEST, CORPUS_CARD]
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

        # The AI corpus card (§14.7): the always-fresh catalog + entity index + query recipe an
        # agent reads to answer "based on the vdocs gold corpus, …" without re-discovering it.
        catalog = mp.build_catalog(_gather_catalog(cfg.index_db))
        entity_index = mp.build_entity_index(_gather_entity_rows(cfg.index_db))
        card = mp.ai_manifest(
            counts,
            catalog,
            entity_index,
            tool_ver=cfg.tool_ver,
            generated_at=generated_at,
            index_fingerprint=_index_fingerprint(cfg.index_db),
            embedding=embedding,
        )
        cas.atomic_write(cfg.ai_manifest, _dumps(card))
        cas.atomic_write(cfg.corpus_card, (mp.corpus_card(card)).encode("utf-8"))

        # B1 (§9.6/§9.7): materialise the curated boilerplate canonical copies so `normalize`'s
        # `_shared/boilerplate/<id>.md` REFERENCE links resolve (single-sourced, de-duplicated).
        shared = mp.shared_boilerplate_files(_load_boilerplate_entries(cfg))
        bp_dir = cfg.gold_shared / "boilerplate"
        for name, text in shared.items():
            cas.atomic_write(bp_dir / name, text.encode("utf-8"))

        return RunResult(
            counts={
                "documents": counts["documents"],
                "version_groups": counts["version_groups"],
                "entities": counts["entities"],
                "relations": counts["relations"],
                "catalog_docs": len(catalog),
                "shared_boilerplate": len(shared),
                "semantic_available": int(embedding is not None),
            }
        )


def _load_boilerplate_entries(cfg) -> list:  # type: ignore[no-untyped-def]
    """The curated boilerplate registry rows (empty if absent) — source of the canonical copies."""
    data = kregistry.load_mapping(
        cfg.registries / "boilerplate" / "boilerplate.yaml", missing_ok=True
    )
    return data.get("boilerplate") or []


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


def _gather_catalog(index_db):  # type: ignore[no-untyped-def]
    """The `is_latest` anchor documents (catalog rows for the AI card), ordered for stable order."""
    conn = db.connect(index_db, read_only=True)
    try:
        rows = conn.execute(
            "SELECT doc_key, doc_id, title, app_code, doc_type, pkg_ns, patch_id, version, "
            "section_count, word_count FROM documents WHERE is_latest=1 "
            "ORDER BY app_code, title, doc_key"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _gather_entity_rows(index_db):  # type: ignore[no-untyped-def]
    """Every entity (type, canonical name, mention count) — grouped/trimmed by the pure builder."""
    conn = db.connect(index_db, read_only=True)
    try:
        rows = conn.execute("SELECT type, canonical_name, mention_count FROM entities").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _index_fingerprint(index_db: Path) -> str:
    """A content fingerprint of `index.db` (streamed sha256) — the staleness stamp the AI card
    records so a consumer can tell whether the card still matches the live index."""
    h = hashlib.sha256()
    with index_db.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


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
