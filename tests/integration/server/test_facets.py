"""Integration test for server.facets — faceted (focused) search over a tiny real index.db (LF).

Builds a small documents + chunks_fts + entities surface across several doc_types/packages/personas
(the persona/profile facets are now baked `documents` columns), then asserts the facet catalog and
the layered narrow→content-search behaviour.
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
          pkg_ns TEXT, app_user TEXT, doc_user TEXT, software_class TEXT, function_category TEXT,
          is_latest INTEGER
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
    # (doc_key, doc_id, title, app_code, doc_type, pkg_ns, app_user, doc_user, software_class,
    #  function_category, is_latest) — app_user/doc_user/software_class/function_category baked.
    conn.executemany(
        "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("RA/um", "RA:um", "Radiology User Manual", "RA", "UM", "RA",
             "clinical", "clinical", "I", "Patient Care Services", 1),
            ("XU/tm", "XU:tm", "Kernel Technical Manual", "XU", "TM", "XU",
             "developer", "developer", "I", "Health Informatics", 1),
            ("LR/ug", "LR:ug", "Lab User Guide", "LR", "UG", "LR",
             "clinical", "clinical", "I", "Patient Care Services", 1),
            ("RA/old", "RA:old", "Radiology UM (old)", "RA", "UM", "RA",
             "clinical", "clinical", "I", "Patient Care Services", 0),
        ],
    )  # fmt: skip
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
    # baked persona + profile facets, counted off the columns
    assert dict(cat["app_user"]) == {"clinical": 2, "developer": 1}
    assert dict(cat["doc_user"]) == {"clinical": 2, "developer": 1}
    assert dict(cat["software_class"]) == {"I": 3}
    assert dict(cat["function_category"]) == {"Patient Care Services": 2, "Health Informatics": 1}


def test_faceted_search_narrows_by_doc_type_and_app_then_searches(tmp_path):
    index_db = tmp_path / "index.db"
    _build(index_db)
    res = facets.faceted_search(index_db, doc_type=["UM"], app=["RA"], query="cancel exam")
    assert res["candidate_docs"] == 1
    assert [h["section_id"] for h in res["hits"]] == ["RA/um/cancel"]


def test_faceted_search_doc_user_filters_the_baked_column(tmp_path):
    index_db = tmp_path / "index.db"
    _build(index_db)
    # doc_user=developer → only the Kernel TM (its baked doc_user is developer)
    res = facets.faceted_search(index_db, doc_user=["developer"], query="callable")
    assert res["candidate_docs"] == 1
    assert [h["section_id"] for h in res["hits"]] == ["XU/tm/api"]


def test_faceted_search_doc_user_clinical_matches_the_clinical_docs(tmp_path):
    index_db = tmp_path / "index.db"
    _build(index_db)
    # doc_user=clinical → the clinical UM/UG (latest), not the developer TM
    res = facets.faceted_search(index_db, doc_user=["clinical"])
    assert res["candidate_docs"] == 2  # RA/um + LR/ug (latest), not XU/tm
    assert sorted(h["doc_key"] for h in res["hits"]) == ["LR/ug", "RA/um"]


def test_faceted_search_app_user_narrows_to_operator_apps(tmp_path):
    index_db = tmp_path / "index.db"
    _build(index_db)
    # app_user=developer → docs of developer-operated apps (XU), regardless of doc_type
    res = facets.faceted_search(index_db, app_user=["developer"])
    assert [h["doc_key"] for h in res["hits"]] == ["XU/tm"]


def test_faceted_search_function_category_facet(tmp_path):
    index_db = tmp_path / "index.db"
    _build(index_db)
    res = facets.faceted_search(index_db, function_category=["Patient Care Services"])
    assert sorted(h["doc_key"] for h in res["hits"]) == ["LR/ug", "RA/um"]


def test_faceted_search_software_class_facet(tmp_path):
    index_db = tmp_path / "index.db"
    _build(index_db)
    res = facets.faceted_search(index_db, software_class=["I"])
    assert res["candidate_docs"] == 3  # all three latest docs are Class I


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
