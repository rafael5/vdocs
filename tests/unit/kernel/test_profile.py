"""Per-document dimensions — what a body is made of (§6.4).

Two jobs, both currently unserved. **Measuring what the pipeline does to a document**:
`capture.yaml` already records a before/after for words (`retention`) and nothing else, so a stage
that halves a document's tables or drops its code blocks changes no recorded number. And **telling
search what a document is**: `documents` carries `word_count`/`section_count`/`image_count`, so
"this one is full of code examples" or "this one is mostly tables" is not expressible.

Counted from the markdown body alone, so the same function can be run at any stage boundary and the
two readings compared. Sidecar-derived counts (CSV tables, TOC entries) belong to the stage that
writes them, not here.
"""

from vdocs.kernel.profile import document_profile


class TestCounts:
    def test_words_and_headings(self) -> None:
        """`words` counts whitespace-separated tokens including markdown syntax — deliberately the
        same counting `retention` already uses, so the two numbers are comparable."""
        p = document_profile("# Title\n\nsome words here\n\n## Section\n\nmore text\n")
        assert p.words == 9  # incl. the two heading markers
        assert p.headings == 2

    def test_heading_depth_is_the_deepest_level_used(self) -> None:
        p = document_profile("# A\n\n## B\n\n#### D\n")
        assert p.heading_depth == 4
        assert p.heading_levels == 3

    def test_fenced_code_blocks_are_counted(self) -> None:
        body = "text\n\n```\nscreen output\n```\n\nmore\n\n```\nsecond\n```\n"
        p = document_profile(body)
        assert p.code_blocks == 2
        assert p.code_lines == 2

    def test_a_tilde_fence_counts_too(self) -> None:
        assert document_profile("~~~\nx\n~~~\n").code_blocks == 1

    def test_gfm_tables_are_counted_by_table_not_by_row(self) -> None:
        body = "| a | b |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n\ntext\n\n| c |\n|---|\n| 5 |\n"
        p = document_profile(body)
        assert p.tables_gfm == 2

    def test_residual_html_tables_are_counted_separately(self) -> None:
        """These are the ones GFM cannot express — a quality signal worth keeping visible."""
        p = document_profile("<table><tr><td>a</td></tr></table>\n\n| a |\n|---|\n| 1 |\n")
        assert p.tables_html == 1 and p.tables_gfm == 1

    def test_images_count_both_markdown_and_html_forms(self) -> None:
        p = document_profile('![alt](abc.png)\n\n<img src="def.png" />\n')
        assert p.images == 2

    def test_internal_links_are_counted(self) -> None:
        p = document_profile("see [Intro](#intro) and [Other](#other) and [ext](https://x)\n")
        assert p.internal_links == 2


class TestEdges:
    def test_an_empty_body_profiles_to_zeroes(self) -> None:
        p = document_profile("")
        assert p.words == 0 and p.headings == 0 and p.code_blocks == 0

    def test_a_heading_inside_a_fence_is_not_a_heading(self) -> None:
        p = document_profile("```\n# not a heading\n```\n")
        assert p.headings == 0 and p.code_blocks == 1

    def test_a_table_row_inside_a_fence_is_not_a_table(self) -> None:
        p = document_profile("```\n| not | a table |\n|---|---|\n```\n")
        assert p.tables_gfm == 0

    def test_an_unclosed_fence_does_not_swallow_the_document(self) -> None:
        p = document_profile("```\nopen\n\n# Heading\n")
        assert p.code_blocks == 1

    def test_it_is_a_pure_function_of_the_body(self) -> None:
        body = "# A\n\n```\nx\n```\n"
        assert document_profile(body) == document_profile(body)


class TestAsDict:
    def test_it_serialises_to_plain_values_for_the_sidecar(self) -> None:
        d = document_profile("# A\n\nword\n").as_dict()
        assert isinstance(d, dict)
        assert d["words"] == 3 and d["headings"] == 1
        assert all(isinstance(v, int) for v in d.values())


class TestCodeSignal:
    """`code_blocks` alone says "no code" about the most code-heavy document in the corpus.

    The FileMan Developer's Guide carries 2,281 M-code references and **zero** fenced blocks — VA
    manuals put code in prose and tables, not in fences. A search consumer asking "does this
    document contain code?" needs the reference count, or it gets the wrong answer on exactly the
    documents it most wants to find.
    """

    def test_routine_references_are_counted(self) -> None:
        p = document_profile("Call ^DIC and ^%ZTLOAD to load.\n")
        assert p.code_refs == 2

    def test_extrinsic_function_calls_are_counted(self) -> None:
        assert document_profile("Use $$GET^DIQ(...) here.\n").code_refs >= 1

    def test_prose_with_no_code_scores_zero(self) -> None:
        assert document_profile("This manual describes the options.\n").code_refs == 0

    def test_a_caret_in_ordinary_prose_is_not_code(self) -> None:
        assert document_profile("see section 3^ or the note\n").code_refs == 0

    def test_code_refs_are_counted_inside_fences_too(self) -> None:
        """A fenced screen capture full of routine calls is still code."""
        assert document_profile("```\nD EN^DIB\n```\n").code_refs >= 1
