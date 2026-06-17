"""Unit tests for the `resolve` stage pure cores (SKL S2.2/S2.3).

The headline proof of the SKL: `file #200`, `the NEW PERSON file`, and `^VA(200,` — three different
surfaces — all resolve to **one** canonical entity id, `fileman_file/200`, data-driven from the
DD seed (no file identity in code). Plus the resolution table is data; classify folds the S1 term
facets; relate emits only registered (closed-set) edge types.
"""

from __future__ import annotations

from vdocs.models.knowledge import EntityNode, Provenance, RelationshipNode, TermNode
from vdocs.stages.index import entities_pure as ent
from vdocs.stages.resolve import resolve_pure as rp

# the FileMan DD seed slice these tests resolve against (the shape of dd-seed.di.yaml `files`)
_SEED = [
    {
        "number": "200",
        "name": "NEW PERSON",
        "global": "^VA(200,",
        "synonyms": ["NEW PERSON file", "the 200 file"],
    },
    {"number": "1", "name": "FILE", "global": "^DIC("},
]

_RULES = ent.compile_rules(
    [
        {
            "type": "fileman_file",
            "pattern": r"(?i)\bfiles?\s+#?(\d+(?:\.\d+)?)\b",
            "canonical": "group1",
        },
        {
            "type": "global",
            "pattern": r"\^%?[A-Z][A-Z0-9]+\b",
            "canonical": "whole",
            "casefold": True,
        },
    ]
)


def test_resolution_index_is_built_from_seed_data_not_code():
    idx = rp.resolution_index(_SEED)
    assert idx.by_number["200"] == "fileman_file/200"
    # name, global, and synonyms all index to the same canonical node
    assert idx.by_surface["NEW PERSON"] == "fileman_file/200"
    assert idx.by_surface["^VA(200,"] == "fileman_file/200"
    assert idx.by_surface["NEW PERSON FILE"] == "fileman_file/200"
    assert idx.entities["fileman_file/200"].canonical_name == "NEW PERSON"


def test_three_surfaces_resolve_to_one_canonical_entity():
    text = "Edit the NEW PERSON file. See file #200. The global is ^VA(200,0)."
    idx = rp.resolution_index(_SEED)
    result = rp.resolve(text, _RULES, idx)
    assert "fileman_file/200" in result.resolved
    surfaces = result.resolved["fileman_file/200"]
    # the file-number form (via the recognizer), the prose name (longest seed surface wins —
    # "NEW PERSON file" over "NEW PERSON"), and the global root all land on the one node
    assert "file #200" in surfaces
    assert any("NEW PERSON" in s for s in surfaces)
    assert "^VA(200," in surfaces


def test_unmapped_recognized_mentions_are_unresolved_candidates():
    text = "The routine ^ZZUNKNOWN is referenced but not in the seed."
    idx = rp.resolution_index(_SEED)
    result = rp.resolve(text, _RULES, idx)
    # a global with no seed mapping is surfaced as an unresolved candidate, never asserted
    assert any(s == "^ZZUNKNOWN" for _t, s in result.unresolved)
    assert "fileman_file/200" not in result.resolved


def test_truncated_global_fragment_of_a_resolved_root_is_not_a_proposal():
    # the recognizer truncates `^VA(200,` to `^VA`; once the full root resolved, the bare fragment
    # must NOT pollute the curator queue (it is already accounted for).
    text = "The global is ^VA(200,0) for the file."
    idx = rp.resolution_index(_SEED)
    result = rp.resolve(text, _RULES, idx)
    assert "fileman_file/200" in result.resolved
    assert not any(s == "^VA" for _t, s in result.unresolved)


def test_resolve_ignores_bare_numbers_without_file_context():
    text = "There were 200 records and 1 error."  # no 'file #' anchor
    idx = rp.resolution_index(_SEED)
    result = rp.resolve(text, _RULES, idx)
    assert result.resolved == {}


# --- classify (S2.3) ---

_PRODUCTS = {
    "DI": [
        {"abbr": "VistA", "term_class": "brand", "canonical_casing": "VistA", "enforce_case": True},
        {"abbr": "CAN", "term_class": "acronym", "enforce_case": True},
    ]
}
_ENGLISH = frozenset({"can", "vista"})  # both lowercases are dictionary words


