"""Unit tests for server.search_pure — turning free user text into a safe FTS5 query (§14.7)."""

from __future__ import annotations

from vdocs.server import search_pure as sp


def test_fts_match_query_quotes_tokens_and_or_joins_for_recall():
    q = sp.fts_match_query("How does KAAJEE authenticate?")
    # alnum tokens, each quoted (so FTS5 never mis-parses a token as an operator), OR-joined
    assert q == '"How" OR "does" OR "KAAJEE" OR "authenticate"'


def test_fts_match_query_drops_single_chars_and_punctuation():
    # a leading caret (e.g. a global ^DPT) and single chars are stripped to alnum tokens
    assert sp.fts_match_query("^DPT a file #2") == '"DPT" OR "file"'


def test_fts_match_query_empty_when_no_usable_token():
    assert sp.fts_match_query("  ?  ") == ""
    assert sp.fts_match_query("") == ""
