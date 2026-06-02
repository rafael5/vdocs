"""Unit tests for discover pure miners — candidate patterns, no mutation (§9.6)."""

from __future__ import annotations

from vdocs.stages.discover import discover_pure as dp

_BOILER = (
    "How to Use This Manual: read each section in order and consult the index for "
    "specific topics covered throughout this document."
)


def test_split_blocks_and_key():
    md = "# H\n\nFirst block.\n\n\nSecond   block.\n"
    assert dp.split_blocks(md) == ["# H", "First block.", "Second   block."]
    assert dp.block_key("  Second   Block.  ") == "second block."  # ws-collapsed, lowercased


def test_recurring_block_below_threshold_is_not_a_candidate():
    docs = {"a/x": _BOILER, "a/y": _BOILER}  # only 2 docs, min_docs=3
    assert dp.mine_recurring_blocks(docs, min_docs=3) == []


def test_long_recurring_block_is_boilerplate_reference():
    docs = {f"app/{i}": f"# {i}\n\n{_BOILER}\n\nUnique para {i}.\n" for i in range(4)}
    cands = dp.mine_recurring_blocks(docs, min_docs=3, auto_docs=10)
    boiler = [c for c in cands if c.registry == "boilerplate"]
    assert len(boiler) == 1
    c = boiler[0]
    assert c.disposition == "REFERENCE"
    assert c.doc_count == 4 and c.grade == "review"  # 4 < auto_docs=10
    assert c.sample_doc_ids[:2] == ["app/0", "app/1"]
    # the unique paragraphs are not candidates
    assert all("unique para" not in c.key for c in cands)


def test_short_recurring_block_is_dead_phrase_delete_never_auto():
    phrase = "This page intentionally left blank."
    docs = {f"d/{i}": f"Intro {i}.\n\n{phrase}\n" for i in range(12)}
    cands = dp.mine_recurring_blocks(docs, min_docs=3, auto_docs=10, phrase_max_len=60)
    (c,) = [c for c in cands if c.registry == "phrases"]
    assert c.disposition == "DELETE"
    # a deletion is never auto-approved on frequency alone (it recurs like a heading does)
    assert c.doc_count == 12 and c.grade == "review"


def test_recurring_heading_is_template_retain_not_phrase_delete():
    # a heading recurs across many docs but is template scaffold — must NOT be DELETE (the
    # real-corpus trap: "# Introduction" appeared in 292 docs and was being auto-DELETE'd)
    docs = {f"d/{i}": f"# Introduction\n\nBody for doc {i} with words.\n" for i in range(20)}
    cands = dp.mine_recurring_blocks(docs, min_docs=3, auto_docs=10)
    head = [c for c in cands if c.key == "# introduction"]
    assert head and head[0].registry == "templates" and head[0].disposition == "RETAIN"
    assert head[0].grade == "auto"  # frequent + non-deleting → auto is fine


def test_candidates_sorted_by_doc_count_desc():
    common = "Common shared block of reasonable length appearing widely across the corpus."
    rare = "Rarer shared block of reasonable length appearing in fewer documents here."
    docs = {f"c/{i}": common for i in range(6)}
    docs.update({f"r/{i}": f"{common}\n\n{rare}" for i in range(3)})  # rare only in 3
    cands = dp.mine_recurring_blocks(docs, min_docs=3)
    assert [c.doc_count for c in cands] == sorted([c.doc_count for c in cands], reverse=True)


def test_count_bare_markers_and_xref_wraps():
    body = "1.\n\n-\n\n* \n\n1. real item\n\n- real item\n\nSee [[ref]](#_Toc1) and [[x]](#_Toc2)\n"
    assert dp.count_bare_markers(body) == 3  # the three empty markers, not the real items
    assert dp.count_xref_wraps(body) == 2  # two [[ cross-ref wraps


