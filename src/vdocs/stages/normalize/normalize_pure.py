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

from vdocs.kernel.text import block_key
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
    "strip_existing_toc",
    "build_toc",
    "regenerate_toc",
    "normalize_body",
]

# `#+` (not `#{1,6}`) on purpose: upstream (Pandoc/convert) emits >6 `#` from deep DOCX outline
# levels (e.g. `########### Table of Contents`). Recognizing them lets `strip_legacy_toc` catch an
# oversized legacy-TOC heading and `infer_heading_levels` collapse the rest into a gap-free ≤6 tree
# — leaving an invalid >6 ATX heading (GitHub renders it as literal text) would be the bug.
_HEADING_RE = re.compile(r"^(#+)\s+(.*?)\s*$")
_HEADING_LINE_RE = re.compile(r"^#+ ", re.MULTILINE)
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_HTML_COMMENT_RE = re.compile(r"^<!--.*-->$")
_MULTI_BLANK = re.compile(r"\n{3,}")
_TOC_ENTRY_RE = re.compile(r"^\s*- \[.*\]\(#.*\)\s*$")
_TAG_RE = re.compile(r"<[^>]+>")
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
        text = _TAG_RE.sub("", m.group(2)).strip().strip("*_ ").strip()
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
    in_fence = False
    found: list[tuple[int, int]] = []  # (line index, original level)
    for i, line in enumerate(lines):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if (m := _HEADING_RE.match(line)) is not None and m.group(2).strip().lower() != "contents":
            found.append((i, len(m.group(1))))
    if not found:
        return body
    base = min(level for _, level in found)
    stack: list[int] = []  # original levels of the current heading's strict ancestors
    for i, level in found:
        while stack and stack[-1] >= level:
            stack.pop()
        new_level = base + len(stack)
        stack.append(level)
        text = _HEADING_RE.match(lines[i]).group(2)  # type: ignore[union-attr]
        lines[i] = "#" * new_level + " " + text
    return "\n".join(lines)


def strip_artifacts(body: str) -> str:
    """F-strip: drop standalone empty HTML comments (Pandoc emits many) + collapse blank runs."""
    kept = [ln for ln in body.split("\n") if not _HTML_COMMENT_RE.match(ln.strip())]
    return _MULTI_BLANK.sub("\n\n", "\n".join(kept)).strip("\n") + "\n"


def subtract_phrases(body: str, phrases: frozenset[str]) -> str:
    """F-phrases: delete whole blocks matching a curated dead phrase (case-insensitive)."""
    if not phrases:
        return body
    lowered = {p.strip().lower() for p in phrases}
    blocks = re.split(r"\n\s*\n", body)
    kept = [b for b in blocks if b.strip().lower() not in lowered]
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


def strip_legacy_toc(body: str, titles: frozenset[str], max_level: int = 3) -> str:
    """F-toc-dedup (§6.7; ``registries/structures`` CANONICALIZE ``toc``, §9.6): remove the source's
    legacy in-body table of contents so the derived ``## Contents`` (F-toc) never duplicates it.

    A legacy contents section is a heading whose text matches one of the curated ``titles``
    (case-insensitive — e.g. ``Table of Contents`` / ``Contents``) and whose level is either
    ≤ ``max_level`` (a normal H1–H3 TOC heading) **or** > 6 (an invalid-GFM oversized heading the
    upstream mangled — its hash count is an artifact, so the text match is trusted; the real corpus
    emits ``########### Table of Contents``). The heading and every following line up to the next
    markdown heading (its page-numbered entries) are dropped. Registry-driven (``titles`` come from
    ``registries/structures``); empty ``titles`` → no-op. Idempotent: a prior run's generated
    ``## Contents`` matches too, so it is rebuilt."""
    if not titles:
        return body
    wanted = {t.strip().lower() for t in titles}
    lines = body.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        m = _HEADING_RE.match(lines[i])
        level = len(m.group(1)) if m else 0
        if m and (level <= max_level or level > 6) and m.group(2).strip().lower() in wanted:
            i += 1
            while i < len(lines) and not _HEADING_RE.match(lines[i]):
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


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


def regenerate_toc(body: str, toc_depth: tuple[int, int] = DEFAULT_TOC_DEPTH) -> str:
    """F-toc: replace any stale ``## Contents`` with a fresh TOC derived from the heading tree.

    Inserted after a leading top-level title heading if present, else at the top of the body."""
    body = strip_existing_toc(body)
    toc = build_toc(parse_headings(body), toc_depth)
    if not toc:
        return body
    lines = body.split("\n")
    # find a leading H1 (skipping blanks) → place Contents just after it; else prepend
    insert_at = 0
    for idx, ln in enumerate(lines):
        if not ln.strip():
            continue
        if _HEADING_RE.match(ln) and ln.startswith("# "):
            insert_at = idx + 1
        break
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
    body = strip_legacy_toc(body, toc_titles)
    body = infer_heading_levels(body)
    headings = parse_headings(body, doc_id)
    bookmark_to_slug = {h.bookmark: h.slug for h in headings if h.bookmark}
    body, outbound = rewrite_link_targets(body, bookmark_to_slug)
    body = regenerate_toc(body, toc_depth)
    body = insert_back_links(body, headings, toc_depth)
    return body, build_anchor_map(headings, doc_id, toc_depth, outbound)
