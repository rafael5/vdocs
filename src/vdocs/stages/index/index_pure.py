"""Pure shredding for `index` — the normalized body → structure-aligned sections (§14.6, §5.5).

Chunks align to **meaningful units** (a whole section), not byte windows: each ATX heading starts a
section that runs to the next heading. Section stable ids are `<doc_key>/<slug>` — the *same*
identity `normalize`'s `refs.yaml` emits (`anchors_pure._stable_id`), built with the shared
fence-aware heading scan + GitHub-slug dedup (`kernel.markdown` / `kernel.text`, §9.2), so the FTS
rows, graph nodes, published anchors, and (later) vector keys all reference one id.
"""

from __future__ import annotations

from dataclasses import dataclass

from vdocs.kernel.markdown import (
    FENCE_RE,
    classify_section,
    iter_headings,
    strip_tags,
    substantive_tokens,
)
from vdocs.stages.normalize.anchors_pure import github_slug

DEFAULT_TOC_DEPTH = (2, 3)

# Oversized-leaf splitting (§14.6). Calibration targets (tune against the B3 golden set), not magic
# constants: only a leaf body larger than OVERSIZED_CHUNK_CHARS is split; each window aims for
# ~CHUNK_TARGET_CHARS, with a one-block overlap so a cross-boundary passage holds.
#
# A1 (§9a) aligned these to the chosen embedder, **bge-m3 (8192-token context)**: the worst case a
# leaf can reach is a single unsplittable block (a wide table/fence forms its own over-target
# window), and the largest such chunk on the golden set is ~14.3k chars ≈ 5.7k tokens — comfortably
# inside 8192. So no chunk is truncated at embed time; `embed` asserts this per-chunk
# (`embed_pure.assert_within_budget`) as a hard gate. (The originally-planned bge-small had a
# 512-token cap that these sizes would have blown — that mismatch is what A1 resolved.)
OVERSIZED_CHUNK_CHARS = 8000
CHUNK_TARGET_CHARS = 4000


@dataclass(frozen=True)
class Section:
    """One structure-aligned chunk: a heading and its body up to the next heading."""

    section_id: str  # "<doc_key>/<slug>" — matches refs.yaml's stable_id
    slug: str
    title: str
    level: int
    text: str  # the heading line through the line before the next heading
    toc_level: bool  # whether the heading is in-TOC at the chosen depth
    kind: str  # "container" | "ok" | "stub" | "hollow" (kernel.markdown.classify_section, §14.6)
    searchable: bool  # belongs on the search surface (FTS/embed) — containers + hollow chunks don't
    section_path: str  # " > "-joined ancestor heading titles — context as metadata (§14.6)


def _unique(slug: str, used: set[str]) -> str:
    """Keep section slugs unique within a doc so `section_id` is a usable PRIMARY KEY.

    GitHub's per-base ``-N`` rule can collide a repeated heading's suffixed slug with a literal
    heading of that name (``Example`` ×2 → ``example``/``example-1`` vs a ``Example 1`` heading →
    ``example-1``) — 3 docs in the real corpus. On a true collision we append a distinctive
    ``-dup-N`` (deterministic, won't re-collide with ordinary ``-N`` slugs). The GitHub anchor for
    those rare headings is itself ambiguous, so `refs.yaml` can't disambiguate either — aligning
    `normalize`'s `github_slug` to a globally-unique rule is a tracked follow-up."""
    if slug not in used:
        used.add(slug)
        return slug
    n = 1
    while f"{slug}-dup-{n}" in used:
        n += 1
    unique = f"{slug}-dup-{n}"
    used.add(unique)
    return unique


@dataclass(frozen=True)
class Chunk:
    """One retrieval unit (the search/embed surface, §5.5): a searchable section's body, split if
    oversized. ``part`` 0 keeps the bare ``section_id``; later parts get a ``#pN`` suffix. Every
    part cites the same ``section_id`` — the anchor a hit resolves to."""

    chunk_id: str
    section_id: str
    part: int
    text: str


def search_chunks(section: Section) -> list[Chunk]:
    """Expand a section into retrieval chunks (§5.5/§14.6). A non-searchable section (container or
    hollow) yields **none** — it is kept off the search surface. A searchable leaf yields one chunk
    (``chunk_id == section_id``), or several windowed parts if oversized: part 0 keeps the bare
    ``section_id`` (id stability), parts ≥1 get a ``#p{n+1}`` suffix, all citing the same anchor."""
    if not section.searchable:
        return []
    windows = split_oversized(section.text)
    if len(windows) == 1:
        return [Chunk(section.section_id, section.section_id, 0, windows[0])]
    return [
        Chunk(
            section.section_id if i == 0 else f"{section.section_id}#p{i + 1}",
            section.section_id,
            i,
            w,
        )
        for i, w in enumerate(windows)
    ]


