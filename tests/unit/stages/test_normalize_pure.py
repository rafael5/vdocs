"""Unit tests for normalize pure F-steps — slugs, TOC, artifact/phrase subtraction (§6.7, §9.6)."""

from __future__ import annotations

from vdocs.stages.normalize import normalize_pure as nz


def test_github_slug_lowercases_drops_punct_and_disambiguates():
    seen: dict[str, int] = {}
    assert nz.github_slug("Introduction", seen) == "introduction"
    assert nz.github_slug("Back-Out Procedure", seen) == "back-out-procedure"
    assert nz.github_slug("Introduction", seen) == "introduction-1"  # duplicate in doc order
    assert nz.github_slug("Introduction", seen) == "introduction-2"


def test_parse_headings_skips_code_fences_and_contents():
    body = "# Title\n\n## Contents\n\n```\n# not a heading\n```\n\n## Real Section\n"
    heads = nz.parse_headings(body)
    assert [(h.level, h.text) for h in heads] == [(1, "Title"), (2, "Real Section")]


def test_recover_headings_promotes_toc_bookmark_paragraphs():
    # Pandoc flattened these — the original Word TOC linked to the _Toc bookmarks (§6.7)
    body = (
        '<span id="_Toc221409085" class="anchor"></span>Revision History\n\n'
        "Some intro text.\n\n"
        '<span id="_Toc221409090" class="anchor"></span>**<span class="smallcaps">Known '
        "Issues</span>**\n\n"
        "details\n"
    )
    out = nz.recover_headings(body)
    assert "## Revision History" in out
    assert "## Known Issues" in out  # inline markup stripped
    assert "Some intro text." in out and "details" in out


def test_recover_headings_skips_docs_that_already_have_headings():
    body = '# Real Heading\n\n<span id="_Toc1" class="anchor"></span>Not Promoted\n'
    # the doc already has a markdown heading tree → leave its _Toc paragraphs alone
    assert nz.recover_headings(body) == body


def test_recover_headings_then_toc_gives_structureless_doc_a_toc():
    body = (
        '<span id="_Toc1" class="anchor"></span>Introduction\n\nbody\n\n'
        '<span id="_Toc2" class="anchor"></span>Installation\n\nsteps\n'
    )
    out, _ = nz.normalize_body(body, frozenset())
    assert "## Contents" in out
    assert "- [Introduction](#introduction)" in out
    assert "- [Installation](#installation)" in out


def test_strip_artifacts_removes_empty_comments_and_collapses_blanks():
    body = "Para one.\n\n<!-- -->\n\n\n\nPara two.\n"
    out = nz.strip_artifacts(body)
    assert "<!-- -->" not in out
    assert "\n\n\n" not in out
    assert "Para one." in out and "Para two." in out


def test_subtract_phrases_deletes_matching_blocks_only():
    body = "Real content.\n\nThis page intentionally left blank.\n\nMore content.\n"
    out = nz.subtract_phrases(body, frozenset({"This page intentionally left blank."}))
    assert "intentionally left blank" not in out
    assert "Real content." in out and "More content." in out
    # no-op when the phrase set is empty
    assert nz.subtract_phrases(body, frozenset()) == body


def test_subtract_phrases_matches_emphasis_wrapped_and_extended_furniture():
    # the real corpus wraps blank-page furniture in emphasis + adds a trailing clause:
    # `*This page intentionally left blank for double-sided printing.*` — a curated long phrase
    # (≥4 words) prefix-matches the marker-stripped block so the variant is still deleted
    body = "Real.\n\n*This page intentionally left blank for double-sided printing.*\n\nMore.\n"
    out = nz.subtract_phrases(body, frozenset({"This page intentionally left blank"}))
    assert "intentionally left blank" not in out
    assert "Real." in out and "More." in out


def test_subtract_phrases_short_phrase_stays_exact_to_avoid_false_deletes():
    # a short (<4-word) phrase must NOT prefix-match real prose that merely begins with it
    body = "End of document processing starts in the morning.\n"
    assert nz.subtract_phrases(body, frozenset({"End of document"})) == body


def test_effective_toc_depth_includes_top_level_when_there_is_no_single_title():
    # a lone leading H1 is the document title → H2–H3 (the default)
    single = nz.parse_headings("# Title\n\n## A\n\n### B\n")
    assert nz.effective_toc_depth(single) == (2, 3)
    # many H1s (sections, not a title) → include H1 so the doc gets a Contents
    many = nz.parse_headings("# One\n\nx\n\n# Two\n\ny\n\n# Three\n\nz\n")
    assert nz.effective_toc_depth(many) == (1, 2)
    assert nz.effective_toc_depth([]) == (2, 3)  # no headings → default


