"""Unit tests for `manifest`'s pure assembler (§14.4, D3) — corpus-manifest.json + discovery.json
from corpus counts. Pure: counts + clock value in, JSON-ready dicts out. The key behaviour is the
**optional `vectors.db`** rule — with no embedding info, semantic search is marked *unavailable* and
the embedding fields are omitted; a Phase-6 re-run fills them and flips the capability on.
"""

from __future__ import annotations

from vdocs.stages.manifest import manifest_pure as mp


def test_shared_boilerplate_files_materializes_approved_entries():
    # B1: each approved boilerplate registry entry → a canonical `<id>.md` carrying its verbatim
    # text, so normalize's `_shared/boilerplate/<id>.md` REFERENCE links resolve.
    entries = [
        {"id": "bp-abc", "label": "VA notice", "text": "VA notice block.", "status": "approved"},
        {"id": "bp-def", "label": "Pending", "text": "draft block", "status": "candidate"},
        {"id": "bp-ghi", "label": "No text", "status": "approved"},
    ]
    files = mp.shared_boilerplate_files(entries)
    assert files == {"bp-abc.md": "VA notice block.\n"}  # only the approved entry with text


def test_shared_boilerplate_files_empty_for_no_registry():
    assert mp.shared_boilerplate_files([]) == {}


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


# --- the AI corpus card (§14.7) -------------------------------------------------------------

_DOCS = [
    {
        "doc_key": "CPRS/or_um", "doc_id": "CPRS:or_um", "title": "OR User Manual",
        "app_code": "CPRS", "doc_type": "UM", "pkg_ns": "OR", "patch_id": "OR*3.0*539",
        "version": "3.0", "section_count": 12, "word_count": 3400,
    },
    {
        "doc_key": "KAAJEE/dibr", "doc_id": "KAAJEE:dibr", "title": "KAAJEE DIBR",
        "app_code": "KAAJEE", "doc_type": "", "pkg_ns": "", "patch_id": "",
        "version": "", "section_count": 5, "word_count": 800,
    },
]  # fmt: skip
_ENTS = [
    {"type": "routine", "canonical_name": "XLFSTR", "mention_count": 42},
    {"type": "routine", "canonical_name": "DGTMV", "mention_count": 10},
    {"type": "global", "canonical_name": "^DPT", "mention_count": 99},
]


def test_build_catalog_resolves_gold_body_path():
    cat = mp.build_catalog(_DOCS)
    # a grouped doc resolves to the version-free anchor relpath (pkg_ns_doctype, lowercased)
    or_um = next(d for d in cat if d["doc_key"] == "CPRS/or_um")
    assert or_um["body_path"] == "documents/gold/consolidated/CPRS/or_um/body.md"
    assert or_um["patch_id"] == "OR*3.0*539" and or_um["sections"] == 12
    # a standalone doc (no doc_type) anchors on its own slug (the doc_key tail)
    dibr = next(d for d in cat if d["doc_key"] == "KAAJEE/dibr")
    assert dibr["body_path"] == "documents/gold/consolidated/KAAJEE/dibr/body.md"


def test_build_entity_index_groups_and_trims_by_mentions():
    idx = mp.build_entity_index(_ENTS, top_n=1)
    assert idx["routine"] == [{"name": "XLFSTR", "mentions": 42}]  # top by mention_count
    assert idx["global"] == [{"name": "^DPT", "mentions": 99}]


def test_ai_manifest_assembles_card_with_recipe_and_fingerprint():
    cat = mp.build_catalog(_DOCS)
    ents = mp.build_entity_index(_ENTS, top_n=25)
    m = mp.ai_manifest(
        _COUNTS, cat, ents, tool_ver="0.1.0", generated_at="t", index_fingerprint="deadbeef"
    )
    assert m["schema_version"] == 1 and m["index_fingerprint"] == "deadbeef"
    assert m["counts"]["documents"] == 469
    assert "vdocs ask" in m["query"]["command"]
    assert "section_id" in m["citation"]["format"]
    assert m["documents"] == cat and m["entities"] == ents
    assert m["capabilities"]["semantic"] is False  # no embedding → semantic off (D3)


def test_corpus_card_renders_usage_catalog_and_recipe():
    cat = mp.build_catalog(_DOCS)
    ents = mp.build_entity_index(_ENTS, top_n=25)
    m = mp.ai_manifest(
        _COUNTS, cat, ents, tool_ver="0.1.0", generated_at="t", index_fingerprint="deadbeef"
    )
    md = mp.corpus_card(m)
    assert md.startswith("# ")
    assert "vdocs ask" in md  # the query recipe is rendered
    assert "OR User Manual" in md  # the catalog is rendered
    assert "documents/gold/consolidated/CPRS/or_um/body.md" in md  # with resolvable paths
    assert "XLFSTR" in md  # entity highlights rendered
    assert "never guess" in md.lower()  # the anti-hallucination usage rule
