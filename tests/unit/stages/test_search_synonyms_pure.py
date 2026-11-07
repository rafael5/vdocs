"""The search synonym table `merge` writes (keyword-search proposal, fix 3).

One table of term → alternatives for every search front door, from the hand-written registry
(`registries/search-synonyms.yaml`: plain-English package names, Kernel parts, judged terms), the
documents' application codes and namespaces with their names, and the SKL's file names. The rules
the readers apply are in `contracts/query/v1.json` (`synonyms`).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from vdocs.stages.merge import merge_pure as mp

VBECS = mp.AppNames(
    code="VBECS",
    name="VistA Blood Establishment Computer Software (VBECS)",
    namespaces=("VBECS", "VBEC"),
)
CPRS = mp.AppNames(
    code="CPRS", name="Computerized Patient Record System", namespaces=("CPRS", "OR")
)
ARWS = mp.AppNames(
    code="AR/WS", name="Pharmacy: Automatic Replenish / Ward Stock", namespaces=("PSGW",)
)
NO_HAND = mp.HandSynonyms(packages={}, kernel_parts=(), terms=())


def _alts(rows: list[mp.SearchSynonymRow], term: str, match_case: int) -> list[str]:
    return [r[2] for r in rows if r[1] == term and r[3] == match_case]


def test_a_plain_name_expands_to_the_package_name_code_and_namespaces() -> None:
    hand = mp.HandSynonyms(packages={"VBECS": ("blood bank",)}, kernel_parts=(), terms=())
    rows, missing = mp.search_synonym_rows([VBECS], hand, [])
    assert _alts(rows, "blood bank", 0) == [
        "VistA Blood Establishment Computer Software",
        "VBECS",
        "VBEC",
    ]
    assert {r[4] for r in rows if r[1] == "blood bank"} == {"package_name"}
    assert missing == []


def test_application_names_are_cleaned_of_prefixes_and_parentheses() -> None:
    rows, _ = mp.search_synonym_rows([ARWS], NO_HAND, [])
    assert _alts(rows, "AR/WS", 1) == ["Automatic Replenish / Ward Stock"]


def test_codes_and_namespaces_expand_to_the_name_but_not_the_name_to_them() -> None:
    # measured 2026-11-06 (reports/mcp-review-synonyms.json): a name expanding to its codes
    # ("Laboratory" → LR, LA, Lab) and product abbreviations expanding to their names ("RPC" →
    # Remote Procedure Call Broker) each cost a judged question its place; neither found anything
    # the code → name rows did not
    rows, _ = mp.search_synonym_rows([VBECS], NO_HAND, [])
    name = "VistA Blood Establishment Computer Software"
    assert _alts(rows, "VBECS", 1) == [name]
    assert _alts(rows, "VBEC", 1) == [name]
    assert not [r for r in rows if r[3] == 0]
    assert {r[4] for r in rows} == {"application"}


def test_an_operator_word_is_never_a_term_or_an_alternative() -> None:
    hand = mp.HandSynonyms(packages={"CPRS": ("patient chart",)}, kernel_parts=(), terms=())
    rows, _ = mp.search_synonym_rows([CPRS], hand, [])
    assert not [r for r in rows if r[1].upper() in ("AND", "OR", "NOT")]
    assert not [r for r in rows if r[2].upper() in ("AND", "OR", "NOT")]
    assert _alts(rows, "patient chart", 0) == ["Computerized Patient Record System", "CPRS"]


def test_rows_are_unique_ignoring_case_and_never_map_a_term_to_itself() -> None:
    rows, _ = mp.search_synonym_rows([CPRS, VBECS], NO_HAND, [])
    keys = [(r[1].lower(), r[3], r[2].lower()) for r in rows]
    assert len(keys) == len(set(keys))
    assert not [r for r in rows if r[1].lower() == r[2].lower()]
    assert [r[0] for r in rows] == list(range(len(rows)))  # seq is the table order


def test_kernel_parts_and_judged_terms_keep_their_own_alternatives() -> None:
    hand = mp.HandSynonyms(
        packages={},
        kernel_parts=((("background jobs",), ("TaskMan",)),),
        terms=(("password", ("verify code",), 0), ("DUZ", ("user number",), 1)),
    )
    rows, _ = mp.search_synonym_rows([], hand, [])
    assert _alts(rows, "background jobs", 0) == ["TaskMan"]
    assert _alts(rows, "password", 0) == ["verify code"]
    assert _alts(rows, "DUZ", 1) == ["user number"]
    assert [r[4] for r in rows] == ["kernel_part", "term", "term"]


def test_skl_file_names_keep_only_distinctive_numbers_and_multi_word_names() -> None:
    skl = [("200", "NEW PERSON"), ("1", "FILE"), ("19", "OPTION"), ("1.2", "ALTERNATE EDITOR")]
    rows, _ = mp.search_synonym_rows([], NO_HAND, skl)
    assert [(r[1], r[2], r[3], r[4]) for r in rows] == [("200", "NEW PERSON", 0, "skl")]


def test_a_one_character_term_is_never_written() -> None:
    app = mp.AppNames(code="Q", name="Quality Thing", namespaces=("Q",))
    rows, _ = mp.search_synonym_rows([app], NO_HAND, [])
    assert not [r for r in rows if len(r[1]) < 2]


def test_a_registry_package_with_no_documents_is_reported_not_guessed() -> None:
    hand = mp.HandSynonyms(packages={"GONE": ("vanished",)}, kernel_parts=(), terms=())
    rows, missing = mp.search_synonym_rows([VBECS], hand, [])
    assert missing == ["GONE"]
    assert not _alts(rows, "vanished", 0)


def test_parse_reads_the_three_sections() -> None:
    text = """
version: 1
packages:
  XM: [email, mail messages]
kernel_parts:
  - names: [background jobs]
    alternatives: [TaskMan]
terms:
  - term: password
    alternatives: [verify code]
    fixes: plain-change-password
"""
    hand = mp.parse_search_synonyms(text)
    assert hand.packages == {"XM": ("email", "mail messages")}
    assert hand.kernel_parts == ((("background jobs",), ("TaskMan",)),)
    assert hand.terms == (("password", ("verify code",), 0),)


def test_parse_refuses_a_term_without_the_judged_query_it_fixes() -> None:
    text = "packages: {}\nterms:\n  - term: password\n    alternatives: [verify code]\n"
    with pytest.raises(ValueError, match="password"):
        mp.parse_search_synonyms(text)


# ── the real registry ─────────────────────────────────────────────────────────────────────────────
REGISTRY = Path("registries/search-synonyms.yaml")
GOLDEN = Path("registries/golden-queries.yaml")


def test_the_registry_names_every_application_once() -> None:
    hand = mp.parse_search_synonyms(REGISTRY.read_text(encoding="utf-8"))
    assert len(hand.packages) == 109
    assert all(hand.packages.values())


def test_every_hand_written_term_fixes_a_judged_golden_query() -> None:
    raw = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    golden = {q["id"] for q in yaml.safe_load(GOLDEN.read_text(encoding="utf-8"))["queries"]}
    for t in raw.get("terms") or []:
        assert t["fixes"] in golden, t
