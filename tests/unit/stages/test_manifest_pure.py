"""Unit tests for `manifest`'s pure assembler (§14.4) — corpus-manifest.json + discovery.json
from corpus counts. Pure: counts + clock value in, JSON-ready dicts out. The corpus is lexical-first
and offline: the capability manifest advertises lexical/structured/graph only — the semantic/vector
path was descoped (no `embedding` field, no `semantic` capability).
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


# --- B2: glossary promotion (§9.6 PROMOTE) -------------------------------------------------------


def test_acronym_table_pairs_extracts_term_definition():
    rows = [
        ["Term", "Description"],
        ["GUI", "Graphical User Interface"],
        ["DLL", "Dynamic Link Library"],
    ]
    assert mp.acronym_table_pairs(rows) == [
        ("GUI", "Graphical User Interface"),
        ("DLL", "Dynamic Link Library"),
    ]


def test_acronym_table_pairs_strips_markdown_emphasis_in_header_and_cells():
    rows = [["**Acronym**", "**Definition**"], ["AD", "Active Directory"]]
    assert mp.acronym_table_pairs(rows) == [("AD", "Active Directory")]


def test_acronym_table_pairs_ignores_non_acronym_tables():
    # a data-dictionary table is not a glossary — must not be harvested
    assert mp.acronym_table_pairs([["File Number", "File Name"], ["2", "PATIENT"]]) == []


def test_acronym_table_pairs_skips_junk_rows():
    rows = [
        ["Acronym", "Definition"],
        ["", "no term"],  # empty term
        ["X" * 60, "term too long"],  # over length cap
        ["OK", "ab"],  # definition too short
        ["VA", "Department of Veterans Affairs"],
    ]
    assert mp.acronym_table_pairs(rows) == [("VA", "Department of Veterans Affairs")]


def test_build_glossary_dedupes_case_insensitively_and_picks_most_common_def():
    pairs = [
        ("VA", "Department of Veterans Affairs"),
        ("va", "Department of Veterans Affairs"),  # same def, different case → one entry
        ("VA", "Veterans Administration"),  # minority def
        ("GUI", "Graphical User Interface"),
    ]
    md = mp.build_glossary(pairs)
    assert md.startswith("# Glossary")
    assert "**VA** — Department of Veterans Affairs" in md  # majority def wins
    assert "Veterans Administration" not in md
    # alphabetical: GUI before VA
    assert md.index("**GUI**") < md.index("**VA**")


def test_build_glossary_empty_is_header_only():
    assert mp.build_glossary([]).strip() == "# Glossary"


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


def test_manifest_capabilities_lexical_structured_graph_only():
    m = mp.corpus_manifest(_COUNTS, tool_ver="0.1.0", generated_at="t")
    assert m["capabilities"]["lexical"] is True  # FTS5 over is_latest sections
    assert m["capabilities"]["structured"] is True and m["capabilities"]["graph"] is True
    # the semantic/vector path is descoped — no semantic capability, no embedding field
    assert "semantic" not in m["capabilities"]
    assert "embedding" not in m


def test_discovery_descriptor_schema_and_ids():
    d = mp.discovery_descriptor(_COUNTS, tool_ver="0.1.0")
    # the stable-ID scheme is the agent's front door (§5.5/§14.4)
    assert "doc_key" in d["id_scheme"] and "section_id" in d["id_scheme"]
    assert "entity_id" in d["id_scheme"]
    # the entity-type vocabulary is advertised
    assert set(d["entity_types"]) == {"build", "global", "fileman_file", "package_namespace"}
    # capabilities mirror the manifest (lexical/structured/graph; no semantic)
    assert d["capabilities"]["graph"] is True
    assert "semantic" not in d["capabilities"]
    assert "embedding" not in d


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


def test_build_entity_index_downweights_low_signal_globals():
    # B3a (§8.2): globals dominate by count but are noise for the headline — capped to a smaller
    # slot count than high-signal types (they stay fully queryable in index.db, untouched here).
    rows = [
        {"type": "global", "canonical_name": f"^G{i}", "mention_count": 100 - i} for i in range(9)
    ]
    rows += [
        {"type": "routine", "canonical_name": f"R{i}", "mention_count": 50 - i} for i in range(9)
    ]
    idx = mp.build_entity_index(rows, top_n=8, low_signal_top_n=3)
    assert len(idx["routine"]) == 8  # high-signal: full cap
    assert len(idx["global"]) == 3  # low-signal globals down-weighted in the headline


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
    assert "semantic" not in m["capabilities"]  # semantic/vector path descoped
    assert "embedding" not in m


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


def test_manifest_embeds_coverage_and_read_contract_when_given():
    # P2.3/P2.4: optional coverage stats + the read-contract version/capabilities (for consumer
    # staleness + capability negotiation). Absent when not supplied (backward-compatible).
    cov = {"function_category": {"populated": 9, "total": 10, "pct": 90.0, "distinct": 8}}
    rc = {"version": "1.2", "capabilities": ["fts5", "vocab_table"]}
    m = mp.corpus_manifest(
        _COUNTS, tool_ver="0.1.0", generated_at="t", coverage=cov, read_contract=rc
    )
    assert m["coverage"]["function_category"]["pct"] == 90.0
    assert m["read_contract"]["version"] == "1.2"
    assert "vocab_table" in m["read_contract"]["capabilities"]


def test_manifest_omits_coverage_and_read_contract_by_default():
    m = mp.corpus_manifest(_COUNTS, tool_ver="0.1.0", generated_at="t")
    assert "coverage" not in m and "read_contract" not in m


def test_facet_distribution_counts_values_per_field():
    # P2.5: the corpus characterization snapshot — distinct values + their doc counts per facet,
    # so an unexpected data-shape shift (a value appearing/vanishing) is a reviewable manifest diff.
    rows = [
        {"function_category": "Pharmacy", "doc_type": "UM"},
        {"function_category": "Pharmacy", "doc_type": "TM"},
        {"function_category": "Laboratory", "doc_type": "UM"},
        {"function_category": "", "doc_type": "UM"},  # empty is not counted
    ]
    dist = mp.facet_distribution(rows, ("function_category", "doc_type"))
    assert dist["function_category"] == {"Laboratory": 1, "Pharmacy": 2}
    assert dist["doc_type"] == {"TM": 1, "UM": 3}
