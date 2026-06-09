"""Unit tests for server.facets_pure — pure facet-narrowing helpers (LF).

Two persona axes, one vocabulary: app_user (who runs the app, per app-profiles) and doc_user
(who reads the doc, per doc-user.yaml with operator→app_user delegation).
"""

from __future__ import annotations

from vdocs.server import facets_pure as fp

# who reads each doc_type: 'operator' delegates to the app's app_user; else a fixed persona
_DOC_USER = {"UM": "operator", "UG": "operator", "TM": "developer", "AG": "sysadmin"}
# who operates each app
_APP_USER = {"SD": "clinical-admin", "OR": "clinical", "PRC": "business-admin"}


def test_narrow_clause_is_latest_only_by_default():
    where, params = fp.narrow_clause()
    assert where == "is_latest = 1" and params == []


def test_narrow_clause_builds_in_filters_in_column_order():
    where, params = fp.narrow_clause(doc_type=["UM"], app=["RA"], pkg_ns=["OR"])
    assert where == "is_latest = 1 AND doc_type IN (?) AND app_code IN (?) AND pkg_ns IN (?)"
    assert params == ["UM", "RA", "OR"]


def test_app_user_clause_filters_by_apps_with_that_operator():
    where, params = fp.app_user_clause("clinical-admin", _APP_USER)
    assert where == "app_code IN (?)" and params == ["SD"]
    # no app has this persona → matches nothing
    assert fp.app_user_clause("sysadmin", _APP_USER) == ("0", [])


def test_doc_user_clause_role_fixed_only():
    # developer: role-fixed TM (any app); no developer-operated app here → fixed only
    where, params = fp.doc_user_clause("developer", _DOC_USER, _APP_USER)
    assert where == "doc_type IN (?)" and params == ["TM"]
    # sysadmin: role-fixed AG; no sysadmin-operated app → fixed only
    where, params = fp.doc_user_clause("sysadmin", _DOC_USER, _APP_USER)
    assert where == "doc_type IN (?)" and params == ["AG"]


def test_doc_user_clause_delegated_only():
    # clinical-admin: NO role-fixed doc_type, but operator-facing docs (UM/UG) of a clinical-admin
    # app (SD) qualify → delegation only
    where, params = fp.doc_user_clause("clinical-admin", _DOC_USER, _APP_USER)
    assert where == "(doc_type IN (?, ?) AND app_code IN (?))"
    assert params == ["UG", "UM", "SD"]


def test_doc_user_clause_combines_fixed_or_delegated_when_both_apply():
    doc_user = {"TM": "developer", "UM": "operator"}
    app_user = {"OR": "developer"}  # a developer-operated app
    where, params = fp.doc_user_clause("developer", doc_user, app_user)
    assert where == "(doc_type IN (?) OR (doc_type IN (?) AND app_code IN (?)))"
    assert params == ["TM", "UM", "OR"]


def test_doc_user_clause_matches_nothing_when_no_codes_or_apps():
    # business-admin: no role-fixed doc_type and no business-admin-operated app → nothing
    assert fp.doc_user_clause(
        "business-admin", {"UM": "operator", "TM": "developer"}, {"OR": "clinical"}
    ) == ("0", [])
