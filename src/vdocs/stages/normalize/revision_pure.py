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

from vdocs.kernel.markdown import HEADING_RE, is_revision_heading
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
from vdocs.kernel.text import (
    MONTH_NAME,
    TAG_RE,  # the single shared HTML-tag matcher (§9.2)
    month_number,
)

_HREF_RE = re.compile(r'href="(#[^"]+)"')
_WS_RE = re.compile(r"\s+")
_BLOCK_END_RE = re.compile(r"</(?:li|p|ul|ol)>", re.IGNORECASE)
_INT_RE = re.compile(r"\d+")
_ISO_MONTH_RE = re.compile(r"\d{4}-\d{2}")
# Revision-table date shapes (§6.4). Each yields a month and a 2- or 4-digit year; a day, where
# present, is dropped (the sidecar's grain is the month). On the 2026-11-05 lake, 1,258 of 9,653
# revision rows used a shape the month-name-only parser left unnormalized.
_NUMERIC_DATE_RES = (
    # 3/2024 · 07/24 · 03-2019 · 01/ 2023 — the 2-digit form is month/YEAR: across 748 rows the
    # first part is always 1–12 and the second runs 00–25 and 95–98, which no day-of-month does
    re.compile(r"^(?P<m>\d{1,2})\s*[/-]\s*(?P<y>\d{4}|\d{2})$"),
    # 3/15/24 · 09/--/1997 (day left blank) · 09//13/2022 · 8//2009 (doubled separator)
    re.compile(r"^(?P<m>\d{1,2})/+(?:\d{1,2}|--)?/+(?P<y>\d{4}|\d{2})$"),
    # 12-22-2004 · 09-5-2014 · 10-30-09
    re.compile(r"^(?P<m>\d{1,2})-\d{1,2}-(?P<y>\d{4}|\d{2})$"),
)
# A month name (not inside a longer word) then a year, optionally with a day between: "Feb 2018",
# "September 26, 2008", "December 18,2008", "August2014", "1September 2009", "Apr 06", "7-Jul-11".
# A 2-digit number straight after the month is read as the year — the corpus forms ("Apr 06",
# "November 07") are years, and a cell holding only a month and a day is not a revision date.
_MONTH_DATE_RE = re.compile(
    rf"(?<![A-Za-z])(?P<mon>{MONTH_NAME})\.?(?![A-Za-z])(?:\s*\d{{1,2}}\s*,)?[\s,-]*"
    r"(?P<y>\d{4}|\d{2})(?!\d)",
    re.IGNORECASE,
)
_SPAN_RE = re.compile(r"\s+to\s+", re.IGNORECASE)
# The descriptive filler *around* the revision table — dead text that carries no unique fact
# (§6.6). Broadened to the real corpus variants: "the following table displays the revision
# history…", "<u>Table 1</u> displays the revision history…", "this table lists the history for
# each revision…". Matched anywhere on a line (the boilerplate sometimes trails a `>` blockquote
# marker or runs a second sentence on the same line), so the whole dead line is dropped.
_REV_CAPTION_RE = re.compile(
    r"(?i)(?:displays the revision history|lists the history for each revision)"
)

# A revision apparatus whose table could not be parsed (or is absent under a real revision heading)
# is retained and flagged — never deleted blind (§6.4 capture-before-strip / fidelity C2).
REVISION_UNPARSED_FLAG = "revision-history-unparsed"


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


def _iso_month(month: int, year: str) -> str | None:
    """``YYYY-MM`` for a month 1–12 and a 2- or 4-digit year (``< 50`` → 20xx), else ``None``."""
    if not 1 <= month <= 12:
        return None
    if len(year) == 2:
        year = ("20" if int(year) < 50 else "19") + year
    return f"{year}-{month:02d}"


def _norm_date(text: str) -> str:
    """Normalise a revision-table date cell to ``YYYY-MM``; otherwise pass it through unchanged.

    Handles the numeric shapes in :data:`_NUMERIC_DATE_RES` (``3/2024``, ``07/24``, ``3/15/24``,
    ``09/--/1997``, ``12-22-2004`` …) and a month name followed by a year (``Feb 2018``,
    ``September 26, 2008``, ``Apr 06`` …). A bold marker left in the cell is ignored, and a span
    (``Sep-Nov 11``, ``01/02/2015 to 01/06/2015``) is dated by its end — the latest change it
    records. Normalising every real shape is what lets ``revision_sidecar`` compute
    ``revision_newest`` (and thus ``official_date``): an unparsed newest row dates a doc too
    early."""
    t = text.strip().strip("*").strip()
    t = _SPAN_RE.split(t)[-1]
    for rx in _NUMERIC_DATE_RES:
        if (m := rx.match(t)) is not None and (iso := _iso_month(int(m["m"]), m["y"])):
            return iso
    named = list(_MONTH_DATE_RE.finditer(t))
    if named and (iso := _iso_month(month_number(named[-1]["mon"]), named[-1]["y"])):
        return iso
    return text.strip()


