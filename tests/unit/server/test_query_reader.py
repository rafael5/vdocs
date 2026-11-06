"""Fix 2 of the keyword-search proposal: one query reader, the same rules in every front door.

The rules and their cases live in contracts/query/v1.json, which vdocs-web and vdocs-cli copy and
run too. This file runs every case against vdocs's reader, checks each expected expression is valid
FTS5, and checks the one vdocs-only behaviour: today's SKL expansion (file 200 → NEW PERSON)
attaches to its own term until fix 3 replaces it with the synonym table.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from vdocs.server import search_pure as sp

CASES = json.loads(
    (Path(__file__).resolve().parents[3] / "contracts/query/v1.json").read_text(encoding="utf-8")
)["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["why"] for c in CASES])
def test_every_contract_case(case: dict) -> None:
    got = sp.read_query(case["query"])
    assert (got.all, got.any) == (case["all"], case["any"])


@pytest.mark.parametrize("case", CASES, ids=[c["why"] for c in CASES])
def test_every_expected_expression_is_valid_fts5(case: dict) -> None:
    con = sqlite3.connect(":memory:")
    con.execute("CREATE VIRTUAL TABLE t USING fts5(body)")
    for expr in (case["all"], case["any"]):
        if expr:
            con.execute("SELECT * FROM t WHERE t MATCH ?", (expr,)).fetchall()  # raises if invalid


def test_skl_expansion_attaches_to_its_own_term() -> None:
    got = sp.read_query("file #200", {"200": "NEW PERSON"})
    assert got.all == '"file" AND ("200" OR "new person")'
    assert got.any == '"file" OR ("200" OR "new person")'


def test_a_quoted_term_is_never_expanded() -> None:
    assert sp.read_query('"200" file', {"200": "NEW PERSON"}).all == '"200" AND "file"'


def test_short_terms_and_multi_run_terms_are_not_expanded() -> None:
    exp = {"DD": "DATA DICTIONARY", "GET1 DIQ": "SHOULD NOT MATCH"}
    assert sp.read_query("DD $$GET1^DIQ", exp).all == '"DD" AND "GET1 DIQ"'
