"""VO.8e — re-create the section headings Docling missed, using the document's own TOC.

Docling's heading detection is visual: it reads type size and weight off the page, so a section
whose heading was set in body-text style is emitted as an ordinary paragraph. The document's table
of contents lists that section by name — so once the TOC is captured (VO.8b) we have an index of
every section the author declared, and can promote the paragraphs that match.

Measured across the 19 PDF-only documents: **815 sections** recoverable on top of 5,400 detected
headings, concentrated in the two Kernel binders (478 and 319).

This is the PDF counterpart of `recover_headings`, which does the same job for DOCX using the Word
`_Toc` bookmarks Pandoc leaves behind. The evidence is different; the principle is identical.

Deliberately conservative: a full-line exact match, appearing **exactly once**, not already a
heading. A title that occurs twice is ambiguous — promoting the wrong one would invent structure.
"""

from vdocs.stages.normalize.normalize_pure import recover_headings_from_toc


def heads(body: str) -> list[str]:
    return [ln for ln in body.split("\n") if ln.startswith("#")]


class TestRecovery:
    def test_a_paragraph_named_in_the_toc_becomes_a_heading(self) -> None:
        body = "## Intro\n\nInstallation Steps\n\nSome prose.\n"
        out = recover_headings_from_toc(body, ["Intro", "Installation Steps"])
        assert "## Installation Steps" in out
        assert "Some prose." in out

    def test_the_promoted_heading_takes_the_document_root_level(self) -> None:
        """Depth is `level_headings_from_numbering`'s job, which runs next — recovery only has to
        make the section visible as a heading."""
        body = "### Intro\n\nInstallation Steps\n"
        out = recover_headings_from_toc(body, ["Installation Steps"])
        assert "### Installation Steps" in out

    def test_a_numbered_recovered_heading_is_left_for_the_depth_step(self) -> None:
        body = "## A\n\n2.1.3 Deep Section\n"
        out = recover_headings_from_toc(body, ["2.1.3 Deep Section"])
        assert "## 2.1.3 Deep Section" in out

    def test_matching_ignores_case_punctuation_and_emphasis(self) -> None:
        body = "## A\n\n**Installation Steps:**\n"
        out = recover_headings_from_toc(body, ["installation steps"])
        assert any("Installation Steps" in h for h in heads(out))


class TestGuards:
    def test_an_ambiguous_title_is_never_promoted(self) -> None:
        """Two candidates means we cannot know which is the section — inventing structure is worse
        than missing it."""
        body = "## A\n\nOverview\n\nsome prose\n\nOverview\n"
        assert recover_headings_from_toc(body, ["Overview"]) == body

    def test_a_title_already_a_heading_is_untouched(self) -> None:
        body = "## Installation Steps\n\nprose\n"
        assert recover_headings_from_toc(body, ["Installation Steps"]) == body

    def test_a_table_row_is_never_promoted(self) -> None:
        body = "## A\n\n| Installation Steps | 4 |\n"
        assert recover_headings_from_toc(body, ["Installation Steps"]) == body

    def test_a_list_item_is_never_promoted(self) -> None:
        body = "## A\n\n- Installation Steps\n"
        assert recover_headings_from_toc(body, ["Installation Steps"]) == body

    def test_a_line_inside_a_code_fence_is_never_promoted(self) -> None:
        body = "## A\n\n```\nInstallation Steps\n```\n"
        assert recover_headings_from_toc(body, ["Installation Steps"]) == body

    def test_a_very_short_title_is_ignored(self) -> None:
        body = "## A\n\nX\n"
        assert recover_headings_from_toc(body, ["X"]) == body

    def test_no_toc_entries_is_a_no_op(self) -> None:
        body = "## A\n\nInstallation Steps\n"
        assert recover_headings_from_toc(body, []) == body

    def test_a_document_with_no_headings_is_untouched(self) -> None:
        """Without a heading tree there is no root level to promote into, and `recover_headings`
        owns the structureless-document path."""
        body = "Installation Steps\n\nprose\n"
        assert recover_headings_from_toc(body, ["Installation Steps"]) == body

    def test_it_is_idempotent(self) -> None:
        body = "## Intro\n\nInstallation Steps\n"
        once = recover_headings_from_toc(body, ["Installation Steps"])
        assert recover_headings_from_toc(once, ["Installation Steps"]) == once


