"""The `merge` stage — fold the SKL (`knowledge.db`) into the shipped `index.db` (SKL S3.3).

`merge` is the post-`resolve` join (D-S3.3a): a thin stage that runs after both `index` and
`resolve` and augments `index.db` from the SKL **additively** (D-S3.3b). Like `relate`, it adds no
new extraction — only *derived* tables over what the two stages already produced:

* **entity_skl** — reconcile the two id schemes (index `fileman_file:200` ↔ SKL `fileman_file/200`)
  on `(type, canonical)`, carrying the SKL identity onto the index side.
* **entity_synonyms** — the SKL surface catalog (canonical name + synonyms) per entity.
* **chunk_entities** — chunk → entity tags (entity-keyed retrieval; distinctive surfaces only).

The tables are the EMPTY shells `index` owns (so the read-schema version is consistent before
`merge` runs); `merge` populates each via `kernel.db.replace_table_atomic`, so `index`'s own tables
in the same file are never touched (the same pattern `relate` uses for `relations`). Where the SKL
has no coverage (no `knowledge.db`, or a non-DI chunk), the tables stay empty / get no rows —
non-SKL coverage is unchanged (friction #3).
"""

from __future__ import annotations

import sqlite3

import structlog

from vdocs.contracts.registry import (
    INDEX_CHUNKS,
    INDEX_ENTITIES,
    KNOWLEDGE_ENTITIES,
    MERGE_CHUNK_ENTITIES,
    MERGE_ENTITY_SKL,
    MERGE_ENTITY_SYNONYMS,
)
from vdocs.kernel import db, knowledge_db
from vdocs.models.stage import Idempotency, RunResult
from vdocs.orchestrator.stage import Stage, StageContext
from vdocs.stages.merge import merge_pure as mp

log = structlog.get_logger(__name__)

# The `{new}` table DDL for replace_table_atomic — MUST match the empty shells `index` creates
# (`stages/index/stage.py` _SCHEMA, read contract v1.5). Kept in lockstep with those shells; the
# read-contract doctor check validates the consumer-facing view columns against the spec.
_ENTITY_SKL_DDL = (
    "CREATE TABLE {new} (entity_id TEXT PRIMARY KEY, node_id TEXT NOT NULL, "
    "type TEXT, canonical TEXT, canonical_name TEXT)"
)
_SYNONYMS_DDL = (
    "CREATE TABLE {new} (node_id TEXT NOT NULL, surface TEXT NOT NULL, kind TEXT NOT NULL, "
    "PRIMARY KEY (node_id, surface))"
)
_CHUNK_ENTITIES_DDL = (
    "CREATE TABLE {new} (chunk_id TEXT NOT NULL, node_id TEXT NOT NULL, "
    "PRIMARY KEY (chunk_id, node_id))"
)


class MergeStage(Stage):
    name = "merge"
    description = "fold the SKL into index.db: reconcile entity ids, synonym catalog, chunk tags"
    requires = [INDEX_ENTITIES, INDEX_CHUNKS, KNOWLEDGE_ENTITIES]
    produces = [MERGE_ENTITY_SKL, MERGE_ENTITY_SYNONYMS, MERGE_CHUNK_ENTITIES]
    idempotency = Idempotency.SKIP_IF_UNCHANGED
    contract_ver = 1  # bump when the merge table shapes change (re-runs search/manifest consumers)

    def run(self, ctx: StageContext, force: bool) -> RunResult:
        cfg = ctx.cfg
        entities = [
            mp.SklEntity(
                node_id=e.node_id,
                type=e.type,
                canonical=e.canonical,
                canonical_name=e.canonical_name,
                synonyms=tuple(e.synonyms),
            )
            for e in knowledge_db.read_entities(cfg.knowledge_db)
        ]
        index_entity_ids = _read_entity_ids(cfg.index_db)
        chunks = _read_chunks(cfg.index_db)

        skl_rows = mp.reconcile(entities, index_entity_ids)
        syn_rows = mp.synonym_rows(entities)
        tags = mp.tag_chunks(chunks, entities)

        _replace(cfg.index_db, "entity_skl", _ENTITY_SKL_DDL,
                 "entity_id, node_id, type, canonical, canonical_name", skl_rows)  # fmt: skip
        _replace(cfg.index_db, "entity_synonyms", _SYNONYMS_DDL, "node_id, surface, kind", syn_rows)
        _replace(cfg.index_db, "chunk_entities", _CHUNK_ENTITIES_DDL, "chunk_id, node_id", tags)

        return RunResult(
            counts={
                "entities_reconciled": len(skl_rows),
                "synonyms": len(syn_rows),
                "chunk_tags": len(tags),
                "skl_entities": len(entities),
            }
        )


def _read_entity_ids(index_db) -> set[str]:  # type: ignore[no-untyped-def]
    """The colon-style ids `index` already wrote — the set the SKL reconciles against."""
    conn = db.connect(index_db, read_only=True)
    try:
        return {r[0] for r in conn.execute("SELECT entity_id FROM entities").fetchall()}
    finally:
        conn.close()


def _read_chunks(index_db) -> list[tuple[str, str]]:  # type: ignore[no-untyped-def]
    """Every `(chunk_id, text)` — the corpus surface scanned for distinctive entity surfaces."""
    conn = db.connect(index_db, read_only=True)
    try:
        return [(r[0], r[1]) for r in conn.execute("SELECT chunk_id, text FROM chunks").fetchall()]
    finally:
        conn.close()


def _replace(index_db, table, ddl, cols, rows):  # type: ignore[no-untyped-def]
    """Populate one merge-owned table via the single-table atomic swap (index tables untouched)."""

    def build_new(conn: sqlite3.Connection, new: str) -> None:
        conn.execute(ddl.format(new=new))
        ph = ", ".join("?" for _ in cols.split(", "))
        conn.executemany(f"INSERT INTO {new} ({cols}) VALUES ({ph})", rows)

    db.replace_table_atomic(index_db, table, build_new)
