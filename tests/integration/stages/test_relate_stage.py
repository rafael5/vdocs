"""relate integration — index.db entities/mentions → index.db:relations (§8). Seeds a small
index.db (documents, entities, entity_mentions), runs RelateStage through the orchestrator, and
asserts the expected doc↔entity / entity↔entity / doc↔doc edges; a re-run is idempotent and the
relations table never disturbs index's own tables.
"""

from __future__ import annotations

from vdocs.contracts.registry import INDEX_DOCUMENTS, INDEX_ENTITIES, INDEX_SECTIONS
from vdocs.kernel import db
from vdocs.models.stage import Decision, StageRun
from vdocs.orchestrator.engine import Orchestrator
from vdocs.stages.relate.stage import RelateStage


def _seed_index(ctx):
    """A minimal index.db: two docs sharing a build entity (significant) + a global (ubiquitous)."""
    conn = db.connect(ctx.cfg.index_db)
    conn.executescript(
        """
        CREATE TABLE documents (doc_key TEXT PRIMARY KEY, is_latest INTEGER);
        CREATE TABLE doc_sections (section_id TEXT PRIMARY KEY, doc_key TEXT);
        CREATE TABLE entities (entity_id TEXT PRIMARY KEY, type TEXT, canonical_name TEXT);
        CREATE TABLE entity_mentions (entity_id TEXT, doc_key TEXT, section_id TEXT);
        """
    )
    conn.executemany("INSERT INTO documents VALUES (?, 1)", [("d1",), ("d2",)])
    conn.executemany(
        "INSERT INTO entities VALUES (?, ?, ?)",
        [("build:X", "build", "X"), ("global:G", "global", "G")],
    )
    conn.executemany(
        "INSERT INTO entity_mentions VALUES (?, ?, ?)",
        [
            ("build:X", "d1", "d1/s1"),
            ("global:G", "d1", "d1/s1"),  # build:X + global:G co-occur in d1/s1
            ("build:X", "d1", "d1/s2"),  # build:X mentioned twice in d1
            ("build:X", "d2", "d2/s1"),  # build:X shared by d1 + d2 → xref
            ("global:G", "d2", "d2/s2"),
        ],
    )
    conn.commit()
    conn.close()
    # one index StageRun carrying all three produced tables (separate records would overwrite)
    ctx.state.record(
        StageRun(
            stage="index",
            scope="",
            status="ok",
            started_at="t",
            finished_at="t",
            inputs_fp={},
            outputs_fp={
                a.key: a.fingerprint(ctx.cfg)
                for a in (INDEX_DOCUMENTS, INDEX_ENTITIES, INDEX_SECTIONS)
            },
            counts={},
            contract_ver=1,
            tool_ver=ctx.cfg.tool_ver,
        )  # fmt: skip
    )


def test_relate_builds_the_expected_edges(ctx):
    _seed_index(ctx)
    (result,) = Orchestrator([RelateStage()]).run(ctx)
    assert result.status == "ok"

    conn = db.connect(ctx.cfg.index_db, read_only=True)
    try:
        edges = {tuple(r) for r in conn.execute("SELECT * FROM relations")}
        # doc → entity (mentions), build:X weight 2 in d1
        assert ("doc", "d1", "mentions", "entity", "build:X", 2) in edges
        assert ("doc", "d2", "mentions", "entity", "build:X", 1) in edges
        # entity ↔ entity co-occurrence within d1/s1
        assert ("entity", "build:X", "cooccurs", "entity", "global:G", 1) in edges
        # doc ↔ doc xref via the shared *build* entity (global is excluded as ubiquitous)
        assert ("doc", "d1", "xref", "doc", "d2", 1) in edges
        assert not any(e[2] == "xref" and "global" in e[4] for e in edges)
        # index's own tables are untouched by the append
        assert conn.execute("SELECT count(*) FROM documents").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM entities").fetchone()[0] == 2
    finally:
        conn.close()


def test_relate_counts_by_relation_type(ctx):
    _seed_index(ctx)
    (result,) = Orchestrator([RelateStage()]).run(ctx)
    # 4 distinct doc↔entity pairs: (d1,build:X), (d1,global:G), (d2,build:X), (d2,global:G)
    assert result.counts["mentions"] == 4
    assert result.counts["cooccurs"] == 1
    assert result.counts["xref"] == 1
    assert result.counts["relations"] == 6


def test_relate_is_idempotent(ctx):
    _seed_index(ctx)
    orch = Orchestrator([RelateStage()])
    orch.run(ctx)
    assert RelateStage().preflight(ctx, force=False).decision is Decision.SKIP
    # a forced re-run rebuilds identical edges
    conn = db.connect(ctx.cfg.index_db, read_only=True)
    before = sorted(tuple(r) for r in conn.execute("SELECT * FROM relations"))
    conn.close()
    orch.run(ctx, force=True)
    conn = db.connect(ctx.cfg.index_db, read_only=True)
    after = sorted(tuple(r) for r in conn.execute("SELECT * FROM relations"))
    conn.close()
    assert before == after