def test_normalize_body_generates_contents_for_multi_h1_doc():
    body = "# Section One\n\nalpha\n\n# Section Two\n\nbeta\n\n# Section Three\n\ngamma\n"
    out, _ = nz.normalize_body(body, frozenset())
    assert out.count("## Contents") == 1  # a Contents IS generated for the all-H1 doc
    assert "- [Section One](#section-one)" in out
    assert "- [Section Two](#section-two)" in out


def test_regenerate_toc_builds_contents_with_anchor_links():
    body = "# Install Guide\n\nIntro.\n\n## Setup\n\nsteps\n\n### Details\n\nx\n"
    out = nz.regenerate_toc(body)
    assert "## Contents" in out
    assert "- [Setup](#setup)" in out
    assert "  - [Details](#details)" in out  # nested one level under Setup
    # the TOC lands after the H1 title, before the first body content
    assert out.index("## Contents") > out.index("# Install Guide")
    assert out.index("## Contents") < out.index("Intro.")


def test_regenerate_toc_is_idempotent():
    body = "# T\n\n## A\n\nbody\n\n## B\n\nbody\n"
    once = nz.regenerate_toc(body)
    assert nz.regenerate_toc(once) == once  # stale TOC stripped + rebuilt identically


def test_regenerate_toc_noop_when_no_headings():
    body = "Just a paragraph with no headings at all.\n"
    assert nz.regenerate_toc(body) == body  # nothing to build a TOC from


def test_strip_existing_toc_removes_prior_contents_block():
    body = "# T\n\n## Contents\n\n- [A](#a)\n  - [B](#b)\n\n## A\n\nreal\n"
    out = nz.strip_existing_toc(body)
    assert "## Contents" not in out and "[A](#a)" not in out
    assert "## A" in out and "real" in out  # real section kept


def test_build_toc_empty_for_no_headings():
    assert nz.build_toc([]) == ""


def test_regenerate_toc_places_after_title_despite_leading_blanks():
    body = "\n\n# Title\n\n## Section\n\nbody\n"  # leading blank lines before the H1
    out = nz.regenerate_toc(body)
    assert out.index("# Title") < out.index("## Contents") < out.index("## Section")


def test_normalize_body_applies_all_steps_in_order():
    body = (
        "# Guide\n\n<!-- -->\n\n## Overview\n\nThis page intentionally left blank.\n\nReal text.\n"
    )
    out, _ = nz.normalize_body(body, frozenset({"This page intentionally left blank."}))
    assert "<!-- -->" not in out
    assert "intentionally left blank" not in out
    assert "## Contents" in out and "- [Overview](#overview)" in out
    assert "Real text." in out


def test_infer_heading_levels_compacts_skipped_levels():
    # H1 → H4 skips two levels; the gap is compacted so the tree nests one level at a time
    body = "# Title\n\ntext\n\n#### Deep\n\nmore\n"
    out = nz.infer_heading_levels(body)
    assert "## Deep" in out and "#### Deep" not in out  # H4 pulled up to H2


def test_infer_heading_levels_builds_consistent_tree():
    body = "# A\n\n### B\n\n#### C\n\n### D\n"
    out = nz.infer_heading_levels(body)
    levels = [len(ln.split(" ")[0]) for ln in out.splitlines() if ln.startswith("#")]
    assert levels == [1, 2, 3, 2]  # B,D → H2 (children of A); C → H3 (child of B)


def test_infer_heading_levels_preserves_h2_rooted_doc():
    # a doc whose shallowest heading is H2 (no H1 title) keeps that baseline — never fabricate H1
    body = "## A\n\n### B\n\n## C\n"
    out = nz.infer_heading_levels(body)
    assert out == body  # already gap-free at base H2 → unchanged


def test_infer_heading_levels_is_idempotent():
    body = "# A\n\n#### B\n\n## C\n\n##### D\n"
    once = nz.infer_heading_levels(body)
    assert nz.infer_heading_levels(once) == once


def test_infer_heading_levels_ignores_code_fences():
    body = "# A\n\n```\n#### not a heading\n```\n\n### Real\n"
    out = nz.infer_heading_levels(body)
    assert "#### not a heading" in out  # fenced content untouched
    assert "## Real" in out  # the real H3 compacted to H2


