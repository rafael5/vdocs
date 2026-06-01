"""Unit tests for fetch pure logic — URL strategy + target selection + index (§8 fetch, §16)."""

from vdocs.models.catalog import DocType, EnrichedDocument
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


def _ed(slug, ext):
    return EnrichedDocument(
        title="T",
        url=f"https://va.gov/d/{slug}{ext}",
        filename=f"{slug}{ext}",
        file_ext=ext,
        app_code="ADT",
        doc_slug=slug,
        doc_type=DocType.INSTALLATION_GUIDE,
    )


def test_select_fetch_targets_prefers_docx_per_logical_doc():
    docs = [_ed("dg_5_3_1057_dibr", ".pdf"), _ed("dg_5_3_1057_dibr", ".docx")]
    targets = fp.select_fetch_targets(docs)
    assert len(targets) == 1
    assert targets[0].file_ext == ".docx"


def test_select_fetch_targets_keeps_pdf_only_doc():
    docs = [_ed("only_pdf", ".pdf")]
    assert [t.file_ext for t in fp.select_fetch_targets(docs)] == [".pdf"]


def test_index_entry_shape():
    entry = fp.index_entry(
        app_code="ADT", title="T", source_url="https://va.gov/x.docx", ext="docx"
    )
    assert entry == {
        "app_code": "ADT",
        "title": "T",
        "source_url": "https://va.gov/x.docx",
        "ext": "docx",
    }
