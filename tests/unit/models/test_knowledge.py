"""Unit tests for models.knowledge — the SKL node boundary types (skl-proposal.md §5, S2.1).

The schema is the S0-ratified §5 model frozen at S2.1: entity / term / relationship nodes, each
carrying identity (`(type, canonical)`), `synonyms[]`, `status`, `provenance[]`, and a
`verification` block (`asserted` now, room for `verified_on` later). These tests pin the identity
formulas, the defaults, and the literal-constrained status/verification fields.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from vdocs.models.knowledge import (
    EntityNode,
    Provenance,
    RelationshipNode,
    TermNode,
    Verification,
)


def test_entity_node_id_is_type_slash_canonical():
    e = EntityNode(type="fileman_file", canonical="200", canonical_name="NEW PERSON")
    assert e.node_id == "fileman_file/200"


def test_entity_defaults_are_approved_and_asserted_with_empty_lists():
    e = EntityNode(type="routine", canonical="DIQ")
    assert e.status == "approved"
    assert e.synonyms == []
    assert e.provenance == []
    assert e.verification == Verification()
    assert e.verification.status == "asserted"
    assert e.verification.verified_on is None


def test_term_node_id_is_term_slash_surface():
    t = TermNode(surface="VistA", term_class="brand", canonical_casing="VistA")
    assert t.node_id == "term/VistA"
    assert t.enforce_case is True
    assert t.collides_with_english is False


def test_relationship_carries_typed_edge_and_provenance():
    r = RelationshipNode(
        src_id="fileman_file/200",
        rel="documented-in",
        dst_id="doc/DI/fm22_2tm",
        provenance=[Provenance(source_sha256="abc", doc="DI/fm22_2tm", section="global-map")],
    )
    assert r.rel == "documented-in"
    assert r.provenance[0].doc == "DI/fm22_2tm"
    assert r.verification.status == "asserted"


def test_status_field_is_constrained_to_the_lifecycle_set():
    with pytest.raises(ValidationError):
        EntityNode(type="x", canonical="y", status="bogus")  # type: ignore[arg-type]


def test_verification_status_is_constrained():
    with pytest.raises(ValidationError):
        Verification(status="maybe")  # type: ignore[arg-type]


def test_verification_can_carry_a_verified_on_block_later():
    v = Verification(status="verified", verified_on={"system": "vehu", "date": "2026-06-17"})
    assert v.verified_on == {"system": "vehu", "date": "2026-06-17"}
