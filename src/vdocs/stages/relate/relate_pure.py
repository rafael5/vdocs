"""Pure edge derivation for `relate` — the knowledge graph over already-extracted entities (§8).

`relate` adds **no new extraction** (that is `index`'s job, §8 note); it only materializes edges
from `index.db`'s entity mentions. Three edge families, all derived from the same mention rows:

- **`mentions`** (doc → entity): each document and the entities it mentions, weight = mention count.
- **`cooccurs`** (entity ↔ entity): entities sharing a *section* — the tight, meaningful scope (not
  whole-document, which would explode); undirected, stored once with `src_id < dst_id`.
- **`xref`** (doc ↔ doc): documents that share a *significant* entity (a caller-chosen set of
  types — e.g. build/file/namespace, excluding ubiquitous ones); undirected; weight = number shared.

Pure: mention rows in, a sorted, de-duplicated list of edge tuples out. Edge =
`(src_type, src_id, rel, dst_type, dst_id, weight)`.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

Edge = tuple[str, str, str, str, str, int]


@dataclass(frozen=True)
class Mention:
    """One row of `index.db:entity_mentions` joined to its entity's type."""

    doc_key: str
    section_id: str
    entity_id: str
    entity_type: str


def derive_edges(mentions: list[Mention], *, xref_types: frozenset[str]) -> list[Edge]:
    """All knowledge-graph edges from the mention rows (sorted, unique). ``xref_types`` selects
    which entity types are "significant" enough to link two documents via `xref` (ubiquitous types
    like raw globals are usually excluded to keep the doc graph meaningful and bounded)."""
    edges: set[Edge] = set()

    # doc → entity (mentions), weight = how many times the doc mentions the entity
    doc_entity: Counter[tuple[str, str]] = Counter()
    # section → its distinct entities (for cooccurs); entity → its distinct docs (for xref)
    section_entities: dict[str, set[str]] = defaultdict(set)
    entity_docs: dict[str, set[str]] = defaultdict(set)

    for m in mentions:
        doc_entity[(m.doc_key, m.entity_id)] += 1
        section_entities[m.section_id].add(m.entity_id)
        if m.entity_type in xref_types:
            entity_docs[m.entity_id].add(m.doc_key)

    for (doc, entity), weight in doc_entity.items():
        edges.add(("doc", doc, "mentions", "entity", entity, weight))

    cooccur: Counter[tuple[str, str]] = Counter()
    for entities in section_entities.values():
        ordered = sorted(entities)
        for i, a in enumerate(ordered):
            for b in ordered[i + 1 :]:
                cooccur[(a, b)] += 1
    for (a, b), weight in cooccur.items():
        edges.add(("entity", a, "cooccurs", "entity", b, weight))

    xref: Counter[tuple[str, str]] = Counter()
    for docs in entity_docs.values():
        ordered = sorted(docs)
        for i, a in enumerate(ordered):
            for b in ordered[i + 1 :]:
                xref[(a, b)] += 1
    for (a, b), weight in xref.items():
        edges.add(("doc", a, "xref", "doc", b, weight))

    return sorted(edges)
