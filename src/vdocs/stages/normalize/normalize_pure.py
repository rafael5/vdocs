"""Pure normalize transforms — the F-steps (§6.7, §9.6). Real-corpus-driven, incremental.

`normalize` is deterministic and per-document: same ``(body, registries)`` in → same body out
(idempotent, §7.4). This set of F-steps, grounded in the real VA corpus, covers:

  F-strip    — remove Pandoc artifacts (empty ``<!-- -->`` comments, runaway blank lines).
  F-phrases  — subtract the **curated** ``registries/phrases`` (dead text deleted outright, §9.6).
  F-anchors  — capture Word bookmarks, rewrite ``](#_Toc…)`` cross-refs to GitHub slugs, build the
               ``refs.yaml`` anchor map (delegated to ``anchors_pure``, §6.7/§5.5).
  F-toc      — regenerate ``## Contents`` from the **actual heading tree** with GitHub-slug anchors
               (§6.7: derive structure, never trust the extracted TOC).
  F-backlink — insert round-trip "↑ Back to Contents" links under each TOC-targeted heading.

  F-boilerplate — reference the **curated** ``registries/boilerplate`` (REFERENCE, not DELETE — the
               block is replaced by a link to one canonical ``gold/_shared`` copy, §9.6).
  F-levels   — infer consistent heading levels (gap-free tree) so the regenerated TOC nests sanely.

Complex tables (``tables_pure``) and the ``(doc_type, era)`` template STRIP+STAMP
(``template_pure``) are stage-level pre-steps (like ``revision_pure``), not part of the body steps.
``source_sha256`` and ``template_id`` are stamped into the frontmatter by the stage; these functions
stay pure over the body text + registries.

Heading identity and the anchor substrate live in the sibling ``anchors_pure`` module (mirroring
the ``revision_pure`` split); ``Heading``/``github_slug``/``parse_headings`` are re-exported here
for the F-toc helpers and existing callers.
"""

from __future__ import annotations

import collections
import html as _html
import re
from collections.abc import Sequence
from dataclasses import dataclass

from vdocs.kernel.markdown import (
    HEADING_RE,
    MULTI_BLANK,
    is_legacy_toc_entry,
    iter_headings,
    strip_tags,
)
from vdocs.kernel.table import PAGE_NUMBER, TOC_ENTRY_IN_TABLE_RE
from vdocs.kernel.text import block_key, github_slug_base
from vdocs.stages.normalize.anchors_pure import (
    DEFAULT_TOC_DEPTH,
    Heading,
    build_anchor_map,
    github_slug,
    insert_back_links,
    parse_headings,
    rewrite_link_targets,
)
from vdocs.stages.normalize.anchors_pure import AnchorMap as AnchorMap

__all__ = [
    "Heading",
    "github_slug",
    "parse_headings",
    "recover_headings",
    "infer_heading_levels",
    "level_headings_from_numbering",
    "recover_headings_from_toc",
    "decode_entities",
    "trim_heading_leaders",
    "strip_artifacts",
    "subtract_phrases",
    "Boilerplate",
    "subtract_boilerplate",
    "block_key",
    "strip_legacy_toc",
    "LegacyTocEntry",
    "parse_legacy_toc_entry",
    "legacy_toc_entries",
    "legacy_toc_targets",
    "correlate_legacy_toc",
    "correlate_bookmarks_by_title",
    "resolve_toc_anchors_by_title",
    "strip_existing_toc",
    "build_toc",
    "effective_toc_depth",
    "regenerate_toc",
    "normalize_body",
]

# Heading/fence/blank-run regexes + the fence-aware scan come from `kernel.markdown` (§9.2) — the
# canonical `#+` resolution (recognize >6-`#` headings) is shared by all four markdown stages.
_HEADING_LINE_RE = re.compile(r"^#+ ", re.MULTILINE)
_HTML_COMMENT_RE = re.compile(r"^<!--.*-->$")
_TOC_ENTRY_RE = re.compile(r"^\s*- \[.*\]\(#.*\)\s*$")
# a paragraph the original Word TOC linked to: a `_Toc…`/`_Ref…` bookmark anchor span at line
# start, followed by the heading text. Pandoc leaves these as plain paragraphs (no `#`). Recovery
# promotes each to a level-2 heading while **keeping** the anchor span on the line above, so
# `parse_headings` can capture the bookmark before `rewrite_link_targets` drops it (§6.7).
_RECOVER_RE = re.compile(r'^(<span id="_(?:Toc|Ref)\w+"[^>]*></span>)\s*(.+?)\s*$', re.MULTILINE)
# A2 (§6.7): the remainder after the span is **bold-wrapped** — a Word heading Pandoc rendered as
# `**bold**` instead of an ATX heading. Whole-line bold (not an inline bold span in prose).
_BOLD_PSEUDO_HEADING_RE = re.compile(r"^\*\*.*\*\*$")


def recover_headings(body: str) -> str:
    """F-recover (§6.7): give a heading tree to docs Pandoc flattened. The original Word TOC links
    to ``_Toc…``/``_Ref…`` bookmarks; Pandoc emits those targets as plain paragraphs (a leading
    ``<span id="_Toc…" …></span>`` + the heading text). Promote each to a level-2 heading
    (stripping inline markup) while **retaining** the bookmark span on the line above, so the
    bookmark identity survives into ``parse_headings``.

    Two modes (A2):
      * **no ATX headings yet** — every bookmark-span paragraph is a heading-recovery seed (the
        structureless-doc path: a flat ``##`` tree beats none);
      * **the doc already has headings** — promote **only** a span paragraph whose text is
        *bold-wrapped* (``**Reminder Location List Menu**``): a styled heading Pandoc rendered as
        bold instead of ``##``. A plain bookmark-span paragraph (a figure/table/inline target) is
        left as prose — high precision, so we recover the lost section headings (and mint the
        anchor their cross-refs resolve to) without promoting non-headings.

    Idempotent: a promoted heading sits on its own line below the (now bare) span, which no longer
    matches the single-line recovery pattern. (Level inference from TOC depth is deferred.)"""
    bold_only = bool(_HEADING_LINE_RE.search(body))  # structured doc → only bold pseudo-headings

    def repl(m: re.Match[str]) -> str:
        if bold_only and not _BOLD_PSEUDO_HEADING_RE.match(m.group(2).strip()):
            return m.group(0)  # a plain bookmark-span paragraph in a structured doc: leave as prose
        # strip inline HTML tags and any wrapping markdown emphasis (**bold**/_italic_)
        text = strip_tags(m.group(2)).strip().strip("*_ ").strip()
        return f"{m.group(1)}\n## {text}" if text else m.group(0)

    return _RECOVER_RE.sub(repl, body)


