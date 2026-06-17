"""SKL node boundary types — the gold `knowledge.db` schema as Pydantic v2 (skl-proposal.md §5).

The Semantic Knowledge Layer is a small, typed, versioned graph (proposal §5). These are the
S0-ratified node kinds, **frozen at S2.1** — the `resolve` stage builds them, `knowledge.db`
persists them, and (later) `publish` joins them into the shipped `index.db` (Q4). Every node carries
the three non-negotiables for an authoritative corpus:

* **identity** — an entity is `(type, canonical)` → the stable id `type/canonical`
  (`fileman_file/200`); a term is `term/<surface>`; a relationship is a typed, directed
  `(src_id, rel, dst_id)` edge.
* **provenance** — where the fact was asserted in the corpus (`source_sha256` + `doc` + `section`),
  so no node is ungrounded (§10).
* **lifecycle + verification** — `status` (`approved|proposed|deprecated`) and a `verification`
  block that is `asserted` today (corpus provenance) with room for `verified_on` when live-DD
  verification lands at S5 — **no migration** (Q2).

S2 builds Entities / Terms / Relationships only; Concepts are out of S2 (Q1).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["approved", "proposed", "deprecated"]


class Provenance(BaseModel):
    """Where a node/edge was asserted: the source doc's content hash + its corpus location."""

    model_config = {"frozen": True}

    source_sha256: str
    doc: str = ""  # the gold doc_key (`<APP>/<slug>`)
    section: str = ""  # the section/anchor within the doc (free-form locator)


class Verification(BaseModel):
    """A node's verification state. `asserted` = backed only by corpus provenance (the S2 default);
    `verified` = confirmed against the live system, carrying a `verified_on` `{system, date}` block
    (deferred to S5, Q2 — the field exists now so the upgrade needs no schema migration)."""

    model_config = {"frozen": True}

    status: Literal["asserted", "verified"] = "asserted"
    verified_on: dict[str, str] | None = None


class EntityNode(BaseModel):
    """A thing in VistA with stable identity — `id = (type, canonical)` (proposal §5.1)."""

    type: str
    canonical: str
    canonical_name: str = ""  # the human name (file #200 → "NEW PERSON")
    synonyms: list[str] = Field(default_factory=list)
    status: Status = "approved"
    provenance: list[Provenance] = Field(default_factory=list)
    verification: Verification = Field(default_factory=Verification)

    @property
    def node_id(self) -> str:
        return f"{self.type}/{self.canonical}"


class TermNode(BaseModel):
    """A *naming* of an entity/concept in prose, carrying the S1 classification facets (§5.2)."""

    surface: str
    term_class: str | None = None
    canonical_casing: str = ""
    enforce_case: bool = True
    collides_with_english: bool = False
    expand_on_first_use: bool = False
    status: Status = "approved"
    provenance: list[Provenance] = Field(default_factory=list)
    verification: Verification = Field(default_factory=Verification)

    @property
    def node_id(self) -> str:
        return f"term/{self.surface}"


class RelationshipNode(BaseModel):
    """A typed, directed, provenanced edge between two nodes (proposal §5.4). `rel` must be a type
    registered in `registries/relationships/edge-types.yaml` — `relate` enforces the closed set
    (Q3); an unregistered type never reaches `knowledge.db`."""

    src_id: str
    rel: str
    dst_id: str
    status: Status = "approved"
    provenance: list[Provenance] = Field(default_factory=list)
    verification: Verification = Field(default_factory=Verification)

    @property
    def edge_id(self) -> str:
        return f"{self.src_id}|{self.rel}|{self.dst_id}"
