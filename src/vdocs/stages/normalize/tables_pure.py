"""Pure complex-table extraction → ``tables/*.csv`` sidecars (§6.4/§6.5/§9.6).

`convert` emits complex tables as raw HTML ``<table>`` (Pandoc) or GFM pipe tables (Docling). The
revision-history table is handled separately (``revision_pure`` → ``revisions.yaml``); this module
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
from vdocs.kernel.table import (
    CELL_RE,
    PIPE_LINE_RE,
    PIPE_SEP_RE,
    TABLE_RE,
    flatten_html,
    html_rows,
    pipe_cells,
    strip_md_links,
)
from vdocs.kernel.text import TAG_RE

# §6.5 guardrail thresholds (calibrated on the real corpus: this leaves ~75% of tables — the short,
# narrow ones — inline, and extracts the tall/wide data tables that bloat the markdown).
_MIN_ROWS = 10  # total rows (header + data)
_MIN_COLS = 8  # columns — a table this wide is unreadable inline regardless of height

_CAPTION_RE = re.compile(r"<caption\b[^>]*>(.*?)</caption>", re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True)
class ExtractedTable:
    """One table lifted to CSV: its sidecar basename, the CSV text, and its shape."""

    name: str  # the sidecar basename, e.g. "table-01.csv"
    csv_text: str
    n_rows: int
    n_cols: int
    caption: str  # the table caption if any (used as the in-body reference label)


def _pipe_cells(line: str) -> list[str]:
    # tables/*.csv wants plain text, so strip md-link syntax (the base primitive keeps it).
    return [strip_md_links(c) for c in pipe_cells(line)]


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
    for m in TABLE_RE.finditer(body):
        cap = _CAPTION_RE.search(m.group(0))
        spans.append(
            _Span(
                m.start(),
                m.end(),
                html_rows(m.group(0)),
                flatten_html(cap.group(1)) if cap else "",
            )
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
        if PIPE_LINE_RE.match(lines[i]) and PIPE_SEP_RE.match(lines[i + 1]):
            j = i + 2
            while j < len(lines) and PIPE_LINE_RE.match(lines[j]):
                j += 1
            rows = [_pipe_cells(lines[i])] + [_pipe_cells(ln) for ln in lines[i + 2 : j]]
            spans.append(_Span(offsets[i], offsets[j - 1] + len(lines[j - 1]), rows, ""))
            i = j
        else:
            i += 1
    return spans


def count_qualifying_tables(body: str) -> int:
    """Number of extraction-qualifying tables (§6.5 thresholds) present in ``body`` — the residue
    post-condition check feeding ``capture.yaml`` (§6.4). After ``extract_tables`` has run, a
    qualifying table still sitting in the normalized body is a silent table-extraction miss, so this
    is normalize's independent re-scan signal for the ``tables`` capture outcome (capture_pure)."""
    spans = _html_spans(body) + _pipe_spans(body)
    return sum(1 for s in spans if _qualifies(s.rows))


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


# --- HTML → GFM canonicalisation (§6.5): one table dialect in gold -------------------------------
# Pandoc emits complex tables as raw HTML, Docling as GFM. The big ones leave as CSV either way, but
# the rest stayed inline in whichever dialect they arrived in — so 60% of gold documents carried
# `<table>` markup, and **5,386 chunks (9.3% of the search index) indexed `colgroup` / `tbody` /
# `tr class="odd"` as tokens**. Converting the faithfully-representable ones removes that noise and
# lands both converters on one shape.
_SPAN_ATTR_RE = re.compile(r"\b(?:colspan|rowspan)\s*=", re.IGNORECASE)
# block content GFM has no cell-level equivalent for (the outer <table> is excluded by counting)
_CELL_BLOCK_RE = re.compile(r"<(?:h[1-6]|ul|ol|pre)\b", re.IGNORECASE)


def _gfm_cell(text: str) -> str:
    """A cell's plain text, safe inside a pipe table."""
    return text.replace("|", r"\|")


