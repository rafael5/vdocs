"""Unit tests for kernel.knowledge_db — the gold `knowledge.db` write/read round-trip (S2.1).

The store is the persisted form of the §5 model. These tests pin that an empty build is valid (the
S2.1 orchestrator gate), and that entity/term/relationship nodes round-trip through the DB without
loss — identity, synonyms, provenance, status, and the verification block all survive.
"""

from __future__ import annotations

from vdocs.kernel import knowledge_db as kdb
from vdocs.models.knowledge import (
    EntityNode,
    Provenance,
    RelationshipNode,
    TermNode,
    Verification,
)


def test_empty_build_is_valid_and_round_trips_empty(tmp_path):
    path = tmp_path / "knowledge.db"
    kdb.write_atomic(path, entities=[], terms=[], relationships=[])
    assert path.is_file()
    assert kdb.read_entities(path) == []
    assert kdb.read_terms(path) == []
    assert kdb.read_relationships(path) == []
    assert kdb.schema_version(path) == kdb.SCHEMA_VERSION


def test_entity_round_trips_with_synonyms_and_provenance(tmp_path):
    path = tmp_path / "knowledge.db"
    e = EntityNode(
        type="fileman_file",
        canonical="200",
        canonical_name="NEW PERSON",
        synonyms=["NEW PERSON file", "^VA(200,"],
        provenance=[Provenance(source_sha256="abc", doc="DI/fm22_2tm", section="intro")],
    )
    kdb.write_atomic(path, entities=[e], terms=[], relationships=[])
    (got,) = kdb.read_entities(path)
    assert got == e


def test_term_round_trips_with_facets(tmp_path):
    path = tmp_path / "knowledge.db"
    t = TermNode(
        surface="VistA",
        term_class="brand",
        canonical_casing="VistA",
        enforce_case=True,
        collides_with_english=False,
        provenance=[Provenance(source_sha256="def", doc="DI/fm22_2um1")],
    )
    kdb.write_atomic(path, entities=[], terms=[t], relationships=[])
    (got,) = kdb.read_terms(path)
    assert got == t


def test_relationship_round_trips_with_verification_block(tmp_path):
    path = tmp_path / "knowledge.db"
    r = RelationshipNode(
        src_id="fileman_file/200",
        rel="documented-in",
        dst_id="doc/DI/fm22_2tm",
        provenance=[Provenance(source_sha256="abc", doc="DI/fm22_2tm")],
        verification=Verification(status="asserted"),
    )
    kdb.write_atomic(path, entities=[], terms=[], relationships=[r])
    (got,) = kdb.read_relationships(path)
    assert got == r
