"""Pure revision-history extraction — the manual version apparatus → ``revisions.yaml`` (§6.4).

Word-origin manuals carry a revision-history table at the top. `normalize` strips that apparatus
from the body (git carries lineage instead) and captures it as a structured ``revisions.yaml``
sidecar that travels with the bundle — this document's own revision-history table. `consolidate`
later folds each version's ``revisions.yaml`` into the version group's cross-version
``history.yaml`` lineage (the source `push --replay-history` replays later, §6.6). Two table
dialects are recognised: the HTML ``<table>`` Pandoc dumps, and
the GFM pipe table Docling emits (for the converter-routed docs). Ported from v1 ``vista-docs``;
pure — plain values in, records + cleaned body out; the stage writes the sidecar.
"""

from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass, field

from vdocs.kernel.table import (
    CELL_RE,
    PIPE_LINE_RE,
    PIPE_SEP_RE,
    ROW_RE,
    TABLE_RE,
    flatten_html,
    md_link_targets,
    pipe_cells,
    strip_md_links,
)
from vdocs.kernel.text import TAG_RE  # the single shared HTML-tag matcher (§9.2)

_HREF_RE = re.compile(r'href="(#[^"]+)"')
_WS_RE = re.compile(r"\s+")
_BLOCK_END_RE = re.compile(r"</(?:li|p|ul|ol)>", re.IGNORECASE)
_INT_RE = re.compile(r"\d+")
_MMYYYY_RE = re.compile(r"^(\d{1,2})/(\d{4})$")
_MDY_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2,4})$")
_REV_CAPTION_RE = re.compile(
    r"(?i)^\s*(?:revision history\s*)?this table lists the history for each revision"
)


@dataclass(frozen=True)
class RevisionRecord:
    """One revision-history row (the redacted PM/Technical-Writer columns are dropped)."""

    date: str
    version: str
    pages: list[int]
    change: str
    refs: list[str] = field(default_factory=list)


# --- cell flattening + date normalisation ----------------------------------
def _flatten_change(cell_html: str) -> str:
    s = _BLOCK_END_RE.sub(" \n", cell_html)
    s = _html.unescape(TAG_RE.sub("", s))
    parts = [_WS_RE.sub(" ", line).strip() for line in s.split("\n")]
    return "; ".join(p for p in parts if p)


def _norm_date(text: str) -> str:
    """'3/2024' → '2024-03'; '3/15/24' → '2024-03'; otherwise unchanged."""
    t = text.strip()
    if (m := _MMYYYY_RE.match(t)) is not None:
        return f"{m.group(2)}-{int(m.group(1)):02d}"
    if (m := _MDY_RE.match(t)) is not None:
        month, year = int(m.group(1)), m.group(3)
        if len(year) == 2:
            year = ("20" if int(year) < 50 else "19") + year
        return f"{year}-{month:02d}"
    return t


def _refs(cell_html: str) -> list[str]:
    return _HREF_RE.findall(cell_html)


def _header_text(table_html: str) -> str:
    rows = ROW_RE.findall(table_html)
    return " ".join(flatten_html(c).lower() for c in CELL_RE.findall(rows[0])) if rows else ""


def _is_revision_header(header: str) -> bool:
    return "date" in header and "change" in header and ("version" in header or "patch" in header)


# --- GFM pipe-table dialect (Docling-origin docs) — cell/regex mechanics in kernel.table --
def _find_pipe_table(body: str) -> tuple[int, int, str] | None:
    lines = body.split("\n")
    offsets, pos = [], 0
    for ln in lines:
        offsets.append(pos)
        pos += len(ln) + 1
    for i in range(len(lines) - 1):
        if not (PIPE_LINE_RE.match(lines[i]) and PIPE_SEP_RE.match(lines[i + 1])):
            continue
        if not _is_revision_header(" ".join(pipe_cells(lines[i])).lower()):
            continue
        j = i + 2
        while j < len(lines) and PIPE_LINE_RE.match(lines[j]):
            j += 1
        return offsets[i], offsets[j - 1] + len(lines[j - 1]), "\n".join(lines[i:j])
    return None


def find_revision_table(body: str) -> tuple[int, int, str] | None:
    """``(start, end, table)`` of the revision table (HTML preferred, then GFM pipe), or None."""
    for m in TABLE_RE.finditer(body):
        if _is_revision_header(_header_text(m.group(0))):
            return m.start(), m.end(), m.group(0)
    return _find_pipe_table(body)


