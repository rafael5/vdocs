"""Shared HTML/GFM table-cell parsing primitives (§9.2/§11 anti-duplication).

`convert` emits tables in two dialects — Pandoc HTML ``<table>`` and Docling GFM pipe tables.
Two ``normalize`` F-steps parse them: ``revision_pure`` (→ ``revisions.yaml``) and ``tables_pure``
(→ ``tables/*.csv``). The cell/row/regex mechanics they share live here exactly once; each stage
keeps only its stage-specific row interpretation. Pure: strings in, plain lists/strings out.
"""

from __future__ import annotations

import html as _html
import re

# --- HTML <table> dialect (Pandoc) ---
TABLE_RE = re.compile(r"<table\b.*?</table>", re.DOTALL | re.IGNORECASE)
ROW_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.DOTALL | re.IGNORECASE)
CELL_RE = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.DOTALL | re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def flatten_html(cell_html: str) -> str:
    """Strip tags, unescape entities, collapse whitespace → the cell's plain text."""
    return _WS_RE.sub(" ", _html.unescape(_TAG_RE.sub("", cell_html))).strip()


def html_rows(table_html: str) -> list[list[str]]:
    """Every ``<tr>`` as a list of flattened ``<td>``/``<th>`` cell texts."""
    return [[flatten_html(c) for c in CELL_RE.findall(r)] for r in ROW_RE.findall(table_html)]


# --- GFM pipe-table dialect (Docling) ---
PIPE_LINE_RE = re.compile(r"^[ \t]*\|.*\|[ \t]*$")
PIPE_SEP_RE = re.compile(r"^[ \t]*\|[ \t:|-]+\|[ \t]*$")
_PIPE_SPLIT_RE = re.compile(r"(?<!\\)\|")
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\((#[^)]*)\)")


def pipe_cells(line: str) -> list[str]:
    """Split a GFM pipe-table row into trimmed cell texts (escaped ``\\|`` restored).

    Markdown-link syntax is left **intact** — the more primitive form; ``revision_pure`` needs
    the links to extract refs, while ``tables_pure`` composes :func:`strip_md_links` on top.
    """
    parts = _PIPE_SPLIT_RE.split(line.strip())
    if parts and parts[0].strip() == "":
        parts = parts[1:]
    if parts and parts[-1].strip() == "":
        parts = parts[:-1]
    return [p.replace("\\|", "|").strip() for p in parts]


def strip_md_links(s: str) -> str:
    """Replace ``[text](#anchor)`` spans with their ``text`` (drop the anchor)."""
    return _MD_LINK_RE.sub(r"\1", s)


def md_link_targets(s: str) -> list[str]:
    """The ``#anchor`` target of every markdown link in ``s``, in order."""
    return [m.group(2) for m in _MD_LINK_RE.finditer(s)]


__all__ = [
    "TABLE_RE",
    "ROW_RE",
    "CELL_RE",
    "PIPE_LINE_RE",
    "PIPE_SEP_RE",
    "flatten_html",
    "html_rows",
    "pipe_cells",
    "strip_md_links",
    "md_link_targets",
]
