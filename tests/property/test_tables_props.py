"""Property test for tables_pure.extract_tables idempotency (§6.4/§6.5, §12).

Lifting qualifying tables to CSV and replacing them with a reference link must be idempotent: a
second pass finds no table (the reference link is not a table) and returns the body unchanged."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from vdocs.stages.normalize import tables_pure as tbl


def _pipe_table(n_rows: int, n_cols: int) -> str:
    header = "| " + " | ".join(f"h{c}" for c in range(n_cols)) + " |"
    sep = "| " + " | ".join("---" for _ in range(n_cols)) + " |"
    rows = ["| " + " | ".join(f"r{r}c{c}" for c in range(n_cols)) + " |" for r in range(n_rows)]
    return "\n".join([header, sep, *rows])


@given(n_rows=st.integers(min_value=0, max_value=15), n_cols=st.integers(min_value=1, max_value=10))
def test_extract_tables_is_idempotent(n_rows: int, n_cols: int):
    body = "# Doc\n\n## Data\n\n" + _pipe_table(n_rows, n_cols) + "\n\nAfter the table.\n"
    once, _ = tbl.extract_tables(body)
    twice, again = tbl.extract_tables(once)
    assert twice == once  # second pass changes nothing
    assert again == []  # …and lifts no further tables
