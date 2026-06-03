"""Shared markdown-structure primitives — the single home (§9.2/§11 anti-duplication).

Headings, code fences, blank-line runs, and tag stripping are parsed by `normalize`, `anchors`,
`template`, and `discover` alike. Their regexes and the fence-aware heading-scan loop lived
copy-pasted across those four modules (heading/fence parse 4–5×); they live here exactly once.

The canonical heading regex is ``#+`` (not ``#{1,6}``): upstream (Pandoc/`convert`) emits >6-``#``
headings from deep DOCX outline levels (e.g. ``########### Table of Contents``), and **every**
caller must recognize them consistently — leaving an invalid >6 ATX heading (GitHub renders it as
literal text) is the bug the ``e1e3b44`` legacy-TOC fix closed. This module makes that resolution
uniform across all four call sites. Pure: strings in, plain values out.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from vdocs.kernel.text import TAG_RE as TAG_RE  # the single tag matcher, re-exported (§9.2)
from vdocs.kernel.text import strip_tags as strip_tags  # re-exported for the markdown call sites

# `#+` (the divergence resolution): recognize >6-hash headings everywhere. ``HEADING_RE`` captures
# (hashes, text); ``FENCE_RE`` matches an opening/closing code fence; ``MULTI_BLANK`` collapses
# runaway blank-line runs to a single blank line.
HEADING_RE = re.compile(r"^(#+)\s+(.*?)\s*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
MULTI_BLANK = re.compile(r"\n{3,}")

# A line that is *entirely* a markdown structural artifact, not prose: an `<img>` figure tag, or a
# `[…](…)` link/secondary-TOC/table-CSV-marker line (with optional `_`/`*`/`↑` wrappers). These
# dominate the corpus's recurring "boilerplate" noise — `[↑ Back to Contents](#contents)` in every
# DIBR doc, plain-text TOC lines like `[1 Introduction [1](#introduction)](#introduction)`, figure
# `<img>` tags, `_[Table 1 (extracted to CSV)](tables/table-01.csv)_` markers — so the block miner
# drops them before classifying recurring blocks. Anchored so a *sentence* that merely contains an
# inline link (text before the `[`) does not match — that is prose and is kept (§9.6, spike Task 1).
ARTIFACT_RE = re.compile(
    r"^[ \t]*(?:"
    r"<img\b[^>]*>"  # a figure image tag (single line, or a multi-line tag once collapsed)
    r"|[_*↑\s]*!?\[.*\]\([^)]*\)[_*\s]*"  # a link / image / TOC / table-CSV-marker-only line
    r")[ \t]*$"
)

_CONTENTS = "contents"

__all__ = [
    "HEADING_RE",
    "FENCE_RE",
    "MULTI_BLANK",
    "ARTIFACT_RE",
    "TAG_RE",
    "strip_tags",
    "iter_headings",
    "is_markdown_artifact",
]


def is_markdown_artifact(line: str) -> bool:
    """True when ``line`` is *entirely* a markdown structural artifact (nav/TOC link, ``<img>``
    figure tag, or table-CSV marker) rather than prose — the shared recognizer (§9.2).

    A blank line is not an artifact (it carries no structure); a prose sentence that merely
    *contains* an inline link is not an artifact (the pattern is anchored at the line start)."""
    return bool(line.strip()) and ARTIFACT_RE.match(line) is not None


def iter_headings(body: str) -> Iterator[tuple[int, int, str]]:
    """Yield ``(line_index, level, text)`` for each ATX heading in ``body`` — the one fence-aware
    heading scan the four markdown stages share (§9.2).

    Skips fenced code blocks (``` / ~~~) and our own generated ``## Contents`` marker — it is
    regenerated each run, so consumers must never treat it as content (TOC/level/scaffold logic).
    ``level`` is the ``#`` count (``#+`` — oversized headings are recognized); ``text`` is the raw
    heading text with surrounding whitespace trimmed but **inline markup retained**, so callers
    that read bookmark spans (``anchors_pure``) still can. The ``line_index`` lets a caller rewrite
    or annotate the exact source line."""
    in_fence = False
    for idx, line in enumerate(body.split("\n")):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = HEADING_RE.match(line)
        if m is None:
            continue
        text = m.group(2)
        if text.strip().lower() == _CONTENTS:
            continue
        yield idx, len(m.group(1)), text
