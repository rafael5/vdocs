"""Unit tests for server.search_pure — ranking weights and expansion maps (§14.7). The query
reader has its own file, test_query_reader.py, driven by contracts/query/v1.json."""

from __future__ import annotations

from vdocs.server import search_pure as sp


def test_bm25_weights_orders_by_column_and_defaults_unspecified_to_one():
    cols = ("chunk_id", "section_id", "doc_key", "title", "section_path", "body")
    w = sp.bm25_weights(cols, {"title": 8.0, "section_path": 4.0, "body": 1.0})
    # one weight per column, in column order; cols not in the map default to 1.0
    assert w == [1.0, 1.0, 1.0, 8.0, 4.0, 1.0]


def test_bm25_weights_module_defaults_favor_title_over_body():
    w = sp.bm25_weights()
    assert len(w) == len(sp.FTS_COLUMNS)
    # title/section_path outweigh body so a doc-defining token in the heading wins (L1.1)
    assert w[sp.FTS_COLUMNS.index("title")] > w[sp.FTS_COLUMNS.index("body")]
    assert w[sp.FTS_COLUMNS.index("section_path")] > w[sp.FTS_COLUMNS.index("body")]


def test_bm25_expr_is_a_weighted_bm25_call_in_column_order():
    expr = sp.bm25_expr("chunks_fts", ("title", "body"), {"title": 8.0, "body": 1.0})
    assert expr == "bm25(chunks_fts, 8.0, 1.0)"


def test_skl_expansion_map_maps_distinctive_number_to_its_name_phrase():
    # SKL entity identity rows (canonical, canonical_name): a file *number* → its spelled-out name,
    # so a query "file #200" expands to the precise phrase "new person" (S3.4 vocabulary mismatch).
    rows = [("200", "NEW PERSON"), ("442", "TORS LOG")]
    assert sp.skl_expansion_map(rows) == {"200": "NEW PERSON", "442": "TORS LOG"}


def test_skl_expansion_map_drops_short_keys_and_single_word_names():
    # guarded: a <3-char key (the matcher ignores it) and a 1-word name (a bare common word
    # like "FILE" must never become an expansion) are both excluded.
    rows = [("1", "FILE"), ("19", "OPTION"), ("200", "NEW PERSON")]
    assert sp.skl_expansion_map(rows) == {"200": "NEW PERSON"}


def test_skl_expansion_map_drops_decimal_keys_that_cannot_match_a_token():
    # FTS tokenises on '.', so a decimal file number like "1.2" can never be a single query token —
    # keeping it would be a dead (and confusing) entry.
    rows = [("1.2", "ALTERNATE EDITOR"), ("200", "NEW PERSON")]
    assert sp.skl_expansion_map(rows) == {"200": "NEW PERSON"}
