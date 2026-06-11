"""index integration — normalized bundles (+ consolidated grouping + staged meta) → index.db
(§5.5/§14.6). Seeds two normalized bundles that are a version group (one is_latest), the
`doc_meta_staged` rows `enrich` writes, and the `consolidated` history flagging the anchor; runs
IndexStage through the orchestrator and asserts documents/doc_sections row counts, `is_latest`
flagging, FTS5 returning only is_latest sections, entities keyed by `(type, canonical)`, stable ids
matching `refs.yaml`, and that the consumed `doc_meta_staged` survives the rebuild.
"""

from __future__ import annotations

import yaml

from vdocs.contracts.registry import CONSOLIDATED, DOC_META_STAGED, TEXT_NORMALIZED
from vdocs.kernel import cas, db, frontmatter
from vdocs.models.stage import StageRun
from vdocs.orchestrator.engine import Orchestrator
from vdocs.stages.enrich.enrich_pure import STAGED_COLUMNS
from vdocs.stages.enrich.stage import _write_staged
from vdocs.stages.index.stage import IndexStage

# two patches of one logical doc (CPRS:OR:IG); the v566 patch is the anchor (is_latest)
_OLD = ("CPRS", "or_3_190_ig", "OR*3*190", "# IG\n\n## Setup\n\nOld setup. Set ^DPT here.\n")
_NEW = (
    "CPRS",
    "or_3_566_ig",
    "OR*3.0*566",
    "# IG\n\n## Setup\n\nNew setup; install OR*3.0*566 and set ^DPT in file #2.\n\n"
    "## Usage\n\nUse the DG package.\n",
)


def _bless(ctx, stage, art):
    ctx.state.record(
        StageRun(
            stage=stage,
            scope="",
            status="ok",
            started_at="t",
            finished_at="t",
            inputs_fp={},
            outputs_fp={art.key: art.fingerprint(ctx.cfg)},
            counts={},
            contract_ver=1,
            tool_ver=ctx.cfg.tool_ver,
        )  # fmt: skip
    )


def _seed_bundle(ctx, app, slug, patch_id, body, title="Install Guide"):
    doc_id = f"{app}:{slug}"
    text = frontmatter.emit(
        {
            "title": title,
            "doc_type": "IG",
            "app_code": app,
            "pkg_ns": "OR",
            "version": "3.0",
            "patch_id": patch_id,
            # §7 profile tags baked by enrich into the body FM — index reads them off `meta`
            "app_user": "clinical",
            "doc_user": "sysadmin",
            "software_class": "I",
            "function_category": "Health Informatics",
            "published": "2015-09",
            "tool_ver": "0.1.0",
        },  # fmt: skip
        body,
    )
    cas.atomic_write(ctx.cfg.silver_normalized / app / slug / "body.md", text.encode())
    return doc_id


def _seed_staged(ctx, docs):
    """Write doc_meta_staged the way enrich does (the table index consumes + preserves)."""
    rows = [
        {c: "" for c in STAGED_COLUMNS}
        | {
            "doc_id": d,
            "app_code": d.split(":")[0],
            "doc_slug": d.split(":")[1],
            "doc_code": "IG",
            "doc_title": "Install Guide",
            "pkg_ns": "OR",
            "anchor_key": "CPRS:OR:IG",
            "group_key": "CPRS:OR:3.0",
            "word_count": 10,
            "bundle_path": f"{d.split(':')[0]}/{d.split(':')[1]}",
        }  # fmt: skip
        for d in docs
    ]
    _write_staged(ctx.cfg.index_db, rows)


def _seed_consolidated(ctx, latest_doc_id, all_doc_ids):
    hist = {
        "anchor_key": "CPRS:OR:IG",
        "member_count": len(all_doc_ids),
        "members": [
            {"doc_id": d, "doc_slug": d.split(":")[1], "is_latest": d == latest_doc_id}
            for d in all_doc_ids
        ],
    }
    cas.atomic_write(
        ctx.cfg.gold_consolidated / "CPRS" / "or_ig" / "history.yaml",
        yaml.safe_dump(hist, sort_keys=False).encode(),
    )


def _seed(ctx):
    old = _seed_bundle(ctx, *_OLD)
    new = _seed_bundle(ctx, *_NEW)
    _seed_staged(ctx, [old, new])
    _seed_consolidated(ctx, latest_doc_id=new, all_doc_ids=[old, new])
    for stage, art in (
        ("normalize", TEXT_NORMALIZED),
        ("consolidate", CONSOLIDATED),
        ("enrich", DOC_META_STAGED),
    ):
        _bless(ctx, stage, art)
    return old, new


