"""Unit tests for the read contract (ADR-0001 P1): the spec is the single source of truth, and the
`v_*` views are GENERATED from it (so they cannot drift), addressable by version, with a declared
capability set."""

from __future__ import annotations

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
    assert rc.version(spec) == "1.0"
    cols = rc.view_columns(spec)
    assert {"v_documents", "v_sections", "v_chunks", "v_entities", "v_entity_mentions"} <= set(cols)
    assert cols["v_documents"][0] == "doc_key"
    assert "fts5" in rc.capabilities(spec)


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
    assert rc.lint_bump(_BASE, _spec("1.1", _PLUS)) == []


def test_additive_without_a_bump_is_flagged():
    problems = rc.lint_bump(_BASE, _spec("1.0", _PLUS))
    assert problems and any("MINOR" in p for p in problems)


def test_removing_a_column_as_a_minor_is_flagged_breaking():
    problems = rc.lint_bump(_BASE, _spec("1.1", _MINUS))
    assert problems and any("MAJOR" in p for p in problems)


def test_breaking_change_with_major_bump_is_clean():
    assert rc.lint_bump(_BASE, _spec("2.0", _MINUS)) == []


def test_column_type_change_is_breaking():
    problems = rc.lint_bump(_BASE, _spec("1.1", [("doc_key", "TEXT"), ("title", "INTEGER")]))
    assert problems and any("MAJOR" in p for p in problems)


def test_removing_a_capability_is_breaking():
    problems = rc.lint_bump(_BASE, _spec("1.1", [("doc_key", "TEXT"), ("title", "TEXT")], caps=()))
    assert problems and any("MAJOR" in p for p in problems)
