"""serve-inventory integration — gold inventory artifacts + the HARD GATE (D1/D2, §8).

Drives catalog → serve-inventory through the orchestrator on a small synthetic crawl,
proving (a) the gold ``inventory.json`` + queryable ``inventory.db`` are written and indexed,
(b) the postflight gate blesses a complete inventory ``ok`` (the fetch gate), and (c) a
gate failure records ``failed`` and refuses to bless.
"""

from __future__ import annotations

import sqlite3

import pytest

from vdocs.kernel import cas
from vdocs.models.catalog import (
    Catalog,
    CatalogApplication,
    CatalogDocument,
    CatalogSection,
    EnrichedInventory,
    EnrichedRecord,
)
from vdocs.orchestrator.engine import Orchestrator
from vdocs.orchestrator.stage import PostflightError
from vdocs.stages.catalog.stage import CatalogStage
from vdocs.stages.serve_inventory.stage import ServeInventoryStage


def _catalog():
    docx = CatalogDocument(
        title="DG*5.3*1057 Deployment, Installation, Back-Out, and Rollback Guide",
        url="https://www.va.gov/vdl/documents/Clinical/ADT/dg_5_3_1057_dibr.docx",
        filename="dg_5_3_1057_dibr.docx",
        file_ext=".docx",
    )
    pdf = docx.model_copy(
        update={
            "url": docx.url.replace(".docx", ".pdf"),
            "filename": "dg_5_3_1057_dibr.pdf",
            "file_ext": ".pdf",
        }
    )
    app = CatalogApplication(
        name="Admission Discharge Transfer",
        app_code="ADT",
        url="https://www.va.gov/vdl/application.asp?appid=55",
        documents=[docx, pdf],
    )
    return Catalog(sections=[CatalogSection(name="Clinical", url="u", applications=[app])])


def _seed_crawl(ctx, documents=2):
    from vdocs.contracts.registry import CATALOG_RAW
    from vdocs.models.stage import StageRun

    cas.atomic_write(ctx.cfg.catalog_raw, _catalog().model_dump_json().encode("utf-8"))
    ctx.state.record(
        StageRun(
            stage="crawl",
            scope="",
            status="ok",
            started_at="t",
            finished_at="t",
            inputs_fp={},
            outputs_fp={CATALOG_RAW.key: CATALOG_RAW.fingerprint(ctx.cfg)},
            counts={"documents": documents},
            contract_ver=1,
            tool_ver=ctx.cfg.tool_ver,
        )
    )


def test_serve_inventory_builds_gold_and_passes_gate(ctx):
    _seed_crawl(ctx)
    results = Orchestrator([CatalogStage(), ServeInventoryStage()]).run(ctx)

    serve = results[-1]
    assert serve.stage == "serve-inventory" and serve.status == "ok"  # gate green = fetch gate
    assert serve.counts == {"records": 2, "genuine": 2}

    # portable JSON view
    inv = EnrichedInventory.model_validate_json(ctx.cfg.gold_inventory_json.read_text())
    assert len(inv.records) == 2

    # published flat CSV table — leads with doc_id, one row per record
    csv_lines = ctx.cfg.gold_inventory_csv.read_text().splitlines()
    header = csv_lines[0].split(",")
    assert header[0] == "doc_id" and "anchor_key" in header and "noise_type" in header
    assert len(csv_lines) == 1 + 2  # header + 2 records
    assert all("ADT:dg_5_3_1057_dibr" in line for line in csv_lines[1:])

    # queryable SQLite with the doc_id join key + selection indexes
    conn = sqlite3.connect(ctx.cfg.gold_inventory_db)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT doc_id, doc_code, noise_type, cots_dependent FROM inventory "
            "WHERE app_name_abbrev = ?",
            ("ADT",),
        ).fetchall()
        assert {r["doc_id"] for r in rows} == {"ADT:dg_5_3_1057_dibr"}
        assert {r["doc_code"] for r in rows} == {"DIBR"}
        assert all(r["cots_dependent"] == 0 for r in rows)  # bool stored as 0/1
        idx = {r["name"] for r in conn.execute("PRAGMA index_list('inventory')")}
        assert "idx_inventory_doc_id" in idx and "idx_inventory_section_code" in idx
    finally:
        conn.close()


def test_serve_inventory_gate_fails_on_count_mismatch(ctx):
    # crawl claims 5 documents but the enriched inventory has 2 → 1:1 gate fails, not blessed
    _seed_crawl(ctx, documents=5)

    with pytest.raises(PostflightError, match="crawl found 5"):
        Orchestrator([CatalogStage(), ServeInventoryStage()]).run(ctx)

    # serve-inventory recorded a failure, never an ok (so fetch's preflight will refuse)
    run = ctx.state.get("serve-inventory")
    assert run is not None and run.status == "failed"


def test_gate_fails_on_corrupt_inventory(ctx):
    # a record with an invalid noise_type in the gold json → gate refuses to bless
    _seed_crawl(ctx, documents=1)
    bad = EnrichedInventory(
        records=[
            EnrichedRecord(
                app_name_abbrev="ADT",
                doc_slug="x",
                section_code="CLI",
                doc_format="pdf",
                system_type="VistA",
                noise_type="bogus",
            )
        ]
    )
    cas.atomic_write(ctx.cfg.gold_inventory_json, bad.model_dump_json().encode("utf-8"))

    verdict = ServeInventoryStage().deep_gate(ctx)
    assert not verdict.ok and "noise_type" in verdict.reason


def test_build_db_clears_a_stale_temp(tmp_path):
    # a leftover .inventory.db.tmp from a crashed prior build is cleared before rebuilding
    from vdocs.stages.serve_inventory.stage import _build_db

    db_path = tmp_path / "inventory.db"
    stale = db_path.with_name(f".{db_path.name}.tmp")
    stale.write_bytes(b"junk")
    _build_db(db_path, [])
    assert db_path.exists() and not stale.exists()


def test_gate_passes_but_warns_on_unclassified_app(ctx):
    # a structurally-sound row whose app has no system_type mapping → gate still green,
    # but the soft unclassified signal is surfaced (logged), not blocked.
    _seed_crawl(ctx, documents=1)
    inv = EnrichedInventory(
        records=[
            EnrichedRecord(
                app_name_abbrev="NEWAPP",
                doc_slug="x",
                section_code="CLI",
                doc_format="pdf",
                system_type="unclassified",
                noise_type="",
            )
        ]
    )
    cas.atomic_write(ctx.cfg.gold_inventory_json, inv.model_dump_json().encode("utf-8"))

    verdict = ServeInventoryStage().deep_gate(ctx)
    assert verdict.ok  # green despite the unclassified app (soft signal only)
