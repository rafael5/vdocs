"""Integration test for server.facets — faceted (focused) search over a tiny real index.db (LF).

Builds a small documents + chunks_fts + entities surface across several doc_types/packages, then
asserts the facet catalog and the layered narrow→content-search behaviour.
"""

from __future__ import annotations

from vdocs.kernel import db
from vdocs.server import facets


def _build(index_db):
    conn = db.connect(index_db)
    conn.executescript(
        """
        CREATE TABLE documents (
          doc_key TEXT PRIMARY KEY, doc_id TEXT, title TEXT, app_code TEXT, doc_type TEXT,
          pkg_ns TEXT, is_latest INTEGER
        );
        CREATE VIRTUAL TABLE chunks_fts USING fts5(
          chunk_id UNINDEXED, section_id UNINDEXED, doc_key UNINDEXED, title, doc_title,
          section_path, body
        );
        CREATE TABLE entities (entity_id TEXT PRIMARY KEY, type TEXT, canonical_name TEXT,
          mention_count INTEGER);
        CREATE TABLE entity_mentions (entity_id TEXT, doc_key TEXT, section_id TEXT);
        """
    )
    conn.executemany(
        "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("RA/um", "RA:um", "Radiology User Manual", "RA", "UM", "RA", 1),
            ("XU/tm", "XU:tm", "Kernel Technical Manual", "XU", "TM", "XU", 1),
            ("LR/ug", "LR:ug", "Lab User Guide", "LR", "UG", "LR", 1),
            ("RA/old", "RA:old", "Radiology UM (old)", "RA", "UM", "RA", 0),
        ],
    )
    conn.executemany(
        "INSERT INTO chunks_fts "
        "(chunk_id, section_id, doc_key, title, doc_title, section_path, body) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("RA/um/cx", "RA/um/cancel", "RA/um", "Cancel an Exam", "Radiology User Manual", "RA",
             "How to cancel a radiology exam or request."),
            ("XU/tm/api", "XU/tm/api", "XU/tm", "Callable API", "Kernel Technical Manual", "XU",
             "Kernel callable entry points and routines."),
            ("LR/ug/au", "LR/ug/audit", "LR/ug", "File 60 Audit", "Lab User Guide", "LR",
             "Audit changes to the Laboratory Test file."),
        ],
    )  # fmt: skip
    conn.execute("INSERT INTO entities VALUES ('fileman_file:60','fileman_file','60',1)")
    conn.execute("INSERT INTO entity_mentions VALUES ('fileman_file:60','LR/ug','LR/ug/audit')")
    conn.commit()
    conn.close()


def test_facet_catalog_counts_latest_docs_by_facet(tmp_path):
    index_db = tmp_path / "index.db"
    _build(index_db)
    cat = facets.facet_catalog(index_db)
    assert dict(cat["doc_type"]) == {"UM": 1, "TM": 1, "UG": 1}  # old RA/um excluded (is_latest=0)
    assert dict(cat["app_code"]) == {"RA": 1, "XU": 1, "LR": 1}
    assert ("fileman_file", 1) in cat["entity_type"]
    # persona facets exist (values depend on app-profiles; just assert the keys are present)
    assert "app_user" in cat and "doc_user" in cat


def test_faceted_search_narrows_by_doc_type_and_app_then_searches(tmp_path):
    index_db = tmp_path / "index.db"
    _build(index_db)
    res = facets.faceted_search(index_db, doc_type=["UM"], app=["RA"], query="cancel exam")
    assert res["candidate_docs"] == 1
    assert [h["section_id"] for h in res["hits"]] == ["RA/um/cancel"]


def test_faceted_search_doc_user_developer_resolves_role_fixed_doc_types(tmp_path):
    index_db = tmp_path / "index.db"
    _build(index_db)
    # doc_user=developer → role-fixed TM (any app); only the Kernel TM qualifies
    res = facets.faceted_search(
        index_db,
        doc_user="developer",
        query="callable",
        doc_user_map={"TM": "developer", "UM": "operator", "UG": "operator"},
        app_user_map={"RA": "clinical", "XU": "developer", "LR": "clinical"},
    )
    assert res["candidate_docs"] == 1
    assert [h["section_id"] for h in res["hits"]] == ["XU/tm/api"]


def test_faceted_search_doc_user_delegates_operator_docs_to_app_user(tmp_path):
    index_db = tmp_path / "index.db"
    _build(index_db)
    # doc_user=clinical → operator-facing UM/UG of clinical-operated apps (RA, LR), not the TM
    res = facets.faceted_search(
        index_db,
        doc_user="clinical",
        doc_user_map={"TM": "developer", "UM": "operator", "UG": "operator"},
        app_user_map={"RA": "clinical", "XU": "developer", "LR": "clinical"},
    )
    assert res["candidate_docs"] == 2  # RA/um + LR/ug (latest), not XU/tm
    assert sorted(h["doc_key"] for h in res["hits"]) == ["LR/ug", "RA/um"]


def test_faceted_search_app_user_narrows_to_operator_apps(tmp_path):
    index_db = tmp_path / "index.db"
    _build(index_db)
    # app_user=developer → docs of developer-operated apps (XU), regardless of doc_type
    res = facets.faceted_search(
        index_db,
        app_user="developer",
        app_user_map={"RA": "clinical", "XU": "developer", "LR": "clinical"},
    )
    assert [h["doc_key"] for h in res["hits"]] == ["XU/tm"]


def test_faceted_search_entity_facet_restricts_to_mentioning_docs(tmp_path):
    index_db = tmp_path / "index.db"
    _build(index_db)
    res = facets.faceted_search(index_db, entity="fileman_file:60", query="audit")
    assert res["candidate_docs"] == 1
    assert [h["section_id"] for h in res["hits"]] == ["LR/ug/audit"]


def test_faceted_search_no_query_browses_the_narrowed_docs(tmp_path):
    index_db = tmp_path / "index.db"
    _build(index_db)
    res = facets.faceted_search(index_db, app=["RA"])  # latest only → one doc
    assert res["candidate_docs"] == 1
    assert [h["doc_key"] for h in res["hits"]] == ["RA/um"]


def test_default_doc_user_loads_the_registry():
    du = facets.default_doc_user()
    assert du.get("TM") == "developer" and du.get("UM") == "operator"


def test_default_app_user_loads_the_registry():
    au = facets.default_app_user()
    # a known clinical app from app-profiles (CPRS = OR namespace abbrev)
    assert au and all(v != "needs-review" for v in au.values())