def test_infer_heading_levels_handles_oversized_hash_headings():
    # upstream (Pandoc/convert) can emit >6 `#` from deep DOCX outline levels; infer must
    # recognize them and collapse into a gap-free ≤6 tree, not leave invalid >6 GFM behind
    body = "## A\n\n######### B\n\n############# C\n"
    out = nz.infer_heading_levels(body)
    levels = [len(ln.split(" ")[0]) for ln in out.splitlines() if ln.startswith("#")]
    assert levels == [2, 3, 4]  # B → child of A (H3); C → child of B (H4)
    assert "#######" not in out  # every oversized prefix collapsed


def test_infer_heading_levels_leaves_generated_contents_heading():
    # the generated `## Contents` TOC marker must be skipped, else re-leveling it breaks
    # normalize_body self-idempotency (it is regenerated each run, not a content section)
    body = "## Contents\n\n- [Setup](#setup)\n\n## Setup\n\n### Detail\n"
    out = nz.infer_heading_levels(body)
    assert "## Contents" in out  # untouched (not promoted to # Contents)


def test_normalize_body_is_self_idempotent_with_generated_toc():
    body = "# Guide\n\n## Setup\n\n#### Deep detail\n\nbody text.\n"
    once, _ = nz.normalize_body(body, frozenset())
    assert "## Contents" in once  # a TOC was generated
    twice, _ = nz.normalize_body(once, frozenset())
    assert twice == once  # second pass is a fixed point


_BP = (
    nz.Boilerplate(
        id="bp-1234",
        label="This document describes the DIBR plan",
        key=nz.block_key("This document describes the DIBR plan for VA Enterprise products."),
    ),
)


def test_subtract_boilerplate_replaces_block_with_reference():
    body = (
        "# Guide\n\nIntro paragraph.\n\n"
        "This document describes the DIBR plan for VA Enterprise products.\n\n"
        "Unique content here.\n"
    )
    out = nz.subtract_boilerplate(body, _BP)
    assert "This document describes the DIBR plan for VA Enterprise" not in out  # text removed
    assert "(_shared/boilerplate/bp-1234.md)" in out  # replaced by a REFERENCE link
    assert "Intro paragraph." in out and "Unique content here." in out  # others untouched


def test_subtract_boilerplate_matches_modulo_whitespace_and_case():
    body = "Intro.\n\nthis  document   describes the DIBR PLAN for va enterprise products.\n"
    out = nz.subtract_boilerplate(body, _BP)
    assert "(_shared/boilerplate/bp-1234.md)" in out  # block_key match ignores spacing/case


def test_subtract_boilerplate_noop_when_no_registry_or_no_match():
    body = "# Guide\n\nNothing boilerplate here.\n"
    assert nz.subtract_boilerplate(body, ()) == body  # empty registry → untouched
    assert nz.subtract_boilerplate(body, _BP) == body  # no matching block → untouched


def test_subtract_boilerplate_is_idempotent():
    body = "Intro.\n\nThis document describes the DIBR plan for VA Enterprise products.\n"
    once = nz.subtract_boilerplate(body, _BP)
    assert nz.subtract_boilerplate(once, _BP) == once  # the reference is not a registered block


_TOC_TITLES = frozenset({"table of contents", "contents"})


def test_strip_legacy_toc_removes_heading_and_entries_until_next_heading():
    # the source's own text TOC (heading + page-numbered entries) must leave the body (§6.7/§9.6)
    body = (
        "# Manual\n\n## Table of Contents\n\n"
        "Introduction .......... 1\nInstallation .......... 4\n\n"
        "## Introduction\n\nreal text\n"
    )
    out = nz.strip_legacy_toc(body, _TOC_TITLES)
    assert "Table of Contents" not in out
    assert ".........." not in out  # the legacy entries went with it
    assert "## Introduction" in out and "real text" in out  # the real section stayed


def test_strip_legacy_toc_matches_case_insensitively_at_h1_to_h3():
    body = "# CONTENTS\n\nA 1\nB 2\n\n## Body\n\nx\n"
    out = nz.strip_legacy_toc(body, _TOC_TITLES)
    assert "CONTENTS" not in out and "A 1" not in out
    assert "## Body" in out and "x" in out


def test_strip_legacy_toc_strips_oversized_hash_toc_heading():
    # real corpus (CPRS cprsguium): the legacy TOC heading arrives as `########### Table of
    # Contents` (upstream emitted >6 `#`); strip must still recognize it and drop its
    # tab-separated page-number entries before the derived `## Contents` is generated
    body = (
        "# Manual\n\n########### Table of Contents\n\n"
        "Introduction\t1\nInstallation\t4\n\n"
        "## Introduction\n\nreal text\n"
    )
    out = nz.strip_legacy_toc(body, _TOC_TITLES)
    assert "Table of Contents" not in out
    assert "Introduction\t1" not in out  # the tab/page-number entries went with it
    assert "## Introduction" in out and "real text" in out


