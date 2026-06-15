"""manifest integration — index.db + consolidated → corpus-manifest.json + discovery.json (§14.4).
Seeds a small index.db (documents/sections/entities/relations) + a consolidated bundle, runs
ManifestStage through the orchestrator, and asserts the JSON schema, counts matching index.db, and
the lexical/structured/graph capability manifest (the semantic/vector path is descoped).
"""

from __future__ import annotations

import json

from vdocs.contracts.registry import (
    CONSOLIDATED,
    INDEX_DOCUMENTS,
    INDEX_ENTITIES,
    RELATIONS,
)
from vdocs.kernel import cas, db
from vdocs.models.stage import Decision, StageRun
from vdocs.orchestrator.engine import Orchestrator
from vdocs.stages.manifest.stage import ManifestStage


def _seed(ctx):
    conn = db.connect(ctx.cfg.index_db)
    conn.executescript(
        """
        CREATE TABLE documents (
          doc_key TEXT PRIMARY KEY, doc_id TEXT, title TEXT, app_code TEXT, doc_type TEXT,
          pkg_ns TEXT, patch_id TEXT, version TEXT, section_count INTEGER, word_count INTEGER,
          is_latest INTEGER
        );
        CREATE TABLE doc_sections (section_id TEXT PRIMARY KEY, is_latest INTEGER);
        CREATE TABLE chunks (chunk_id TEXT PRIMARY KEY, section_id TEXT);
        CREATE TABLE entities (
          entity_id TEXT PRIMARY KEY, type TEXT, canonical_name TEXT, mention_count INTEGER
        );
        CREATE TABLE relations (src_id TEXT, rel TEXT, dst_id TEXT);
        """
    )
    conn.executemany(
        "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            # d1: a grouped (versioned) anchor; d3: a standalone anchor; d2: a prior version
            ("CPRS/or_um", "CPRS:or_um", "OR User Manual", "CPRS", "UM", "OR",
             "OR*3.0*539", "3.0", 4, 1200, 1),
            ("CPRS/or_um_old", "CPRS:or_um_old", "OR User Manual", "CPRS", "UM", "OR",
             "OR*3.0*1", "3.0", 4, 1100, 0),
            ("KAAJEE/dibr", "KAAJEE:dibr", "KAAJEE DIBR", "KAAJEE", "", "",
             "", "", 3, 800, 1),
        ],
    )  # fmt: skip
    conn.executemany(
        "INSERT INTO doc_sections VALUES (?, ?)", [("d1/a", 1), ("d2/a", 0), ("d3/a", 1)]
    )
    # the search surface = chunks (one per searchable is_latest section here)
    conn.executemany("INSERT INTO chunks VALUES (?, ?)", [("d1/a", "d1/a"), ("d3/a", "d3/a")])
    conn.executemany(
        "INSERT INTO entities VALUES (?, ?, ?, ?)",
        [("build:X", "build", "X", 2), ("global:G", "global", "G", 9),
         ("global:H", "global", "H", 3)],
    )  # fmt: skip
    conn.executemany(
        "INSERT INTO relations VALUES (?, ?, ?)",
        [("d1", "mentions", "build:X"), ("d1", "xref", "d3")],
    )
    conn.commit()
    conn.close()
    # a consolidated bundle (the version-group rollup input)
    cas.atomic_write(
        ctx.cfg.gold_consolidated / "CPRS" / "or_ig" / "history.yaml", b"anchor_key: x\n"
    )

    ctx.state.record(
        StageRun(
            stage="index",
            scope="",
            status="ok",
            started_at="t",
            finished_at="t",
            inputs_fp={},
            outputs_fp={a.key: a.fingerprint(ctx.cfg) for a in (INDEX_DOCUMENTS, INDEX_ENTITIES)},
            counts={},
            contract_ver=1,
            tool_ver=ctx.cfg.tool_ver,
        )  # fmt: skip
    )
    for stage, art in (("consolidate", CONSOLIDATED), ("relate", RELATIONS)):
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