def test_mine_converter_routing_flags_xref_explosion_not_missing_headings():
    # the v1 signal: a doc with a heavy [[…]] cross-ref explosion (cprsguium has 573 headings
    # AND 3,058 bare markers — measuring headings would MISS it)
    exploded = "# Heading\n\n" + ("-\n\n[[x]](#_Toc1)\n\n" * 60)  # 60 xref wraps + 60 bare markers
    docs = {
        "CPRS/cprsguium": exploded,
        "CPRS/clean": "# Title\n\n1. real item\n\n2. another real item\n",  # no [[ → fine
        "ADT/structureless": "word " * 500,  # no headings but also no [[ → NOT a Docling case
    }
    cands = dp.mine_converter_routing(docs, min_xref_wraps=50)
    assert [c.doc_id for c in cands] == ["CPRS/cprsguium"]
    c = cands[0]
    assert c.suggested_converter == "docling"
    assert c.xref_wraps == 60 and c.bare_markers == 60
    assert "cross-ref wraps explode" in c.reason


def test_near_identical_boilerplate_blocks_cluster_as_one_candidate():
    # §9.6 step 1: boilerplate drifts by a word across docs, so exact-string equality under-counts.
    # Two docs carry one spelling, two carry a near-identical spelling (one word differs). Neither
    # spelling alone reaches min_docs=3, but as a near-dup cluster the union does → ONE candidate.
    a = (
        "How to Use This Manual: read each section in order and consult the index for "
        "specific topics covered throughout this document."
    )
    b = a.replace("consult the index", "consult the appendix")  # one phrase differs
    docs = {
        "app/0": f"# 0\n\n{a}\n\nUnique para zero.\n",
        "app/1": f"# 1\n\n{a}\n\nUnique para one.\n",
        "app/2": f"# 2\n\n{b}\n\nUnique para two.\n",
        "app/3": f"# 3\n\n{b}\n\nUnique para three.\n",
    }
    # exact-only would yield zero boilerplate candidates (each spelling in just 2 docs)
    boiler = [
        c
        for c in dp.mine_recurring_blocks(docs, min_docs=3, near_dup_threshold=0.6)
        if c.registry == "boilerplate"
    ]
    assert len(boiler) == 1
    c = boiler[0]
    assert c.disposition == "REFERENCE"
    assert c.doc_count == 4  # the union of both near-identical spellings
    assert c.sample_doc_ids[:2] == ["app/0", "app/1"]


def test_distinct_boilerplate_blocks_do_not_over_cluster():
    # two genuinely different long blocks must NOT merge — near-dup clustering is precise
    one = "The clinical reminders subsystem evaluates cohort logic and resolution rules per case."
    two = "Order checks fire during order entry to warn about drug interactions and allergies."
    docs = {}
    docs.update({f"a/{i}": one for i in range(3)})
    docs.update({f"b/{i}": two for i in range(3)})
    boiler = [
        c
        for c in dp.mine_recurring_blocks(docs, min_docs=3, near_dup_threshold=0.6)
        if c.registry == "boilerplate"
    ]
    assert len(boiler) == 2  # stayed apart


def test_mine_structures_callout_variants_canonicalize_to_one_convention():
    # the real-corpus trap: the same "Note" callout is styled a dozen ways (**Note:, NOTE:,
    # **Note** :, Note:) — one convention, many stylings → CANONICALIZE to one GFM form
    docs = {
        "a/0": "Intro.\n\n**Note:** save first.\n",
        "a/1": "Intro.\n\nNOTE: save first.\n",
        "a/2": "Intro.\n\n**Note** : save first.\n",
        "a/3": "Intro.\n\nNote: nothing here.\n",
    }
    cands = dp.mine_structures(docs, min_docs=3)
    note = [c for c in cands if c.key == "callout:note"]
    assert len(note) == 1
    c = note[0]
    assert c.convention == "callout"
    assert c.disposition == "CANONICALIZE"
    assert c.canonical_form == "> [!NOTE]"  # GitHub alert syntax
    assert c.doc_count == 4
    assert len(c.variants) >= 3  # several distinct source stylings observed


