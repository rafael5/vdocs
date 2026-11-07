"""Fix 2 of the keyword-search proposal: one query reader, the same rules in every front door.

The rules and their cases live in contracts/query/v1.json, which vdocs-web and vdocs-cli copy and
run too. This file runs every case against vdocs's reader, with and without the contract's fixed
synonym table (fix 3), and checks each expected expression is valid FTS5.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from vdocs.server import search_pure as sp

CONTRACT = json.loads(
    (Path(__file__).resolve().parents[3] / "contracts/query/v1.json").read_text(encoding="utf-8")
)
CASES = CONTRACT["cases"]
SYN = CONTRACT["synonyms"]
TABLE = sp.synonyms_from_rows((r["term"], r["alternative"], r["match_case"]) for r in SYN["table"])


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


@pytest.mark.parametrize("case", SYN["cases"], ids=[c["why"] for c in SYN["cases"]])
def test_every_synonym_case(case: dict) -> None:
    got = sp.read_query(case["query"], TABLE)
    assert (got.all, got.any) == (case["all"], case["any"])


@pytest.mark.parametrize("case", SYN["cases"], ids=[c["why"] for c in SYN["cases"]])
def test_every_synonym_expression_is_valid_fts5(case: dict) -> None:
    test_every_expected_expression_is_valid_fts5(case)


def test_an_empty_table_expands_nothing() -> None:
    assert sp.read_query("blood bank", sp.NO_SYNONYMS).all == '"blood" AND "bank"'
