"""Pure cores of the `merge` stage — SKL (`knowledge.db`) → entity-keyed `index.db` (SKL S3.3).

`merge` is the post-`resolve` join (D-S3.3a): it augments `index.db` from the SKL **additively**
(D-S3.3b), reconciling the two id schemes and projecting the SKL surfaces into `index.db` so the
shipped one file carries entity identity. Like `relate`, it adds only *derived* tables — no new
extraction. Every function here is pure: SKL nodes + index rows in, sorted unique tuples out; the
thin `stage.py` driver does the I/O.

* **reconcile** — `index` keys an entity `fileman_file:200` (colon, its own recognition pass); the
  SKL keys it `fileman_file/200` (slash). The two reconcile on `(type, canonical)`: the index id is
  `f"{type}:{canonical}"`, so an SKL entity maps to the index row of the same `(type, canonical)`
  when that row exists. Carries the SKL id + identity onto the index side.
* **synonym_rows** — every surface (canonical name + synonyms) per SKL entity — the synonym catalog
  the shipped index carries (and the seed the S3.4 search expansion derives from).
* **tag_chunks** — chunk → entity tags: a chunk is *about* an entity when one of its
  **distinctive** surfaces occurs in the chunk text. Distinctive-only is the load-bearing safety
  rule — the real SKL has common-word names (`fileman_file/1` = "FILE", `/19` = "OPTION") that would
  tag the whole corpus if matched bare.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# (entity_id, node_id, type, canonical, canonical_name) — the colon↔slash reconciliation row.
EntitySklRow = tuple[str, str, str, str, str]
# (node_id, surface, kind) — kind ∈ {canonical_name, synonym}.
SynonymRow = tuple[str, str, str]
# (chunk_id, node_id) — a chunk-level entity tag.
ChunkTag = tuple[str, str]


@dataclass(frozen=True)
class SklEntity:
    """One SKL entity, as `merge` consumes it (a thin read of `knowledge.db:entities`)."""

    node_id: str
    type: str
    canonical: str
    canonical_name: str
    synonyms: tuple[str, ...]


def index_entity_id(etype: str, canonical: str) -> str:
    """The colon-style id `index` keys entities by — MUST mirror `stages/index/stage.py`
    (`eid = f"{etype}:{canon}"`). The single point the two schemes are reconciled."""
    return f"{etype}:{canonical}"


def reconcile(entities: list[SklEntity], index_entity_ids: set[str]) -> list[EntitySklRow]:
    """The colon↔slash join map: one row per SKL entity whose `(type, canonical)` is also an `index`
    entity (so the SKL id attaches to a real index row). SKL entities absent from `index` are
    dropped — `merge` augments where both DBs agree, never inventing index rows (friction #3)."""
    rows = [
        (index_entity_id(e.type, e.canonical), e.node_id, e.type, e.canonical, e.canonical_name)
        for e in entities
        if index_entity_id(e.type, e.canonical) in index_entity_ids
    ]
    return sorted(rows)


def synonym_rows(entities: list[SklEntity]) -> list[SynonymRow]:
    """Every surface of every SKL entity: the canonical name (kind `canonical_name`) then each
    distinct synonym (kind `synonym`). De-duplicated per entity (the SKL `synonyms` list usually
    repeats the canonical name); sorted, stable."""
    rows: list[SynonymRow] = []
    for e in entities:
        seen: set[str] = set()
        if e.canonical_name:
            rows.append((e.node_id, e.canonical_name, "canonical_name"))
            seen.add(e.canonical_name)
        for s in e.synonyms:
            if s and s not in seen:
                rows.append((e.node_id, s, "synonym"))
                seen.add(s)
    return sorted(rows)


def is_distinctive(surface: str) -> bool:
    """True when a surface is specific enough to tag/expand on — never a bare common word. A surface
    is distinctive iff it carries a digit (a file number / numbered global), is a global (`^…`), or
    is multi-word. So "200"/"^VA(200,"/"NEW PERSON" qualify; "FILE"/"OPTION" do not."""
    s = surface.strip()
    if not s:
        return False
    if any(ch.isdigit() for ch in s) or s.startswith("^"):
        return True
    return len(s.split()) >= 2


def distinctive_surfaces(entity: SklEntity) -> list[str]:
    """The entity's tag-worthy surfaces (canonical name + synonyms, distinctive only), de-duped in
    first-seen order. Empty when the entity has only bare common-word surfaces."""
    out: list[str] = []
    seen: set[str] = set()
    for s in (entity.canonical_name, *entity.synonyms):
        if s and s not in seen and is_distinctive(s):
            out.append(s)
            seen.add(s)
    return out


def _norm(surface: str) -> str:
    """Match key: upper-cased, internal whitespace collapsed (globals keep their punctuation)."""
    return re.sub(r"\s+", " ", surface.strip()).upper()


def _bounded(surface: str) -> str:
    """One alternation branch with a non-alphanumeric boundary guard added **only** at an
    alphanumeric edge — so a name like "NEW PERSON" can't match inside a longer word, but a global
    ending in `,`/`(` (e.g. `^VA(200,`) stays matchable mid-token (followed by subscripts). Mirrors
    `resolve_pure._bounded`."""
    left = r"(?<![A-Za-z0-9])" if surface[:1].isalnum() else ""
    right = r"(?![A-Za-z0-9])" if surface[-1:].isalnum() else ""
    return f"{left}{re.escape(surface)}{right}"


def tag_chunks(chunks: list[tuple[str, str]], entities: list[SklEntity]) -> list[ChunkTag]:
    """`(chunk_id, node_id)` tags: a chunk is tagged with an entity when any of that entity's
    *distinctive* surfaces occurs in the chunk text (case-insensitive, alnum-boundary-guarded).
    `chunks` is `(chunk_id, text)`. Sorted, de-duplicated (one tag per chunk/entity however many
    surface hits). Non-matching chunks (incl. non-DI chunks) simply get no tags (friction #3)."""
    surf_to_nodes: dict[str, set[str]] = {}
    for e in entities:
        for s in distinctive_surfaces(e):
            surf_to_nodes.setdefault(_norm(s), set()).add(e.node_id)
    if not surf_to_nodes:
        return []
    # longest-first so the most specific surface anchors the alternation (compile once).
    branches = [_bounded(s) for s in sorted(surf_to_nodes, key=len, reverse=True)]
    rx = re.compile("|".join(branches), re.IGNORECASE)

    out: set[ChunkTag] = set()
    for chunk_id, text in chunks:
        for m in rx.finditer(text):
            for node_id in surf_to_nodes[_norm(m.group(0))]:
                out.add((chunk_id, node_id))
    return sorted(out)