def _refs(cell_html: str) -> list[str]:
    return _HREF_RE.findall(cell_html)


def _header_text(table_html: str) -> str:
    rows = ROW_RE.findall(table_html)
    return " ".join(flatten_html(c).lower() for c in CELL_RE.findall(rows[0])) if rows else ""


def _is_revision_header(header: str) -> bool:
    """The §6.4 corrected detection contract: a revision-table header (markup already stripped by
    ``flatten_html``/``pipe_cells``, case-folded) has a **date** column **and** a change-description
    column (``description`` **or** ``change``). A version-ish column (``version``/``revision``/
    ``patch``) is optional. This replaces the v1-ported predicate that required ``change`` **and**
    (``version``|``patch``) — which matched ~0 of the corpus's real ``Date·Revision·Description``
    tables. False positives are prevented by the heading-proximity guard, not by extra columns."""
    return "date" in header and ("description" in header or "change" in header)


# Window (in non-blank lines) the candidate table is allowed to sit below its revision-history
# heading — covers a blank line + an optional descriptive caption between heading and table.
_REV_HEADING_LOOKBACK = 4


def _under_revision_heading(lines: list[str], table_line: int) -> bool:
    """Proximity guard (§6.4): the candidate table at ``table_line`` is the revision table only
    when a revision-history section header sits just above it. Scans the preceding **non-blank**
    lines (skipping blanks + a descriptive caption); a revision heading within ``_REV_HEADING_
    LOOKBACK`` lines → accept; any other ATX heading first → reject (the table belongs to that
    section, not a revision section)."""
    seen = 0
    for j in range(table_line - 1, -1, -1):
        ln = lines[j]
        if not ln.strip():
            continue
        if is_revision_heading(ln):
            return True
        if HEADING_RE.match(ln):  # a different real section heading → not a revision table
            return False
        seen += 1
        if seen >= _REV_HEADING_LOOKBACK:
            return False
    return False


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
        # The header signature is normally in the first pipe row, but Docling/Pandoc often emit a
        # leading **empty** header row (``|  |  |  |``) with the real ``Date|Version|Description``
        # columns in the first *data* row — so check that row too (§6.4).
        if not (
            _is_revision_header(" ".join(pipe_cells(lines[i])).lower())
            or (
                i + 2 < len(lines)
                and PIPE_LINE_RE.match(lines[i + 2])
                and _is_revision_header(" ".join(pipe_cells(lines[i + 2])).lower())
            )
        ):
            continue
        if not _under_revision_heading(lines, i):  # proximity guard (§6.4)
            continue
        j = i + 2
        while j < len(lines) and PIPE_LINE_RE.match(lines[j]):
            j += 1
        return offsets[i], offsets[j - 1] + len(lines[j - 1]), "\n".join(lines[i:j])
    return None


def find_revision_table(body: str) -> tuple[int, int, str] | None:
    """``(start, end, table)`` of the revision table (HTML preferred, then GFM pipe), or None.

    Detection is gated on the §6.4 column contract **and** proximity to a revision-history section
    header — so an unrelated date/description table elsewhere in the body is never stripped."""
    lines = body.split("\n")
    for m in TABLE_RE.finditer(body):
        if _is_revision_header(_header_text(m.group(0))) and _under_revision_heading(
            lines, body.count("\n", 0, m.start())
        ):
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
        _col(header, "version", "revision", "patch"),
        _col(header, "page"),
        _col(header, "description", "change"),
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
    rows = [ln for ln in table.split("\n") if PIPE_LINE_RE.match(ln) and not PIPE_SEP_RE.match(ln)]
    if len(rows) < 2:
        return []
    # The header row is normally the first, but a leading **empty** row (Docling/Pandoc artifact)
    # pushes the real ``Date|Version|Description`` columns into the first data row — use the first
    # row that actually looks like a revision header, and treat the rows after it as data (§6.4).
    hidx = next(
        (k for k, r in enumerate(rows) if _is_revision_header(" ".join(pipe_cells(r)).lower())), 0
    )
    header = [h.lower() for h in pipe_cells(rows[hidx])]
    di, vi, pi, ci = (
        _col(header, "date"),
        _col(header, "version", "revision", "patch"),
        _col(header, "page"),
        _col(header, "description", "change"),
    )
    records: list[RevisionRecord] = []
    for row in rows[hidx + 1 :]:
        cells = pipe_cells(row)
        if not any(c.strip() for c in cells):  # skip an all-empty row (the leading-blank artifact)
            continue

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
def _has_revision_heading(body: str) -> bool:
    return any(is_revision_heading(ln) for ln in body.split("\n"))


