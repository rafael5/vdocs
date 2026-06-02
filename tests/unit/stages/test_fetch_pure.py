"""Unit tests for fetch pure logic — URL strategy + target selection + index (§8 fetch, §16)."""

from vdocs.models.catalog import EnrichedRecord
from vdocs.stages.fetch import fetch_pure as fp


def test_swap_extension_docx_to_pdf_and_back():
    assert fp.swap_extension("https://va.gov/x.docx") == "https://va.gov/x.pdf"
    assert fp.swap_extension("https://va.gov/x.pdf") == "https://va.gov/x.docx"
    assert fp.swap_extension("https://va.gov/x.txt") == "https://va.gov/x.txt"


def test_candidate_urls_tries_own_then_other_format():
    assert fp.candidate_urls("https://va.gov/x.docx") == [
        "https://va.gov/x.docx",
        "https://va.gov/x.pdf",
    ]


def test_candidate_urls_no_duplicate_when_no_swap():
    assert fp.candidate_urls("https://va.gov/x.txt") == ["https://va.gov/x.txt"]


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


def test_select_fetch_targets_prefers_docx_per_logical_doc():
    docs = [_rec("dg_5_3_1057_dibr", "pdf"), _rec("dg_5_3_1057_dibr", "docx")]
    targets = fp.select_fetch_targets(docs)
    assert len(targets) == 1
    assert targets[0].doc_format == "docx"


def test_select_fetch_targets_keeps_pdf_only_doc():
    docs = [_rec("only_pdf", "pdf")]
    assert [t.doc_format for t in fp.select_fetch_targets(docs)] == ["pdf"]


def test_select_fetch_targets_excludes_noise():
    # chrome/forms (noise_type set) are never fetched — only green inventory rows (§9.5)
    docs = [_rec("vba_form_x", "pdf", noise="vba_form"), _rec("real_doc", "docx")]
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
