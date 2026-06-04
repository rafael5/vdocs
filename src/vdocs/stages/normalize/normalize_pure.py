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


def recover_headings(body: str) -> str:
    """F-recover (§6.7): give a heading tree to docs Pandoc flattened. The original Word TOC links
    to ``_Toc…``/``_Ref…`` bookmarks; Pandoc emits those targets as plain paragraphs (a leading
    ``<span id="_Toc…" …></span>`` + the heading text). Promote each to a level-2 heading
    (stripping inline markup) while **retaining** the bookmark span on the line above, so the
    bookmark identity survives into ``parse_headings``. Runs **only when the body has no markdown
    headings**, so well-structured docs are left untouched. (Level inference from TOC
    depth/numbering is deferred — a flat tree still gives a working TOC + anchors where none
    existed.)"""
    if _HEADING_LINE_RE.search(body):
        return body

    def repl(m: re.Match[str]) -> str:
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


def _is_loose_toc_entry(line: str) -> bool:
    return _LOOSE_TOC_ENTRY_RE.match(line) is not None


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
            drop.add(i)
            j = i + 1
            while j < n and not HEADING_RE.match(lines[j]):
                drop.add(j)
                if _is_loose_toc_entry(lines[j]) and (e := parse_legacy_toc_entry(lines[j])):
                    entries.append(e)
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
                    if (e := parse_legacy_toc_entry(lines[j])) is not None:
                        entries.append(e)
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
    """The TOC depth to actually use for a document (§6.7). A **lone** leading top-level heading is
    the document title, so the navigable structure is the two levels below it (the ``H2–H3``
    default). But when the shallowest level has **several** headings, those are sections, not a
    title — include that level so multi-``H1`` docs (release notes, flat manuals) still get a
    ``## Contents`` instead of an empty one. No headings → the default."""
    levels = sorted({h.level for h in headings})
    if not levels:
        return default
    base = levels[0]
    base_count = sum(1 for h in headings if h.level == base)
    if base_count <= 1 and len(levels) > 1:  # a single title heading above deeper sections
        return (base + 1, base + 2)
    return (base, base + 1)


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
    body = subtract_phrases(strip_artifacts(recover_headings(body)), phrases)
    body = subtract_boilerplate(body, boilerplate)
    # CORRELATE-BEFORE-DROPPING (§6.7 role-1): capture the legacy TOC's original entries (title +
    # page + anchor) *before* it leaves the body, then strip it (ATX-heading + plain-text forms).
    toc_entries = legacy_toc_entries(body, toc_titles)
    body = strip_legacy_toc(body, toc_titles)
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
    slugs = {h.slug for h in headings}

    def _anchor_resolves(anchor: str) -> bool:
        a = anchor.lstrip("#")
        return a in slugs or a in recovered

    toc_unresolved = [
        a
        for a in correlate_legacy_toc([e.anchor for e in toc_entries], headings)
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