def test_normalize_body_strips_oversized_legacy_toc():
    # end-to-end on the real cprsguium shape: an >6-hash TOC heading + tab/page-number entries
    body = (
        "# CPRS User Manual\n\n########### Table of Contents\n\n"
        "Introduction\t1\nSelecting a Patient\t6\n\n"
        "## Introduction\n\nintro text\n\n## Selecting a Patient\n\nbody\n"
    )
    out, _ = nz.normalize_body(body, frozenset(), toc_titles=_TOC_TITLES)
    assert "Table of Contents" not in out
    assert "\t1" not in out and "\t6" not in out  # legacy page-numbered entries gone
    assert out.count("## Contents") == 1
    assert "- [Introduction](#introduction)" in out


def test_strip_legacy_toc_noop_without_titles_or_match():
    body = "# Manual\n\n## Overview\n\ntext\n"
    assert nz.strip_legacy_toc(body, frozenset()) == body  # registry empty → no-op
    assert nz.strip_legacy_toc(body, _TOC_TITLES) == body  # no contents heading → unchanged


def test_strip_legacy_toc_leaves_unrelated_headings():
    # a non-TOC heading that merely contains the word is not a contents section
    body = "# Manual\n\n## Table of Contents Overview\n\nkept\n"
    assert nz.strip_legacy_toc(body, _TOC_TITLES) == body  # exact text match only


def test_strip_legacy_toc_removes_plain_text_header_and_double_bracket_entries():
    # the real corpus shape (§6.7): a *plain-text* `Table of Contents` line (not an ATX heading)
    # followed by the page-numbered `[Title [n](#anchor)](#anchor)` entry block
    body = (
        "Department of Veterans Affairs\n\n"
        "Table of Contents\n\n"
        "[Introduction [1](#introduction)](#introduction)\n\n"
        "[Routines [8](#routines-1)](#routines-1)\n\n"
        "# Introduction\n\nreal text\n\n## Routines\n\nx\n\n## Routines\n\ny\n"
    )
    out = nz.strip_legacy_toc(body, _TOC_TITLES)
    assert "Table of Contents" not in out
    assert "[Introduction [1]" not in out and "[Routines [8]" not in out  # entries gone
    assert "# Introduction" in out and "real text" in out  # real content kept


def test_strip_legacy_toc_strips_toc_heading_at_any_level():
    # the old `max_level=3` gate missed an H4–H6 `Table of Contents` heading (VPFS shape); an exact
    # curated-title match is legacy at any level
    body = "# Doc\n\n##### Table of Contents\n\nIntro [1](#intro)\n\n## Real\n\nkept\n"
    out = nz.strip_legacy_toc(body, _TOC_TITLES)
    assert "Table of Contents" not in out
    assert "## Real" in out and "kept" in out


def test_strip_legacy_toc_drops_bare_header_with_degraded_entries():
    # a legacy `Table of Contents` whose entries degraded to plain text / page-numbered headings
    # (no `(#anchor)` links left): the stale header label is dropped on its own
    body = "Cover\n\nTable of Contents\n\n# Introduction 1\n\nbody text\n"
    out = nz.strip_legacy_toc(body, _TOC_TITLES)
    assert "Table of Contents" not in out
    assert "# Introduction 1" in out and "body text" in out  # real (page-numbered) heading kept


def test_strip_legacy_toc_drops_blockquote_and_bullet_prefixed_entries():
    body = (
        "Contents\n\n"
        "> [3.2 Site Info [4](#site-info)](#site-info)\n\n"
        "  - [[2237](#_bookmark10)](#2237_bookmark10)\n\n"
        "# Real\n\nkept\n"
    )
    out = nz.strip_legacy_toc(body, _TOC_TITLES)
    assert "site-info" not in out and "2237" not in out  # prefixed legacy entries dropped
    assert "# Real" in out and "kept" in out


def test_strip_legacy_toc_handles_list_of_figures_and_bold_atx_header():
    # the corpus also carries `List of Figures`/`List of Tables` plain-text TOCs and bold-markup
    # ATX headers (`# **Table of Contents**`) — both must be recognised and dropped (§6.7)
    titles = frozenset({"table of contents", "list of figures"})
    body = (
        "# **Table of Contents**\n\n"
        "[Intro [1](#intro)](#intro)\n\n"
        "List of Figures\n\n"
        "[Figure 1 [5](#_Toc1)](#_Toc1)\n\n"
        "# Intro\n\nreal\n"
    )
    out = nz.strip_legacy_toc(body, titles)
    assert "Table of Contents" not in out and "List of Figures" not in out
    assert "[Intro [1]" not in out and "[Figure 1 [5]" not in out
    assert "# Intro" in out and "real" in out