def test_mine_structures_detects_toc_and_revision_table_shapes():
    body = "# Title\n\n## Table of Contents\n\n- [A](#a)\n\n## Revision History\n\n| v | d |\n"
    docs = {f"d/{i}": body for i in range(3)}
    cands = dp.mine_structures(docs, min_docs=3)
    keys = {c.key for c in cands}
    assert "toc:contents" in keys
    assert "revision-table" in keys
    toc = next(c for c in cands if c.key == "toc:contents")
    assert toc.convention == "toc" and toc.disposition == "CANONICALIZE"


def test_mine_structures_below_threshold_is_not_a_candidate():
    # callout AND heading conventions both in only 2 docs (< min_docs=3) → no candidates
    docs = {
        "a/0": "**Note:** once.\n\n## Contents\n\n## Revision History\n",
        "a/1": "**Note:** twice.\n\n## Contents\n\n## Revision History\n",
    }
    assert dp.mine_structures(docs, min_docs=3) == []


def test_extract_era_buckets_title_page_date_by_decade():
    # the title-page date is the real publication-era signal (DOCX metadata is a 2020-21
    # bulk-re-export artifact; VDL file_date is ~empty) — bucket it by decade
    assert dp.extract_era("# Guide\n\nUser Manual\n\nJanuary 1998\n") == "1990s"
    assert dp.extract_era("# Guide\n\nSeptember 2020\n") == "2020s"
    assert dp.extract_era("# Guide\n\nMarch 2013\n") == "2010s"
    # no parseable date in the head → unknown (never silently dropped)
    assert dp.extract_era("# Guide\n\nno date here at all\n") == "unknown"
    # a date buried deep in the body (past the title-page window) does not count
    assert dp.extract_era("# Guide\n\n" + "x\n" * 80 + "June 1995\n") == "unknown"


def _doc(title_date, sections):
    heads = "\n\n".join(f"## {s}" for s in sections)
    return f"# Title Page\n\n{title_date}\n\n{heads}\n\nbody text here.\n"


def test_mine_templates_clusters_same_scaffold_per_doc_type_era():
    # four user guides (UM), same era, same section scaffold → ONE (doc_type, era) template
    sections = ["Orientation", "Getting Started", "Options", "Troubleshooting", "Glossary"]
    docs = {f"APP/um_{i}": _doc("January 2013", sections) for i in range(4)}
    doc_types = {k: "UM" for k in docs}
    tmpls = dp.mine_templates(docs, doc_types, min_docs=3)
    assert len(tmpls) == 1
    t = tmpls[0]
    assert t.doc_type == "UM" and t.era == "2010s"
    assert t.disposition == "STRIP"
    assert t.doc_count == 4
    assert t.template_id.startswith("UM:2010s:")
    # the retained structural schema captures the ordered sections (§9.8)
    schema_titles = [s.title for s in t.sections]
    assert schema_titles == sections
    assert all(s.required for s in t.sections)  # present in every cluster member → required


def test_mine_templates_separates_doc_types_and_eras():
    sections = ["Orientation", "Getting Started", "Glossary"]
    docs = {}
    docs.update({f"A/um_{i}": _doc("January 2013", sections) for i in range(3)})  # UM 2010s
    docs.update({f"A/ig_{i}": _doc("January 2013", sections) for i in range(3)})  # IG 2010s
    docs.update({f"A/um9_{i}": _doc("January 1998", sections) for i in range(3)})  # UM 1990s
    doc_types = {}
    doc_types.update({f"A/um_{i}": "UM" for i in range(3)})
    doc_types.update({f"A/ig_{i}": "IG" for i in range(3)})
    doc_types.update({f"A/um9_{i}": "UM" for i in range(3)})
    tmpls = dp.mine_templates(docs, doc_types, min_docs=3)
    keys = {(t.doc_type, t.era) for t in tmpls}
    assert keys == {("UM", "2010s"), ("IG", "2010s"), ("UM", "1990s")}


def test_mine_templates_below_threshold_and_unknown_doctype_skipped():
    sections = ["A", "B", "C"]
    docs = {f"X/d_{i}": _doc("January 2013", sections) for i in range(2)}  # only 2 (< min_docs)
    docs["X/notype"] = _doc("January 2013", sections)  # no doc_type → skipped
    doc_types = {f"X/d_{i}": "TM" for i in range(2)}  # X/notype absent
    assert dp.mine_templates(docs, doc_types, min_docs=3) == []