def _to_gfm(rows: list[list[str]]) -> str:
    """Rectangular rows → a GFM pipe table, first row as the header (GFM requires one)."""
    width = len(rows[0])
    lines = [
        "| " + " | ".join(_gfm_cell(c) for c in rows[0]) + " |",
        "|" + "|".join(["---"] * width) + "|",
    ]
    lines += ["| " + " | ".join(_gfm_cell(c) for c in r) + " |" for r in rows[1:]]
    return "\n".join(lines)


def html_tables_to_gfm(body: str) -> str:
    """Rewrite inline Pandoc ``<table>`` blocks as GFM pipe tables where GFM can say the same thing.

    Converts only a table that is **rectangular, span-free, and free of cell-level block content**,
    and is not a 1x1 wrapper. Everything else is left as HTML on purpose: a ``colspan`` merge, a
    heading or list inside a cell, or a nested table cannot be expressed in GFM, and flattening one
    anyway produces something that *reads* like data while misrepresenting the source. Measured on
    gold: 4,055 of 8,086 inline tables convert; 1,056 use spans, 2,023 hold block content, 774 are
    Word text-boxes wrapping terminal screen captures, 134 are nested.

    Idempotent — the output contains no ``<table>``, so a second pass finds nothing."""

    def repl(m: re.Match[str]) -> str:
        html = m.group(0)
        if html.lower().count("<table") > 1 or _SPAN_ATTR_RE.search(html):
            return html
        if _CELL_BLOCK_RE.search(html):
            return html
        rows = [r for r in html_rows(html) if r]
        if not rows or len({len(r) for r in rows}) > 1:
            return html
        if len(rows) == 1 and len(rows[0]) == 1:
            return html  # a text-box, not a table
        return _to_gfm(rows)

    return TABLE_RE.sub(repl, body)


# --- 1x1 text-boxes → fenced code blocks (§6.5) --------------------------------------------------
# A 1x1 `<table>` in a VA manual is not data: it is the house convention for showing **verbatim
# machine output** in a bordered box — List Manager screens, roll-and-scroll prompts, menu listings,
# HL7 messages, MailMan traffic, system warnings. 774 survive in gold, and inspecting them found no
# prose to protect. Fencing also stops captured output being parsed as document structure: a screen
# line like `# DRUG QTY # REFS DAYS SUPPLY` currently reads as a markdown heading.
_ONE_ROW_RE = re.compile(r"<tr\b", re.IGNORECASE)
_LINE_BREAK_RE = re.compile(r"</p>\s*<p\b[^>]*>|<br\s*/?>", re.IGNORECASE)
# block content a fence would misrepresent by flattening it into plain lines
_BOX_BLOCK_RE = re.compile(r"<(?:h[1-6]|ul|ol|table)\b", re.IGNORECASE)


def _fence_for(text: str) -> str:
    """A fence longer than the longest backtick run inside the content, so it always closes."""
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    return "`" * max(3, longest + 1)


def text_boxes_to_code_fences(body: str) -> str:
    """Rewrite 1x1 Word text-boxes as fenced code blocks, preserving their line structure.

    Line breaks come from the paragraph/``<br>`` boundaries Pandoc emits (530 of the 774 boxes
    carry one ``<p>`` per screen line); inline markup is stripped and entities decoded, but
    **whitespace is deliberately not collapsed** — column alignment is what a screen capture is
    made of, which is why this cannot reuse ``flatten_html``.

    Left alone: anything that is not exactly one row and one cell, and any box holding a list,
    heading or nested table — a fence would flatten those into text that merely looks like output.
    Idempotent: the result contains no ``<table>``."""

    def repl(m: re.Match[str]) -> str:
        html = m.group(0)
        if len(_ONE_ROW_RE.findall(html)) != 1 or _BOX_BLOCK_RE.search(html[html.find(">") :]):
            return html
        cells = CELL_RE.findall(html)
        if len(cells) != 1:
            return html
        text = _LINE_BREAK_RE.sub("\n", cells[0])
        lines = [_html.unescape(TAG_RE.sub("", ln)).rstrip() for ln in text.split("\n")]
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        if not lines:
            return html
        fence = _fence_for("\n".join(lines))
        return fence + "\n" + "\n".join(lines) + "\n" + fence

    return TABLE_RE.sub(repl, body)
