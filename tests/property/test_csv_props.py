"""Property test for kernel.csv.to_csv — round-trip with adversarial cells (§12).

The fixed-example tests never feed cells containing the delimiter, embedded quotes, or newlines —
exactly the inputs that break naive CSV serialisation. This drives those through ``to_csv`` and
reads them back, asserting nothing is lost or mangled."""

from __future__ import annotations

import csv
import io

from hypothesis import given
from hypothesis import strategies as st

from vdocs.kernel.csv import to_csv

# Adversarial cell text: commas, quotes, newlines, tabs — but no NUL (csv rejects it) and no
# surrogate code points (not encodable). Bytes that csv genuinely round-trips.
_cell = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
    max_size=25,
)


@given(rows=st.lists(st.lists(_cell, min_size=1, max_size=4), min_size=1, max_size=6))
def test_to_csv_round_trips_adversarial_cells(rows: list[list[str]]):
    ncols = max(len(r) for r in rows)
    columns = [f"c{i}" for i in range(ncols)]
    dicts = [{columns[i]: (r[i] if i < len(r) else "") for i in range(ncols)} for r in rows]

    text = to_csv(columns, dicts)

    reader = csv.DictReader(io.StringIO(text, newline=""))
    back = list(reader)
    assert [[d[c] for c in columns] for d in back] == [[d[c] for c in columns] for d in dicts]