def test_index_builds_documents_sections_entities(ctx):
    old, new = _seed(ctx)
    (result,) = Orchestrator([IndexStage()]).run(ctx)
    assert result.status == "ok"
    assert result.counts["documents"] == 2

    conn = db.connect(ctx.cfg.index_db, read_only=True)
    try:
        # is_latest flagging from consolidated: the v566 anchor is latest, v190 is not
        latest = dict(conn.execute("SELECT doc_id, is_latest FROM documents").fetchall())
        assert latest[new] == 1 and latest[old] == 0

        # §7 profile tags baked into the body FM land as documents columns (filterable offline)
        prof = conn.execute(
            "SELECT app_user, doc_user, software_class, function_category "
            "FROM documents WHERE doc_id = ?",
            (new,),
        ).fetchone()
        assert tuple(prof) == ("clinical", "sysadmin", "I", "Health Informatics")

        # ALL sections present (both docs), each carrying is_latest
        n_sections = conn.execute("SELECT count(*) FROM doc_sections").fetchone()[0]
        assert n_sections == 5  # old: IG + Setup; new: IG + Setup + Usage (every heading a section)

        # stable ids match refs.yaml's <doc_key>/<slug> form
        ids = {r[0] for r in conn.execute("SELECT section_id FROM doc_sections")}
        assert "CPRS/or_3_566_ig/usage" in ids and "CPRS/or_3_190_ig/setup" in ids

        # FTS5 (over chunks) is anchor-only: a term unique to the OLD body returns nothing; NEW hits
        fts_old = conn.execute(
            "SELECT count(*) FROM chunks_fts WHERE chunks_fts MATCH 'Old'"
        ).fetchone()[0]
        fts_new = conn.execute(
            "SELECT doc_key FROM chunks_fts WHERE chunks_fts MATCH 'install'"
        ).fetchall()
        assert fts_old == 0  # superseded section excluded from the search surface (§14.6)
        assert all(r[0] == "CPRS/or_3_566_ig" for r in fts_new) and fts_new
        # chunks are the retrieval units: every searchable is_latest section yields a chunk row,
        # each citing a real section_id anchor
        n_chunks = conn.execute("SELECT count(*) FROM chunks").fetchone()[0]
        assert n_chunks > 0
        orphan = conn.execute(
            "SELECT count(*) FROM chunks c "
            "WHERE c.section_id NOT IN (SELECT section_id FROM doc_sections)"
        ).fetchone()[0]
        assert orphan == 0  # every chunk resolves to an anchor section

        # entities keyed by (type, canonical), extracted from the anchor only
        ents = {(t, c) for t, c in conn.execute("SELECT type, canonical_name FROM entities")}
        assert ("build", "OR*3.0*566") in ents
        assert ("global", "^DPT") in ents
        assert ("fileman_file", "2") in ents
        assert ("package_namespace", "DG") in ents

        # the consumed doc_meta_staged survived the rebuild (self-contained, re-runnable)
        staged_n = conn.execute("SELECT count(*) FROM doc_meta_staged").fetchone()[0]
        assert staged_n == 2
    finally:
        conn.close()


def test_index_denoises_title_preserving_source_and_app_name(ctx):
    # a title heavy with version/patch noise → `title` is abbreviation-first
    # ("<product abbr> — <suffix>", version/patch stripped); raw preserved as `title_source`;
    # `app_name`/`product_*` populated. ACKQ has no product-registry entry → defaults to app_code.
    from vdocs.kernel import personas

    raw = "QUASAR Version 3 User Manual (Updated ACKQ*3*21)"
    body = "# UM\n\n## Use\n\nUse QUASAR.\n"
    _seed_bundle(ctx, "ACKQ", "quasar_um", "ACKQ*3*21", body, title=raw)
    _seed_staged(ctx, ["ACKQ:quasar_um"])
    _seed_consolidated(ctx, latest_doc_id="ACKQ:quasar_um", all_doc_ids=["ACKQ:quasar_um"])
    for stage, art in (
        ("normalize", TEXT_NORMALIZED),
        ("consolidate", CONSOLIDATED),
        ("enrich", DOC_META_STAGED),
    ):
        _bless(ctx, stage, art)
    (result,) = Orchestrator([IndexStage()]).run(ctx)
    assert result.status == "ok"

    expected_app = personas.app_names(ctx.cfg.registries).get("ACKQ", "")
    conn = db.connect(ctx.cfg.index_db, read_only=True)
    try:
        title, src, app_name, p_abbr, p_full, pub_year = conn.execute(
            "SELECT title, title_source, app_name, product_abbr, product_full, pub_year "
            "FROM documents WHERE doc_id = 'ACKQ:quasar_um'"
        ).fetchone()
    finally:
        conn.close()
    assert pub_year == "2015"  # derived from the gold FM 'published: 2015-09'
    # "Version 3" + "(Updated ACKQ*3*21)" stripped; ACKQ's product-names entry → QUASAR
    assert title == "QUASAR — User Manual"
    assert src == raw  # raw title preserved for provenance/search
    assert app_name and app_name == expected_app  # canonical app name populated
    assert p_abbr == "QUASAR" and p_full == "Quality Audiology and Speech Analysis and Reporting"


