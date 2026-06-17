"""merge integration — SKL (knowledge.db) folded into index.db (SKL S3.3). Seeds a tiny index.db
(entities + chunks) and a knowledge.db slice (file #200 = NEW PERSON), runs MergeStage through the
orchestrator, and asserts the entity-keying: the colon↔slash reconciliation, the synonym catalog,
and chunk tags by distinctive surface — a chunk *about* file #200 is reachable via the entity by
`NEW PERSON` / `^VA(200,` even when it never spells the number. Index's own tables are untouched and
a re-run is idempotent; a common-word surface never over-tags.
"""

from __future__ import annotations

from vdocs.contracts.registry import INDEX_CHUNKS, INDEX_ENTITIES, KNOWLEDGE_ENTITIES
from vdocs.kernel import db, knowledge_db
from vdocs.models.knowledge import EntityNode, Provenance
from vdocs.models.stage import Decision, StageRun
from vdocs.orchestrator.engine import Orchestrator
from vdocs.stages.merge.stage import MergeStage

# file #200 (NEW PERSON) + file #1 ("FILE", a common-word name that must NOT over-tag).
_ENTITIES = [
    EntityNode(
        type="fileman_file",
        canonical="200",
        canonical_name="NEW PERSON",
        synonyms=["NEW PERSON", "^VA(200,", "NEW PERSON file", "the 200 file"],
        provenance=[Provenance(source_sha256="x", doc="DI/fm")],
    ),
    EntityNode(
        type="fileman_file",
        canonical="1",
        canonical_name="FILE",
        synonyms=["FILE", "^DIC("],
        provenance=[Provenance(source_sha256="x", doc="DI/fm")],
    ),
]


def _seed(ctx):
    """A minimal index.db (entities + chunks) + a knowledge.db slice, with recorded index/resolve
    runs so merge's preflight trusts its inputs."""
    conn = db.connect(ctx.cfg.index_db)
    conn.executescript(
        """
        CREATE TABLE entities (entity_id TEXT PRIMARY KEY, type TEXT, canonical_name TEXT);
        CREATE TABLE chunks (chunk_id TEXT PRIMARY KEY, section_id TEXT, doc_key TEXT,
                             part INTEGER, text TEXT);
        """
    )
    # index recognized file #200 and file #1 (both present so both can reconcile)
    conn.executemany(
        "INSERT INTO entities VALUES (?, ?, ?)",
        [("fileman_file:200", "fileman_file", "200"), ("fileman_file:1", "fileman_file", "1")],
    )
    conn.executemany(
        "INSERT INTO chunks VALUES (?, ?, ?, ?, ?)",
        [
            ("c-np", "DI/fm/s1", "DI/fm", 0, "the NEW PERSON file stores users; global ^VA(200,0)"),
            ("c-file", "DI/fm/s2", "DI/fm", 0, "open the FILE and edit it"),  # common word → no tag
            ("c-none", "DI/fm/s3", "DI/fm", 0, "unrelated prose with no entity surfaces"),
        ],
    )
    conn.commit()
    conn.close()

    ctx.cfg.knowledge_db.parent.mkdir(parents=True, exist_ok=True)
    knowledge_db.write_atomic(ctx.cfg.knowledge_db, entities=_ENTITIES, terms=[], relationships=[])

    ctx.state.record(
        StageRun(
            stage="index",
            scope="",
            status="ok",
            started_at="t",
            finished_at="t",
            inputs_fp={},
            outputs_fp={a.key: a.fingerprint(ctx.cfg) for a in (INDEX_ENTITIES, INDEX_CHUNKS)},
            counts={},
            contract_ver=12,
            tool_ver=ctx.cfg.tool_ver,
        )  # fmt: skip
    )
    ctx.state.record(
        StageRun(
            stage="resolve",
            scope="",
            status="ok",
            started_at="t",
            finished_at="t",
            inputs_fp={},
            outputs_fp={KNOWLEDGE_ENTITIES.key: KNOWLEDGE_ENTITIES.fingerprint(ctx.cfg)},
            counts={},
            contract_ver=1,
            tool_ver=ctx.cfg.tool_ver,
        )  # fmt: skip
    )


def test_merge_reconciles_ids_and_keys_chunks_by_entity(ctx):
    _seed(ctx)
    (result,) = Orchestrator([MergeStage()]).run(ctx)
    assert result.status == "ok"

    conn = db.connect(ctx.cfg.index_db, read_only=True)
    try:
        # reconciliation: index colon-id ↔ SKL slash node_id, on (type, canonical)
        skl = dict(conn.execute("SELECT entity_id, node_id FROM entity_skl").fetchall())
        assert skl["fileman_file:200"] == "fileman_file/200"
        assert skl["fileman_file:1"] == "fileman_file/1"

        # synonym catalog carries every surface
        surfaces = {s for (s,) in conn.execute(
            "SELECT surface FROM entity_synonyms WHERE node_id='fileman_file/200'"
        )}  # fmt: skip
        assert {"NEW PERSON", "^VA(200,", "the 200 file"} <= surfaces

        # chunk tags: the NEW PERSON chunk is reachable via the entity (by name AND by global),
        # though it never spells "200"; the common-word "FILE" chunk is NOT tagged to file/1.
        tagged = {c for (c,) in conn.execute(
            "SELECT chunk_id FROM chunk_entities WHERE node_id='fileman_file/200'"
        )}  # fmt: skip
        assert "c-np" in tagged
        all_tagged = {c for (c,) in conn.execute("SELECT chunk_id FROM chunk_entities")}
        assert "c-file" not in all_tagged  # common-word "FILE" never tags file/1
        assert "c-none" not in all_tagged

        # index's own tables untouched (additive, D-S3.3b)
        assert conn.execute("SELECT count(*) FROM entities").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM chunks").fetchone()[0] == 3
    finally:
        conn.close()


def test_merge_is_idempotent(ctx):
    _seed(ctx)
    orch = Orchestrator([MergeStage()])
    orch.run(ctx)
    assert MergeStage().preflight(ctx, force=False).decision is Decision.SKIP
    conn = db.connect(ctx.cfg.index_db, read_only=True)
    before = sorted(tuple(r) for r in conn.execute("SELECT * FROM chunk_entities"))
    conn.close()
    orch.run(ctx, force=True)
    conn = db.connect(ctx.cfg.index_db, read_only=True)
    after = sorted(tuple(r) for r in conn.execute("SELECT * FROM chunk_entities"))
    conn.close()
    assert before == after