class TestPromotionLevel:
    """A recovered section is a sibling of the document's other sections, not of its title.

    Promoting to the shallowest level instead made 478 recovered headings `#` in the Kernel
    Developer's Guide. That swamped its lone `#` title, so `level_headings_from_numbering` no longer
    saw a flat document and declined — the recovery silently destroyed the five-level outline it was
    meant to complete."""

    def test_recovery_uses_the_modal_heading_level_not_the_shallowest(self) -> None:
        body = "# Doc Title\n\n## Section A\n\n## Section B\n\nMissed Section\n"
        out = recover_headings_from_toc(body, ["Missed Section"])
        assert "## Missed Section" in out
        assert "# Missed Section" not in out.replace("## Missed Section", "")

    def test_the_document_title_is_not_swamped(self) -> None:
        body = "# Title\n\n## A\n\n## B\n\nX Section\n\nY Section\n"
        out = recover_headings_from_toc(body, ["X Section", "Y Section"])
        assert len([h for h in heads(out) if h.startswith("# ")]) == 1


class TestCaptionsAreNotSections:
    """A "List of Tables"/"List of Figures" is a legacy TOC too, and its entries are captured — but
    a caption names a figure, not a section. Promoting them found 7 bogus headings in
    `ifcp5_1tech_manual` ("Table 4.6. List of Routines (PRCFC - PRCFE)"), which would fragment the
    section tree and put chunk boundaries on captions."""

    def test_a_table_caption_is_not_promoted(self) -> None:
        body = "## A\n\nTable 4.6. List of Routines\n"
        assert recover_headings_from_toc(body, ["Table 4.6. List of Routines"]) == body

    def test_a_figure_caption_is_not_promoted(self) -> None:
        body = "## A\n\nFigure 12: Sample Output\n"
        assert recover_headings_from_toc(body, ["Figure 12: Sample Output"]) == body

    def test_a_real_section_starting_with_the_word_table_is_kept(self) -> None:
        """`Table Maintenance` is a section; the guard keys on a caption *number*, not the word."""
        body = "## A\n\nTable Maintenance\n"
        out = recover_headings_from_toc(body, ["Table Maintenance"])
        assert "## Table Maintenance" in out


class TestTocEntryLinesAreNotHeadings:
    """A line that is itself a TOC entry must never be promoted.

    In an unstripped TOC region the entry line *is* the title, so recovery matched it and produced
    headings like `27.1 Introduction ..........................` — dot leader and all. Those reach
    the heading tree, the regenerated Contents, the anchors and `section_path`."""

    def test_a_dot_leader_entry_is_never_promoted(self) -> None:
        body = "## A\n\nIntroduction ................................ 27\n"
        assert recover_headings_from_toc(body, ["Introduction"]) == body

    def test_a_trailing_page_number_entry_is_never_promoted(self) -> None:
        body = "## A\n\nGlossary 113\n"
        assert recover_headings_from_toc(body, ["Glossary"]) == body

    def test_a_real_section_line_is_still_promoted(self) -> None:
        body = "## A\n\nGlossary\n"
        assert "## Glossary" in recover_headings_from_toc(body, ["Glossary"])


class TestHeadingsNeverKeepADotLeader:
    """Docling sometimes detects a TOC line as a heading, so the heading text arrives as
    `27.1 Introduction ....................... 27`. That reaches the heading tree, the regenerated
    Contents, the anchor slug and `section_path` — a section whose name contains its own page
    number. Trim the leader; the heading keeps its title."""

    def test_a_trailing_dot_leader_and_page_are_trimmed(self) -> None:
        from vdocs.stages.normalize.normalize_pure import trim_heading_leaders

        out = trim_heading_leaders("## 27.1 Introduction ....................... 27\n")
        assert out.strip() == "## 27.1 Introduction"

    def test_a_leader_with_no_page_number_is_trimmed(self) -> None:
        from vdocs.stages.normalize.normalize_pure import trim_heading_leaders

        assert trim_heading_leaders("# Glossary .........\n").strip() == "# Glossary"

    def test_an_ordinary_heading_is_untouched(self) -> None:
        from vdocs.stages.normalize.normalize_pure import trim_heading_leaders

        body = "## Introduction\n\nprose ...... with dots\n"
        assert trim_heading_leaders(body) == body

    def test_an_ellipsis_in_a_heading_is_not_a_leader(self) -> None:
        from vdocs.stages.normalize.normalize_pure import trim_heading_leaders

        body = "## Select an option ...\n"
        assert trim_heading_leaders(body) == body
