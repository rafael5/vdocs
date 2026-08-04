"""Pandoc's inline HTML tables → GFM, so gold carries one table dialect (§6.5).

`convert` emits complex tables as raw HTML (Pandoc) or GFM pipe tables (Docling). The big ones are
lifted to `tables/*.csv` either way, but the rest stay inline in whichever dialect they arrived in —
so 60% of gold documents carry `<table>` markup that Docling-converted documents never have.

That is not only a rendering difference. **5,386 chunks — 9.3% of the search index — carry HTML tag
soup into FTS5**: `colgroup`, `col style="width: 100%"`, `tbody`, `tr class="odd"` are all indexed
as tokens. Converting to GFM removes the noise and makes both converters land on one shape.

Measured on the 8,086 inline tables left in gold: **4,055 (50.1%) are cleanly convertible**, and the
rest genuinely are not — 1,056 use colspan/rowspan, 2,023 hold headings or lists inside cells, 774
are 1x1 Word text-boxes wrapping terminal screen captures, 134 are nested. GFM cannot express any of
those, so they are left as HTML rather than silently flattened into something that reads like data
but isn't.
"""

from vdocs.stages.normalize.tables_pure import html_tables_to_gfm

SIMPLE = (
    "<table><thead><tr><th>API</th><th>Description</th></tr></thead>"
    "<tbody><tr><td>DGPFAPIU</td><td>Support utilities</td></tr></tbody></table>"
)


class TestConversion:
    def test_a_rectangular_table_becomes_gfm(self) -> None:
        out = html_tables_to_gfm(SIMPLE)
        assert "<table" not in out
        assert "| API | Description |" in out
        assert "| DGPFAPIU | Support utilities |" in out

    def test_it_emits_the_gfm_separator_row(self) -> None:
        lines = [ln for ln in html_tables_to_gfm(SIMPLE).split("\n") if ln.strip()]
        assert lines[1].replace(" ", "") == "|---|---|"

    def test_the_noise_attributes_are_gone(self) -> None:
        """`colgroup`/`col style`/`tr class` were being indexed as search tokens."""
        html = (
            '<table><colgroup><col style="width: 50%" /></colgroup>'
            '<tbody><tr class="odd"><td>a</td><td>b</td></tr>'
            '<tr class="even"><td>c</td><td>d</td></tr></tbody></table>'
        )
        out = html_tables_to_gfm(html)
        for noise in ("colgroup", "col style", "class=", "tbody", "<tr"):
            assert noise not in out

    def test_a_pipe_inside_a_cell_is_escaped(self) -> None:
        html = "<table><tr><td>a|b</td><td>c</td></tr><tr><td>d</td><td>e</td></tr></table>"
        out = html_tables_to_gfm(html)
        assert r"a\|b" in out

    def test_entities_are_decoded_and_whitespace_collapsed(self) -> None:
        html = "<table><tr><td>OI&amp;T</td><td>x</td></tr><tr><td>y</td><td>z</td></tr></table>"
        assert "OI&T" in html_tables_to_gfm(html)

    def test_surrounding_prose_is_untouched(self) -> None:
        body = f"Before.\n\n{SIMPLE}\n\nAfter."
        out = html_tables_to_gfm(body)
        assert out.startswith("Before.") and out.rstrip().endswith("After.")

    def test_it_is_idempotent(self) -> None:
        once = html_tables_to_gfm(SIMPLE)
        assert html_tables_to_gfm(once) == once


class TestLeftAsHtml:
    """GFM cannot express these. Flattening them would produce something that reads like a table
    and misrepresents the source — worse than leaving markup a renderer still handles."""

    def _unchanged(self, html: str) -> None:
        assert html_tables_to_gfm(html) == html

    def test_colspan_is_left_alone(self) -> None:
        self._unchanged(
            '<table><tr><td colspan="2">wide</td></tr><tr><td>a</td><td>b</td></tr></table>'
        )

    def test_rowspan_is_left_alone(self) -> None:
        self._unchanged(
            '<table><tr><td rowspan="2">tall</td><td>a</td></tr><tr><td>b</td></tr></table>'
        )

    def test_a_heading_inside_a_cell_is_left_alone(self) -> None:
        self._unchanged(
            '<table><tr><td><h3 id="x">Error</h3></td><td>b</td></tr>'
            "<tr><td>c</td><td>d</td></tr></table>"
        )

    def test_a_list_inside_a_cell_is_left_alone(self) -> None:
        self._unchanged(
            "<table><tr><td><ul><li>one</li></ul></td><td>b</td></tr>"
            "<tr><td>c</td><td>d</td></tr></table>"
        )

    def test_a_one_by_one_table_is_left_alone(self) -> None:
        """774 of these — a Word text-box wrapping a terminal screen capture, not tabular data.
        Rendering it as a one-cell table would assert a structure the source never had."""
        self._unchanged(
            "<table><tr><td>Select OPTION: HOME// LAT RIGHT MARGIN: 80//</td></tr></table>"
        )

    def test_a_nested_table_is_left_alone(self) -> None:
        self._unchanged(
            "<table><tr><td><table><tr><td>x</td></tr></table></td><td>b</td></tr></table>"
        )

    def test_a_ragged_table_is_left_alone(self) -> None:
        self._unchanged("<table><tr><td>a</td><td>b</td></tr><tr><td>c</td></tr></table>")

    def test_an_empty_table_is_left_alone(self) -> None:
        self._unchanged("<table><tbody></tbody></table>")

    def test_a_body_with_no_tables_is_returned_unchanged(self) -> None:
        self._unchanged("Just prose.\n\nAnd more.\n")