def test_mine_templates_outlier_subcluster_below_threshold_dropped():
    # a (doc_type, era) bucket with enough docs total, but one doc's scaffold is an outlier: the
    # 3-doc consensus cluster emits, the lone outlier sub-cluster is below min_docs and is dropped
    common = ["Orientation", "Getting Started", "Options", "Troubleshooting", "Glossary"]
    outlier = ["Architecture", "Routines", "Files", "Protocols", "Exported Options"]
    docs = {f"A/g_{i}": _doc("June 2016", common) for i in range(3)}
    docs["A/odd"] = _doc("June 2016", outlier)
    doc_types = {k: "UM" for k in docs}
    tmpls = dp.mine_templates(docs, doc_types, min_docs=3, scaffold_threshold=0.6)
    assert len(tmpls) == 1  # only the 3-doc consensus survives; the outlier is dropped
    assert tmpls[0].doc_count == 3


def test_mine_templates_repeated_heading_counted_once_per_doc():
    # a section title repeated within one document must count once toward the consensus (not inflate
    # required/level stats) — exercises the per-doc dedupe in the schema builder
    sections = ["Overview", "Overview", "Glossary"]  # "Overview" appears twice in each doc
    docs = {f"A/d_{i}": _doc("March 2008", sections) for i in range(3)}
    doc_types = {k: "TM" for k in docs}
    (t,) = dp.mine_templates(docs, doc_types, min_docs=3)
    titles = [s.title for s in t.sections]
    assert titles == ["Overview", "Glossary"]  # deduped within each doc
    assert all(s.required for s in t.sections)


def test_curated_structures_registry_is_well_formed():
    # the P2.2a starter set curated from the real corpus must stay consistent with the miner's
    # canonical-form logic (so a curation edit that drifts from the code is caught here)
    import yaml

    from vdocs.config import Settings

    path = Settings().registries / "structures" / "structures.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    conventions = data["conventions"]
    assert conventions, "curated structures starter set is empty"
    keys = {c["key"] for c in conventions}
    assert {"callout:note", "toc:contents", "revision-table"} <= keys
    for c in conventions:
        assert c["disposition"] == "CANONICALIZE"
        assert c["status"] == "approved"
        if c["convention"] == "callout":
            # the curated canonical_form must match what the miner would emit for that label
            assert c["canonical_form"] == dp._callout_canonical_form(c["label"])


def test_curated_templates_registry_is_well_formed():
    # the P2.2b starter set curated from the real corpus: every template carries a non-trivial
    # retained schema (§9.8) keyed by (doc_type, era) with a STRIP disposition
    import yaml

    from vdocs.config import Settings

    path = Settings().registries / "templates" / "templates.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    templates = data["templates"]
    assert templates, "curated templates starter set is empty"
    for t in templates:
        assert t["disposition"] == "STRIP"
        assert t["status"] == "approved"
        assert t["template_id"].startswith(f"{t['doc_type']}:{t['era']}:")
        assert t["sections"], "a curated template must retain a non-trivial schema"
        for s in t["sections"]:
            assert {"section_id", "title", "level", "required", "toc_level"} <= set(s)


def test_mine_glossary_acronyms_filters_stopwords():
    docs = {
        "a/1": "The CPRS and TIU systems; NOTE: see YES/NO and TO use it.",
        "a/2": "CPRS uses TIU for notes; NOTE the OR namespace; YES.",
        "a/3": "TIU and CPRS again; also XWB here; NO and TO.",
    }
    cands = dp.mine_glossary(docs, min_docs=3)
    terms = {c.key for c in cands}
    assert terms == {"CPRS", "TIU"}  # NOTE/YES/NO/TO/OR filtered as stopwords; XWB in <3 docs
    assert all(c.disposition == "PROMOTE" and c.grade == "review" for c in cands)
