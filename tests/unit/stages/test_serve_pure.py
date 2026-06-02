"""Unit tests for serve-inventory pure logic — doc_id + the HARD GATE (D1/D2, §7, §8)."""

from __future__ import annotations

from vdocs.models.catalog import EnrichedRecord
from vdocs.stages.serve_inventory import serve_pure as sp


def _rec(**kw):
    base = dict(
        app_name_abbrev="ADT",
        doc_slug="dg_5_3_1057_dibr",
        section_code="CLI",
        doc_format="docx",
        system_type="VistA",
        noise_type="",
    )
    base.update(kw)
    return EnrichedRecord(**base)


def test_doc_id_is_app_code_colon_slug():
    assert sp.doc_id(_rec()) == "ADT:dg_5_3_1057_dibr"


def test_gate_passes_on_complete_inventory():
    recs = [_rec(), _rec(doc_format="pdf")]
    g = sp.evaluate_gate(recs, crawl_documents=2)
    assert g.ok and g.reason == ""


def test_gate_fails_when_empty():
    g = sp.evaluate_gate([], crawl_documents=0)
    assert not g.ok and "empty" in g.reason


def test_gate_fails_on_count_mismatch_vs_crawl():
    g = sp.evaluate_gate([_rec()], crawl_documents=2)
    assert not g.ok and "crawl found 2" in g.reason


def test_gate_skips_count_check_when_crawl_unknown():
    assert sp.evaluate_gate([_rec()], crawl_documents=None).ok


def test_gate_fails_on_bad_noise_type():
    g = sp.evaluate_gate([_rec(noise_type="weird")], crawl_documents=1)
    assert not g.ok and "noise_type" in g.reason


def test_gate_fails_on_missing_system_type():
    g = sp.evaluate_gate([_rec(system_type="")], crawl_documents=1)
    assert not g.ok and "system_type" in g.reason


def test_gate_fails_on_missing_section_or_format():
    assert not sp.evaluate_gate([_rec(section_code="")], crawl_documents=1).ok
    assert not sp.evaluate_gate([_rec(doc_format="")], crawl_documents=1).ok


def test_gate_passes_but_reports_unclassified_as_soft_signal():
    g = sp.evaluate_gate([_rec(system_type="unclassified")], crawl_documents=1)
    assert g.ok and g.unclassified == 1
