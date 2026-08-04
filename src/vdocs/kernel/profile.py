"""Per-document dimensions — what a body is made of (§6.4, §9.2).

Serves two questions the pipeline could not previously answer.

**What did we do to this document?** ``capture.yaml``'s ``retention`` block already records a
before/after for *words*, and nothing else — so a transform that halved a document's tables or
dropped its code blocks would move no recorded number. Profiling the body at two stage boundaries
and diffing makes every such change visible instead of invisible.

**What kind of document is this?** ``documents`` carries ``word_count``/``section_count``/
``image_count``, so "full of code examples" or "mostly tables" is not expressible — and those are
exactly the shapes a search consumer wants to know about before it ranks or renders.

Counted from the markdown body alone, so the same function can run at any stage boundary and two
readings are comparable. Counts that come from sidecars (extracted CSV tables, captured TOC entries)
belong to the stage that writes them, not here. Fence-aware throughout: a heading or table row
inside a code fence is sample output, not structure.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from vdocs.kernel.markdown import HEADING_RE

_FENCE_RE = re.compile(r"^\s*(```+|~~~+)")
_PIPE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_MD_IMG_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_HTML_IMG_RE = re.compile(r"<img\b", re.IGNORECASE)
_HTML_TABLE_RE = re.compile(r"<table\b", re.IGNORECASE)
_INTERNAL_LINK_RE = re.compile(r"\[[^\]]*\]\(#[^)]*\)")
# VistA code references: a routine/global label (`^DIC`, `^%ZTLOAD`) or an extrinsic call
# (`$$GET^DIQ`). VA manuals put code in prose and tables rather than fences — the FileMan
# Developer's Guide has 2,281 of these and **zero** fenced blocks — so `code_blocks` alone would
# tell a search consumer the most code-heavy document in the corpus contains no code.
_CODE_REF_RE = re.compile(r"\^%?[A-Z][A-Z0-9]{1,7}\b|\$\$[A-Z0-9]+\^")


@dataclass(frozen=True)
class DocumentProfile:
    """The countable shape of one markdown body."""

    words: int
    headings: int
    heading_levels: int  # how many distinct levels are used
    heading_depth: int  # the deepest level used
    code_blocks: int
    code_lines: int
    tables_gfm: int
    tables_html: int  # residual — what GFM could not express (§6.5)
    images: int
    internal_links: int
    code_refs: int  # VistA routine/global/extrinsic references — see _CODE_REF_RE

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


def document_profile(body: str) -> DocumentProfile:
    """Count the body's dimensions. Fence-aware: content inside a code fence is sample output, so
    a ``#`` line or a pipe row in there is neither a heading nor a table."""
    levels: set[int] = set()
    headings = code_blocks = code_lines = tables = 0
    fence = ""
    in_table = False
    for line in body.split("\n"):
        if fence:
            if _FENCE_RE.match(line) and line.strip().startswith(fence):
                fence = ""  # the closing fence is delimiter, not content
            else:
                code_lines += 1
            continue
        if (m := _FENCE_RE.match(line)) is not None:
            fence = m.group(1)
            code_blocks += 1
            in_table = False
            continue
        if _PIPE_ROW_RE.match(line):
            if not in_table:
                tables += 1
                in_table = True
            continue
        in_table = False
        if (hm := HEADING_RE.match(line)) is not None:
            headings += 1
            levels.add(len(hm.group(1)))
    return DocumentProfile(
        words=len(body.split()),
        headings=headings,
        heading_levels=len(levels),
        heading_depth=max(levels, default=0),
        code_blocks=code_blocks,
        code_lines=code_lines,
        tables_gfm=tables,
        tables_html=len(_HTML_TABLE_RE.findall(body)),
        images=len(_MD_IMG_RE.findall(body)) + len(_HTML_IMG_RE.findall(body)),
        internal_links=len(_INTERNAL_LINK_RE.findall(body)),
        code_refs=len(_CODE_REF_RE.findall(body)),
    )