def infer_heading_levels(body: str) -> str:
    """F-levels (§6.7): rewrite heading ``#`` prefixes so the heading tree has **no skipped
    levels**, giving the regenerated TOC a sane nesting.

    Some docs jump levels (H1 → H4) or are inconsistently leveled. Each heading is reassigned to
    its depth in a gap-free hierarchy, anchored at the document's *shallowest* heading level — so an
    H2-rooted doc stays H2-rooted (H1 is the document title, never fabricated). Fence-aware (code
    blocks untouched) and idempotent (an already-gap-free tree is returned unchanged). Slugs depend
    on heading *text*, not level, so the anchor map / recovery paths are unaffected.

    The generated ``## Contents`` heading is skipped (as in ``parse_headings``) — it is our own TOC
    marker, regenerated each run, so re-leveling it would break ``normalize_body`` idempotency."""
    lines = body.split("\n")
    found = list(iter_headings(body))  # (line index, original level, text); fence- + Contents-aware
    if not found:
        return body
    base = min(level for _, level, _ in found)
    stack: list[int] = []  # original levels of the current heading's strict ancestors
    for i, level, text in found:
        while stack and stack[-1] >= level:
            stack.pop()
        new_level = base + len(stack)
        stack.append(level)
        lines[i] = "#" * new_level + " " + text
    return "\n".join(lines)


_MIN_RECOVERED_TITLE = 3  # a one- or two-character "title" is noise, not a section
# A figure/table caption from a "List of Tables"/"List of Figures" — captured like any legacy TOC
# entry, but it names a figure, not a section. Keys on the caption *number*, so a real section
# called "Table Maintenance" is untouched.
_CAPTION_RE = re.compile(r"^(?:table|figure|exhibit|chart|screen)\s+\d", re.IGNORECASE)
# A line that is structurally not a prose paragraph. `*`/`-`/`+` count as list markers only when
# followed by whitespace — `**Installation Steps:**` is a bold pseudo-heading (a Word heading the
# converter rendered as bold), which is exactly the kind of line worth recovering.
_NON_PROSE_RE = re.compile(r"^(?:[|>#!<]|[-*+]\s|\d+[.)]\s)")


def _heading_key(text: str) -> str:
    """Heading identity for TOC correlation: emphasis, markup and trailing punctuation flattened,
    case- and whitespace-insensitive — so ``**Installation Steps:**`` matches ``installation
    steps``."""
    return " ".join(re.sub(r"[*_`#]", " ", strip_tags(text)).split()).lower().strip(" .:")


def recover_headings_from_toc(body: str, toc_titles: Sequence[str]) -> str:
    """F-toc-recover (VO.8e): promote the paragraphs the document's own TOC declares as sections.

    Docling reads headings off the page visually, so a section set in body-text style arrives as an
    ordinary paragraph. The captured legacy TOC (VO.8b) is the author's own index of every section,
    which makes it the evidence for putting those headings back — the PDF counterpart of
    :func:`recover_headings`, which uses Word ``_Toc`` bookmarks for DOCX.

    Measured on the 19 PDF-only documents: **+815 sections** over 5,400 detected headings, 797 of
    them in the two Kernel binders.

    Conservative by design — a candidate must match a TOC title exactly (modulo case, emphasis and
    trailing punctuation), occur **exactly once** in the body, sit on its own line as prose, and not
    already be a heading. A title occurring twice is ambiguous, and inventing structure in the wrong
    place is worse than leaving a section undetected. The promoted heading takes the document's root
    level; depth is :func:`level_headings_from_numbering`'s job, which runs next."""
    wanted = {
        k
        for t in toc_titles
        if len(k := _heading_key(t)) >= _MIN_RECOVERED_TITLE and not _CAPTION_RE.match(k)
    }
    if not wanted:
        return body
    found = list(iter_headings(body))
    if not found:
        return body  # no tree to promote into — `recover_headings` owns the structureless path
    wanted -= {_heading_key(text) for _, _, text in found}
    if not wanted:
        return body
    lines = body.split("\n")
    fenced = {i for i, _l, _t in _fenced_line_indices(body)}
    counts: dict[str, list[int]] = {}
    for i, raw in enumerate(lines):
        s = raw.strip()
        if not s or i in fenced or _NON_PROSE_RE.match(s):
            continue
        if _is_toc_nav_line(s):
            continue  # the line IS a TOC entry — promoting it yields a heading with a dot leader
        if (k := _heading_key(s)) in wanted:
            counts.setdefault(k, []).append(i)
    # Promote to the document's SECTION level (the most common heading level), not its shallowest.
    # A recovered section is a sibling of the existing sections, not of the document title — and
    # promoting 478 of them to `#` would swamp the lone title, which is how the flat-document guard
    # in `level_headings_from_numbering` decides a document still needs its outline rebuilt.
    modal = collections.Counter(level for _, level, _ in found).most_common(1)[0][0]
    root = "#" * modal
    for k, where in counts.items():
        # unambiguous only — two candidates means we cannot know which one is the section
        if len(where) == 1:
            i = where[0]
            lines[i] = f"{root} {strip_tags(lines[i].strip()).strip('*_ ').strip()}"
    return "\n".join(lines)


def _fenced_line_indices(body: str) -> list[tuple[int, str, str]]:
    """Indices of lines inside a fenced code block — recovery must never promote sample output."""
    out: list[tuple[int, str, str]] = []
    fence = ""
    for i, line in enumerate(body.split("\n")):
        s = line.strip()
        if fence:
            out.append((i, line, fence))
            if s.startswith(fence):
                fence = ""
            continue
        if s.startswith("```") or s.startswith("~~~"):
            fence = s[:3]
            out.append((i, line, fence))
    return out


_SECTION_NUMBER_RE = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+\S")
_MAX_HEADING_LEVEL = 6  # markdown's deepest; beyond it a heading stops being one