def test_manifest_writes_both_json_with_counts(ctx):
    _seed(ctx)
    (result,) = Orchestrator([ManifestStage()]).run(ctx)
    assert result.status == "ok"

    manifest = json.loads(ctx.cfg.corpus_manifest.read_text())
    assert manifest["counts"]["documents"] == 3
    assert manifest["counts"]["version_groups"] == 2  # the two is_latest docs
    assert manifest["counts"]["sections_searchable"] == 2
    assert manifest["counts"]["entities_by_type"] == {"build": 1, "global": 2}
    assert manifest["counts"]["relations_by_type"] == {"mentions": 1, "xref": 1}
    # lexical/structured/graph are live off index.db; the semantic/vector path is descoped
    assert manifest["capabilities"] == {
        "lexical": True,
        "structured": True,
        "graph": True,
    }
    assert "embedding" not in manifest
    assert "section_id" in manifest["id_scheme"]  # the stable-ID contract advertised

    discovery = json.loads(ctx.cfg.discovery_json.read_text())
    assert set(discovery["entity_types"]) == {"build", "global"}
    assert "semantic" not in discovery["capabilities"]
    assert discovery["counts"]["version_groups"] == 2


def test_manifest_writes_ai_corpus_card(ctx):
    _seed(ctx)
    (result,) = Orchestrator([ManifestStage()]).run(ctx)
    assert result.counts["catalog_docs"] == 2  # the two is_latest anchors

    card = json.loads(ctx.cfg.ai_manifest.read_text())
    assert card["index_fingerprint"]  # the staleness stamp is recorded
    assert "vdocs ask" in card["query"]["command"]
    by_key = {d["doc_key"]: d for d in card["documents"]}
    assert set(by_key) == {"CPRS/or_um", "KAAJEE/dibr"}  # prior version excluded
    # the grouped anchor resolves to the version-free consolidated body path
    assert by_key["CPRS/or_um"]["body_path"] == "documents/gold/consolidated/CPRS/or_um/body.md"
    assert by_key["KAAJEE/dibr"]["body_path"] == "documents/gold/consolidated/KAAJEE/dibr/body.md"
    # entity index is grouped by type, ordered by mention count
    assert card["entities"]["global"][0] == {"name": "G", "mentions": 9}

    md = ctx.cfg.corpus_card.read_text()
    assert "OR User Manual" in md and "never guess" in md.lower()


def test_manifest_skips_on_unchanged_rerun(ctx):
    _seed(ctx)
    Orchestrator([ManifestStage()]).run(ctx)
    assert ManifestStage().preflight(ctx, force=False).decision is Decision.SKIP


def test_manifest_counts_stable_across_forced_rerun(ctx):
    # generated_at tracks the clock (so a forced rebuild's timestamp differs by design); the corpus
    # *counts* and capabilities are a pure function of the inputs and must be byte-stable
    _seed(ctx)
    orch = Orchestrator([ManifestStage()])
    orch.run(ctx)
    first = json.loads(ctx.cfg.corpus_manifest.read_text())
    orch.run(ctx, force=True)
    second = json.loads(ctx.cfg.corpus_manifest.read_text())
    assert first["counts"] == second["counts"]
    assert first["capabilities"] == second["capabilities"]
    assert first["generated_at"] != second["generated_at"]  # the clock advanced


def test_manifest_carries_read_contract_and_coverage(ctx):
    # P2.3/P2.4: the manifest advertises the read-contract version + capabilities (consumer
    # negotiation) and per-facet coverage stats (consumer staleness/quality).
    _seed(ctx)
    (result,) = Orchestrator([ManifestStage()]).run(ctx)
    assert result.status == "ok"
    manifest = json.loads(ctx.cfg.corpus_manifest.read_text())
    assert manifest["read_contract"]["version"] == "1.3"
    assert "fts5" in manifest["read_contract"]["capabilities"]
    # pkg_ns exists in the fixture schema → covered (defensive: absent facet columns are skipped)
    assert manifest["coverage"]["pkg_ns"]["total"] == 2  # two is_latest anchors
    # P2.5 characterization snapshot: doc_type distribution over is_latest gold (d1=UM, d3="")
    assert manifest["characterization"]["doc_type"] == {"UM": 1}
