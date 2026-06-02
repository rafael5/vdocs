"""Unit tests for serve-inventory pure logic — doc_id + the HARD GATE (D1/D2, §7, §8)."""

from __future__ import annotations

from vdocs.models.catalog import EnrichedRecord
from vdocs.models.stage import Acquisition
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


def test_gate_fails_when_no_genuine_documents():
    # sane distributions (crawl-spec §7): every record classified as (valid) noise means the
    # genuine inventory collapsed to empty — a systemic enrichment bug, not a blessable inventory
    g = sp.evaluate_gate([_rec(noise_type="vba_form")], crawl_documents=1)
    assert not g.ok and "genuine" in g.reason


# --- inventory_status join -------------------------------------------------
def test_inventory_status_collapses_formats_and_joins_acquisitions():
    docx = _rec(doc_format="docx", doc_code="DIBR", doc_title="T")
    pdf = _rec(doc_format="pdf", doc_code="DIBR", doc_title="T")  # same doc_id (shared slug)
    other = _rec(doc_slug="other_doc", doc_code="RN")
    noise = _rec(doc_slug="vba", noise_type="vba_form")  # excluded — not a candidate
    acqs = {
        "ADT:dg_5_3_1057_dibr": Acquisition(
            doc_id="ADT:dg_5_3_1057_dibr",
            source_url="u",
            status="fetched",
            sha256="abc",
            fetched_at="2026-06-01",
        )  # fmt: skip
    }
    rows = sp.inventory_status([docx, pdf, other, noise], acqs)
    by_id = {r.doc_id: r for r in rows}
    # PDF/DOCX collapse to one logical doc; noise excluded
    assert set(by_id) == {"ADT:dg_5_3_1057_dibr", "ADT:other_doc"}
    assert by_id["ADT:dg_5_3_1057_dibr"].status == "fetched"
    assert by_id["ADT:dg_5_3_1057_dibr"].sha256 == "abc"
    assert by_id["ADT:other_doc"].status == "not_acquired"  # no acquisition yet


def test_status_summary_counts():
    docx = _rec(doc_format="docx")
    other = _rec(doc_slug="other_doc")
    third = _rec(doc_slug="third_doc")
    acqs = {
        "ADT:dg_5_3_1057_dibr": Acquisition(
            doc_id="ADT:dg_5_3_1057_dibr", source_url="u", status="fetched"
        )
    }
    summary = sp.status_summary(sp.inventory_status([docx, other, third], acqs))
    assert summary == {"total": 3, "fetched": 1, "not_acquired": 2}


# --- out-of-scope (PDF-only) docs are flagged, not silently dropped (§1) ---
def test_pdf_only_doc_is_flagged_out_of_scope():
    # a logical doc with no DOCX representation is out of scope — never fetchable
    pdf_only = _rec(doc_slug="pdf_only", doc_format="pdf")
    (row,) = sp.inventory_status([pdf_only], {})
    assert row.doc_id == "ADT:pdf_only" and row.status == "out_of_scope"


def test_dual_format_doc_stays_in_scope():
    # DOCX + PDF of one logical doc → in scope via the DOCX, just not fetched yet
    docx = _rec(doc_format="docx")
    pdf = _rec(doc_format="pdf")  # same doc_id (shared slug)
    (row,) = sp.inventory_status([docx, pdf], {})
    assert row.status == "not_acquired"


def test_status_summary_counts_out_of_scope():
    docx = _rec(doc_format="docx")
    pdf_only = _rec(doc_slug="pdf_only", doc_format="pdf")
    summary = sp.status_summary(sp.inventory_status([docx, pdf_only], {}))
    assert summary == {"total": 2, "not_acquired": 1, "out_of_scope": 1}