def level_headings_from_numbering(body: str) -> str:
    """F-depth (VO.8c): give a **flat** document its outline back from its own section numbering.

    Docling detects headings in a PDF but assigns them all one level — every heading in the Kernel
    Developer's Guide comes out `##`. :func:`infer_heading_levels` cannot help: it removes gaps in
    an existing hierarchy, so flat stays flat, and the regenerated ``## Contents`` becomes hundreds
    of siblings with a degenerate ``section_path``.

    The documents state their own structure: ``2.6.10.1.1 Example 1`` is five levels deep. Depth is
    the count of numbering components, offset from the document's root level; an unnumbered heading
    stays at the root (``Revision History`` is a section, not an orphan), and depth is capped at
    markdown's six levels.

    **Applies only to a document with no hierarchy at all** (one distinct heading level, ignoring a
    lone document title). Re-deriving levels for a document that already has a tree would rewrite
    the structure of every DOCX-derived document in the corpus from a heuristic — far worse than the
    flat case this fixes; measured, it touches 2 of the 615 existing gold documents, both of which
    have genuinely numbered sections sitting flat. Fence-aware and idempotent: re-running on the
    levelled output sees a tree and declines."""
    found = list(iter_headings(body))  # fence- + generated-Contents-aware
    body_headings = _below_document_title(found)
    if len({level for _, level, _ in body_headings}) != 1:
        return body  # no headings, or a real tree already — leave it alone
    depths = [_SECTION_NUMBER_RE.match(text) for _, _, text in body_headings]
    if not any(depths):
        return body  # nothing to derive structure from
    base = body_headings[0][1]
    lines = body.split("\n")
    for (i, _level, text), m in zip(body_headings, depths, strict=True):
        depth = len(m.group(1).split(".")) - 1 if m else 0
        lines[i] = "#" * min(base + depth, _MAX_HEADING_LEVEL) + " " + text
    return "\n".join(lines)


def _below_document_title(
    found: list[tuple[int, int, str]],
) -> list[tuple[int, int, str]]:
    """``found`` minus a shallowest level that is just the document title.

    A Docling-converted PDF typically emits one ``#`` title above a wall of identical ``##``
    sections; counting the title as a second tier would make the document look structured and
    decline the rescue. The same "a lone shallowest heading is a title, several are sections" rule
    :func:`effective_toc_depth` already applies (§6.7) — kept at ≤2 here because a PDF cover page
    often yields a title plus a subtitle."""
    if not found:
        return found
    levels = sorted({level for _, level, _ in found})
    if len(levels) > 1 and sum(1 for _, level, _ in found if level == levels[0]) <= 2:
        return [h for h in found if h[1] != levels[0]]
    return found


_ENTITY_RE = re.compile(r"&(?:amp|lt|gt|quot|apos|nbsp|#\d{2,5}|#x[0-9a-fA-F]{2,4});")


def decode_entities(body: str) -> str:
    """F-entities (§6.5): turn HTML entities back into the characters they stand for.

    Docling escapes ``<`` and ``>`` in text, and VistA manuals are full of M code that uses them —
    ``K:$L(X)>40!($L(X)<3) X`` arrives as ``K:$L(X)&gt;40!($L(X)&lt;3) X``. That costs a search
    every time: FTS5 tokenises ``&gt;`` into the noise token ``gt``, so a query for the code cannot
    match the text containing it (1,659 escapes in the FileMan Developer's Guide alone). It is also
    a convergence fix — the Pandoc path already yields raw ``<``/``>`` in code, so leaving only
    Docling's escaped would keep two converters producing different text for identical source.

    **One level only.** ``&amp;lt;`` is the literal text ``&lt;`` — documentation *about* escaping —
    and decoding twice would silently turn it into the thing it describes.

    Ordered late in :func:`normalize_body`, after every step that reads HTML structure, so a decoded
    ``<`` can never be mistaken for markup by this pipeline."""
    return _ENTITY_RE.sub(lambda m: _html.unescape(m.group(0)), body)


# A heading that ends in a dot leader (optionally followed by a page number) is a TOC line the
# converter mistook for a heading — 4+ dots, so a genuine "Select an option ..." ellipsis survives.
_HEADING_LEADER_RE = re.compile(
    r"[ \t]*\.{4,}[ \t]*(?:" + PAGE_NUMBER + r")?[ \t]*$", re.IGNORECASE
)


def trim_heading_leaders(body: str) -> str:
    """Drop a trailing dot leader (and its page number) from a heading's text (§6.7).

    Docling detects headings visually, so a line in an unstripped table of contents can arrive as
    ``## 27.1 Introduction ....................... 27``. Left alone it becomes a section whose name
    contains its own page number — in the heading tree, the regenerated ``## Contents``, the anchor
    slug and ``section_path``. Fence-aware; a genuine ellipsis (``...``) is not a leader."""
    lines = body.split("\n")
    for i, level, text in iter_headings(body):
        trimmed = _HEADING_LEADER_RE.sub("", text).rstrip()
        if trimmed and trimmed != text:
            lines[i] = "#" * level + " " + trimmed
    return "\n".join(lines)


def strip_artifacts(body: str) -> str:
    """F-strip: drop standalone empty HTML comments (Pandoc emits many) + collapse blank runs."""
    kept = [ln for ln in body.split("\n") if not _HTML_COMMENT_RE.match(ln.strip())]
    return MULTI_BLANK.sub("\n\n", "\n".join(kept)).strip("\n") + "\n"


def _furniture_core(text: str) -> str:
    """A block's alphanumeric core — emphasis markers (``*``/``_``/`` ` ``), punctuation, and
    whitespace runs all flattened away — so a curated dead phrase matches the paper-era variant
    the corpus actually emits (``*This page intentionally left blank for double-sided printing.*``
    vs the phrase ``This page intentionally left blank``)."""
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", text.lower()).split())


def subtract_phrases(body: str, phrases: frozenset[str]) -> str:
    """F-phrases: delete whole blocks matching a curated dead phrase (§9.6, DELETE).

    A block is dead text when its alphanumeric core (emphasis/punctuation flattened by
    :func:`_furniture_core`) **equals** a phrase's core, **or** — for a sufficiently specific
    phrase (≥4 words) — **begins with** it (so an emphasis-wrapped blank-page line with a trailing
    "for double-sided printing." clause is still removed). The ≥4-word guard keeps short phrases
    (``End of document``) exact-only, so real prose that merely opens with the words is never eaten.
    """
    if not phrases:
        return body
    cores = [c for c in (_furniture_core(p) for p in phrases) if c]
    long_cores = [c for c in cores if len(c.split()) >= 4]
    blocks = re.split(r"\n\s*\n", body)
    kept = []
    for b in blocks:
        bc = _furniture_core(b)
        if bc in cores or any(bc.startswith(c + " ") or bc == c for c in long_cores):
            continue
        kept.append(b)
    return "\n\n".join(kept)


# Gold-root-relative path to the single-sourced boilerplate copies (§9.7: gold/_shared/boilerplate).
# Kept gold-root-relative on purpose — `publish` resolves it to the bundle's published depth (see
# subtract_boilerplate's PUBLISH SEAM note).
SHARED_BOILERPLATE_DIR = "_shared/boilerplate"


@dataclass(frozen=True)
class Boilerplate:
    """A curated boilerplate block: its canonical id, a short link label, and the match key.

    The canonical copy (``text``) lives in ``registries/boilerplate`` (destined for
    ``gold/_shared/boilerplate/<id>.md``); only the ``key`` is needed to recognise a body block."""

    id: str
    label: str
    key: str


