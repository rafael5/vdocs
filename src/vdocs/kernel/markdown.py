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

# Revision-history section headers come in four corpus forms — ATX (`#…`), bold (`**…**`),
# blockquote (`> …`), and a bare plain line — over a small curated vocabulary (§6.4). The single
# matcher (§9.2): `revision_pure`'s proximity guard and `discover`'s structure miner both key on
# this one vocabulary, so broadening it broadens both. `Documentation Revisions` /
# `Template Revision History` are the late-gen DIBR/template variants the corpus actually carries.
REVISION_HEADING_TEXTS = frozenset(
    {
        "revision history",
        "revisions",
        "documentation revisions",
        "documentation revision history",
        "template revision history",
    }
)
# Leading `>`/`#`/`*` heading furniture + trailing `*`/`:`/whitespace — stripped to bare text.
_HEADING_FURNITURE_RE = re.compile(r"^[>#*\s]+|[*\s:]+$")

# Legacy in-body table of contents (§6.7): the source's own page-numbered TOC. Its header is a
# `Table of Contents` / `Contents` line (ATX **or** plain text), and each entry is the
# double-bracketed page-numbered link `[Title [12](#anchor)](#anchor)` Pandoc emits. Both
# recognizers live here once: `template_pure` keys on them to bound the title-page cover, and
# `normalize`'s legacy-TOC strip + correlation key on them to drop the TOC (tenet #13 — the
# recognised heading *texts* are curated in `registries/structures`; the entry *shape* is here).
LEGACY_TOC_TITLES = frozenset({"table of contents", "contents"})
# The inner ``[<page>]`` carries the page number, which across the corpus is a plain integer
# (``12``), a **roman numeral** for front matter (``vii``/``xxxiv`` — i/v/x/l/c/d/m), or a
# **chapter-dash** form (``7-9``/``6-1``). Matching only ``\d+`` missed every front-matter TOC
# (whose first entries are roman), so the plain-text header was never recognised and the whole TOC
# survived. The page class is case-insensitive roman letters + digits + hyphen.
# Allow a leading blockquote (``>``) / bullet (``-``/``*``/``+``) / ordered (``1.``) marker before
# the entry — the corpus wraps TOC entries in all of these.
_TOC_ENTRY_PREFIX = r"(?:[>*+\-][ \t]+|\d+\.[ \t]+)*"
LEGACY_TOC_ENTRY_RE = re.compile(
    r"(?i)^[ \t]*" + _TOC_ENTRY_PREFIX + r"\[.*\[[0-9ivxlcdm\-]+\]\(#[^)]*\)\]\(#[^)]*\)[ \t]*$"
)
_TOC_TARGET_RE = re.compile(r"\]\((#[^)]*)\)")

__all__ = [
    "HEADING_RE",
    "FENCE_RE",
    "MULTI_BLANK",
    "ARTIFACT_RE",
    "TAG_RE",
    "REVISION_HEADING_TEXTS",
    "LEGACY_TOC_TITLES",
    "LEGACY_TOC_ENTRY_RE",
    "strip_tags",
    "iter_headings",
    "is_markdown_artifact",
    "heading_furniture_text",
    "is_revision_heading",
    "is_legacy_toc_entry",
    "legacy_toc_target",
]


def heading_furniture_text(line: str) -> str:
    """A heading line's bare text — leading ``>``/``#``/``*`` markup and trailing ``*``/``:``
    stripped, casefolded — the shared normaliser for matching markup-varied section headers
    across the markdown stages (§9.2). ``> **Revision History**`` → ``revision history``."""
    return _HEADING_FURNITURE_RE.sub("", line.strip()).strip().lower()


def is_revision_heading(line: str) -> bool:
    """True when ``line`` is a revision-history section header in **any** corpus form — ATX, bold,
    blockquote-bold, a bare plain line, or the **old-gen bookmark-span** line
    (``<span id="_Toc…"></span>Revision History``) that flat Pandoc output emits for an unstyled
    heading (§6.4/§6.7 recovery-seed shape). HTML tags are stripped first, so the section is
    recognised at *extraction* time — before heading recovery promotes it to an ATX heading — and
    the revision apparatus is captured or flagged, never silently left in the body. A descriptive
    sentence that merely opens with the words is still rejected (its normalised text isn't one of
    the curated headings), so the proximity guard never mistakes prose for a section header."""
    return heading_furniture_text(strip_tags(line)) in REVISION_HEADING_TEXTS


def is_legacy_toc_entry(line: str) -> bool:
    """True when ``line`` is a legacy page-numbered TOC entry — ``[Title [12](#anchor)](#anchor)``
    (§6.7). The shared recognizer for the title-page cover boundary and the legacy-TOC strip."""
    return LEGACY_TOC_ENTRY_RE.match(line) is not None


def legacy_toc_target(line: str) -> str | None:
    """The ``#anchor`` a legacy TOC entry ultimately points at (the **last** ``](#…)`` target — the
    outer link, not the inner page number), or ``None`` if ``line`` is not a legacy TOC entry.
    Used by the §6.7 role-1 correlation (does every legacy entry map to a derived heading?)."""
    if not is_legacy_toc_entry(line):
        return None
    targets = _TOC_TARGET_RE.findall(line)
    return targets[-1] if targets else None


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
