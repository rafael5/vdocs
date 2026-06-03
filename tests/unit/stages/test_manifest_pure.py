"""Unit tests for `manifest`'s pure assembler (§14.4, D3) — corpus-manifest.json + discovery.json
from corpus counts. Pure: counts + clock value in, JSON-ready dicts out. The key behaviour is the
**optional `vectors.db`** rule — with no embedding info, semantic search is marked *unavailable* and
the embedding fields are omitted; a Phase-6 re-run fills them and flips the capability on.
"""

from __future__ import annotations

from vdocs.stages.manifest import manifest_pure as mp

_COUNTS = {
    "documents": 469,
    "documents_latest": 290,
    "version_groups": 290,
    "sections": 25981,
    "sections_searchable": 16756,
    "entities": 1796,
    "entities_by_type": {
        "build": 149,
        "global": 1405,
        "fileman_file": 223,
        "package_namespace": 19,
    },
    "relations": 24366,
    "relations_by_type": {"mentions": 3099, "cooccurs": 17368, "xref": 3899},
}


def test_manifest_counts_and_lineage():
    m = mp.corpus_manifest(_COUNTS, tool_ver="0.1.0", generated_at="2026-06-02T00:00:00Z")
    assert m["counts"]["documents"] == 469
    assert m["counts"]["version_groups"] == 290
    assert m["counts"]["sections_searchable"] == 16756
    assert m["counts"]["entities_by_type"]["global"] == 1405
    assert m["tool_ver"] == "0.1.0" and m["generated_at"] == "2026-06-02T00:00:00Z"


def test_manifest_marks_semantic_unavailable_without_vectors():
    m = mp.corpus_manifest(_COUNTS, tool_ver="0.1.0", generated_at="t")
    assert m["capabilities"]["semantic"] is False  # no vectors.db yet (D3)
    assert m["capabilities"]["lexical"] is True  # FTS5 over is_latest sections
    assert m["capabilities"]["structured"] is True and m["capabilities"]["graph"] is True
    assert m["embedding"] is None  # embedding-model id+version omitted until embed lands


def test_manifest_fills_embedding_when_vectors_present():
    embedding = {"model": "all-MiniLM-L6-v2", "version": "2", "dim": 384}
    m = mp.corpus_manifest(_COUNTS, tool_ver="0.1.0", generated_at="t", embedding=embedding)
    assert m["capabilities"]["semantic"] is True
    assert m["embedding"] == embedding


def test_discovery_descriptor_schema_and_ids():
    d = mp.discovery_descriptor(_COUNTS, tool_ver="0.1.0")
    # the stable-ID scheme is the agent's front door (§5.5/§14.4)
    assert "doc_key" in d["id_scheme"] and "section_id" in d["id_scheme"]
    assert "entity_id" in d["id_scheme"]
    # the entity-type vocabulary is advertised
    assert set(d["entity_types"]) == {"build", "global", "fileman_file", "package_namespace"}
    # capabilities mirror the manifest (semantic off without vectors)
    assert d["capabilities"]["semantic"] is False
    assert d["capabilities"]["graph"] is True


def test_discovery_semantic_on_with_embedding():
    d = mp.discovery_descriptor(_COUNTS, tool_ver="0.1.0", embedding={"model": "m", "dim": 8})
    assert d["capabilities"]["semantic"] is True
