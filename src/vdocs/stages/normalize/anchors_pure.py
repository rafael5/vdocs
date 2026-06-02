"""Pure anchor substrate — the heading-identity layer that ``index``/``relate``/``embed``/
``serve-mcp`` all hang off (§6.7, §5.5).

Conversion emits Word-bookmark anchors (``[Intro](#_Toc1234)`` targeting a hidden ``_Toc1234`` —
v1's measured reality). Those bookmarks don't resolve on GitHub. This module:

  * **captures** the ``_Toc…``/``_Ref…`` bookmark a heading carries (inline on the ``##`` line, or
    on the line immediately above — the recovery-seed shape) instead of dropping it (§6.7);
  * **rewrites** every in-body ``](#_Toc…)`` cross-reference to its GitHub heading slug, recording
    unmapped targets as ``UNRESOLVED`` (a fidelity signal — never a crash);
  * builds the ``(stable_section_id ↔ github_slug ↔ original_bookmark)`` **anchor map** that
    serialises to the ``refs.yaml`` sidecar — the one home for anchors, shared by the TOC,
    cross-refs, the published markdown, and the MCP resource URIs (§5.5);
  * inserts the round-trip **"↑ Back to Contents"** back-links that make navigation bidirectional.

Pure: plain values in, records + rewritten body out; the stage writes the sidecar (mirrors
``revision_pure`` / ``revisions.yaml``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from vdocs.kernel.text import github_slug_base

# Depth (decided, §6.7): template-governed `toc_level` per section is the goal, but
# `registries/templates` isn't built yet — ship the H2–H3 fallback (H1 is the doc title, never a
# TOC entry). TEMPLATE SEAM: when the template F-step lands, resolve depth per (doc_type, era)
# from the template schema and pass it in instead of this constant.
DEFAULT_TOC_DEPTH = (2, 3)

# `#+` (not `#{1,6}`): upstream emits >6 `#` from deep DOCX outline levels; capture them so they
# get slugs/anchors. By the time `parse_headings` runs in `normalize_body`, `infer_heading_levels`
# has already collapsed the tree to ≤6 (see normalize_pure for the rationale).
_HEADING_RE = re.compile(r"^(#+)\s+(.*?)\s*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_TAG_RE = re.compile(r"<[^>]+>")

# A Word bookmark id is `_Toc…`/`_Ref…`. Four shapes we read/match it in:
_BOOKMARK_SPAN_RE = re.compile(r'<span id="(_(?:Toc|Ref)\w+)"[^>]*>\s*</span>')  # inline on heading
_LONE_BOOKMARK_RE = re.compile(r'^\s*<span id="(_(?:Toc|Ref)\w+)"[^>]*>\s*</span>\s*$')  # above it
_LINK_TARGET_RE = re.compile(r"\]\(#(_(?:Toc|Ref)\w+)\)")  # in-body cross-ref `](#_Toc…)`
_ANCHOR_SPAN_RE = re.compile(r'<span id="_(?:Toc|Ref)\w+"[^>]*>\s*</span>')  # redundant post-write

_BACKLINK = "[↑ Back to Contents](#contents)"
_BACKLINK_RE = re.compile(r"^\[↑ Back to Contents\]\(#contents\)\s*$")
_MULTI_BLANK = re.compile(r"\n{3,}")

UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class Heading:
    level: int
    text: str
    slug: str
    bookmark: str | None  # the _Toc…/_Ref… id Pandoc attached to this heading, if any
    stable_id: str  # "<doc_id>/<slug>" — see Decision 1 (build_anchor_map docstring)


@dataclass(frozen=True)
class AnchorRow:
    """One anchor-map row: the identity of a single heading across every downstream consumer."""

    stable_section_id: str
    github_slug: str
    original_bookmark: str | None
    level: int
    title: str
    toc_level: bool  # whether this heading is in-TOC at the chosen depth


@dataclass(frozen=True)
class AnchorMap:
    """The pure record that serialises to ``refs.yaml`` (§6.7)."""

    doc_id: str
    toc_depth: tuple[int, int]
    rows: list[AnchorRow]
    outbound: dict[str, str]  # bookmark → resolved slug, or UNRESOLVED


def github_slug(text: str, seen: dict[str, int]) -> str:
    """A GitHub-compatible heading anchor slug — the shared ``kernel/text.github_slug_base`` rule
    plus GitHub's ``-1``/``-2`` duplicate disambiguation in document order (§6.7)."""
    base = github_slug_base(text)
    n = seen.get(base, 0)
    seen[base] = n + 1
    return base if n == 0 else f"{base}-{n}"


def _stable_id(doc_id: str, slug: str) -> str:
    """Decision 1: ``<doc_id>/<slug>`` — human-readable, the same identity MCP URIs will use.
    Churns on retitle; the future ``index`` stage owns ID *persistence* across runs."""
    return f"{doc_id}/{slug}" if doc_id else slug