def subtract_boilerplate(body: str, registry: Sequence[Boilerplate]) -> str:
    """F-boilerplate (§9.6 REFERENCE): replace each body block matching a curated boilerplate
    block with a link to the canonical shared copy — kept once, de-duplicated (distinct from
    ``subtract_phrases``, which DELETEs). Matching is whitespace/case-insensitive (``block_key``);
    idempotent (the reference link it leaves is not a registered block).

    PUBLISH SEAM (§5.3/§9.7): the emitted target ``_shared/boilerplate/<id>.md`` names the
    **gold-root** canonical home ``gold/_shared/boilerplate/<id>.md``; it is written in
    gold-root-relative form here because the silver bundle's eventual published depth is not known
    until ``publish`` lays out the human tree. ``publish`` owns rewriting these to the correct
    relative depth when it materialises bundles (the same way it materialises images) — this is a
    tracked publish-phase responsibility, not a silently bundle-relative link."""
    if not registry:
        return body
    by_key = {b.key: b for b in registry}
    out: list[str] = []
    for block in re.split(r"\n\s*\n", body):
        bp = by_key.get(block_key(block))
        if bp is None:
            out.append(block)
        else:
            label = bp.label.replace("[", "").replace("]", "")
            out.append(f"_[{label} — shared boilerplate]({SHARED_BOILERPLATE_DIR}/{bp.id}.md)_")
    return "\n\n".join(out)


# A *loose* legacy-TOC entry, used **only inside a confirmed TOC block** (after a recognised
# header). Covers the three page-number placements the corpus emits, with an optional leading
# ``N.`` ordered-list marker:
#   * double-bracket  ``[Title [12](#a)](#a)``
#   * single-bracket  ``Introduction [1](#a)``          (inner ``[page]`` bracket)
#   * page-in-text    ``1.  [Introduction 14](#a)``      (page appended to the link text)
# Kept distinct from the kernel ``is_legacy_toc_entry`` (strict double-bracket): these looser shapes
# are ambiguous with an ordinary in-prose link, so they are trusted only within the bounded TOC
# block, never globally (the header-less catch-all uses the strict form).
_PAGE = r"[0-9ivxlcdm][0-9ivxlcdm.\-]*"  # int / roman / chapter-dash page number (case-insensitive)
_LOOSE_TOC_ENTRY_RE = re.compile(
    r"(?i)^[ \t]*(?:[>*+\-][ \t]+|\d+\.[ \t]+)*\[?[^\]\n]*?"
    r"(?:\[" + _PAGE + r"\]|[ \t]" + _PAGE + r")"
    r"\]?\(#[^)]*\)(?:\]\(#[^)]*\))?[ \t]*$"
)
_TOC_TARGET_RE = re.compile(r"\]\((#[^)]*)\)")


_TOC_PREFIX_RE = re.compile(r"^[ \t]*(?:[>*+\-][ \t]+|\d+\.[ \t]+)*")
_INNER_PAGE_RE = re.compile(r"\[(" + _PAGE + r")\]\(#[^)]*\)", re.IGNORECASE)
_LINK_TEXT_RE = re.compile(r"\[([^\]]*)\]\(#[^)]*\)")
_TRAILING_PAGE_RE = re.compile(r"\s(" + _PAGE + r")$", re.IGNORECASE)


@dataclass(frozen=True)
class LegacyTocEntry:
    """One original (paper-era) table-of-contents entry — its title, the **original page number**,
    and the anchor it pointed at — captured verbatim into ``toc.yaml`` before the legacy TOC leaves
    the body (§6.7), so the derived link-based ``## Contents`` keeps a reference back to the printed
    document's pagination."""

    title: str
    page: str
    anchor: str


def parse_plain_toc_entry(line: str) -> LegacyTocEntry | None:
    """Parse the **anchorless** paper form of a legacy TOC entry — ``Introduction .......... 1``,
    ``Glossary 113`` — into ``(title, page, anchor="")``, or ``None`` when there is no trailing
    page number.

    P3.1: the pre-anchor VistA manuals Pandoc converts emit exactly this shape (no ``](#…)`` link
    survives), and the TOC strip drops those lines like any other inside a confirmed TOC region.
    Without this parser they left the body with **no record at all** — a capture-before-strip
    violation (§6.4/§6.7) invisible to every other net (the typed-capture residue scan only asks
    whether a legacy-TOC *heading* survived, and the strip removed that too), and the measured root
    cause of both live QUARANTINE documents. Trusted **only inside a confirmed TOC block** (like the
    loose form), never globally: a bare "Title 12" line is ambiguous with ordinary prose."""
    s = _TOC_PREFIX_RE.sub("", line.strip())
    if _TOC_TARGET_RE.search(s):
        return None  # an anchored entry — parse_legacy_toc_entry owns the linked dialects
    # drop the dot/space leader ("....", " . . . ") that separates the title from its page number
    s = re.sub(r"[.\s]{2,}(?=" + _PAGE + r"$)", " ", s, flags=re.IGNORECASE)
    m = _TRAILING_PAGE_RE.search(s)
    if m is None:
        return None
    title = strip_tags(s[: m.start()]).strip().strip(".").strip("*_ ").strip()
    return LegacyTocEntry(title, m.group(1), "") if title else None


def parse_legacy_toc_entry(line: str) -> LegacyTocEntry | None:
    """Parse a legacy TOC entry line into ``(title, page, anchor)`` across every corpus dialect, or
    ``None`` when the line is not an entry. The page is the inner ``[n]`` bracket when present
    (``[Title [12](#a)](#a)``), else the trailing number in the link text (``[Title 12](#a)``); the
    anchor is the outer (last) ``](#…)`` target; leading bullet/blockquote/ordered markers are
    stripped first."""
    s = _TOC_PREFIX_RE.sub("", line.strip())
    anchors = _TOC_TARGET_RE.findall(s)
    if not anchors:
        return None
    anchor = anchors[-1]
    if (inner := _INNER_PAGE_RE.search(s)) is not None:
        page = inner.group(1)
        title = s[: inner.start()].strip().lstrip("[").strip()
    else:
        link = _LINK_TEXT_RE.search(s)
        text = link.group(1).strip() if link else ""
        if (m := _TRAILING_PAGE_RE.search(text)) is not None:
            page, title = m.group(1), text[: m.start()].strip()
        else:
            page, title = "", text
    return LegacyTocEntry(title.strip("*_ ").strip(), page, anchor)


