"""Unit tests for enrich pure logic — identity frontmatter + staged doc-meta row (§6.3, §8)."""

from __future__ import annotations

from vdocs.kernel import personas
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
        "app_status": "active",
        "tool_ver": "0.1.0",
    }


def test_identity_frontmatter_omits_empty_identity_fields():
    fm = ep.identity_frontmatter(_rec(pkg_ns="", patch_ver="", patch_id=""), tool_ver="0.1.0")
    assert "pkg_ns" not in fm and "version" not in fm and "patch_id" not in fm
    assert fm["title"] and fm["tool_ver"] == "0.1.0"  # populated keys remain


def test_profile_frontmatter_resolves_the_four_tags():
    maps = personas.ProfileMaps(
        app_user={"ADT": "clinical-admin"},
        software_class={"ADT": "I"},
        function_category={"ADT": "Health Informatics"},
        doc_user={"DIBR": "sysadmin", "UM": "operator"},
    )
    # DIBR is role-fixed sysadmin (independent of the app's clinical-admin app_user)
    assert ep.profile_frontmatter(_rec(), maps) == {
        "app_user": "clinical-admin",
        "doc_user": "sysadmin",
        "software_class": "I",
        "function_category": "Health Informatics",
    }
    # a UM delegates to the app's app_user; an operator doc of an un-profiled app yields no tags
    assert ep.profile_frontmatter(_rec(doc_code="UM"), maps)["doc_user"] == "clinical-admin"
    assert ep.profile_frontmatter(_rec(app_name_abbrev="ZZZ", doc_code="UM"), maps) == {}
    # but a role-fixed doc_type still resolves doc_user even when the app has no profile
    assert ep.profile_frontmatter(_rec(app_name_abbrev="ZZZ"), maps) == {"doc_user": "sysadmin"}


# --- CI.3: VA lifecycle labels travel with the document --------------------------------------


def test_frontmatter_carries_lifecycle_labels_when_va_supplies_them():
    fm = ep.identity_frontmatter(
        _rec(app_status="decommissioned", decommission_date="2022-05", cots_dependent=True),
        tool_ver="0.1.0",
    )
    assert fm["app_status"] == "decommissioned"
    assert fm["decommission_date"] == "2022-05"
    assert fm["cots_dependent"] == "true"


def test_frontmatter_absent_lifecycle_labels_stay_absent():
    fm = ep.identity_frontmatter(_rec(), tool_ver="0.1.0")
    assert fm["app_status"] == "active"  # VA always labels the app
    assert "decommission_date" not in fm  # no date supplied → no key, no default
    assert "cots_dependent" not in fm  # not commercially replaced → no key
    assert "out_of_scope_reason" not in fm


def test_staged_row_carries_lifecycle_labels():
    row = ep.staged_row(
        _rec(app_status="archive", decommission_date="2010-01", cots_dependent=True),
        body="",
        bundle_path="x",
    )
    assert row["app_status"] == "archive"
    assert row["decommission_date"] == "2010-01"
    assert row["cots_dependent"] == 1  # INTEGER in doc_meta_staged / documents
    assert row["out_of_scope_reason"] == ""


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