def _strip_apparatus(body: str, start: int, end: int) -> str:
    """Remove the revision **apparatus** — the whole span from the governing revision-history
    heading through the end of the table (``[start:end]``), including any descriptive filler/caption
    between them (§6.4/§6.6). The heading is located by scanning back over the proximity window the
    detector already validated, so content *above* that heading (e.g. the title-page cover) is
    untouched. A duplicated caption paragraph elsewhere is dropped too."""
    lines = body.split("\n")
    table_line = body.count("\n", 0, start)
    cut_from = table_line  # fallback: just the table (the proximity guard normally finds a heading)
    seen = 0
    for j in range(table_line - 1, -1, -1):
        if not lines[j].strip():
            continue
        if is_revision_heading(lines[j]):
            cut_from = j
            break
        seen += 1
        if seen > _REV_HEADING_LOOKBACK:
            break
    before = "\n".join(lines[:cut_from]).rstrip("\n")
    after = body[end:].lstrip("\n")
    cleaned = (before + "\n\n" + after) if before else after
    # Pandoc duplicates the table <caption> as a body paragraph — drop any such dead line too.
    return "\n".join(ln for ln in cleaned.split("\n") if not _REV_CAPTION_RE.search(ln))


def extract_revision_history(body: str) -> tuple[str, list[RevisionRecord], str | None]:
    """Strip the revision apparatus (heading + table + descriptive boilerplate) **only after** the
    table is parsed, returning ``(cleaned_body, records, flag)`` (§6.4 capture-before-strip).

    * a parseable revision table → apparatus removed, ``records`` captured, ``flag`` ``None``;
    * a revision-history **heading with no parseable table** → body **unchanged** and
      ``flag = REVISION_UNPARSED_FLAG`` (a fidelity signal — never deleted blind);
    * no revision apparatus at all → ``(body, [], None)`` unchanged.
    """
    records: list[RevisionRecord] = []
    flag: str | None = None
    # Loop: a single document may carry several revision tables (the DIBR template ships both a
    # "Revision History" and a "Documentation Revisions" table). Lift each parseable one and strip
    # its apparatus; stop at the first detected-but-unparseable table (retain + flag — never delete
    # blind), or when no more revision tables remain.
    while (found := find_revision_table(body)) is not None:
        start, end, table = found
        recs = parse_revision_table(table)
        if not recs:
            flag = REVISION_UNPARSED_FLAG
            break
        records.extend(recs)
        body = _strip_apparatus(body, start, end)
    # A revision-history heading still in the body (no parseable table beneath it) is a fidelity
    # signal — retained, flagged, never silently dropped (§6.4 capture-before-strip).
    if flag is None and _has_revision_heading(body):
        flag = REVISION_UNPARSED_FLAG
    return body, records, flag


def revision_sidecar(records: list[RevisionRecord], *, not_after: str) -> dict:
    """The ``revisions.yaml`` mapping: a summary + this document's own ordered revision-history
    records (§6.4). Named for the per-document grain — the cross-version ``history.yaml`` *lineage*
    (which folds each member's ``revisions.yaml``) is ``consolidate``'s artifact (§6.6).

    ``not_after`` (``YYYY-MM``, the month of the run) bounds the summary dates: a revision cannot
    postdate the run that reads it, so a later date is a typo (GMRC ``consum`` records ``3018-03``)
    and is left out of ``revision_newest``/``revision_oldest``. The row itself is kept as
    written."""
    dates = [r.date for r in records if _ISO_MONTH_RE.fullmatch(r.date) and r.date <= not_after]
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
