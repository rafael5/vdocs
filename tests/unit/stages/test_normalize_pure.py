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
