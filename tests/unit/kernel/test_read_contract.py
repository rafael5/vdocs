"""Unit tests for the read contract (ADR-0001 P1): the spec is the single source of truth, and the
`v_*` views are GENERATED from it (so they cannot drift), addressable by version, with a declared
capability set."""

from __future__ import annotations

from pathlib import Path

from vdocs.kernel import read_contract as rc

_SPEC = {
    "read_schema_version": "1.0",
    "views": {
        "v_documents": {
            "source": "documents",
            "columns": {
                "doc_key": {"type": "TEXT", "nullable": False},
                "title": {"type": "TEXT", "nullable": True},
                "is_latest": {"type": "INTEGER", "nullable": False},
            },
        },
        "v_entities": {
            "source": "entities",
            "columns": {"entity_id": {"type": "TEXT", "nullable": False}},
        },
    },
    "capabilities": ["fts5", "pub_year"],
}


def test_view_ddl_generates_a_create_view_per_view_in_column_order():
    ddl = rc.view_ddl(_SPEC)
    assert "CREATE VIEW v_documents AS SELECT doc_key, title, is_latest FROM documents;" in ddl
    assert "CREATE VIEW v_entities AS SELECT entity_id FROM entities;" in ddl


def test_view_columns_maps_view_to_ordered_column_names():
    cols = rc.view_columns(_SPEC)
    assert cols["v_documents"] == ["doc_key", "title", "is_latest"]
    assert cols["v_entities"] == ["entity_id"]


def test_version_and_capabilities_read_from_spec():
    assert rc.version(_SPEC) == "1.0"
    assert rc.capabilities(_SPEC) == ["fts5", "pub_year"]


def test_load_reads_the_real_v1_contract():
    # the shipped contract parses and declares the views consumers bind to
    spec = rc.load(rc.contract_path())
    assert rc.version(spec) == "1.8"
    cols = rc.view_columns(spec)
    expected = {"v_documents", "v_sections", "v_chunks", "v_entities", "v_entity_mentions"}
    assert expected <= set(cols) and "v_vocab" in cols
    assert cols["v_documents"][0] == "doc_key"
    assert {"fts5", "vocab_table"} <= set(rc.capabilities(spec))


# --- P1.6: contract-lint — the semver bump-type guard (no breaking change as a MINOR) ------------


def _spec(version, cols, caps=("fts5",)):
    """A one-view spec: cols is a list of (name, type) pairs."""
    return {
        "read_schema_version": version,
        "views": {
            "v_documents": {"source": "documents", "columns": {c: {"type": t} for c, t in cols}}
        },
        "capabilities": list(caps),
    }


_BASE = _spec("1.0", [("doc_key", "TEXT"), ("title", "TEXT")])
_PLUS = [("doc_key", "TEXT"), ("title", "TEXT"), ("pub_year", "TEXT")]  # an added column
_MINUS = [("doc_key", "TEXT")]  # `title` removed → breaking


def test_additive_minor_bump_is_clean():
    assert rc.lint_bump(_BASE, _spec("1.2", _PLUS)) == []


def test_additive_without_a_bump_is_flagged():
    problems = rc.lint_bump(_BASE, _spec("1.0", _PLUS))
    assert problems and any("MINOR" in p for p in problems)


def test_removing_a_column_as_a_minor_is_flagged_breaking():
    problems = rc.lint_bump(_BASE, _spec("1.2", _MINUS))
    assert problems and any("MAJOR" in p for p in problems)


def test_breaking_change_with_major_bump_is_clean():
    assert rc.lint_bump(_BASE, _spec("2.0", _MINUS)) == []


def test_column_type_change_is_breaking():
    problems = rc.lint_bump(_BASE, _spec("1.2", [("doc_key", "TEXT"), ("title", "INTEGER")]))
    assert problems and any("MAJOR" in p for p in problems)


def test_removing_a_capability_is_breaking():
    problems = rc.lint_bump(_BASE, _spec("1.2", [("doc_key", "TEXT"), ("title", "TEXT")], caps=()))
    assert problems and any("MAJOR" in p for p in problems)


# --- 1.6 → 1.7: the inventory view (inventory browser step 1) ---------------------------------
# lint_latest() compares the two highest MAJOR files and is a no-op while only v1.json exists, so
# the MINOR bump is checked against a frozen copy of the 1.6 spec (git show 8e79641:…/v1.json).

_V1_6 = Path(__file__).parents[2] / "fixtures" / "read-contract-v1.6.json"


_V1_7 = Path(__file__).parents[2] / "fixtures" / "read-contract-v1.7.json"


def test_the_inventory_bump_is_a_correctly_sized_minor():
    prev, cur = rc.load(_V1_6), rc.load(_V1_7)
    assert rc.version(prev) == "1.6" and rc.version(cur) == "1.7"
    assert rc.lint_bump(prev, cur) == []


def test_the_same_additions_without_the_bump_would_red():
    cur = rc.load(_V1_7)
    assert rc.lint_bump(rc.load(_V1_6), {**cur, "read_schema_version": "1.6"})


# --- 1.7 → 1.8: the search synonym table (keyword-search proposal, fix 3) ----------------------
# Checked against a frozen copy of the 1.7 spec (git show 3732525:contracts/read/v1.json).


def test_the_search_synonyms_bump_is_a_correctly_sized_minor():
    prev, cur = rc.load(_V1_7), rc.load(rc.contract_path())
    assert rc.version(prev) == "1.7" and rc.version(cur) == "1.8"
    assert rc.lint_bump(prev, cur) == []
    assert "v_search_synonyms" in rc.view_columns(cur)
    assert "search_synonyms" in rc.capabilities(cur)


def test_the_synonym_view_without_the_bump_would_red():
    cur = rc.load(rc.contract_path())
    assert rc.lint_bump(rc.load(_V1_7), {**cur, "read_schema_version": "1.7"})


def test_v_inventory_publishes_the_rows_columns_in_order():
    from vdocs.stages.index.inventory_pure import INVENTORY_COLUMNS

    spec = rc.load(rc.contract_path())
    assert rc.view_columns(spec)["v_inventory"] == list(INVENTORY_COLUMNS)
    assert {"inventory", "last_updated"} <= set(rc.capabilities(spec))
    assert rc.view_columns(spec)["v_documents"][-2:] == ["last_updated", "last_updated_source"]