# --- the table dialect (VO.8b): Docling renders a legacy PDF TOC as a markdown table ---------
# A `|`-delimited row never ends in a page number, so `_TRAILING_PAGE_RE` cannot see it and the
# region strip used to bound at the first row — leaving the whole TOC in the body (11.9% of the
# Kernel Developer's Guide) with one entry captured. Rows are also duplicated across every cell,
# and one cell can carry several entries run together.
_TABLE_SEPARATOR_RE = re.compile(r"^[ \t]*\|[\s:|-]*\|[ \t]*$")
# One entry *found* (not split out): a title, its dot leader, and the page number. Matching the
# whole shape is what keeps `2.1.1 Example.....2` intact — splitting on a page-number pattern tears
# it apart, because a section number like `2.1.1` is itself a valid page-number match. Defined once
# in `kernel.table` because `tables_pure` needs the same test to avoid lifting a TOC to CSV (§9.2).
_TOC_TABLE_ENTRY_RE = TOC_ENTRY_IN_TABLE_RE


def split_toc_table_row(line: str) -> list[str]:
    """The TOC entries carried by one markdown table row, or ``[]`` when it is not one (VO.8b).

    Three shapes are handled: a **separator** row (no entries), **duplicated cells** (Docling
    repeats the same entry across all four columns — captured once, or `toc.yaml` would gain three
    phantoms), and **several entries in one cell**, split at each dot-leader-plus-page boundary.

    A row with no dot-leader page entry in any cell returns ``[]`` so a genuine content table is
    never mistaken for a TOC — the same "trusted only inside a confirmed TOC region" rule the loose
    and plain dialects already follow."""
    s = line.strip()
    if not s.startswith("|") or _TABLE_SEPARATOR_RE.match(line):
        return []
    cells: dict[str, None] = {}  # ordered set — Docling repeats a cell verbatim across columns
    for cell in (c.strip() for c in s.strip("|").split("|")):
        if cell:
            cells.setdefault(cell, None)
    # Scan the row as one string rather than cell by cell: Docling splits a single entry across
    # cells, putting the section number and/or the page number in their own column
    # (`| 1.4.1 | Intended Audience ......... | 7 |`). Joining after de-duplication reunites them —
    # and keeps the section number attached to its title, which is what carries the outline depth.
    joined = " ".join(cells)
    entries: dict[str, None] = {}
    for m in _TOC_TABLE_ENTRY_RE.finditer(joined):
        if entry := m.group(0).strip():
            entries.setdefault(entry, None)
    return list(entries)


def _toc_table_lines(lines: list[str], start: int, end: int) -> set[int]:
    """Indices in ``[start, end)`` belonging to a contiguous markdown-table run that carries at
    least one parsable TOC entry (VO.8b).

    Docling emits the whole legacy TOC as **one table**, and plenty of its rows carry no page
    number of their own — a bare section number (``| 2.5 |``), a title wrapped onto its own row, an
    empty spacer. Judged individually those read as prose and bound the strip one row into the
    block; judged as part of a run that demonstrably contains TOC entries, they are what they are.

    The run must *prove itself* with a real entry, so an ordinary content table is never claimed —
    and everything outside such a run still faces the unchanged ``has_prose`` guard."""
    out: set[int] = set()
    i = start
    while i < end:
        if not lines[i].lstrip().startswith("|"):
            i += 1
            continue
        j = i
        while j < end and lines[j].lstrip().startswith("|"):
            j += 1
        if any(split_toc_table_row(lines[k]) for k in range(i, j)):
            out.update(range(i, j))
        i = j
    return out


def capture_toc_entries(line: str) -> list[LegacyTocEntry]:
    """Every :class:`LegacyTocEntry` on one TOC-region line — a list, because a table row can carry
    many (the other dialects carry at most one). The strip and the capture read the *same*
    function, which is what keeps "anything dropped is recorded" true by construction."""
    if rows := split_toc_table_row(line):
        return [e for r in rows if (e := parse_plain_toc_entry(r)) is not None]
    if (e := _capture_toc_entry(line)) is not None:
        return [e]
    return _table_row_titles(line)


def _table_row_titles(line: str) -> list[LegacyTocEntry]:
    """Title-only entries for a TOC-table row the entry parsers could not read (VO.8b).

    Inside a confirmed TOC block, rows still get dropped when their page number carries no dot
    leader (``Appendix E: Exported Values.379``, ``Exported Routines``). Recording them page-less
    beats losing them: ``toc.yaml`` is a record, so over-capturing costs a junk row while
    under-capturing is the silent content loss this corpus has already suffered once.

    Separator, empty and pure-leader rows carry nothing and record nothing."""
    s = line.strip()
    if not s.startswith("|") or _TABLE_SEPARATOR_RE.match(line):
        return []
    seen: dict[str, None] = {}
    for cell in (c.strip() for c in s.strip("|").split("|")):
        title = strip_tags(cell).strip(". ").strip("*_ ").strip()
        if title and re.search(r"[A-Za-z]", title):
            seen.setdefault(title, None)
    return [LegacyTocEntry(t, "", "") for t in seen]


def _is_loose_toc_entry(line: str) -> bool:
    return _LOOSE_TOC_ENTRY_RE.match(line) is not None


def _capture_toc_entry(line: str) -> LegacyTocEntry | None:
    """The capture half of the strip/capture pair (P3.1): parse a TOC-region line into a
    :class:`LegacyTocEntry` in **either** dialect — anchored (``parse_legacy_toc_entry``) or the
    anchorless paper form (``parse_plain_toc_entry``) — or ``None`` for a blank/leader line that
    carries no entry.

    The invariant this exists to hold: **anything the strip drops that is an entry is captured.**
    Keeping the two halves in one function is what stops them drifting apart again — the previous
    split (drop every region line, capture only linked ones) deleted ~1,000 words of paper TOC per
    affected document with no record."""
    if _is_loose_toc_entry(line) and (e := parse_legacy_toc_entry(line)) is not None:
        return e
    return parse_plain_toc_entry(line)


def _is_toc_nav_line(line: str) -> bool:
    """A line that belongs to a legacy-TOC block — a blank, an anchor-linked entry, a dotted/plain
    entry ending in a page number, or a **table row** carrying such entries (VO.8b, Docling's PDF
    dialect) — as opposed to body prose. Bounds the ATX-heading TOC strip so it stops at the first
    real prose line instead of running into a flattened doc's body (which has no terminating
    heading to stop it).

    A table *separator* row counts too: it sits inside the block and carries nothing, so treating it
    as prose would bound the strip one line into the TOC."""
    s = line.strip()
    if not s:
        return True
    if s.startswith("|"):
        # a content table (no dot-leader page entries) is prose and correctly ends the region
        return bool(_TABLE_SEPARATOR_RE.match(line)) or bool(split_toc_table_row(line))
    return _is_loose_toc_entry(line) or _TRAILING_PAGE_RE.search(s) is not None


