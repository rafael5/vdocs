"""Unit tests for server.facets_pure — pure facet-narrowing helpers (LF)."""

from __future__ import annotations

from vdocs.server import facets_pure as fp


def test_audience_codes_returns_doc_types_for_an_audience():
    mapping = {"UM": "clinical", "UG": "clinical", "TM": "technical"}
    assert fp.audience_codes("clinical", mapping) == ["UG", "UM"]  # sorted
    assert fp.audience_codes("technical", mapping) == ["TM"]
    assert fp.audience_codes("nope", mapping) == []


def test_narrow_clause_is_latest_only_by_default():
    where, params = fp.narrow_clause()
    assert where == "is_latest = 1" and params == []


def test_narrow_clause_builds_in_filters_in_column_order():
    where, params = fp.narrow_clause(doc_type=["UM"], app=["RA"], pkg_ns=["OR"])
    assert where == "is_latest = 1 AND doc_type IN (?) AND app_code IN (?) AND pkg_ns IN (?)"
    assert params == ["UM", "RA", "OR"]


def test_narrow_clause_multiple_values_get_multiple_placeholders():
    where, params = fp.narrow_clause(doc_type=["UM", "UG"])
    assert where == "is_latest = 1 AND doc_type IN (?, ?)"
    assert params == ["UM", "UG"]


def test_resolve_doc_types_merges_explicit_and_audience():
    mapping = {"UM": "clinical", "UG": "clinical", "TM": "technical"}
    # explicit doc_type + audience union, de-duped + sorted
    assert fp.resolve_doc_types(["TM"], "clinical", mapping) == ["TM", "UG", "UM"]
    assert fp.resolve_doc_types(None, "technical", mapping) == ["TM"]
    assert fp.resolve_doc_types(["UM"], None, mapping) == ["UM"]
    assert fp.resolve_doc_types(None, None, mapping) == []