def test_chunks_fts_indexes_doc_title_so_title_only_tokens_match(ctx):
    # "Guide" appears only in the document title ("Install Guide") — never in a section title or
    # body — so it is findable iff doc_title is its own FTS column (L1.2: doc-defining-token fix).
    _seed(ctx)
    (result,) = Orchestrator([IndexStage()]).run(ctx)
    assert result.status == "ok"
    conn = db.connect(ctx.cfg.index_db, read_only=True)
    try:
        hits = conn.execute(
            "SELECT DISTINCT doc_key FROM chunks_fts WHERE chunks_fts MATCH 'Guide'"
        ).fetchall()
    finally:
        conn.close()
    assert hits and all(r[0] == "CPRS/or_3_566_ig" for r in hits)


def test_index_reads_toc_depth_from_refs_yaml(ctx):
    # a bundle's refs.yaml toc_depth drives section toc_level (not the default)
    old, new = _seed(ctx)
    cas.atomic_write(
        ctx.cfg.silver_normalized / "CPRS" / "or_3_566_ig" / "refs.yaml",
        yaml.safe_dump({"doc_id": "CPRS/or_3_566_ig", "toc_depth": [2, 2], "anchors": []}).encode(),
    )
    _bless(ctx, "normalize", TEXT_NORMALIZED)  # the tree changed → re-fingerprint
    (result,) = Orchestrator([IndexStage()]).run(ctx)
    assert result.status == "ok"
    conn = db.connect(ctx.cfg.index_db, read_only=True)
    try:
        # toc_depth (2,2) ⇒ the H1 "ig" and H2 "usage" sections: only H2 is in-TOC
        rows = dict(
            conn.execute(
                "SELECT slug, toc_level FROM doc_sections WHERE doc_key = 'CPRS/or_3_566_ig'"
            ).fetchall()
        )
        assert rows["usage"] == 1 and rows["ig"] == 0
    finally:
        conn.close()


def test_index_handles_empty_staged_table(ctx):
    # a normalized bundle with no matching staged row → identity falls back to FM; empty staged
    # carries forward as an empty table (no rows) without error
    _seed_bundle(ctx, "ADT", "lone_doc", "ADT*1*1", "# Lone\n\n## S\n\nbody ^DPT\n")
    _seed_consolidated(ctx, latest_doc_id="ADT:lone_doc", all_doc_ids=["ADT:lone_doc"])
    _write_staged(ctx.cfg.index_db, [])  # enrich produced an empty staging table
    for stage, art in (
        ("normalize", TEXT_NORMALIZED),
        ("consolidate", CONSOLIDATED),
        ("enrich", DOC_META_STAGED),
    ):
        _bless(ctx, stage, art)
    (result,) = Orchestrator([IndexStage()]).run(ctx)
    assert result.status == "ok" and result.counts["documents"] == 1
    conn = db.connect(ctx.cfg.index_db, read_only=True)
    try:
        row = conn.execute("SELECT doc_id, is_latest FROM documents").fetchone()
        assert row[0] == "ADT:lone_doc" and row[1] == 1  # FM-derived doc_id; is_latest from history
        assert conn.execute("SELECT count(*) FROM doc_meta_staged").fetchone()[0] == 0
    finally:
        conn.close()


def test_index_skips_on_unchanged_rerun(ctx):
    _seed(ctx)
    Orchestrator([IndexStage()]).run(ctx)
    from vdocs.models.stage import Decision

    assert IndexStage().preflight(ctx, force=False).decision is Decision.SKIP


