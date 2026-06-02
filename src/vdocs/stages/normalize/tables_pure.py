"""Pure complex-table extraction → ``tables/*.csv`` sidecars (§6.4/§6.5/§9.6).

`convert` emits complex tables as raw HTML ``<table>`` (Pandoc) or GFM pipe tables (Docling). The
revision-history table is handled separately (``revision_pure`` → ``history.yaml``); this module
handles the *remaining* data tables. **Qualifying** (genuinely large) tables — data dictionaries,
long code/option tables — are lifted to a ``tables/*.csv`` bundle sidecar and replaced in the body
with a markdown reference link, so the body stays readable and the tabular data stays queryable.

The §6.5 **don't-over-decompose** guardrail: small/narrow tables read fine inline and are left as
GFM/HTML — only tables that are tall (``≥ _MIN_ROWS`` total rows) or very wide (``≥ _MIN_COLS``
columns) are extracted. Pure: plain values in, ``(cleaned_body, [ExtractedTable])`` out; the stage
writes the CSV sidecars and counts them. Serialisation reuses ``kernel/csv`` (§9.2 — one writer).
"""

from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass

from vdocs.kernel.csv import to_csv

# §6.5 guardrail thresholds (calibrated on the real corpus: this leaves ~75% of tables — the short,
# narrow ones — inline, and extracts the tall/wide data tables that bloat the markdown).
_MIN_ROWS = 10  # total rows (header + data)
_MIN_COLS = 8  # columns — a table this wide is unreadable inline regardless of height

_TABLE_RE = re.compile(r"<table\b.*?</table>", re.DOTALL | re.IGNORECASE)
_ROW_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.DOTALL | re.IGNORECASE)
_CELL_RE = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.DOTALL | re.IGNORECASE)
_CAPTION_RE = re.compile(r"<caption\b[^>]*>(.*?)</caption>", re.DOTALL | re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_PIPE_LINE_RE = re.compile(r"^[ \t]*\|.*\|[ \t]*$")
_PIPE_SEP_RE = re.compile(r"^[ \t]*\|[ \t:|-]+\|[ \t]*$")
_PIPE_SPLIT_RE = re.compile(r"(?<!\\)\|")
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\((#[^)]*)\)")


@dataclass(frozen=True)
class ExtractedTable:
    """One table lifted to CSV: its sidecar basename, the CSV text, and its shape."""

    name: str  # the sidecar basename, e.g. "table-01.csv"
    csv_text: str
    n_rows: int
    n_cols: int
    caption: str  # the table caption if any (used as the in-body reference label)


def _flatten(cell_html: str) -> str:
    return _WS_RE.sub(" ", _html.unescape(_TAG_RE.sub("", cell_html))).strip()


def _html_rows(table_html: str) -> list[list[str]]:
    return [[_flatten(c) for c in _CELL_RE.findall(r)] for r in _ROW_RE.findall(table_html)]


def _pipe_cells(line: str) -> list[str]:
    parts = _PIPE_SPLIT_RE.split(line.strip())
    if parts and parts[0].strip() == "":
        parts = parts[1:]
    if parts and parts[-1].strip() == "":
        parts = parts[:-1]
    return [_MD_LINK_RE.sub(r"\1", p.replace("\\|", "|")).strip() for p in parts]


def _qualifies(rows: list[list[str]]) -> bool:
    """Extraction-worthy when tall or very wide (§6.5 guardrail); else it stays inline."""
    if len(rows) < 2:
        return False
    n_cols = max((len(r) for r in rows), default=0)
    return len(rows) >= _MIN_ROWS or n_cols >= _MIN_COLS


def _unique_columns(header: list[str]) -> list[str]:
    """Header cells as unique, non-blank column names (blank → ``col_N``, dupes → suffixed)."""
    out: list[str] = []
    counts: dict[str, int] = {}
    for i, cell in enumerate(header):
        name = cell.strip() or f"col_{i + 1}"
        if name in counts:
            counts[name] += 1
            name = f"{name}_{counts[name]}"
        else:
            counts[name] = 0
        out.append(name)
    return out


def _to_csv(rows: list[list[str]]) -> str:
    columns = _unique_columns(rows[0])
    data = [dict(zip(columns, r)) for r in rows[1:]]
    return to_csv(columns, data)


@dataclass(frozen=True)
class _Span:
    start: int
    end: int
    rows: list[list[str]]
    caption: str


def _html_spans(body: str) -> list[_Span]:
    spans: list[_Span] = []
    for m in _TABLE_RE.finditer(body):
        cap = _CAPTION_RE.search(m.group(0))
        spans.append(
            _Span(m.start(), m.end(), _html_rows(m.group(0)), _flatten(cap.group(1)) if cap else "")
        )
    return spans


def _pipe_spans(body: str) -> list[_Span]:
    lines = body.split("\n")
    offsets, pos = [], 0
    for ln in lines:
        offsets.append(pos)
        pos += len(ln) + 1
    spans: list[_Span] = []
    i = 0
    while i < len(lines) - 1:
        if _PIPE_LINE_RE.match(lines[i]) and _PIPE_SEP_RE.match(lines[i + 1]):
            j = i + 2
            while j < len(lines) and _PIPE_LINE_RE.match(lines[j]):
                j += 1
            rows = [_pipe_cells(lines[i])] + [_pipe_cells(ln) for ln in lines[i + 2 : j]]
            spans.append(_Span(offsets[i], offsets[j - 1] + len(lines[j - 1]), rows, ""))
            i = j
        else:
            i += 1
    return spans


def extract_tables(body: str) -> tuple[str, list[ExtractedTable]]:
    """Lift qualifying tables to CSV and replace each with a reference link (§6.4/§6.5).

    Tables are numbered in document order (``table-01.csv`` …); small tables are left untouched.
    Idempotent: the reference links it leaves behind are not tables, so a second pass extracts
    nothing and returns the body unchanged."""
    spans = sorted(_html_spans(body) + _pipe_spans(body), key=lambda s: s.start)
    qualifying = [s for s in spans if _qualifies(s.rows)]
    if not qualifying:
        return body, []

    tables: list[ExtractedTable] = []
    out: list[str] = []
    cursor = 0
    for n, span in enumerate(qualifying, start=1):
        name = f"table-{n:02d}.csv"
        n_cols = max(len(r) for r in span.rows)
        tables.append(
            ExtractedTable(
                name=name,
                csv_text=_to_csv(span.rows),
                n_rows=len(span.rows),
                n_cols=n_cols,
                caption=span.caption,
            )
        )
        label = span.caption or f"Table {n}"
        out.append(body[cursor : span.start])
        out.append(f"_[{label} (extracted to CSV)](tables/{name})_")
        cursor = span.end
    out.append(body[cursor:])
    return "".join(out), tables