def parse_headings(body: str, doc_id: str = "") -> list[Heading]:
    """The ATX heading tree (``#``…``######``), skipping fenced code and our own ``## Contents``.

    Captures the ``_Toc…``/``_Ref…`` bookmark on the heading line (inline span) or on the line
    immediately above it (the recovery-seed shape) — for both late-gen and old-gen docs (§6.7)."""
    headings: list[Heading] = []
    seen: dict[str, int] = {}
    in_fence = False
    prev_bookmark: str | None = None  # a lone bookmark span on the immediately preceding line
    for line in body.splitlines():
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            prev_bookmark = None
            continue
        if in_fence:
            continue
        m = _HEADING_RE.match(line)
        if m is None:
            lone = _LONE_BOOKMARK_RE.match(line)
            prev_bookmark = lone.group(1) if lone else None
            continue
        raw = m.group(2)
        inline = _BOOKMARK_SPAN_RE.search(raw)
        bookmark = inline.group(1) if inline else prev_bookmark
        prev_bookmark = None
        text = _TAG_RE.sub("", raw).strip()
        if not text or text.lower() == "contents":
            continue
        slug = github_slug(text, seen)
        headings.append(Heading(len(m.group(1)), text, slug, bookmark, _stable_id(doc_id, slug)))
    return headings


def rewrite_link_targets(body: str, bookmark_to_slug: dict[str, str]) -> tuple[str, dict[str, str]]:
    """Rewrite every ``](#_Toc…)`` / ``](#_Ref…)`` cross-ref target to its GitHub slug, then drop
    the now-redundant heading-anchor spans (GitHub mints slug anchors from heading text).

    Targets with no mapping are recorded as ``UNRESOLVED`` in the outbound map and left untouched
    in the body (a fidelity signal — never a crash, §6.7)."""
    outbound: dict[str, str] = {}

    def repl(m: re.Match[str]) -> str:
        bm = m.group(1)
        slug = bookmark_to_slug.get(bm)
        if slug is None:
            outbound[bm] = UNRESOLVED
            return m.group(0)
        outbound[bm] = slug
        return f"](#{slug})"

    body = _LINK_TARGET_RE.sub(repl, body)
    body = _ANCHOR_SPAN_RE.sub("", body)
    return body, outbound


def build_anchor_map(
    headings: list[Heading],
    doc_id: str,
    toc_depth: tuple[int, int] = DEFAULT_TOC_DEPTH,
    outbound: dict[str, str] | None = None,
) -> AnchorMap:
    """The pure ``refs.yaml`` record: one row per heading carrying
    ``(stable_section_id, github_slug, original_bookmark, level, title, toc_level)`` plus the
    doc's chosen ``toc_depth`` and the outbound cross-ref map.

    Decision 1: ``stable_section_id = "<doc_id>/<slug>"`` — human-readable, stable while the
    heading text is stable, the same identity MCP URIs will use (§5.5)."""
    lo, hi = min(toc_depth), max(toc_depth)
    rows = [
        AnchorRow(
            stable_section_id=_stable_id(doc_id, h.slug),
            github_slug=h.slug,
            original_bookmark=h.bookmark,
            level=h.level,
            title=h.text,
            toc_level=lo <= h.level <= hi,
        )
        for h in headings
    ]
    return AnchorMap(doc_id, (lo, hi), rows, dict(outbound or {}))


def strip_back_links(body: str) -> str:
    """Remove any previously-inserted back-links (for idempotency, like ``strip_existing_toc``)."""
    return "\n".join(ln for ln in body.split("\n") if not _BACKLINK_RE.match(ln))


def insert_back_links(
    body: str, headings: list[Heading], toc_depth: tuple[int, int] = DEFAULT_TOC_DEPTH
) -> str:
    """Insert a ``[↑ Back to Contents](#contents)`` link under each TOC-targeted heading (§6.7).

    Idempotent: strips any existing back-link first. Out-of-depth headings (e.g. H4+ under the
    default) get no back-link; the ``## Contents`` heading itself is never targeted."""
    body = strip_back_links(body)
    lo, hi = min(toc_depth), max(toc_depth)
    targeted = {h.slug for h in headings if lo <= h.level <= hi}
    out: list[str] = []
    seen: dict[str, int] = {}
    in_fence = False
    for line in body.split("\n"):
        out.append(line)
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _HEADING_RE.match(line)
        if m is None:
            continue
        text = _TAG_RE.sub("", m.group(2)).strip()
        if not text or text.lower() == "contents":
            continue
        if github_slug(text, seen) in targeted:
            out += ["", _BACKLINK]
    return _MULTI_BLANK.sub("\n\n", "\n".join(out)).strip("\n") + "\n"


def anchor_sidecar(amap: AnchorMap) -> dict:
    """The ``refs.yaml`` mapping: doc id + chosen depth + the per-heading anchor rows + the
    outbound cross-ref map (§6.7). Mirrors ``revision_pure.revision_sidecar``."""
    return {
        "doc_id": amap.doc_id,
        "toc_depth": list(amap.toc_depth),
        "anchors": [
            {
                "stable_id": r.stable_section_id,
                "slug": r.github_slug,
                "bookmark": r.original_bookmark,
                "level": r.level,
                "title": r.title,
                "toc_level": r.toc_level,
            }
            for r in amap.rows
        ],
        "outbound": dict(amap.outbound),
    }
