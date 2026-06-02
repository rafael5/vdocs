"""CSV-table serialisation — the single shared implementation (design §9.2/§11).

The inventory-medallion stages (``crawl``/``catalog``/``serve-inventory``) each publish a
human-browsable flat ``.csv`` alongside their JSON. The row-building is stage-specific (different
sources, different column mappings), but the serialisation mechanics — header + ordered cells,
tolerate extra keys from ``model_dump()`` — are one primitive shared here, not copy-pasted per
stage (§11: a primitive used by ≥2 stages lives in the kernel). Pure: no I/O, no logging.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Mapping, Sequence


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
