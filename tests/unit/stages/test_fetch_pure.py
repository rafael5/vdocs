"""Unit tests for fetch pure logic — target selection + index (§8 fetch, §16).

The pipeline is **DOCX-only** (§1): PDF is out of scope, so there is no format fallback and
PDF-only documents are never fetch targets.
"""

from vdocs.models.catalog import EnrichedRecord
from vdocs.stages.fetch import fetch_pure as fp


def test_url_ext():
    assert fp.url_ext("https://va.gov/a/b.DOCX") == "docx"
    assert fp.url_ext("https://va.gov/a/b") == ""


def _rec(slug, fmt, noise=""):
    return EnrichedRecord(
        doc_title="T",
        doc_url=f"https://va.gov/d/{slug}.{fmt}",
        doc_filename=f"{slug}.{fmt}",
        doc_format=fmt,
        app_name_abbrev="ADT",
        doc_slug=slug,
        doc_code="DIBR",
        noise_type=noise,
    )


def test_select_fetch_targets_picks_docx_per_logical_doc():
    # a logical doc published as both DOCX and PDF → the DOCX record is the only target
    docs = [_rec("dg_5_3_1057_dibr", "pdf"), _rec("dg_5_3_1057_dibr", "docx")]
    targets = fp.select_fetch_targets(docs)
    assert len(targets) == 1
    assert targets[0].doc_format == "docx"


def test_select_fetch_targets_excludes_pdf_only_doc():
    # PDF is out of scope (§1): a doc with no DOCX representation is never a target
    docs = [_rec("only_pdf", "pdf")]
    assert fp.select_fetch_targets(docs) == []


def test_select_fetch_targets_excludes_noise():
    # chrome/forms (noise_type set) are never fetched — only green inventory rows (§9.5)
    docs = [_rec("vba_form_x", "docx", noise="vba_form"), _rec("real_doc", "docx")]
    assert [t.doc_slug for t in fp.select_fetch_targets(docs)] == ["real_doc"]


def test_index_entry_shape():
    entry = fp.index_entry(
        app_code="ADT", doc_slug="x_um", title="T", source_url="https://va.gov/x.docx", ext="docx"
    )
    assert entry == {
        "app_code": "ADT",
        "doc_slug": "x_um",
        "title": "T",
        "source_url": "https://va.gov/x.docx",
        "ext": "docx",
    }
