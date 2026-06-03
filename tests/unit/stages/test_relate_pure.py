"""Unit tests for `relate`'s pure edge derivation (§8 — the knowledge graph).

`relate` adds ONLY edges over the entities `index` already extracted: doc↔entity (`mentions`),
entity↔entity (`cooccurs`, within a section), and doc↔doc (`xref`, via a shared significant entity).
Pure: mention rows in, sorted unique edge tuples out.
"""

from __future__ import annotations

from vdocs.stages.relate import relate_pure as rp


def _m(doc, section, entity_id, entity_type):
    return rp.Mention(doc_key=doc, section_id=section, entity_id=entity_id, entity_type=entity_type)


_MENTIONS = [
    _m("d1", "d1/s1", "build:X", "build"),
    _m("d1", "d1/s1", "global:G", "global"),
    _m("d1", "d1/s2", "build:X", "build"),  # build:X mentioned twice in d1
    _m("d2", "d2/s1", "build:X", "build"),
    _m("d2", "d2/s2", "global:G", "global"),
]


def test_mentions_edges_doc_to_entity_with_weight():
    edges = rp.derive_edges(_MENTIONS, xref_types=frozenset({"build"}))
    mentions = {e for e in edges if e[2] == "mentions"}
    assert ("doc", "d1", "mentions", "entity", "build:X", 2) in mentions  # twice in d1
    assert ("doc", "d1", "mentions", "entity", "global:G", 1) in mentions
    assert ("doc", "d2", "mentions", "entity", "build:X", 1) in mentions


def test_cooccurs_edges_are_section_scoped_and_undirected():
    edges = rp.derive_edges(_MENTIONS, xref_types=frozenset({"build"}))
    cooccurs = [e for e in edges if e[2] == "cooccurs"]
    # only d1/s1 co-hosts two distinct entities → one undirected pair (sorted src<dst), weight 1
    assert cooccurs == [("entity", "build:X", "cooccurs", "entity", "global:G", 1)]


def test_xref_edges_link_docs_sharing_a_significant_entity():
    edges = rp.derive_edges(_MENTIONS, xref_types=frozenset({"build"}))
    xref = [e for e in edges if e[2] == "xref"]
    # build:X is shared by d1 and d2 (a build id is significant); global:G is excluded by xref_types
    assert xref == [("doc", "d1", "xref", "doc", "d2", 1)]


def test_xref_excludes_ubiquitous_types():
    # with only 'global' allowed, build:X no longer links; global:G is in different sections but
    # shared across d1/d2 → a global-based xref appears (caller chooses which types are significant)
    edges = rp.derive_edges(_MENTIONS, xref_types=frozenset({"global"}))
    xref = [e for e in edges if e[2] == "xref"]
    assert xref == [("doc", "d1", "xref", "doc", "d2", 1)]


def test_derive_edges_is_deterministic_and_sorted():
    edges = rp.derive_edges(_MENTIONS, xref_types=frozenset({"build"}))
    assert edges == sorted(edges)  # stable, order-independent output
    assert len(edges) == len(set(edges))  # no duplicate edges


def test_empty_mentions_yield_no_edges():
    assert rp.derive_edges([], xref_types=frozenset({"build"})) == []
