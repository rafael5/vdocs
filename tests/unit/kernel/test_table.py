"""Unit tests for kernel.table — shared HTML/GFM table-cell primitives (§9.2)."""

from vdocs.kernel.table import (
    PIPE_LINE_RE,
    PIPE_SEP_RE,
    flatten_html,
    html_rows,
    md_link_targets,
    pipe_cells,
    strip_md_links,
)


def test_flatten_html_strips_tags_entities_and_whitespace():
    assert flatten_html("<b>Hello&amp;  </b>\n  world") == "Hello& world"


def test_html_rows_extracts_cells_per_row():
    table = "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>"
    assert html_rows(table) == [["A", "B"], ["1", "2"]]


def test_pipe_cells_trims_outer_empties_and_unescapes():
    assert pipe_cells("| a | b\\|c | d |") == ["a", "b|c", "d"]


def test_pipe_cells_leaves_md_links_intact():
    # the base primitive does NOT strip md-links — revision_pure needs them to pull refs
    assert pipe_cells("| [p1](#a) | done |") == ["[p1](#a)", "done"]


def test_strip_md_links_keeps_text_drops_anchor():
    assert strip_md_links("see [page 3](#p3) and [4](#p4)") == "see page 3 and 4"


def test_md_link_targets_returns_anchors():
    assert md_link_targets("[a](#x) text [b](#y)") == ["#x", "#y"]


def test_pipe_line_and_separator_regexes():
    assert PIPE_LINE_RE.match("| a | b |")
    assert PIPE_SEP_RE.match("| --- | :--: |")
    assert not PIPE_SEP_RE.match("| a | b |")
