"""CSV-table serialisation — the single shared implementation (design §9.2/§11).

The inventory-medallion stages (``crawl``/``catalog``/``serve-inventory``) each publish a
human-browsable flat ``.csv`` alongside their JSON. The row-building is stage-specific (different
sources, different column mappings), but the serialisation mechanics — header + ordered cells,
tolerate extra keys from ``model_dump()`` — are one primitive shared here, not copy-pasted per
stage (§11: a primitive used by ≥2 stages lives in the kernel). ``to_csv`` is pure; ``read_rows``
is the one I/O function (a tolerant reader for the extracted ``tables/*.csv`` sidecars).
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path


def to_csv(
    columns: Sequence[str],
    rows: Iterable[Mapping[str, object]],
    *,
    strict: bool = False,
) -> str:
    """Render ``rows`` as a CSV string: a header line of ``columns`` then one line per row,
    cells emitted in ``columns`` order. Keys absent from ``columns`` are dropped (so a Pydantic
    ``model_dump()`` can be passed whole); missing keys yield blank cells. Set ``strict=True`` to
    raise on any extra key (``csv.DictWriter``'s ``extrasaction='raise'``)."""
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf, fieldnames=list(columns), extrasaction="raise" if strict else "ignore"
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def read_rows(path: Path) -> list[list[str]]:
    """Read a CSV file into a list of rows (each a list of cell strings); ``[]`` if it is missing
    or unreadable. The tolerant counterpart to :func:`to_csv`, shared by the stages that scan
    extracted ``tables/*.csv`` sidecars (``index``, ``manifest``) so the open-and-swallow
    boilerplate lives once (§9.2) — a malformed/binary sidecar must never abort the caller."""
    if not path.is_file():
        return []
    try:
        with path.open(newline="", encoding="utf-8") as fh:
            return list(csv.reader(fh))
    except (OSError, UnicodeDecodeError, csv.Error):
        return []