def test_strip_legacy_toc_removes_orphaned_double_bracket_entries():
    # a figure-list / header-less block whose header text isn't curated still loses its unambiguous
    # double-bracket page-numbered entries (only ever legacy nav) — even with an empty titles set
    body = (
        "Some intro paragraph.\n\n"
        "[Figure 1 - Foo [5](#_Toc1)](#_Toc1)\n\n"
        "[Figure 2 - Bar [6](#_Toc2)](#_Toc2)\n\n"
        "## Real Section\n\nkept\n"
    )
    out = nz.strip_legacy_toc(body, frozenset())  # no curated titles at all
    assert "[Figure 1 - Foo" not in out and "[Figure 2 - Bar" not in out
    assert "Some intro paragraph." in out and "## Real Section" in out and "kept" in out


def test_legacy_toc_targets_collects_outer_anchors():
    body = (
        "Table of Contents\n\n"
        "[Introduction [1](#introduction)](#introduction)\n\n"
        "[Lost Section [9](#_Toc55)](#_Toc55)\n\n"
        "# Introduction\n\nx\n"
    )
    assert nz.legacy_toc_targets(body, _TOC_TITLES) == ["#introduction", "#_Toc55"]


def test_correlate_legacy_toc_flags_unresolved_entries():
    # role-1 cross-check: a target with no derived-heading counterpart is unresolved (Word bookmark
    # that never resolved, or a heading lost in conversion) — a fidelity flag, not a silent loss
    headings = nz.parse_headings("# Introduction\n\nx\n")  # only `introduction` exists
    unresolved = nz.correlate_legacy_toc(["#introduction", "#_Toc55", "#missing"], headings)
    assert unresolved == ["#_Toc55", "#missing"]  # #introduction resolves; the others don't


def test_normalize_body_strips_plain_text_legacy_toc_and_records_unresolved():
    body = (
        "Table of Contents\n\n"
        "[Overview [1](#overview)](#overview)\n\n"
        "[Ghost [9](#_Toc99)](#_Toc99)\n\n"
        "# Introduction\n\nreal text\n\n## Overview\n\ndetails\n"
    )
    out, amap = nz.normalize_body(body, frozenset(), toc_titles=_TOC_TITLES)
    assert "Table of Contents" not in out and "#_Toc99" not in out  # legacy TOC dropped
    assert out.count("## Contents") == 1  # exactly one derived TOC
    assert "- [Overview](#overview)" in out
    assert amap.toc_unresolved == ["#_Toc99"]  # the unresolved bookmark is flagged, not lost


def test_normalize_body_strips_legacy_toc_then_derives_single_contents():
    body = (
        "# Install Guide\n\n## Table of Contents\n\n"
        "Setup .......... 2\nDetails .......... 5\n\n"
        "## Setup\n\nsteps\n\n### Details\n\nx\n"
    )
    out, _ = nz.normalize_body(body, frozenset(), toc_titles=_TOC_TITLES)
    assert ".........." not in out  # legacy text TOC gone
    assert out.count("## Contents") == 1  # exactly one derived TOC, no duplicate
    assert "Table of Contents" not in out  # legacy heading not carried as a TOC entry either
    assert "- [Setup](#setup)" in out and "  - [Details](#details)" in out


def test_curated_structures_registry_toc_is_well_formed():
    # the curated structures registry must carry the `match` variants normalize keys on (§9.6)
    import yaml

    from vdocs.config import Settings

    path = Settings().registries / "structures" / "structures.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    toc = next(c for c in data["conventions"] if c["key"] == "toc:contents")
    assert toc["disposition"] == "CANONICALIZE" and toc["status"] == "approved"
    assert "contents" in {m.lower() for m in toc["match"]}  # the consumer's match list


def test_curated_boilerplate_registry_is_well_formed():
    # the P1.b starter set curated from the real corpus: each `key` must equal block_key(text)
    import yaml

    from vdocs.config import Settings

    path = Settings().registries / "boilerplate" / "boilerplate.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    entries = data["boilerplate"]
    assert entries, "curated boilerplate starter set is empty"
    for e in entries:
        assert e["status"] == "approved"
        assert e["key"] == nz.block_key(e["text"])  # the match key matches its canonical text
        assert e["id"].startswith("bp-")
