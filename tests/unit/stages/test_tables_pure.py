"""Unit tests for tables_pure — complex tables → tables/*.csv sidecars (§6.4/§6.5)."""

from __future__ import annotations

from vdocs.stages.normalize import tables_pure as tp


def _html_table(n_rows, n_cols=3, header=("Field", "Type", "Description")):
    head = "".join(f"<th>{h}</th>" for h in header[:n_cols])
    rows = [f"<tr>{head}</tr>"]
    for i in range(n_rows):
        cells = "".join(f"<td>r{i}c{c}</td>" for c in range(n_cols))
        rows.append(f"<tr>{cells}</tr>")
    return "<table>" + "".join(rows) + "</table>"


def _pipe_table(n_data_rows, n_cols=3):
    header = "| " + " | ".join(f"H{c}" for c in range(n_cols)) + " |"
    sep = "|" + "|".join(["---"] * n_cols) + "|"
    rows = [header, sep]
    for i in range(n_data_rows):
        rows.append("| " + " | ".join(f"r{i}c{c}" for c in range(n_cols)) + " |")
    return "\n".join(rows)


def test_large_html_table_extracted_to_csv_with_reference():
    body = f"# Doc\n\nIntro.\n\n{_html_table(12)}\n\nOutro.\n"
    cleaned, tables = tp.extract_tables(body)
    assert len(tables) == 1
    t = tables[0]
    assert t.name == "table-01.csv"
    # CSV carries the header + every data row (kernel/csv serialisation)
    assert t.csv_text.splitlines()[0] == "Field,Type,Description"
    assert "r0c0,r0c1,r0c2" in t.csv_text
    assert t.csv_text.count("\n") >= 12  # header + 12 data rows
    # the table is replaced in the body by a reference link to the sidecar
    assert "<table" not in cleaned
    assert "[" in cleaned and "(tables/table-01.csv)" in cleaned
    assert "Intro." in cleaned and "Outro." in cleaned


def test_small_table_left_inline_not_extracted():
    # §6.5 don't over-decompose: a short, narrow table reads fine inline → stays GFM/HTML
    body = f"# Doc\n\n{_html_table(3)}\n"
    cleaned, tables = tp.extract_tables(body)
    assert tables == []
    assert cleaned == body  # untouched


def test_large_pipe_table_extracted():
    body = f"# Doc\n\n{_pipe_table(11)}\n\nAfter.\n"
    cleaned, tables = tp.extract_tables(body)
    assert len(tables) == 1
    assert tables[0].name == "table-01.csv"
    assert tables[0].csv_text.splitlines()[0] == "H0,H1,H2"
    assert "(tables/table-01.csv)" in cleaned
    assert "| r0c0 |" not in cleaned  # the pipe-table rows are gone from the body


def test_wide_short_table_qualifies_on_columns():
    # few rows but very wide (cols >= 8) → extract (an inline 8-wide table is unreadable)
    body = f"# Doc\n\n{_html_table(3, n_cols=8, header=tuple(f'H{i}' for i in range(8)))}\n"
    _, tables = tp.extract_tables(body)
    assert len(tables) == 1


def test_multiple_tables_numbered_in_document_order():
    body = f"# Doc\n\n{_html_table(12)}\n\nmiddle\n\n{_pipe_table(11)}\n"
    cleaned, tables = tp.extract_tables(body)
    assert [t.name for t in tables] == ["table-01.csv", "table-02.csv"]
    assert "(tables/table-01.csv)" in cleaned and "(tables/table-02.csv)" in cleaned


def test_extract_tables_is_idempotent():
    body = f"# Doc\n\n{_html_table(12)}\n\n{_pipe_table(11)}\n"
    cleaned, tables = tp.extract_tables(body)
    again, tables2 = tp.extract_tables(cleaned)
    assert tables2 == []  # the references are not tables → nothing left to extract
    assert again == cleaned


def test_no_tables_is_noop():
    body = "# Doc\n\nJust prose, no tables here.\n"
    cleaned, tables = tp.extract_tables(body)
    assert cleaned == body and tables == []


def test_header_only_table_is_not_extracted():
    # a degenerate table with no data rows (and not wide) never qualifies
    body = "# Doc\n\n<table><tr><th>A</th><th>B</th></tr></table>\n"
    cleaned, tables = tp.extract_tables(body)
    assert tables == [] and cleaned == body


def test_duplicate_header_columns_are_uniquified_in_csv():
    rows = "".join(f"<tr><td>n{i}</td><td>m{i}</td><td>t{i}</td></tr>" for i in range(12))
    body = "# Doc\n\n<table><tr><th>Name</th><th>Name</th><th>Type</th></tr>" + rows + "</table>\n"
    _, tables = tp.extract_tables(body)
    assert tables[0].csv_text.splitlines()[0] == "Name,Name_1,Type"  # dupe header suffixed
