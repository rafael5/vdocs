"""Unit tests for stages.publish.tables_pure — materialize the gold table CSV sidecars into the
fileman-docs master (FileMan docs-as-code pilot, L1.3; see the impl plan in docs/).

Gold renders every table as a dead `_[Table N](tables/table-NN.csv)_` link (defect D-5). This pure
transform classifies each table (§4 of the master-publication proposal): narrative → inline GFM;
reference data → an authoritative `data/*.yml` record set PLUS a rendered GFM table (drift-gated).
Pure: parsed rows (+ context) → a MaterializedTable.
"""

from __future__ import annotations

from vdocs.stages.publish import tables_pure as t

_REF_HEADER = [["Global", "Description"], ["**^DD**", "Dictionaries"], ["**^DDA**", "Audit trail"]]
_NARRATIVE = [["Step", "Action"], ["1", "Select the option"], ["2", "Enter data"]]


# --- classification (the §4 signals) -----------------------------------------------------------
def test_reference_by_header_keyword():
    assert t.classify(_REF_HEADER) == "reference"  # "Global" is a VistA reference-shape header


def test_reference_by_row_count():
    rows = [["A", "B"]] + [[f"r{i}", "x"] for i in range(13)]  # 13 data rows ≥ threshold
    assert t.classify(rows) == "reference"


def test_narrative_small_non_reference_table():
    assert t.classify(_NARRATIVE) == "narrative"


# --- GFM rendering -----------------------------------------------------------------------------
def test_render_gfm_has_header_separator_and_preserves_inline_markdown():
    gfm = t.render_gfm(_REF_HEADER)
    lines = gfm.splitlines()
    assert lines[0] == "| Global | Description |"
    assert lines[1] == "| --- | --- |"
    assert "| **^DD** | Dictionaries |" in lines  # inline markdown kept (renderInline)


def test_render_gfm_escapes_pipe_in_cells():
    gfm = t.render_gfm([["H"], ["a | b"]])
    assert r"a \| b" in gfm


def test_render_gfm_pads_ragged_rows_to_header_width():
    gfm = t.render_gfm([["A", "B", "C"], ["only one"]])
    assert "| only one |  |  |" in gfm


# --- materialize: reference → records + gfm; narrative → gfm only ------------------------------
def test_materialize_reference_emits_records_and_gfm():
    m = t.materialize(_REF_HEADER)
    assert m.kind == "reference"
    assert m.records == [
        {"Global": "**^DD**", "Description": "Dictionaries"},
        {"Global": "**^DDA**", "Description": "Audit trail"},
    ]
    assert m.gfm.startswith("| Global | Description |")


def test_materialize_narrative_has_no_records():
    m = t.materialize(_NARRATIVE)
    assert m.kind == "narrative"
    assert m.records is None
    assert "| Step | Action |" in m.gfm


def test_materialize_flags_ragged():
    assert t.materialize([["A", "B"], ["x"]]).ragged is True
    assert t.materialize(_NARRATIVE).ragged is False


def test_empty_table_is_narrative_and_safe():
    m = t.materialize([])
    assert m.kind == "narrative"
    assert m.records is None
    assert m.gfm == ""


def test_deterministic():
    assert t.materialize(_REF_HEADER) == t.materialize(_REF_HEADER)
