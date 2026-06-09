"""Unit tests for server.facets_pure — pure facet-narrowing helpers (LF).

The two persona axes (app_user / doc_user) plus software_class / function_category are now **baked
columns** on `documents` (resolved once at `enrich` from app-profiles.yaml + doc-user.yaml), so
narrowing is a plain column `IN (...)` filter — no query-time registry resolution.
"""

from __future__ import annotations

from vdocs.server import facets_pure as fp


def test_narrow_clause_is_latest_only_by_default():
    where, params = fp.narrow_clause()
    assert where == "is_latest = 1" and params == []


def test_narrow_clause_builds_in_filters_in_column_order():
    where, params = fp.narrow_clause(doc_type=["UM"], app=["RA"], pkg_ns=["OR"])
    assert where == "is_latest = 1 AND doc_type IN (?) AND app_code IN (?) AND pkg_ns IN (?)"
    assert params == ["UM", "RA", "OR"]


def test_narrow_clause_includes_persona_and_profile_columns():
    where, params = fp.narrow_clause(
        app_user=["clinical"],
        doc_user=["developer"],
        software_class=["I"],
        function_category=["Patient Care Services"],
    )
    assert where == (
        "is_latest = 1 AND app_user IN (?) AND doc_user IN (?) "
        "AND software_class IN (?) AND function_category IN (?)"
    )
    assert params == ["clinical", "developer", "I", "Patient Care Services"]


def test_narrow_clause_multi_value_in_one_column():
    where, params = fp.narrow_clause(doc_user=["clinical", "clinical-admin"])
    assert where == "is_latest = 1 AND doc_user IN (?, ?)"
    assert params == ["clinical", "clinical-admin"]