def test_classify_folds_s1_facets_and_autoderives_collision():
    terms = rp.classify_terms(_PRODUCTS, english_words=_ENGLISH)
    by_surface = {t.surface: t for t in terms}
    # brand: internal-capital typography → never collides → enforced
    assert by_surface["VistA"].collides_with_english is False
    assert by_surface["VistA"].term_class == "brand"
    # all-caps acronym whose lowercase is a word → collides → spelling-accept only
    assert by_surface["CAN"].collides_with_english is True


def test_classify_emits_the_full_superset_regardless_of_appearance():
    # S3.1 (friction #4): EVERY curated surface becomes a Term node (the superset build-termbase
    # projects from), not only those seen in the corpus.
    terms = rp.classify_terms(_PRODUCTS, english_words=_ENGLISH)
    assert {t.surface for t in terms} == {"VistA", "CAN"}


def test_classify_provenance_corpus_where_seen_else_registry_marker():
    reg = Provenance(source_sha256="", doc="registry:product-names.yaml")
    corpus = Provenance(source_sha256="deadbeef", doc="DI/fm")
    terms = {
        t.surface: t
        for t in rp.classify_terms(
            _PRODUCTS,
            english_words=_ENGLISH,
            provenance={"VistA": [corpus]},
            registry_provenance=reg,
        )
    }
    assert terms["VistA"].provenance == [corpus]  # seen in the corpus → corpus provenance
    assert terms["CAN"].provenance == [reg]  # not seen → curated registry origin (still grounded)


# --- relate (S2.3): closed registered edge set (Q3) ---


def test_partition_edges_rejects_unregistered_types():
    registered = frozenset({"documented-in", "synonym-of"})
    edges = [
        RelationshipNode(src_id="a", rel="documented-in", dst_id="doc/x"),
        RelationshipNode(src_id="a", rel="invented-edge", dst_id="b"),
    ]
    kept, rejected = rp.partition_edges(edges, registered)
    assert [e.rel for e in kept] == ["documented-in"]
    assert [e.rel for e in rejected] == ["invented-edge"]


def test_documented_in_edges_link_entities_to_their_docs():
    edges = rp.documented_in_edges({"DI/fm22_2tm": {"fileman_file/200", "fileman_file/1"}})
    rels = {(e.src_id, e.rel, e.dst_id) for e in edges}
    assert ("fileman_file/200", "documented-in", "doc/DI/fm22_2tm") in rels
    assert ("fileman_file/1", "documented-in", "doc/DI/fm22_2tm") in rels


# --- verify (S2.3): every node asserted (Q2) ---


def test_all_asserted_holds_for_default_nodes():
    e = EntityNode(type="fileman_file", canonical="200")
    t = TermNode(surface="VistA")
    r = RelationshipNode(src_id="a", rel="documented-in", dst_id="doc/x")
    assert rp.all_asserted([e], [t], [r]) is True


def test_all_asserted_is_a_real_gate_a_verified_node_in_s2_trips_it():
    # S2 has NO live verification (Q2): a node that somehow arrived `verified` violates the S2
    # invariant — the gate must distinguish the states, not pass vacuously.
    from vdocs.models.knowledge import Verification

    e = EntityNode(type="x", canonical="y", verification=Verification(status="verified"))
    assert rp.all_asserted([e]) is False


def test_build_proposals_aggregates_unresolved_into_a_curator_queue():
    unresolved = [
        ("global", "^ZZA", "DI/a"),
        ("global", "^ZZA", "DI/b"),
        ("routine", "DIEZ", "DI/a"),
    ]
    proposals = rp.build_proposals(unresolved)
    # most-frequent first; every proposal is status:proposed (never asserted) and grounded in docs
    assert proposals[0]["surface"] == "^ZZA"
    assert proposals[0]["occurrences"] == 2
    assert proposals[0]["docs"] == ["DI/a", "DI/b"]
    assert all(p["status"] == "proposed" for p in proposals)


def test_entities_from_resolution_carry_seed_identity_and_provenance():
    idx = rp.resolution_index(_SEED)
    prov = {"fileman_file/200": [Provenance(source_sha256="abc", doc="DI/fm22_2tm")]}
    nodes = rp.entities_from_resolution(idx, {"fileman_file/200"}, provenance=prov)
    (node,) = nodes
    assert node.canonical_name == "NEW PERSON"
    assert "^VA(200," in node.synonyms
    assert node.provenance[0].source_sha256 == "abc"
    assert node.verification.status == "asserted"
