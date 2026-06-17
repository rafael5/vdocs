"""The gold `knowledge.db` store — the persisted SKL graph (skl-proposal.md §5, S2.1).

`knowledge.db` is the SKL's **own** gold artifact (Q4: two DBs joined on entity-id; the merge into
the shipped `index.db` is a later `publish` concern, not S2). This module is the single I/O boundary
for it (§9.2): the frozen schema, the atomic whole-store build, and the read-back that reconstructs
the `models.knowledge` nodes verbatim. List-valued fields (`synonyms`, `provenance`) are stored as
JSON in a column — the node round-trips losslessly and the §4 provenance-completeness gate (S4) can
still assert `json_array_length(provenance) > 0` in SQL.

Built with `kernel.db.build_atomic` (the hardened temp+rename build) so a crash never leaves a
half-written store the `resolve` postflight would mistake for complete.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from vdocs.kernel import db
from vdocs.models.knowledge import (
    EntityNode,
    Provenance,
    RelationshipNode,
    TermNode,
    Verification,
)

# Bump when the knowledge.db node shape changes (re-runs the `resolve` stage + any consumer).
SCHEMA_VERSION = "1.0"

_SCHEMA = """
CREATE TABLE entities (
  node_id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  canonical TEXT NOT NULL,
  canonical_name TEXT,
  synonyms TEXT NOT NULL,            -- JSON array of surface strings
  status TEXT NOT NULL,             -- approved | proposed | deprecated
  provenance TEXT NOT NULL,         -- JSON array of {source_sha256, doc, section}
  verification_status TEXT NOT NULL,-- asserted | verified
  verified_on TEXT                  -- JSON {system, date} or NULL
);
CREATE TABLE terms (
  node_id TEXT PRIMARY KEY,
  surface TEXT NOT NULL,
  term_class TEXT,
  canonical_casing TEXT,
  enforce_case INTEGER NOT NULL,
  collides_with_english INTEGER NOT NULL,
  expand_on_first_use INTEGER NOT NULL,
  status TEXT NOT NULL,
  provenance TEXT NOT NULL,
  verification_status TEXT NOT NULL,
  verified_on TEXT
);
CREATE TABLE relationships (
  src_id TEXT NOT NULL,
  rel TEXT NOT NULL,
  dst_id TEXT NOT NULL,
  status TEXT NOT NULL,
  provenance TEXT NOT NULL,
  verification_status TEXT NOT NULL,
  verified_on TEXT,
  PRIMARY KEY (src_id, rel, dst_id)
);
CREATE INDEX idx_entities_type ON entities(type);
CREATE INDEX idx_relationships_src ON relationships(src_id);
CREATE INDEX idx_relationships_dst ON relationships(dst_id);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def _prov_json(provenance: list[Provenance]) -> str:
    return json.dumps([p.model_dump() for p in provenance])


def _verified_json(v: Verification) -> str | None:
    return json.dumps(v.verified_on) if v.verified_on is not None else None


def write_atomic(
    path: Path,
    *,
    entities: list[EntityNode],
    terms: list[TermNode],
    relationships: list[RelationshipNode],
    schema_version: str = SCHEMA_VERSION,
) -> None:
    """Build a fresh `knowledge.db` from the resolved nodes (atomic temp+rename)."""

    def build(conn: sqlite3.Connection) -> None:
        conn.executescript(_SCHEMA)
        conn.executemany(
            "INSERT INTO entities (node_id, type, canonical, canonical_name, synonyms, status, "
            "provenance, verification_status, verified_on) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    e.node_id,
                    e.type,
                    e.canonical,
                    e.canonical_name,
                    json.dumps(e.synonyms),
                    e.status,
                    _prov_json(e.provenance),
                    e.verification.status,
                    _verified_json(e.verification),
                )
                for e in entities
            ],
        )
        conn.executemany(
            "INSERT INTO terms (node_id, surface, term_class, canonical_casing, enforce_case, "
            "collides_with_english, expand_on_first_use, status, provenance, verification_status, "
            "verified_on) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    t.node_id,
                    t.surface,
                    t.term_class,
                    t.canonical_casing,
                    int(t.enforce_case),
                    int(t.collides_with_english),
                    int(t.expand_on_first_use),
                    t.status,
                    _prov_json(t.provenance),
                    t.verification.status,
                    _verified_json(t.verification),
                )
                for t in terms
            ],
        )
        conn.executemany(
            "INSERT INTO relationships (src_id, rel, dst_id, status, provenance, "
            "verification_status, verified_on) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    r.src_id,
                    r.rel,
                    r.dst_id,
                    r.status,
                    _prov_json(r.provenance),
                    r.verification.status,
                    _verified_json(r.verification),
                )
                for r in relationships
            ],
        )
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('schema_version', ?)", (schema_version,)
        )

    db.build_atomic(path, build)


def _provenance(raw: str) -> list[Provenance]:
    return [Provenance(**d) for d in json.loads(raw)]


def _verification(status: str, verified_on: str | None) -> Verification:
    return Verification(
        status=status,  # type: ignore[arg-type]
        verified_on=json.loads(verified_on) if verified_on is not None else None,
    )


def read_entities(path: Path) -> list[EntityNode]:
    conn = db.connect(path, read_only=True)
    try:
        rows = conn.execute(
            "SELECT type, canonical, canonical_name, synonyms, status, provenance, "
            "verification_status, verified_on FROM entities ORDER BY node_id"
        ).fetchall()
    finally:
        conn.close()
    return [
        EntityNode(
            type=r[0],
            canonical=r[1],
            canonical_name=r[2] or "",
            synonyms=json.loads(r[3]),
            status=r[4],
            provenance=_provenance(r[5]),
            verification=_verification(r[6], r[7]),
        )
        for r in rows
    ]


def read_terms(path: Path) -> list[TermNode]:
    conn = db.connect(path, read_only=True)
    try:
        rows = conn.execute(
            "SELECT surface, term_class, canonical_casing, enforce_case, collides_with_english, "
            "expand_on_first_use, status, provenance, verification_status, verified_on "
            "FROM terms ORDER BY node_id"
        ).fetchall()
    finally:
        conn.close()
    return [
        TermNode(
            surface=r[0],
            term_class=r[1],
            canonical_casing=r[2] or "",
            enforce_case=bool(r[3]),
            collides_with_english=bool(r[4]),
            expand_on_first_use=bool(r[5]),
            status=r[6],
            provenance=_provenance(r[7]),
            verification=_verification(r[8], r[9]),
        )
        for r in rows
    ]


def read_relationships(path: Path) -> list[RelationshipNode]:
    conn = db.connect(path, read_only=True)
    try:
        rows = conn.execute(
            "SELECT src_id, rel, dst_id, status, provenance, verification_status, verified_on "
            "FROM relationships ORDER BY src_id, rel, dst_id"
        ).fetchall()
    finally:
        conn.close()
    return [
        RelationshipNode(
            src_id=r[0],
            rel=r[1],
            dst_id=r[2],
            status=r[3],
            provenance=_provenance(r[4]),
            verification=_verification(r[5], r[6]),
        )
        for r in rows
    ]


def schema_version(path: Path) -> str:
    conn = db.connect(path, read_only=True)
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    finally:
        conn.close()
    return row[0] if row else ""
