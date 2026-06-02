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
