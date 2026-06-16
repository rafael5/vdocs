"""Table materialization for ``export-fileman`` (FileMan docs-as-code pilot, L1.3; see
``docs/fileman-docs-pilot-implementation-plan.md`` and the master-publication proposal §4).

Gold renders every extracted table as a dead ``_[Table N](tables/table-NN.csv)_`` link (D-5) —
invisible on github.com. This pure transform turns a parsed table into something the fileman-docs
master can actually show, routed by the §4 classifier:

* **narrative / presentational** → inline GFM pipe table (cells keep inline markdown — vdocs-web
  proved ``renderInline`` works for ``**EN^DIK**`` etc.).
* **reference data** → an authoritative ``data/table-NN.yml`` record set (one dict per row, keyed by
  header) **plus** a rendered GFM table in the page. The data file is the source; the in-page
  table is generated from it and drift-gated (lossless — cell values verbatim, markdown and all).

Classification is deterministic (no AI): a table is **reference** if it has many rows or a VistA
reference-shaped header (File/Field/Global/Routine/RPC/Option/Error/…); otherwise **narrative**.

Pure: ``materialize(rows) -> MaterializedTable``; no I/O. The L1.4 driver reads the CSV sidecars
(``kernel.csv.read_rows``), calls this, replaces the placeholder, and writes any ``data/*.yml``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# A table with at least this many data rows leans reference (a big field/routine listing).
_REFERENCE_ROW_THRESHOLD = 12

# Header tokens marking a VistA reference-shaped table (normalized: lowercased, markdown stripped).
_REFERENCE_HEADER_TOKENS = frozenset(
    {
        "file",
        "field",
        "global",
        "routine",
        "rpc",
        "option",
        "error",
        "node",
        "subscript",
        "xref",
        "cross-reference",
        "entry",
        "callable",
        "parameter",
        "namespace",
        "key",
        "template",
    }
)
_NORMALIZE_RE = re.compile(r"[*_`#]")


@dataclass(frozen=True)
class MaterializedTable:
    """The materialized form of one gold table."""

    kind: str  # "reference" | "narrative"
    gfm: str  # rendered GFM pipe table ("" for an empty table)
    records: list[dict[str, str]] | None  # reference only — the data/*.yml content
    ragged: bool  # any source row's arity != the header's


def _norm(cell: str) -> str:
    return _NORMALIZE_RE.sub("", cell).strip().lower()


def classify(rows: list[list[str]]) -> str:
    """Route a table to ``"reference"`` or ``"narrative"`` by the §4 signals."""
    if not rows:
        return "narrative"
    if len(rows) - 1 >= _REFERENCE_ROW_THRESHOLD:
        return "reference"
    header_tokens = {_norm(c) for c in rows[0]}
    if header_tokens & _REFERENCE_HEADER_TOKENS:
        return "reference"
    return "narrative"


def _cell(s: str) -> str:
    return s.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").strip()


def render_gfm(rows: list[list[str]]) -> str:
    """Render rows (header first) as a GFM pipe table; ragged rows padded to header width."""
    if not rows:
        return ""
    width = len(rows[0])
    out = ["| " + " | ".join(_cell(c) for c in rows[0]) + " |"]
    out.append("| " + " | ".join(["---"] * width) + " |")
    for row in rows[1:]:
        cells = [row[i] if i < len(row) else "" for i in range(width)]
        out.append("| " + " | ".join(_cell(c) for c in cells) + " |")
    return "\n".join(out)


def _records(rows: list[list[str]]) -> list[dict[str, str]]:
    width = len(rows[0])
    header = [_NORMALIZE_RE.sub("", h).strip() or f"col_{i + 1}" for i, h in enumerate(rows[0])]
    out: list[dict[str, str]] = []
    for row in rows[1:]:
        cells = [row[i] if i < len(row) else "" for i in range(width)]
        out.append(dict(zip(header, cells)))
    return out


def materialize(rows: list[list[str]]) -> MaterializedTable:
    """Classify + render one table into its publishable form."""
    if not rows:
        return MaterializedTable(kind="narrative", gfm="", records=None, ragged=False)
    width = len(rows[0])
    ragged = any(len(r) != width for r in rows[1:])
    kind = classify(rows)
    records = _records(rows) if kind == "reference" else None
    return MaterializedTable(kind=kind, gfm=render_gfm(rows), records=records, ragged=ragged)
