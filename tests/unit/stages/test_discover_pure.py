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


def test_short_recurring_block_is_dead_phrase_delete_and_auto_graded():
    phrase = "This page intentionally left blank."
    docs = {f"d/{i}": f"Intro {i}.\n\n{phrase}\n" for i in range(12)}
    cands = dp.mine_recurring_blocks(docs, min_docs=3, auto_docs=10, phrase_max_len=60)
    (c,) = [c for c in cands if c.registry == "phrases"]
    assert c.disposition == "DELETE"
    assert c.doc_count == 12 and c.grade == "auto"  # 12 ≥ auto_docs


def test_candidates_sorted_by_doc_count_desc():
    common = "Common shared block of reasonable length appearing widely across the corpus."
    rare = "Rarer shared block of reasonable length appearing in fewer documents here."
    docs = {f"c/{i}": common for i in range(6)}
    docs.update({f"r/{i}": f"{common}\n\n{rare}" for i in range(3)})  # rare only in 3
    cands = dp.mine_recurring_blocks(docs, min_docs=3)
    assert [c.doc_count for c in cands] == sorted([c.doc_count for c in cands], reverse=True)


def test_mine_glossary_acronyms():
    docs = {
        "a/1": "The CPRS and TIU systems integrate with HL7.",
        "a/2": "CPRS uses TIU for notes.",
        "a/3": "TIU and CPRS again; also XWB here.",
    }
    cands = dp.mine_glossary(docs, min_docs=3)
    terms = {c.key for c in cands}
    assert terms == {"CPRS", "TIU"}  # XWB/HL7 appear in <3 docs
    assert all(c.disposition == "PROMOTE" and c.grade == "review" for c in cands)
