"""Unit tests for the published vocabulary builder (ADR-0001 P2): controlled vocabularies sourced
from the registries (the SSOT), emitted into index.db's `vocab` table so consumers read them as
data instead of hardcoding them — and so `doctor` can gate that every facet value is defined."""

from __future__ import annotations

from vdocs.config import Settings
from vdocs.kernel import vocab


def _rows():
    return vocab.vocab_rows(Settings().registries)


def test_vocab_rows_are_kind_code_label_description_tuples():
    rows = _rows()
    assert rows and all(len(r) == 4 for r in rows)
    kinds = {r[0] for r in rows}
    assert {"function_category", "doc_type", "section", "persona"} <= kinds


def test_function_domains_carry_their_definition():
    rows = {(k, c): (lbl, desc) for k, c, lbl, desc in _rows()}
    lbl, desc = rows[("function_category", "Laboratory")]
    assert lbl == "Laboratory" and "blood bank" in desc
    assert "\n" not in desc  # folded multiline definition collapses to one line


def test_doc_type_label_and_section_and_persona_present():
    rows = {(k, c): (lbl, desc) for k, c, lbl, desc in _rows()}
    assert rows[("doc_type", "UM")][0] == "User Manual"
    sec_label, sec_desc = rows[("section", "CLI")]
    assert sec_label == "Clinical" and "patient-care" in sec_desc
    assert "care staff" in rows[("persona", "clinical")][1]


def test_vocab_rows_are_deterministic():
    assert _rows() == _rows()
