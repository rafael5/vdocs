"""1x1 Word text-boxes → fenced code blocks (§6.5).

A 1x1 `<table>` in a VA manual is not tabular data — it is the house convention for showing
**verbatim machine output** in a bordered box: List Manager screens, roll-and-scroll prompts, menu
listings, HL7 messages, MailMan messages, system warnings. 774 of them survive in gold.

Inspecting the population settled two things. There is no prose to protect — an attempt to
classify "terminal capture" vs "other" produced only false negatives (`==[ WRAP ] == [INSERT]
===<NOTE TO PROVIDER >`, `LOCAL TITLE: … DATE OF NOTE:` and `MSH|^~\\&|LA7UI1|500|…` all landed in
"other"). And fencing does more than render correctly: a captured screen line like
`# DRUG QTY # REFS DAYS SUPPLY SUBS` currently parses as a **markdown heading**, so the fence stops
machine output being read as document structure.

The one thing that must not be reused here is `flatten_html`: it collapses whitespace, which is
exactly the column alignment a screen capture is made of.
"""

from vdocs.stages.normalize.tables_pure import text_boxes_to_code_fences


class TestConversion:
    def test_a_one_by_one_box_becomes_a_fence(self) -> None:
        out = text_boxes_to_code_fences("<table><tr><td>Select OPTION: HOME//</td></tr></table>")
        assert out.startswith("```") and out.rstrip().endswith("```")
        assert "Select OPTION: HOME//" in out
        assert "<table" not in out

    def test_paragraph_boundaries_become_line_breaks(self) -> None:
        """530 of the 774 carry one `<p>` per screen line — that is the line structure."""
        html = "<table><tr><td><p>line one</p><p>line two</p><p>line three</p></td></tr></table>"
        body = text_boxes_to_code_fences(html)
        assert [ln for ln in body.split("\n") if ln and not ln.startswith("```")] == [
            "line one",
            "line two",
            "line three",
        ]

    def test_br_also_breaks_lines(self) -> None:
        html = "<table><tr><td>a<br />b</td></tr></table>"
        assert "a\nb" in text_boxes_to_code_fences(html)

    def test_leading_whitespace_is_preserved(self) -> None:
        """Column alignment IS the content of a screen capture — `flatten_html` would destroy it."""
        html = "<table><tr><td><p>NAME     QTY</p><p>ASPIRIN   30</p></td></tr></table>"
        assert "ASPIRIN   30" in text_boxes_to_code_fences(html)

    def test_inline_markup_is_stripped_and_entities_decoded(self) -> None:
        html = "<table><tr><td><p><strong>OI&amp;T MENU</strong></p></td></tr></table>"
        out = text_boxes_to_code_fences(html)
        assert "OI&T MENU" in out and "<strong>" not in out

    def test_a_hash_line_is_protected_from_becoming_a_heading(self) -> None:
        html = "<table><tr><td># DRUG QTY # REFS DAYS SUPPLY</td></tr></table>"
        out = text_boxes_to_code_fences(html)
        fenced = out.split("```")[1]
        assert fenced.strip().startswith("# DRUG")

    def test_backticks_in_the_content_get_a_longer_fence(self) -> None:
        html = "<table><tr><td>use ``` to quote</td></tr></table>"
        out = text_boxes_to_code_fences(html)
        assert out.startswith("````")

    def test_surrounding_prose_is_untouched(self) -> None:
        body = "Before.\n\n<table><tr><td>screen</td></tr></table>\n\nAfter."
        out = text_boxes_to_code_fences(body)
        assert out.startswith("Before.") and out.rstrip().endswith("After.")

    def test_it_is_idempotent(self) -> None:
        once = text_boxes_to_code_fences("<table><tr><td><p>a</p><p>b</p></td></tr></table>")
        assert text_boxes_to_code_fences(once) == once


class TestLeftAlone:
    def _unchanged(self, html: str) -> None:
        assert text_boxes_to_code_fences(html) == html

    def test_a_real_table_is_untouched(self) -> None:
        self._unchanged("<table><tr><td>a</td><td>b</td></tr><tr><td>c</td><td>d</td></tr></table>")

    def test_a_single_row_two_column_table_is_untouched(self) -> None:
        self._unchanged("<table><tr><td>a</td><td>b</td></tr></table>")

    def test_a_box_containing_a_list_is_untouched(self) -> None:
        """A fence would flatten the list into text that only looks like output."""
        self._unchanged("<table><tr><td><ul><li>one</li><li>two</li></ul></td></tr></table>")

    def test_a_box_containing_a_heading_is_untouched(self) -> None:
        self._unchanged('<table><tr><td><h3 id="x">Real Heading</h3></td></tr></table>')

    def test_a_nested_table_is_untouched(self) -> None:
        self._unchanged("<table><tr><td><table><tr><td>x</td></tr></table></td></tr></table>")

    def test_an_empty_box_is_untouched(self) -> None:
        self._unchanged("<table><tr><td>  </td></tr></table>")

    def test_a_body_with_no_tables_is_untouched(self) -> None:
        self._unchanged("Just prose.\n")