def _blocks(text: str) -> list[str]:
    """Split ``text`` into paragraph blocks separated by blank lines, keeping a fenced code block
    (``` / ~~~) atomic — its inner blank lines never break it (so a split never lands mid-fence)."""
    blocks: list[str] = []
    cur: list[str] = []
    in_fence = False
    for line in text.split("\n"):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            cur.append(line)
            continue
        if not in_fence and line.strip() == "":
            if cur:
                blocks.append("\n".join(cur))
                cur = []
            continue
        cur.append(line)
    if cur:
        blocks.append("\n".join(cur))
    return blocks


def split_oversized(
    text: str, *, target: int = CHUNK_TARGET_CHARS, hard: int = OVERSIZED_CHUNK_CHARS
) -> list[str]:
    """Split an oversized leaf body into structure-aligned windows (§14.6, A1).

    Bodies ``<= hard`` are returned unchanged (``[text]``). Larger bodies are windowed on paragraph
    boundaries — never inside a fenced code block (``_blocks`` keeps fences atomic) — each window
    aiming for ~``target`` chars, with a **one-block overlap**: the last block of each window is
    repeated at the start of the next so a passage spanning the boundary is not lost. No content is
    dropped (every source block appears in some window). A single block larger than ``target`` (e.g.
    a big table or fence) can't be split structurally, so it forms its own (over-target) window."""
    if len(text) <= hard:
        return [text]
    windows: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for b in _blocks(text):
        if cur and cur_len + len(b) > target:
            windows.append("\n\n".join(cur))
            cur = [cur[-1]]  # overlap: carry the last block into the next window
            cur_len = len(cur[0])
        cur.append(b)
        cur_len += len(b)
    if cur:
        windows.append("\n\n".join(cur))
    return windows


def shred_sections(
    body: str, doc_key: str, toc_depth: tuple[int, int] = DEFAULT_TOC_DEPTH
) -> list[Section]:
    """Split `body` into heading-delimited sections (fence-aware; the generated ``## Contents`` and
    bookmark-only headings are skipped, matching `anchors_pure.parse_headings` so slugs align)."""
    lo, hi = min(toc_depth), max(toc_depth)
    lines = body.split("\n")
    heads = [(idx, level, strip_tags(raw).strip()) for idx, level, raw in iter_headings(body)]
    heads = [(idx, level, title) for idx, level, title in heads if title]
    seen: dict[str, int] = {}
    used: set[str] = set()
    sections: list[Section] = []
    path_stack: list[tuple[int, str]] = []  # (level, title) of the current heading's open ancestors
    for i, (idx, level, title) in enumerate(heads):
        slug = _unique(github_slug(title, seen), used)
        end = heads[i + 1][0] if i + 1 < len(heads) else len(lines)
        text = "\n".join(lines[idx:end]).strip()
        # Ancestor-title path (same stack discipline as normalize_pure.infer_heading_levels, so the
        # two stages agree on the tree): pop ancestors at this level or deeper, join what remains.
        while path_stack and path_stack[-1][0] >= level:
            path_stack.pop()
        section_path = " > ".join(t for _, t in path_stack)
        path_stack.append((level, title))
        # Structure-aware classification (§14.6, A1): a heading whose next heading is strictly
        # deeper is a *container* (substance lives in subsections); otherwise judge its own body
        # (the lines after the heading) by the shared substantive-token floor. Containers + hollow
        # chunks stay as rows (the anchor/nav map is complete) but are kept off the search surface.
        is_container = i + 1 < len(heads) and heads[i + 1][1] > level
        has_referent, tokens = substantive_tokens(lines[idx + 1 : end])
        kind = classify_section(is_container=is_container, has_referent=has_referent, tokens=tokens)
        sections.append(
            Section(
                section_id=f"{doc_key}/{slug}",
                slug=slug,
                title=title,
                level=level,
                text=text,
                toc_level=lo <= level <= hi,
                kind=kind,
                searchable=kind in ("ok", "stub"),
                section_path=section_path,
            )
        )
    return sections
