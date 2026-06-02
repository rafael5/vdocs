"""Unit tests for inventory boundary models — the explicit out-of-scope flag (§1, §5.6).

The pipeline is DOCX-only: an :class:`EnrichedRecord` derives ``out_of_scope_reason`` from its
``doc_format`` so every inventory row carries an explicit in-scope/out-of-scope flag.
"""

from vdocs.models.catalog import EnrichedRecord


def _rec(fmt):
    return EnrichedRecord(app_name_abbrev="ADT", doc_slug="x", doc_format=fmt)


def test_docx_record_is_in_scope():
    assert _rec("docx").out_of_scope_reason == ""


def test_pdf_record_is_flagged_out_of_scope():
    assert _rec("pdf").out_of_scope_reason == "pdf"


def test_legacy_doc_record_is_flagged_out_of_scope():
    assert _rec("doc").out_of_scope_reason == "doc"


def test_explicit_out_of_scope_reason_is_preserved():
    # an explicitly-set reason is not overwritten by the format-derived default
    r = EnrichedRecord(doc_format="docx", out_of_scope_reason="manual_exclude")
    assert r.out_of_scope_reason == "manual_exclude"