def _norm_toc_title(line: str) -> str:
    """A legacy-TOC heading line's bare title — HTML tags (the ``<span id="_Toc…">`` bookmark
    old-gen headers carry), emphasis (``*``/``_``/`` ` ``), ATX/blockquote markers, and whitespace
    runs all flattened — so a curated title matches every markup variant the corpus emits
    (``# **Table of Contents**``, ``<span id="_Toc1"></span>List of Figures``, ``## Contents``)."""
    return " ".join(re.sub(r"[*_`>#]", " ", strip_tags(line)).split()).lower()


def _followed_by_toc_entry(lines: list[str], i: int, lookahead: int = 2) -> bool:
    """True when a legacy page-numbered TOC entry appears within the next ``lookahead`` non-blank
    lines after ``i`` — the guard that a *plain-text* ``Table of Contents`` line really heads a
    legacy TOC (not a stray mention of the words)."""
    seen = 0
    for j in range(i + 1, len(lines)):
        if not lines[j].strip():
            continue
        if _is_loose_toc_entry(lines[j]):
            return True
        seen += 1
        if seen >= lookahead:
            return False
    return False


def _scan_legacy_toc(
    body: str, titles: frozenset[str], max_level: int
) -> tuple[set[int], list[LegacyTocEntry]]:
    """The single legacy-TOC scanner (§6.7): returns the line indices to drop **and** the parsed
    ``LegacyTocEntry`` (title + original page + anchor) of every dropped page-numbered entry — for
    both the role-1 correlation and the ``toc.yaml`` capture.

    Two corpus forms are recognised:
      * **ATX heading** — a ``Table of Contents`` / ``Contents`` heading at H1–H3 (or the oversized
        >6-``#`` form upstream mangles); drop the heading + every line up to the next markdown
        heading (its dotted/tab/double-bracket page entries).
      * **plain text** — a bare ``Table of Contents`` line (no ``#``) **immediately followed by**
        the page-numbered ``[Title [n](#anchor)](#anchor)`` entry block; drop the header + that
        contiguous entry/blank run (stopping before the next real content line)."""
    wanted = {t.strip().lower() for t in titles}
    lines = body.split("\n")
    drop: set[int] = set()
    entries: list[LegacyTocEntry] = []
    n = len(lines)
    i = 0
    while i < n:
        if i in drop:
            i += 1
            continue
        m = HEADING_RE.match(lines[i])
        # A heading whose *full* text is exactly a curated legacy-TOC title is legacy at **any**
        # level — H1–H3, the H4–H6 the old `max_level=3` gate missed, and the oversized >6-`#`
        # form upstream mangles. The exact title match (not a substring) keeps it safe.
        if m and _norm_toc_title(lines[i]) in wanted:
            # Region end: the next markdown heading, or EOF. A clean TOC region is entries + blanks;
            # a Pandoc-flattened doc has no terminating heading, so "drop to the next heading" ran
            # to EOF and deleted the body. If the region carries substantive prose (a non-blank line
            # that isn't a page-numbered entry), bound the drop to the contiguous leading entry/
            # blank run — stop at the first prose line (mirrors the plain-text branch). Otherwise
            # drop the whole region (byte-identical to before for every well-formed doc).
            h = i + 1
            while h < n and not HEADING_RE.match(lines[h]):
                h += 1
            tbl = _toc_table_lines(lines, i + 1, h)  # VO.8b — the TOC-as-table block, whole
            has_prose = any(
                not _is_toc_nav_line(lines[k]) and k not in tbl for k in range(i + 1, h)
            )
            drop.add(i)
            j = i + 1
            while j < (n if has_prose else h):
                if has_prose and not _is_toc_nav_line(lines[j]) and j not in tbl:
                    break  # first body-prose line ends the bounded TOC region
                drop.add(j)
                entries.extend(capture_toc_entries(lines[j]))
                j += 1
            i = j
            continue
        if not m and lines[i].strip() and _norm_toc_title(lines[i]) in wanted:
            if not _followed_by_toc_entry(lines, i):
                # a bare legacy header whose entries degraded to plain text / page-numbered
                # headings (no `(#anchor)` links left to consume): drop just the stale header label
                # so it does not linger above the derived `## Contents`.
                drop.add(i)
                i += 1
                continue
            drop.add(i)
            j = i + 1
            while j < n:
                if not lines[j].strip():  # blanks: only swallow them if more entries follow
                    k = j
                    while k < n and not lines[k].strip():
                        k += 1
                    if k < n and _is_loose_toc_entry(lines[k]):
                        drop.update(range(j, k))
                        j = k
                        continue
                    break
                if _is_loose_toc_entry(lines[j]):
                    drop.add(j)
                    entries.extend(capture_toc_entries(lines[j]))
                    j += 1
                    continue
                break
            i = j
            continue
        # Orphaned strict legacy entry (a figure/table list or a header-less block whose header
        # text isn't curated): the double-bracket page-numbered form is unambiguous — only ever
        # legacy navigation — so it is stripped wherever it appears, and its target captured for the
        # role-1 correlation. (Single-bracket entries stay trusted only under a header, above.)
        if is_legacy_toc_entry(lines[i]):
            drop.add(i)
            if (e := parse_legacy_toc_entry(lines[i])) is not None:
                entries.append(e)
        i += 1
    return drop, entries


def strip_legacy_toc(body: str, titles: frozenset[str], max_level: int = 3) -> str:
    """F-toc-dedup (§6.7; ``registries/structures`` CANONICALIZE ``toc``, §9.6): remove the source's
    legacy in-body table of contents — in **both** the ATX-heading and plain-text forms (see
    :func:`_scan_legacy_toc`) — so the derived ``## Contents`` (F-toc) never duplicates it.

    Registry-driven for the *header* line (``titles`` come from ``registries/structures``), but the
    unambiguous double-bracket page-numbered **entries** are stripped even with no curated title.
    Idempotent: a prior run's generated ``## Contents`` is an ATX ``contents`` heading, so it is
    itself stripped and rebuilt identically."""
    drop, _ = _scan_legacy_toc(body, titles, max_level)
    return "\n".join(line for i, line in enumerate(body.split("\n")) if i not in drop)


def legacy_toc_entries(
    body: str, titles: frozenset[str], max_level: int = 3
) -> list[LegacyTocEntry]:
    """The original legacy-TOC entries (title + page + anchor), captured **before** the TOC is
    stripped (§6.7) — the input to both the role-1 correlation and the ``toc.yaml`` sidecar. No
    legacy TOC ⇒ ``[]``."""
    _, entries = _scan_legacy_toc(body, titles, max_level)
    return entries


def legacy_toc_targets(body: str, titles: frozenset[str], max_level: int = 3) -> list[str]:
    """The outer ``#anchor`` targets of the legacy TOC's page-numbered entries (§6.7) — the role-1
    completeness oracle's input. Thin view over :func:`legacy_toc_entries`."""
    return [e.anchor for e in legacy_toc_entries(body, titles, max_level)]


