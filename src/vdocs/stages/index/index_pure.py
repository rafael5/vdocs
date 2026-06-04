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
    classify_section,
    iter_headings,
    strip_tags,
    substantive_tokens,
)
from vdocs.stages.normalize.anchors_pure import github_slug

DEFAULT_TOC_DEPTH = (2, 3)


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
    for i, (idx, level, title) in enumerate(heads):
        slug = _unique(github_slug(title, seen), used)
        end = heads[i + 1][0] if i + 1 < len(heads) else len(lines)
        text = "\n".join(lines[idx:end]).strip()
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
            )
        )
    return sections