def test_index_preserves_staged_across_forced_rebuild(ctx):
    # a forced re-run must still find doc_meta_staged (index carried it forward, not wiped)
    _seed(ctx)
    orch = Orchestrator([IndexStage()])
    orch.run(ctx)
    orch.run(ctx, force=True)
    conn = db.connect(ctx.cfg.index_db, read_only=True)
    try:
        assert conn.execute("SELECT count(*) FROM doc_meta_staged").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM documents").fetchone()[0] == 2
    finally:
        conn.close()


def test_index_stamps_read_contract_meta(ctx):
    # P0 (ADR-0001): index.db carries a `meta` table with the structural-contract version
    # (read_schema_version) + the data fingerprint (corpus_content_hash) + the doc count.
    _seed(ctx)
    (result,) = Orchestrator([IndexStage()]).run(ctx)
    assert result.status == "ok"
    conn = db.connect(ctx.cfg.index_db, read_only=True)
    try:
        meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
    finally:
        conn.close()
    assert meta["read_schema_version"] == "1.2"
    assert meta["corpus_doc_count"] == "2"  # both version-group members are documents
    assert len(meta["corpus_content_hash"]) == 64  # sha256 hexdigest


def test_index_content_hash_stable_across_forced_rebuild(ctx):
    # the corpus fingerprint is deterministic: rebuilding the identical corpus yields the same
    # hash (no build timestamps baked in), so a consumer/cache can tell "same corpus, rebuilt".
    _seed(ctx)
    orch = Orchestrator([IndexStage()])
    orch.run(ctx)

    def _hash():
        conn = db.connect(ctx.cfg.index_db, read_only=True)
        try:
            return conn.execute(
                "SELECT value FROM meta WHERE key = 'corpus_content_hash'"
            ).fetchone()[0]
        finally:
            conn.close()

    first = _hash()
    orch.run(ctx, force=True)
    assert _hash() == first


def test_index_emits_read_contract_views_matching_the_spec(ctx):
    # P1 (ADR-0001): index.db exposes the v_* read interface, generated from contracts/read/v1.json
    # (the SSOT) — so the views' columns match the spec and the views return the base-table data.
    from vdocs.kernel import read_contract as rc

    _seed(ctx)
    (result,) = Orchestrator([IndexStage()]).run(ctx)
    assert result.status == "ok"
    spec = rc.load(rc.contract_path(base=ctx.cfg.read_contract_dir))
    want_cols = rc.view_columns(spec)

    conn = db.connect(ctx.cfg.index_db, read_only=True)
    try:
        for view, cols in want_cols.items():
            got = [r[1] for r in conn.execute(f"PRAGMA table_info({view})").fetchall()]
            assert got == cols, f"{view} columns drifted from the spec"
        # the view is a faithful window on its base table (same row count)
        assert (
            conn.execute("SELECT count(*) FROM v_documents").fetchone()[0]
            == conn.execute("SELECT count(*) FROM documents").fetchone()[0]
        )
        # is_latest flows through the view
        latest = conn.execute("SELECT count(*) FROM v_documents WHERE is_latest = 1").fetchone()[0]
        assert latest == 1
        # the read_schema_version stamped in meta is the spec's version (single source)
        ver = conn.execute("SELECT value FROM meta WHERE key = 'read_schema_version'").fetchone()[0]
        assert ver == rc.version(spec) == "1.2"
    finally:
        conn.close()


def test_index_publishes_the_vocab_table(ctx):
    # P2 (ADR-0001): index.db carries the controlled facet vocabularies as data (v_vocab), sourced
    # from registries — so consumers read definitions instead of hardcoding them.
    from vdocs.kernel import vocab as kv

    _seed(ctx)
    (result,) = Orchestrator([IndexStage()]).run(ctx)
    assert result.status == "ok"
    want = kv.vocab_rows(ctx.cfg.registries)
    conn = db.connect(ctx.cfg.index_db, read_only=True)
    try:
        got = conn.execute(
            "SELECT kind, code, label, description FROM v_vocab ORDER BY kind, code"
        ).fetchall()
        # every registry-sourced vocabulary row is published verbatim via the view
        assert [tuple(r) for r in got] == sorted(want)
        # the four facet axes are all present
        kinds = {r[0] for r in got}
        assert {"function_category", "doc_type", "section", "persona"} <= kinds
        # a known definition is queryable (the explainer's data source)
        desc = conn.execute(
            "SELECT description FROM v_vocab WHERE kind='persona' AND code='clinical'"
        ).fetchone()[0]
        assert "care staff" in desc
    finally:
        conn.close()