def correlate_legacy_toc(targets: list[str], headings: list[Heading]) -> list[str]:
    """Role-1 cross-check (§6.7): the legacy-TOC entry ``targets`` whose ``#anchor`` has **no**
    counterpart heading in the derived tree — preserving document order, de-duplicated.

    A resolved target's anchor equals a derived heading's GitHub slug; an unresolved one is either
    (a) a Word bookmark (``#_Toc…``/``#_Ref…``) that never matched a heading or (b) an intended
    section that lost its heading level in conversion. Both are **heading-recovery inputs + fidelity
    flags**, never silent losses — so the legacy TOC is only safe to drop once they are recorded."""
    slugs = {h.slug for h in headings}
    unresolved: list[str] = []
    for t in targets:
        if t.lstrip("#") in slugs or t in unresolved:
            continue
        unresolved.append(t)
    return unresolved


def resolve_toc_anchors_by_title(
    toc_entries: list[LegacyTocEntry], headings: list[Heading]
) -> list[LegacyTocEntry]:
    """Give an **anchorless** legacy-TOC entry the anchor of the heading it names (VO.8f).

    A Word TOC carries ``](#_Toc…)`` links, so the DOCX path fills ``toc.yaml``'s ``anchor`` and
    ``resolved`` columns. A PDF's TOC is printed text — ``Introduction .......... 1`` — with no link
    of any kind, so every Docling-captured entry landed ``anchor: ''``, ``resolved: false``: the
    same schema, but two columns dead on one converter and live on the other, and a sidecar unusable
    as a navigation index for exactly the documents whose outline we most need.

    Composes what is already in hand — the entry gives a title, the derived tree gives title → slug,
    the same correlation :func:`correlate_bookmarks_by_title` performs for Word bookmarks, keyed
    here on the title itself. First match in document order, since a repeated title is inherently
    ambiguous.

    An entry that already carries an anchor is never second-guessed (the Word bookmark is
    authoritative), and one that matches no heading **stays anchorless** — it never pointed
    anywhere, and per P3.1 it must not become a fidelity flag manufactured out of printed
    pagination."""
    by_base: dict[str, str] = {}
    for hd in headings:
        by_base.setdefault(github_slug_base(hd.text), hd.slug)
    out: list[LegacyTocEntry] = []
    for e in toc_entries:
        if not e.anchor and (slug := by_base.get(github_slug_base(e.title))):
            out.append(LegacyTocEntry(e.title, e.page, f"#{slug}"))
        else:
            out.append(e)
    return out


def correlate_bookmarks_by_title(
    toc_entries: list[LegacyTocEntry], headings: list[Heading]
) -> dict[str, str]:
    """Recover the ``_Toc…``/``_Ref…`` bookmark → GitHub-slug mapping for headings whose inline
    bookmark span conversion dropped — so ``parse_headings`` captured the heading but with
    ``bookmark=None``, leaving the in-body ``](#_Toc…)`` cross-refs to it ``UNRESOLVED`` (§6.7).

    Composes the two halves already in hand: the legacy TOC records ``bookmark ↔ title`` (captured
    to ``toc.yaml`` before the TOC leaves the body) and the derived tree gives ``title → slug``.
    For each legacy entry whose anchor is a Word bookmark, map that bookmark to the slug of the
    heading whose title slugifies the same — first match in document order (a repeated title is
    inherently ambiguous; the first heading is the deterministic best choice; the slug of a base's
    first occurrence is the bare base, so the title's slug-base keys it directly). This is the
    recoverable, C5-bounded resolvability class the validate gate measures (FF C5)."""
    by_base: dict[str, str] = {}
    for h in headings:
        by_base.setdefault(github_slug_base(h.text), h.slug)
    recovered: dict[str, str] = {}
    for e in toc_entries:
        bm = e.anchor.lstrip("#")
        if not (bm.startswith("_Toc") or bm.startswith("_Ref")) or not e.title:
            continue
        if (slug := by_base.get(github_slug_base(e.title))) is not None:
            recovered.setdefault(bm, slug)
    return recovered


def strip_existing_toc(body: str) -> str:
    """Remove a previously-generated ``## Contents`` block (its heading + list) for idempotency."""
    lines = body.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].strip().lower() == "## contents":
            i += 1
            while i < len(lines) and (not lines[i].strip() or _TOC_ENTRY_RE.match(lines[i])):
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


def effective_toc_depth(
    headings: list[Heading], default: tuple[int, int] = DEFAULT_TOC_DEPTH
) -> tuple[int, int]:
    """The TOC depth to actually use for a document (§6.7): from the top **section** level down to
    the deepest heading the document actually uses.

    A **lone** leading top-level heading is the document title, so the span starts below it; when
    the shallowest level has **several** headings those are sections, not a title, and the span
    includes them (multi-``H1`` release notes and flat manuals still get a ``## Contents``). No
    headings → the default.

    **It spans every level, not two** (human review, 2026-08-04). The source PDFs' printed tables of
    contents list every level and ours listed two, so the Contents was silently truncated against
    the document it describes: 704 of 846 headings missing on the FileMan Developer's Guide, 1,589
    of 2,144 on the CPRS Technical Manual. The heading tree is the structure; showing a fixed slice
    of it was a navigation loss, not a simplification."""
    levels = sorted({h.level for h in headings})
    if not levels:
        return default
    base = levels[0]
    base_count = sum(1 for h in headings if h.level == base)
    if base_count <= 1 and len(levels) > 1:  # a single title heading above deeper sections
        return (base + 1, max(levels))
    return (base, max(levels))


def build_toc(headings: list[Heading], toc_depth: tuple[int, int] = DEFAULT_TOC_DEPTH) -> str:
    """A ``## Contents`` GFM list linking each in-depth heading to its slug anchor (nested by
    level). Only headings within ``toc_depth`` are listed — H1 is the doc title, never a TOC
    entry (§6.7), and the TOC, back-links, and anchor map all share this depth so they agree."""
    lo, hi = min(toc_depth), max(toc_depth)
    entries = [h for h in headings if lo <= h.level <= hi]
    if not entries:
        return ""
    base = min(h.level for h in entries)
    lines = ["## Contents", ""]
    lines += [f"{'  ' * (h.level - base)}- [{h.text}](#{h.slug})" for h in entries]
    return "\n".join(lines)


_BOLD_LINE_RE = re.compile(r"^\*\*.+\*\*$")
_ITALIC_LINE_RE = re.compile(r"^_.+_$")
_SOURCE_LINE_RE = re.compile(r"^Source: ")


