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


def _seed_search_synonyms(index_db, rows):
    """Add the merge-filled search_synonyms table and its v_search_synonyms view (contract 1.8)."""
    conn = db.connect(index_db)
    conn.executescript(
        """
        CREATE TABLE search_synonyms (seq INTEGER PRIMARY KEY, term TEXT NOT NULL,
          alternative TEXT NOT NULL, match_case INTEGER NOT NULL, source TEXT NOT NULL);
        CREATE VIEW v_search_synonyms AS
          SELECT seq, term, alternative, match_case, source FROM search_synonyms;
        """
    )
    conn.executemany(
        "INSERT INTO search_synonyms VALUES (?, ?, ?, ?, ?)",
        [(i, *r) for i, r in enumerate(rows)],
    )
    conn.commit()
    conn.close()


def test_search_synonyms_reads_the_table_and_is_empty_when_absent(tmp_path):
    index_db = tmp_path / "index.db"
    _build(index_db)
    # an index.db from before contract 1.8 has no table: no expansion
    assert search.search_synonyms(str(index_db)) == search.sp.NO_SYNONYMS
    _seed_search_synonyms(
        index_db,
        [("200", "NEW PERSON", 0, "skl"), ("KAAJEE", "Kernel Authentication", 1, "application")],
    )
    search.search_synonyms.cache_clear()
    syn = search.search_synonyms(str(index_db))
    assert syn.folded == {"200": ("NEW PERSON",)}
    assert syn.exact == {"KAAJEE": ("Kernel Authentication",)}


def test_lexical_search_applies_the_synonym_table_by_default(tmp_path):
    # a query naming the file by its NUMBER finds the chunk that only spells the NAME: the table
    # expands "200" → "NEW PERSON" (the SKL's file name, now a row of the one synonym table).
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
    _seed_search_synonyms(index_db, [("200", "NEW PERSON", 0, "skl")])
    search.search_synonyms.cache_clear()
    off = search.lexical_search(index_db, "200", k=5, synonyms=search.sp.NO_SYNONYMS)
    assert not any(h["section_id"] == "DI/fm/np" for h in off)
    on = search.lexical_search(index_db, "200", k=5)
    assert any(h["section_id"] == "DI/fm/np" for h in on)
    # quoted text is exact: never expanded
    assert not any(h["section_id"] == "DI/fm/np" for h in search.lexical_search(index_db, '"200"'))


# --- fix 2 (keyword-search proposal): every keyword must appear; any-word fallback, flagged -------
def _ids(hits):
    return sorted(h["section_id"] for h in hits)


def test_keyword_search_requires_every_keyword(tmp_path):
    index_db = tmp_path / "index.db"
    _build(index_db)
    res = search.keyword_search(index_db, "KAAJEE broker", k=5, synonyms=search.sp.NO_SYNONYMS)
    assert _ids(res.hits) == ["KAAJEE/dibr/intro"]  # the CPRS passage has no "broker"
    assert res.any_word is False


def test_keyword_search_falls_back_to_any_keyword_and_says_so(tmp_path):
    index_db = tmp_path / "index.db"
    _build(index_db)
    # "tokens" is only in the CPRS passage and "broker" only in the KAAJEE one
    res = search.keyword_search(index_db, "tokens broker", k=5, synonyms=search.sp.NO_SYNONYMS)
    assert _ids(res.hits) == ["CPRS/or_um/auth", "KAAJEE/dibr/intro"]
    assert res.any_word is True


def test_a_typed_operator_turns_the_fallback_off(tmp_path):
    index_db = tmp_path / "index.db"
    _build(index_db)
    res = search.keyword_search(index_db, "tokens AND broker", k=5, synonyms=search.sp.NO_SYNONYMS)
    assert res.hits == [] and res.any_word is False


def test_not_excludes_a_keyword(tmp_path):
    index_db = tmp_path / "index.db"
    _build(index_db)
    hits = search.lexical_search(index_db, "KAAJEE NOT broker", k=5, synonyms=search.sp.NO_SYNONYMS)
    assert _ids(hits) == ["CPRS/or_um/auth"]


def test_a_quoted_phrase_must_appear_as_typed(tmp_path):
    index_db = tmp_path / "index.db"
    _build(index_db)
    assert _ids(
        search.lexical_search(index_db, '"single sign-on"', k=5, synonyms=search.sp.NO_SYNONYMS)
    ) == ["CPRS/or_um/auth"]
    assert (
        search.lexical_search(index_db, '"sign-on single"', k=5, synonyms=search.sp.NO_SYNONYMS)
        == []
    )


def test_the_envelope_notes_the_fallback_only_when_it_ran():
    assert "note" not in search.search_envelope([{"section_id": "x"}])
    noted = search.search_envelope([{"section_id": "x"}], any_word=True)
    assert noted["note"] == search.ANY_WORD_NOTE
    assert "warning" not in noted
