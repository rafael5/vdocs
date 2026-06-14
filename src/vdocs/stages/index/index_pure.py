"""Pure shredding for `index` — the normalized body → structure-aligned sections (§14.6, §5.5).

Chunks align to **meaningful units** (a whole section), not byte windows: each ATX heading starts a
section that runs to the next heading. Section stable ids are `<doc_key>/<slug>` — the *same*
identity `normalize`'s `refs.yaml` emits (`anchors_pure._stable_id`), built with the shared
fence-aware heading scan + GitHub-slug dedup (`kernel.markdown` / `kernel.text`, §9.2), so the FTS
rows, graph nodes, published anchors, and (later) vector keys all reference one id.
"""

from __future__ import annotations

import hashlib
import re
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

# --- read-contract meta (ADR-0001, P0) ----------------------------------------------------------
# index.db carries a `meta(key, value)` table with two independent version axes consumers check:
#   • read_schema_version — the *structural* contract (semver; bumped when views/columns change).
#   • corpus_content_hash — the *data* fingerprint; changes iff the document set/its fields change.
# The hash is deterministic and order-independent (no build timestamps) so an identical corpus
# rebuilds to the same fingerprint — consumers/caches can tell "the corpus changed" from "same
# corpus, rebuilt". The wall-clock build time is deliberately NOT hashed (and lives in the publish
# manifest, not here) so index.db stays reproducible.
READ_SCHEMA_VERSION = "1.0"