# --- parsing ---------------------------------------------------------------
def _col(header: list[str], *names: str) -> int | None:
    for i, h in enumerate(header):
        if any(n in h for n in names):
            return i
    return None


def _parse_html_table(table_html: str) -> list[RevisionRecord]:
    rows = ROW_RE.findall(table_html)
    if not rows:
        return []
    header = [flatten_html(c).lower() for c in CELL_RE.findall(rows[0])]
    di, vi, pi, ci = (
        _col(header, "date"),
        _col(header, "version", "patch"),
        _col(header, "page"),
        _col(header, "change"),
    )
    records: list[RevisionRecord] = []
    for row in rows[1:]:
        cells = CELL_RE.findall(row)
        if not cells:
            continue

        def cell(idx: int | None, _cells: list[str] = cells) -> str:
            return _cells[idx] if idx is not None and idx < len(_cells) else ""

        records.append(
            RevisionRecord(
                date=_norm_date(flatten_html(cell(di))),
                version=flatten_html(cell(vi)),
                pages=[int(n) for n in _INT_RE.findall(flatten_html(cell(pi)))],
                change=_flatten_change(cell(ci)),
                refs=_refs(cell(pi)) + _refs(cell(ci)),
            )
        )
    return records


def _parse_pipe_table(table: str) -> list[RevisionRecord]:
    lines = [ln for ln in table.split("\n") if PIPE_LINE_RE.match(ln)]
    if len(lines) < 2:
        return []
    header = [h.lower() for h in pipe_cells(lines[0])]
    di, vi, pi, ci = (
        _col(header, "date"),
        _col(header, "version", "patch"),
        _col(header, "page"),
        _col(header, "change"),
    )
    records: list[RevisionRecord] = []
    for row in lines[2:]:
        if PIPE_SEP_RE.match(row):
            continue
        cells = pipe_cells(row)

        def cell(idx: int | None, _cells: list[str] = cells) -> str:
            return _cells[idx] if idx is not None and idx < len(_cells) else ""

        page_raw, change_raw = cell(pi), cell(ci)
        records.append(
            RevisionRecord(
                date=_norm_date(cell(di)),
                version=cell(vi),
                pages=[int(n) for n in _INT_RE.findall(strip_md_links(page_raw))],
                change=_WS_RE.sub(" ", strip_md_links(change_raw)).strip(),
                refs=md_link_targets(page_raw) + md_link_targets(change_raw),
            )
        )
    return records


def parse_revision_table(table: str) -> list[RevisionRecord]:
    """Parse a revision table (HTML or GFM pipe) into records."""
    return _parse_html_table(table) if "<table" in table.lower() else _parse_pipe_table(table)


# --- the F-step ------------------------------------------------------------
def extract_revision_history(body: str) -> tuple[str, list[RevisionRecord]]:
    """Remove the revision table (+ a preceding caption/duplicated-caption paragraph) from the
    body and return ``(cleaned_body, records)``. No revision table → ``(body, [])`` unchanged."""
    found = find_revision_table(body)
    if found is None:
        return body, []
    start, end, table = found
    records = parse_revision_table(table)
    before = re.sub(r"\n*[ \t]*Revision History[ \t]*\n*$", "", body[:start])
    cleaned = before.rstrip("\n") + "\n\n" + body[end:].lstrip("\n")
    # Pandoc duplicates the table <caption> as a body paragraph — drop it too.
    cleaned = "\n".join(ln for ln in cleaned.split("\n") if not _REV_CAPTION_RE.match(ln))
    return cleaned, records


def revision_sidecar(records: list[RevisionRecord]) -> dict:
    """The ``revisions.yaml`` mapping: a summary + this document's own ordered revision-history
    records (§6.4). Named for the per-document grain — the cross-version ``history.yaml`` *lineage*
    (which folds each member's ``revisions.yaml``) is ``consolidate``'s artifact (§6.6)."""
    dates = [r.date for r in records if re.fullmatch(r"\d{4}-\d{2}", r.date)]
    return {
        "revision_count": len(records),
        "revision_newest": max(dates) if dates else None,
        "revision_oldest": min(dates) if dates else None,
        "revisions": [
            {
                "date": r.date,
                "version": r.version,
                "pages": r.pages,
                "change": r.change,
                "refs": r.refs,
            }
            for r in records
        ],
    }
