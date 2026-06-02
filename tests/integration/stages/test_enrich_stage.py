"""enrich integration — bake identity FM + stage doc metadata (Phase 3, §6.3, §8).

Seeds a converted bundle + the enriched inventory, runs EnrichStage through the orchestrator,
and asserts the text@enriched body carries the identity frontmatter (round-trips via the
kernel codec, computed fields absent) and index.db:doc_meta_staged holds the staged row.
"""

from __future__ import annotations

import sqlite3

from vdocs.contracts.registry import CATALOG_ENRICHED, TEXT_CONVERTED
from vdocs.kernel import cas, frontmatter
from vdocs.models.catalog import EnrichedInventory, EnrichedRecord
from vdocs.models.stage import StageRun
from vdocs.orchestrator.engine import Orchestrator
from vdocs.stages.enrich.stage import EnrichStage


def _record(**kw):
    base = dict(
        section_name="Clinical",
        section_code="CLI",
        app_name_abbrev="ADT",
        doc_slug="dg_5_3_1057_dibr",
        doc_code="DIBR",
        doc_label="Deployment, Installation, Back-Out, and Rollback Guide",
        doc_title="DG*5.3*1057 Deployment Guide",
        pkg_ns="DG",
        patch_ver="5.3",
        patch_id="DG*5.3*1057",
        doc_url="https://va.gov/d/dg_5_3_1057_dibr.docx",
        doc_format="docx",
    )
    base.update(kw)
    return EnrichedRecord(**base)


def _seed(ctx, records):
    # the enriched inventory (catalog ok)
    cas.atomic_write(
        ctx.cfg.catalog_enriched,
        EnrichedInventory(records=records).model_dump_json().encode("utf-8"),
    )
    # one converted bundle at <app>/<slug>/body.md (convert ok)
    cas.atomic_write(
        ctx.cfg.silver_converted / "ADT" / "dg_5_3_1057_dibr" / "body.md",
        b"# DG Deployment\n\nInstall steps here.\n",
    )
    for stage, art in (("catalog", CATALOG_ENRICHED), ("convert", TEXT_CONVERTED)):
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
            )
        )


def test_enrich_bakes_frontmatter_and_stages_meta(ctx):
    # a docx + its pdf companion share the bundle (DOCX wins the join); a noise row is excluded
    _seed(
        ctx,
        [
            _record(),
            _record(doc_format="pdf", doc_url="https://va.gov/d/x.pdf"),
            _record(doc_slug="vba_form_x", noise_type="vba_form"),
        ],
    )
    (result,) = Orchestrator([EnrichStage()]).run(ctx)

    assert result.status == "ok"
    assert result.counts == {"documents": 1, "missing_record": 0}

    enriched = ctx.cfg.silver_enriched / "ADT" / "dg_5_3_1057_dibr" / "body.md"
    meta, body = frontmatter.parse(enriched.read_text())
    assert meta["title"] == "DG*5.3*1057 Deployment Guide"
    assert meta["doc_type"] == "DIBR" and meta["app_code"] == "ADT" and meta["section"] == "CLI"
    assert meta["version"] == "5.3" and meta["source_url"].endswith(".docx")  # docx preferred
    assert "word_count" not in meta  # computed fields never baked into the body (§6.3)
    assert body.strip() == "# DG Deployment\n\nInstall steps here.".strip()

    # index.db:doc_meta_staged carries the staged row (identity + computed word_count)
    conn = sqlite3.connect(ctx.cfg.index_db)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM doc_meta_staged WHERE doc_id = ?", ("ADT:dg_5_3_1057_dibr",)
        ).fetchone()
        assert (
            row["doc_code"] == "DIBR" and row["word_count"] == 6
        )  # "# DG Deployment Install steps here."
        assert row["bundle_path"] == "ADT/dg_5_3_1057_dibr"
    finally:
        conn.close()


def test_enrich_warns_and_skips_bundle_with_no_inventory_record(ctx):
    # an orphan converted bundle with no inventory record (written before the convert
    # fingerprint is recorded, so it's part of the blessed text@converted tree)
    cas.atomic_write(ctx.cfg.silver_converted / "ZZZ" / "orphan_doc" / "body.md", b"# Orphan\n")
    _seed(ctx, [_record()])  # one matching record for the seeded bundle
    (result,) = Orchestrator([EnrichStage()]).run(ctx)
    assert result.counts == {"documents": 1, "missing_record": 1}
    # the matched doc is enriched; the orphan is skipped (WARN), not written
    assert (ctx.cfg.silver_enriched / "ADT" / "dg_5_3_1057_dibr" / "body.md").exists()
    assert not (ctx.cfg.silver_enriched / "ZZZ" / "orphan_doc" / "body.md").exists()