def corpus_content_hash(documents: list[tuple]) -> str:
    """A deterministic sha256 fingerprint over the (order-independent) document rows."""
    h = hashlib.sha256()
    for row in sorted(documents):
        h.update(repr(row).encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def meta_rows(
    documents: list[tuple], schema_version: str = READ_SCHEMA_VERSION
) -> list[tuple[str, str]]:
    """The `meta` rows written into index.db: the schema-version axis + the corpus fingerprint."""
    return [
        ("read_schema_version", schema_version),
        ("corpus_content_hash", corpus_content_hash(documents)),
        ("corpus_doc_count", str(len(documents))),
    ]


# Oversized-leaf splitting (§14.6). Calibration targets (tune against the B3 golden set), not magic
# constants: only a leaf body larger than OVERSIZED_CHUNK_CHARS is split; each window aims for
# ~CHUNK_TARGET_CHARS, with a one-block overlap so a cross-boundary passage holds.
#
# These bound the lexical FTS5 chunk: the worst case a leaf can reach is a single unsplittable
# block (a wide table/fence forms its own over-target window), and the largest such chunk on the
# golden set is ~14.3k chars — well-formed, self-contained retrieval units for snippet context.
# (The semantic/vector path that originally drove the exact token sizing was descoped; the corpus
# is lexical-first and offline, so these are tuned for FTS chunking, not an embedder budget.)
OVERSIZED_CHUNK_CHARS = 8000
CHUNK_TARGET_CHARS = 4000

# A2b small-leaf merge — built and tested, but **kept off**. Merging adjacent small leaves raises
# mean chunk substance (+53% on the golden set) and drives redundancy→0, but it costs *lexical*
# citation precision: merged content is cited under the first leaf's anchor, so a fine-grained
# section query resolves to the merge-anchor sibling (golden nDCG@10 0.395→0.223). For the
# lexical-first corpus that precision loss isn't worth it, so merging stays off.
MERGE_SMALL_LEAVES = False


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


def _windows_to_chunks(section_id: str, text: str) -> list[Chunk]:
    """Window ``text`` (split if oversized) into chunks all citing ``section_id``: part 0 keeps the
    bare id (id stability), parts ≥1 get a ``#p{n+1}`` suffix."""
    windows = split_oversized(text)
    if len(windows) == 1:
        return [Chunk(section_id, section_id, 0, windows[0])]
    return [
        Chunk(section_id if i == 0 else f"{section_id}#p{i + 1}", section_id, i, w)
        for i, w in enumerate(windows)
    ]


def search_chunks(section: Section) -> list[Chunk]:
    """Expand a single section into retrieval chunks (§5.5/§14.6). A non-searchable section
    (container or hollow) yields **none** — it is kept off the search surface. A searchable leaf
    yields one chunk (``chunk_id == section_id``), or several windowed parts if oversized."""
    if not section.searchable:
        return []
    return _windows_to_chunks(section.section_id, section.text)


@dataclass(frozen=True)
class ChunkUnit:
    """A2b coherent chunking unit (§9c): one or more small adjacent leaf sections merged into a
    single retrieval unit. ``section_id``/``title``/``section_path`` are the **first**
    (representative) leaf's — the anchor a hit cites; ``member_ids`` lists every folded-in leaf for
    traceability; ``text`` is the concatenated bodies. A unit of one is just a single searchable
    leaf."""

    section_id: str
    title: str
    section_path: str
    text: str
    member_ids: tuple[str, ...]


def chunk_units(
    sections: list[Section],
    *,
    target: int = CHUNK_TARGET_CHARS,
    merge: bool = MERGE_SMALL_LEAVES,
) -> list[ChunkUnit]:
    """Group a document's sections into chunk units. With ``merge=False`` (the current default —
    `MERGE_SMALL_LEAVES`) every searchable leaf is its own unit (one chunk per leaf, oversized
    split), identical to the pre-A2b behavior. With ``merge=True`` it merges **consecutive small
    leaf sections under the same parent heading** (§9c) so a chunk is a coherent unit of knowledge
    rather than a one-line fragment. Merge rules — a leaf joins the current run iff it is
    searchable, has the **same non-empty** ``section_path`` (provably the same parent heading —
    never across an H2 boundary or a top-level/empty path), is itself smaller than ``target``, and
    keeps the run within ``target``.
    Anything else (a non-searchable section, a path change, a leaf ≥ target, an over-budget run)
    flushes the current run; a non-mergeable searchable leaf stands as its own unit (and is split
    later if oversized). The merged chunk cites the first leaf — adjacent siblings resolve to the
    same anchor, which is right beside them under the shared parent."""
    units: list[ChunkUnit] = []
    run: list[Section] = []

    def flush() -> None:
        if run:
            first = run[0]
            text = "\n\n".join(s.text for s in run)
            units.append(
                ChunkUnit(
                    first.section_id,
                    first.title,
                    first.section_path,
                    text,
                    tuple(s.section_id for s in run),
                )
            )
            run.clear()

    for s in sections:
        if not s.searchable:
            flush()
            continue
        mergeable = merge and bool(s.section_path) and len(s.text) < target
        if not mergeable:
            flush()
            units.append(ChunkUnit(s.section_id, s.title, s.section_path, s.text, (s.section_id,)))
            continue
        run_len = sum(len(r.text) for r in run)
        if run and (run[0].section_path != s.section_path or run_len + len(s.text) > target):
            flush()
        run.append(s)
    flush()
    return units


def chunks_for_unit(unit: ChunkUnit) -> list[Chunk]:
    """Window a chunk unit's merged text into retrieval chunks (oversized → ``#pN``), all citing the
    unit's representative ``section_id``."""
    return _windows_to_chunks(unit.section_id, unit.text)


# B3b (§8.4): `normalize` lifts a complex table out of prose into a `tables/*.csv` sidecar, leaving
# an in-body reference `_[<caption> (extracted to CSV)](tables/<name>.csv)_`. That makes the table
# invisible to search. `index` re-introduces each table as a distinct **searchable** chunk (caption
# + flattened rows) citing the section it came from, so data-dictionary lookups work again.
TABLE_REF_RE = re.compile(
    r"_\[(?P<caption>.+?) \(extracted to CSV\)\]\(tables/(?P<name>table-\d+\.csv)\)_"
)


def find_table_refs(text: str) -> list[tuple[str, str]]:
    """The extracted-table references in a section body: ``[(csv_name, caption), …]`` (§8.4)."""
    return [(m.group("name"), m.group("caption")) for m in TABLE_REF_RE.finditer(text)]


def table_chunk_text(caption: str, rows: list[list[str]]) -> str:
    """A flat, searchable text rendering of an extracted table: the caption then one line per row
    (cells `` | ``-joined). Empty caption/rows are dropped — an empty table yields ``""``."""
    lines = [caption.strip()] if caption.strip() else []
    lines.extend(" | ".join(c.strip() for c in row) for row in rows if any(c.strip() for c in row))
    return "\n".join(lines)


def table_chunk_texts(
    caption: str,
    rows: list[list[str]],
    *,
    target: int = CHUNK_TARGET_CHARS,
    hard: int = OVERSIZED_CHUNK_CHARS,
) -> list[str]:
    """Render an extracted table into one or more searchable chunk texts (B3b). A table within
    ``hard`` chars is a single chunk; a larger one is **windowed by rows** (each ≤ ~``target``,
    never exceeding the embedder budget that `embed` asserts) with the **caption repeated** in every
    window so each part is self-describing and no row is lost. Empty → ``[]``."""
    full = table_chunk_text(caption, rows)
    if not full.strip():
        return []
    if len(full) <= hard:
        return [full]
    cap = caption.strip()
    base = len(cap) + 1 if cap else 0
    windows: list[str] = []
    cur: list[list[str]] = []
    cur_len = base
    for row in rows:
        line = " | ".join(c.strip() for c in row)
        if not line.strip():
            continue
        if cur and cur_len + len(line) + 1 > target:
            windows.append(table_chunk_text(caption, cur))
            cur, cur_len = [], base
        cur.append(row)
        cur_len += len(line) + 1
    if cur:
        windows.append(table_chunk_text(caption, cur))
    return [w for w in windows if w.strip()]


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
    dropped (every source block appears in some window). A single block larger than ``target``
    (e.g. a big table or fence) can't be split structurally, so a final guarantee pass
    line/char-splits any window still over ``hard`` — so **no window exceeds ``hard``** (the chunk
    size bound holds even for an unextracted inline-HTML table with no blank-line boundaries)."""
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
    # guarantee ≤ hard: a blank-line-less block (inline HTML table) can otherwise form one over-hard
    # window that would blow the embedder budget — hard-split such windows by lines, then chars.
    bounded: list[str] = []
    for w in windows:
        bounded.extend([w] if len(w) <= hard else _split_long(w, hard))
    return bounded


def _split_long(block: str, limit: int) -> list[str]:
    """Split a single over-``limit`` block (no blank lines to break on) into ``<= limit`` pieces —
    by lines, and a single over-limit line by character windows. Every piece is ``<= limit``."""
    pieces: list[str] = []
    cur: list[str] = []
    cur_len = 0

    def flush() -> None:
        nonlocal cur, cur_len
        if cur:
            pieces.append("\n".join(cur))
            cur, cur_len = [], 0

    for raw in block.split("\n"):
        line = raw
        while len(line) > limit:  # a single enormous line → hard character windows
            flush()
            pieces.append(line[:limit])
            line = line[limit:]
        if cur and cur_len + len(line) + 1 > limit:
            flush()
        cur.append(line)
        cur_len += len(line) + 1
    flush()
    return pieces


def fts_doc_title(app_name: str, title: str) -> str:
    """The name tokens for the FTS ``doc_title`` column: the display title with the package's
    application name folded in (e.g. ``"FileMan"``). Titles are frequently namespace-prefixed
    (``"DI — Technical Manual"``), so without this a name search by the well-known package name
    misses every doc but the rare one carrying it in the title. Skipped when the app name is empty
    or already present in the title (no doubling)."""
    app = app_name.strip()
    if not app or app.lower() in title.lower():
        return title
    return f"{app} {title}"


def shred_sections(
    body: str,
    doc_key: str,
    toc_depth: tuple[int, int] = DEFAULT_TOC_DEPTH,
    doc_title: str = "",
) -> list[Section]:
    """Split `body` into heading-delimited sections (fence-aware; the generated ``## Contents`` and
    bookmark-only headings are skipped, matching `anchors_pure.parse_headings` so slugs align).

    A heading-less body (menu listings, quick-reference cards, change-pages — real text with no
    ATX headings) would otherwise yield zero sections, so the document gets no chunks and is
    invisible to preview/search. When no heading-derived section survives, fall back to a single
    whole-body section (slug ``body``, titled from ``doc_title``) so the text is still indexed."""
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
    if not sections and body.strip():
        # No heading produced a section — emit the whole body as one leaf so its text still reaches
        # the chunk/FTS surface (classified by the shared substantive-token floor, like any leaf).
        has_referent, tokens = substantive_tokens(lines)
        kind = classify_section(is_container=False, has_referent=has_referent, tokens=tokens)
        sections.append(
            Section(
                section_id=f"{doc_key}/body",
                slug="body",
                title=doc_title or "Document",
                level=1,
                text=body.strip(),
                toc_level=True,
                kind=kind,
                searchable=kind in ("ok", "stub"),
                section_path="",
            )
        )
    return sections