def _is_title_block_line(line: str) -> bool:
    """A line belonging to the leading title block: a legacy leading H1, or a line of the
    standardized cover (§6.4) — a bold title, its italic version/published meta, or the
    ``Source:`` line. These sit above the TOC; everything else opens the document body."""
    if HEADING_RE.match(line) and line.startswith("# "):
        return True
    s = line.strip()
    return bool(_BOLD_LINE_RE.match(s) or _ITALIC_LINE_RE.match(s) or _SOURCE_LINE_RE.match(s))


def _title_block_end(lines: list[str]) -> int:
    """Insert offset just past the leading title block — the standardized cover (bold title +
    italic meta + ``Source:`` line) or a legacy leading H1, skipping the blanks between them.
    0 when the body opens straight into content, so the TOC then prepends."""
    last = -1
    for idx, ln in enumerate(lines):
        if not ln.strip():
            continue
        if _is_title_block_line(ln):
            last = idx
            continue
        break
    return last + 1


def regenerate_toc(body: str, toc_depth: tuple[int, int] = DEFAULT_TOC_DEPTH) -> str:
    """F-toc: replace any stale ``## Contents`` with a fresh TOC derived from the heading tree.

    Inserted after the leading title block (the standardized cover or a legacy top-level title
    heading) if present, else at the top of the body — so the title always sits above the TOC."""
    body = strip_existing_toc(body)
    toc = build_toc(parse_headings(body), toc_depth)
    if not toc:
        return body
    lines = body.split("\n")
    insert_at = _title_block_end(lines)
    head, tail = lines[:insert_at], lines[insert_at:]
    return "\n".join([*head, "", toc, "", *tail]).strip("\n") + "\n"


def normalize_body(
    body: str,
    phrases: frozenset[str],
    doc_id: str = "",
    toc_depth: tuple[int, int] = DEFAULT_TOC_DEPTH,
    boilerplate: Sequence[Boilerplate] = (),
    toc_titles: frozenset[str] = frozenset(),
) -> tuple[str, AnchorMap]:
    """Apply the F-steps in order and return ``(body, anchor_map)`` (§6.7).

    Order matters for idempotency: recover headings → strip artifacts → subtract curated phrases →
    **reference curated boilerplate** (REFERENCE, §9.6) → **strip the legacy in-body TOC** (curated
    ``registries/structures`` ``toc``, §9.6) so the derived TOC below isn't a duplicate →
    **infer consistent heading levels** (gap-free tree) → parse the heading tree **once** (capturing
    bookmarks) → rewrite ``_Toc``/``_Ref`` cross-refs to GitHub slugs (using that tree) → regenerate
    the TOC (same slugs, so TOC + map stay consistent) → insert round-trip back-links. The anchor
    map travels to the ``refs.yaml`` sidecar.

    ``toc_depth`` is the H2–H3 fallback today; the template F-step will resolve it per
    ``(doc_type, era)`` and pass it in (the template seam lives in ``anchors_pure``)."""
    # Decode entities FIRST among the body steps: the stage's HTML-structure readers (table
    # extraction, HTML→GFM, text-box fencing) have already run, so a decoded `<` cannot be taken
    # for markup — and doing it before any heading is parsed keeps slugs, TOC links and anchors
    # computed from one spelling. Decoding *after* the TOC was generated desynchronised them and
    # cost 28 of 1,567 links on the FileMan Developer's Guide.
    body = subtract_phrases(strip_artifacts(recover_headings(decode_entities(body))), phrases)
    body = subtract_boilerplate(body, boilerplate)
    # CORRELATE-BEFORE-DROPPING (§6.7 role-1): capture the legacy TOC's original entries (title +
    # page + anchor) *before* it leaves the body, then strip it (ATX-heading + plain-text forms).
    toc_entries = legacy_toc_entries(body, toc_titles)
    body = strip_legacy_toc(body, toc_titles)
    # VO.8e, before the depth steps: the captured TOC is the author's index of every section, so
    # the paragraphs it names are the headings the converter failed to detect. Recovering them
    # first means a recovered *numbered* heading still gets its depth below.
    body = trim_heading_leaders(body)  # a heading is never a TOC line (§6.7)
    body = recover_headings_from_toc(body, [e.title for e in toc_entries])
    # VO.8c, before the gap-filler: a flat document (every Docling-converted PDF) gets its outline
    # from its own section numbering; `infer_heading_levels` then normalises whatever gaps remain.
    body = level_headings_from_numbering(body)
    body = infer_heading_levels(body)
    headings = parse_headings(body, doc_id)
    # Resolve the TOC depth: an explicit non-default override (the template seam) wins; otherwise
    # adapt to the heading tree so multi-H1 docs still get a `## Contents` (§6.7).
    depth = toc_depth if toc_depth != DEFAULT_TOC_DEPTH else effective_toc_depth(headings)
    # RECOVER-DROPPED-BOOKMARKS (§6.7, FF C5): a heading whose `_Toc…` span conversion dropped
    # parses with no bookmark, so its in-body cross-refs would resolve UNRESOLVED. Reconstruct the
    # bookmark→slug mapping from the legacy TOC's `bookmark ↔ title` × the derived `title → slug`,
    # then thread it through outbound resolution AND the legacy-TOC resolved/unresolved views so
    # refs.yaml stays internally consistent (a recovered anchor is no longer "lost").
    recovered = correlate_bookmarks_by_title(toc_entries, headings)
    # VO.8f: a printed (anchorless) TOC entry gets the anchor of the heading it names, so `toc.yaml`
    # has the same live `anchor`/`resolved` columns whichever converter produced the body.
    toc_entries = resolve_toc_anchors_by_title(toc_entries, headings)
    slugs = {h.slug for h in headings}

    def _anchor_resolves(anchor: str) -> bool:
        a = anchor.lstrip("#")
        return a in slugs or a in recovered

    # Only an entry that CARRIED an anchor can be unresolved: an anchorless paper entry
    # (``Introduction .......... 1``) never pointed anywhere, so counting it would manufacture a
    # fidelity flag out of printed pagination (P3.1).
    toc_unresolved = [
        a
        for a in correlate_legacy_toc([e.anchor for e in toc_entries if e.anchor], headings)
        if a.lstrip("#") not in recovered
    ]
    legacy_toc = [
        {
            "title": e.title,
            "page": e.page,
            "anchor": e.anchor,
            "resolved": _anchor_resolves(e.anchor),
        }
        for e in toc_entries
    ]
    bookmark_to_slug = {h.bookmark: h.slug for h in headings if h.bookmark}
    for bm, slug in recovered.items():  # inline-captured spans (more authoritative) already win
        bookmark_to_slug.setdefault(bm, slug)
    body, outbound = rewrite_link_targets(body, bookmark_to_slug)
    body = regenerate_toc(body, depth)
    body = insert_back_links(body, headings, depth)
    return body, build_anchor_map(headings, doc_id, depth, outbound, toc_unresolved, legacy_toc)
