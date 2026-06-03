"""The `relate` stage — index.db entities → index.db:relations (the knowledge graph, §8).

Cheap and re-runnable: it adds **no new extraction** (that is `index`'s job), only *edges* over the
entities `index` already wrote — doc↔entity (`mentions`), entity↔entity (`cooccurs`, section-
scoped), and doc↔doc (`xref`, via a shared *significant* entity). The `relations` table is appended
to `index.db` through `kernel.db.replace_table_atomic`, so `index`'s own tables in the same file are
never touched.
"""

from __future__ import annotations

import structlog

from vdocs.contracts.registry import (
    INDEX_DOCUMENTS,
    INDEX_ENTITIES,
    INDEX_SECTIONS,
    RELATIONS,
)
from vdocs.kernel import db
from vdocs.models.stage import Idempotency, RunResult
from vdocs.orchestrator.stage import Stage, StageContext
from vdocs.stages.relate import relate_pure as rp

log = structlog.get_logger(__name__)

# Which entity types are "significant" enough to link two documents by `xref`. Ubiquitous raw
# globals are excluded so the doc graph stays meaningful and bounded; build ids / FileMan files /
# package namespaces are document-distinguishing.
XREF_TYPES = frozenset({"build", "fileman_file", "package_namespace"})

_RELATIONS_DDL = """
CREATE TABLE {new} (
  src_type TEXT NOT NULL, src_id TEXT NOT NULL,
  rel TEXT NOT NULL,
  dst_type TEXT NOT NULL, dst_id TEXT NOT NULL,
  weight INTEGER NOT NULL,
  PRIMARY KEY (src_type, src_id, rel, dst_type, dst_id)
)
"""


class RelateStage(Stage):
    name = "relate"
    description = (
        "materialize the knowledge graph (doc↔entity, entity↔entity, doc↔doc) into relations"
    )
    requires = [INDEX_DOCUMENTS, INDEX_ENTITIES, INDEX_SECTIONS]
    produces = [RELATIONS]
    idempotency = Idempotency.SKIP_IF_UNCHANGED

    def run(self, ctx: StageContext, force: bool) -> RunResult:
        mentions = _read_mentions(ctx.cfg.index_db)
        edges = rp.derive_edges(mentions, xref_types=XREF_TYPES)

        def build_new(conn, new):  # type: ignore[no-untyped-def]
            conn.execute(_RELATIONS_DDL.format(new=new))
            conn.executemany(
                f"INSERT INTO {new} "
                "(src_type, src_id, rel, dst_type, dst_id, weight) VALUES (?, ?, ?, ?, ?, ?)",
                edges,
            )

        db.replace_table_atomic(ctx.cfg.index_db, "relations", build_new)
        by_rel: dict[str, int] = {}
        for e in edges:
            by_rel[e[2]] = by_rel.get(e[2], 0) + 1
        return RunResult(
            counts={
                "relations": len(edges),
                "mentions": by_rel.get("mentions", 0),
                "cooccurs": by_rel.get("cooccurs", 0),
                "xref": by_rel.get("xref", 0),
            }
        )


def _read_mentions(index_db):  # type: ignore[no-untyped-def]
    """Each `entity_mentions` row joined to its entity's type — the input to edge derivation."""
    conn = db.connect(index_db, read_only=True)
    try:
        rows = conn.execute(
            "SELECT em.doc_key, em.section_id, em.entity_id, e.type "
            "FROM entity_mentions em JOIN entities e ON e.entity_id = em.entity_id"
        ).fetchall()
    finally:
        conn.close()
    return [
        rp.Mention(doc_key=r[0], section_id=r[1], entity_id=r[2], entity_type=r[3]) for r in rows
    ]
