"""Tests for the shared markdown-structure primitives (kernel/markdown.py, §9.2)."""

from __future__ import annotations

from vdocs.kernel import markdown as md


def test_heading_re_matches_one_to_eleven_hashes():
    for n in range(1, 12):
        m = md.HEADING_RE.match("#" * n + " Title")
        assert m is not None
        assert len(m.group(1)) == n
        assert m.group(2) == "Title"


def test_heading_re_requires_space_and_trims_trailing_ws():
    assert md.HEADING_RE.match("##notitle") is None  # no space after hashes
    assert md.HEADING_RE.match("## Spaced   ").group(2) == "Spaced"


def test_fence_re_matches_backtick_and_tilde_fences():
    assert md.FENCE_RE.match("```python")
    assert md.FENCE_RE.match("   ~~~")
    assert md.FENCE_RE.match("not a fence") is None


def test_multi_blank_collapses_runs():
    assert md.MULTI_BLANK.sub("\n\n", "a\n\n\n\n\nb") == "a\n\nb"


def test_strip_tags_removes_html_tags():
    assert md.strip_tags('<span id="_Toc1">x</span> y') == "x y"
    assert md.strip_tags("no tags") == "no tags"


def test_iter_headings_skips_fenced_code():
    body = "# Real\n\n```\n# fake heading in fence\n```\n\n## Also Real\n"
    got = list(md.iter_headings(body))
    assert [(level, text) for _, level, text in got] == [(1, "Real"), (2, "Also Real")]


def test_iter_headings_skips_generated_contents_marker():
    body = "# Title\n\n## Contents\n\n- [a](#a)\n\n## Section\n"
    texts = [text for _, _, text in md.iter_headings(body)]
    assert "Contents" not in texts
    assert texts == ["Title", "Section"]


def test_iter_headings_recognizes_oversized_headings():
    # upstream (Pandoc) emits >6 `#` from deep DOCX outline levels — all callers must see them
    body = "########### Deep Heading\n\nbody\n"
    got = list(md.iter_headings(body))
    assert got == [(0, 11, "Deep Heading")]


def test_iter_headings_yields_raw_text_with_inline_markup():
    body = '## <span id="_Toc1"></span>Intro\n'
    (_, level, text) = next(iter(md.iter_headings(body)))
    assert level == 2
    assert text == '<span id="_Toc1"></span>Intro'  # raw — bookmark span retained for callers


def test_is_markdown_artifact_matches_structural_only_lines():
    # the dominant boilerplate *noise* is structural markdown, not prose (vdocs-spike §Task 1):
    # nav links, secondary plain-text TOC lines, figure images, table-CSV markers — all entirely
    # structure, with optional `_`/`*`/`↑` wrappers
    assert md.is_markdown_artifact("[↑ Back to Contents](#contents)")
    assert md.is_markdown_artifact("[1 Introduction [1](#introduction)](#introduction)")
    assert md.is_markdown_artifact('<img src="media/image1.png" width="200" />')
    assert md.is_markdown_artifact("_[Table 1 (extracted to CSV)](tables/table-01.csv)_")
    assert md.is_markdown_artifact("  *[Figure 2](assets/fig-02.png)*  ")  # wrapped + indented
    assert md.is_markdown_artifact("![](27daafb0.png)")  # markdown image syntax (CAS asset ref)
    assert md.is_markdown_artifact("![alt caption](assets/a0e627.jpeg)")


def test_is_markdown_artifact_keeps_prose_with_inline_link():
    # a real sentence that merely *contains* an inline link is prose, never an artifact
    assert not md.is_markdown_artifact("See [the install guide](#install) for the procedure.")
    assert not md.is_markdown_artifact("Plain prose paragraph with no links at all.")
    assert not md.is_markdown_artifact("## Introduction")  # a heading is structure, not an artifact
    assert not md.is_markdown_artifact("")  # a blank line is not, by itself, an artifact


def test_is_revision_heading_matches_every_corpus_form():
    # the broadened §6.4 detector: ATX, bold, blockquote-bold, plain, caps, the longer dialects
    for line in (
        "# Revision History",
        "## Revision History",
        "### Template Revision History",
        "**Revision History**",
        "> **Revision History**",
        "> Revision History",
        "Revision History",
        "REVISION HISTORY**",
        "Documentation Revisions",
        "> **Documentation Revisions**",
        "Documentation Revision History",
        "Revisions",
    ):
        assert md.is_revision_heading(line), line


def test_is_revision_heading_rejects_prose_and_other_headings():
    assert not md.is_revision_heading("# Introduction")
    assert not md.is_revision_heading("Table of Contents")
    # a descriptive sentence that merely starts with the words is not a section header
    assert not md.is_revision_heading(
        "Revision History showing date artifact was created or revised, version, description."
    )
    assert not md.is_revision_heading("")


def test_is_legacy_toc_entry_matches_double_bracket_page_numbered_lines():
    assert md.is_legacy_toc_entry("[Introduction [1](#introduction)](#introduction)")
    assert md.is_legacy_toc_entry("  [Routines [8](#routines-1)](#routines-1)  ")
    assert not md.is_legacy_toc_entry("- [Introduction](#introduction)")  # modern Contents entry
    assert not md.is_legacy_toc_entry("See [the guide [1](#g)](#g) now.")  # prose, not anchored
    assert not md.is_legacy_toc_entry("plain prose")


def test_legacy_toc_target_returns_outer_anchor():
    # the outer link is the real target; the inner `[12](#…)` is the page number
    assert md.legacy_toc_target("[Intro [1](#intro)](#intro)") == "#intro"
    assert md.legacy_toc_target("[X [9](#_Toc55)](#_Toc55)") == "#_Toc55"
    assert md.legacy_toc_target("not an entry") is None
