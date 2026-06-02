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


def test_count_headings():
    body = "# A\n\ntext\n\n## B\n\n### C\n\nnot # a heading inline\n"
    assert nz_count(body) == 3


def nz_count(body):
    return dp.count_headings(body)


def test_mine_converter_routing_flags_structureless_long_docs():
    long_no_heads = "word " * 500  # 500 words, no headings → Pandoc lost the structure
    docs = {
        "CPRS/or_30_243rn": long_no_heads,
        "CPRS/cprsguium": "# Title\n\n## Section\n\n" + ("word " * 500),  # has headings → fine
        "ADT/short": "word word word",  # short → not flagged even with no headings
    }
    cands = dp.mine_converter_routing(docs, min_words=400)
    assert [c.doc_id for c in cands] == ["CPRS/or_30_243rn"]
    c = cands[0]
    assert c.suggested_converter == "docling" and c.headings == 0 and c.words >= 400
    assert "structure lost" in c.reason


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
