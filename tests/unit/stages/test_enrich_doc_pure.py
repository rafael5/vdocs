"""Unit tests for enrich pure logic — identity frontmatter + staged doc-meta row (§6.3, §8)."""

from __future__ import annotations

from vdocs.models.catalog import EnrichedRecord
from vdocs.stages.enrich import enrich_pure as ep


def _rec(**kw):
    base = dict(
        app_name_abbrev="ADT",
        doc_slug="dg_5_3_1057_dibr",
        doc_code="DIBR",
        doc_label="Deployment, Installation, Back-Out, and Rollback Guide",
        doc_title="DG*5.3*1057 Deployment Guide",
        section_code="CLI",
        pkg_ns="DG",
        patch_ver="5.3",
        patch_id="DG*5.3*1057",
        doc_url="https://va.gov/d/dg_5_3_1057_dibr.docx",
        doc_format="docx",
    )
    base.update(kw)
    return EnrichedRecord(**base)


def test_doc_id_and_word_count():
    assert ep.doc_id(_rec()) == "ADT:dg_5_3_1057_dibr"
    assert ep.word_count("one two  three\nfour") == 4
    assert ep.word_count("") == 0


def test_identity_frontmatter_maps_and_orders_keys():
    fm = ep.identity_frontmatter(_rec(), tool_ver="0.1.0")
    assert fm == {
        "title": "DG*5.3*1057 Deployment Guide",
        "doc_type": "DIBR",
        "app_code": "ADT",
        "section": "CLI",
        "pkg_ns": "DG",
        "version": "5.3",
        "patch_id": "DG*5.3*1057",
        "source_url": "https://va.gov/d/dg_5_3_1057_dibr.docx",
        "tool_ver": "0.1.0",
    }


def test_identity_frontmatter_omits_empty_identity_fields():
    fm = ep.identity_frontmatter(_rec(pkg_ns="", patch_ver="", patch_id=""), tool_ver="0.1.0")
    assert "pkg_ns" not in fm and "version" not in fm and "patch_id" not in fm
    assert fm["title"] and fm["tool_ver"] == "0.1.0"  # populated keys remain


def test_staged_row_carries_identity_plus_computed():
    row = ep.staged_row(_rec(), body="a b c d e", bundle_path="ADT/dg_5_3_1057_dibr")
    assert row["doc_id"] == "ADT:dg_5_3_1057_dibr"
    assert row["word_count"] == 5  # computed — staged, never baked into the body
    assert row["bundle_path"] == "ADT/dg_5_3_1057_dibr"
    assert row["anchor_key"] == "" and row["doc_code"] == "DIBR"


def test_staged_columns_match_row_keys():
    row = ep.staged_row(_rec(), body="", bundle_path="x")
    assert set(ep.STAGED_COLUMNS) == set(row.keys())
    assert "word_count" in ep.STAGED_COLUMNS
