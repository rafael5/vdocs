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
