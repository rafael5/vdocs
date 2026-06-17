"""Integration test for server.search.lexical_search — FTS5 over a tiny real index.db (§14.7).

Builds the `chunks_fts` + `documents` surface `index` produces, then asserts the search returns
ranked, pre-cited hits (stable section_id, resolved gold body_path, snippet) and honours the
structured app pre-filter.
"""

from __future__ import annotations

from vdocs.kernel import db
from vdocs.server import search


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
        """
    )
    conn.executemany(
        "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("CPRS/or_um", "CPRS:or_um", "OR User Manual", "CPRS", "UM", "OR", 1),
            ("KAAJEE/dibr", "KAAJEE:dibr", "KAAJEE DIBR", "KAAJEE", "", "", 1),
        ],
    )
    conn.executemany(
        "INSERT INTO chunks_fts "
        "(chunk_id, section_id, doc_key, title, doc_title, section_path, body) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("CPRS/or_um/auth", "CPRS/or_um/auth", "CPRS/or_um", "Authentication", "OR User Manual",
             "OR", "KAAJEE handles user authentication and single sign-on tokens."),
            ("KAAJEE/dibr/intro", "KAAJEE/dibr/intro", "KAAJEE/dibr", "Introduction", "KAAJEE DIBR",
             "KAAJEE", "KAAJEE is the Kernel Authentication and Authorization broker."),
        ],
    )  # fmt: skip
    conn.commit()
    conn.close()


def test_lexical_search_returns_pre_cited_ranked_hits(tmp_path):
    index_db = tmp_path / "index.db"
    _build(index_db)
    hits = search.lexical_search(index_db, "KAAJEE authentication", k=5)
    assert hits, "expected at least one hit"
    top = hits[0]
    assert top["section_id"].startswith(("CPRS/or_um", "KAAJEE/dibr"))
    assert top["uri"] == f"vdocs://section/{top['section_id']}"
    assert top["body_path"].startswith("documents/gold/consolidated/")
    assert "[" in top["snippet"] and "]" in top["snippet"]  # match is highlighted
    assert hits == sorted(hits, key=lambda h: -h["score"])  # ranked, best first


def test_lexical_search_app_prefilter(tmp_path):
    index_db = tmp_path / "index.db"
    _build(index_db)
    hits = search.lexical_search(index_db, "KAAJEE authentication", k=5, app=["KAAJEE"])
    assert hits and all(h["app_code"] == "KAAJEE" for h in hits)


def test_lexical_search_empty_query_returns_nothing(tmp_path):
    index_db = tmp_path / "index.db"
    _build(index_db)
    assert search.lexical_search(index_db, "   ?  ", k=5) == []


def _seed_entity_skl(index_db, rows):
    """Add the merge-owned entity_skl table (canonical, canonical_name) skl_expansions reads."""
    conn = db.connect(index_db)
    conn.execute(
        "CREATE TABLE entity_skl (entity_id TEXT PRIMARY KEY, node_id TEXT, "
        "type TEXT, canonical TEXT, canonical_name TEXT)"
    )
    conn.executemany("INSERT INTO entity_skl VALUES (?, ?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()


def test_skl_expansions_reads_entity_skl_and_is_empty_when_absent(tmp_path):
    index_db = tmp_path / "index.db"
    _build(index_db)
    # no entity_skl table yet → no-op (back-compat with a pre-merge index.db)
    assert search.skl_expansions(str(index_db)) == {}
    _seed_entity_skl(
        index_db,
        [("fileman_file:200", "fileman_file/200", "fileman_file", "200", "NEW PERSON")],
    )
    search.skl_expansions.cache_clear()
    assert search.skl_expansions(str(index_db)) == {"200": "NEW PERSON"}


def test_lexical_search_uses_skl_expansion_by_default(tmp_path):
    # a query naming the file by its NUMBER finds the chunk that only spells the NAME (S3.4 fix):
    # the SKL expands "200" → the phrase "new person".
    index_db = tmp_path / "index.db"
    _build(index_db)
    conn = db.connect(index_db)
    conn.execute(
        "INSERT INTO chunks_fts (chunk_id, section_id, doc_key, title, doc_title, section_path, "
        "body) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("DI/fm/np", "DI/fm/np", "KAAJEE/dibr", "Users", "FileMan", "DI",
         "The NEW PERSON file holds every user account."),
    )  # fmt: skip
    conn.commit()
    conn.close()
    _seed_entity_skl(
        index_db,
        [("fileman_file:200", "fileman_file/200", "fileman_file", "200", "NEW PERSON")],
    )
    search.skl_expansions.cache_clear()
    # the bare number names the entity but appears nowhere in the name-only chunk:
    # without expansion (opt out) it never reaches it
    off = search.lexical_search(index_db, "200", k=5, expansions={})
    assert not any(h["section_id"] == "DI/fm/np" for h in off)
    # default (None) → SKL expansion on → "200" expands to "new person" → the chunk is retrievable
    on = search.lexical_search(index_db, "200", k=5)
    assert any(h["section_id"] == "DI/fm/np" for h in on)
