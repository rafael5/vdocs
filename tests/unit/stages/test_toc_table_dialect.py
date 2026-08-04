"""VO.8b — the table-shaped legacy TOC dialect Docling emits for PDFs.

Docling renders a legacy table of contents as a markdown *table*. Three things make it unlike every
dialect `normalize` already handles:

* the row is `|`-delimited, so `_TRAILING_PAGE_RE` never matches (the line ends in `|`, not a page
  number) and the strip bounded at the first row instead of consuming the TOC;
* rows are frequently duplicated across all four cells;
* one cell can carry several entries run together — `2.1.1 Example.....2 2.2 $$FIPS^XIPUTIL()....2`.

The consequence measured on the Kernel Developer's Guide: dot-leader runs 3,417 -> 3,416 and ONE
entry captured to `toc.yaml`. Nothing was deleted — this was the safe failure — but 11.9% of that
document's body was un-stripped TOC, and it is the outline we actually want, not junk.

Capture-before-strip is absolute here: anything the strip drops must be parsed into `toc.yaml`.
"""

from vdocs.stages.normalize import normalize_pure as nz

SEP = "|--------|--------|"
DUP = (
    "| Revision History...........................ii "
    "| Revision History...........................ii "
    "| Revision History...........................ii |"
)
MULTI = (
    "| 2.1.1 Example.................................. 2 "
    "2.2 $$FIPS^XIPUTIL(): FIPS Code for ZIP Code....2 | x |"
)


class TestSplitTocTableRow:
    def test_a_separator_row_carries_no_entries(self) -> None:
        assert nz.split_toc_table_row(SEP) == []

    def test_a_non_table_line_is_not_a_table_row(self) -> None:
        assert nz.split_toc_table_row("Introduction .......... 1") == []

    def test_duplicated_cells_collapse_to_one_entry(self) -> None:
        """Docling repeats the same entry across every column; capturing it four times would
        put three phantom entries in toc.yaml."""
        assert nz.split_toc_table_row(DUP) == ["Revision History...........................ii"]

    def test_several_entries_in_one_cell_are_split(self) -> None:
        parts = nz.split_toc_table_row(MULTI)
        assert len(parts) == 2
        assert parts[0].startswith("2.1.1 Example")
        assert parts[1].startswith("2.2 $$FIPS^XIPUTIL()")

    def test_a_table_row_with_no_page_numbers_is_not_a_toc_row(self) -> None:
        """A real content table inside the TOC region must not be eaten."""
        assert nz.split_toc_table_row("| Date | Revision | Description | Author |") == []


class TestRecognitionAndCapture:
    def test_a_toc_table_row_is_a_nav_line(self) -> None:
        """The bug: this returned False, so `has_prose` went true and the strip bounded."""
        assert nz._is_toc_nav_line(DUP) is True
        assert nz._is_toc_nav_line(SEP) is True

    def test_a_content_table_row_is_not_a_nav_line(self) -> None:
        assert nz._is_toc_nav_line("| Date | Revision | Description | Author |") is False

    def test_entries_are_captured_from_a_table_row(self) -> None:
        entries = nz.capture_toc_entries(MULTI)
        assert [e.title for e in entries] == [
            "2.1.1 Example",
            "2.2 $$FIPS^XIPUTIL(): FIPS Code for ZIP Code",
        ]
        assert [e.page for e in entries] == ["2", "2"]

    def test_a_roman_page_number_is_captured(self) -> None:
        (entry,) = nz.capture_toc_entries(DUP)
        assert entry.title == "Revision History" and entry.page == "ii"


class TestStripAndCaptureTogether:
    BODY = "\n".join(
        [
            "# Kernel Developer's Guide",
            "",
            "## Table of Contents",
            "",
            DUP,
            SEP,
            MULTI,
            "",
            "## Introduction",
            "",
            "Real prose that must survive.",
            "",
        ]
    )
    TITLES = frozenset({"table of contents", "contents"})

    def test_the_table_toc_is_stripped(self) -> None:
        out = nz.strip_legacy_toc(self.BODY, self.TITLES)
        assert "Revision History" not in out
        assert "$$FIPS^XIPUTIL()" not in out
        assert "Real prose that must survive." in out
        assert "## Introduction" in out

    def test_every_stripped_entry_is_captured(self) -> None:
        """The invariant: nothing leaves the body without a record."""
        entries = nz.legacy_toc_entries(self.BODY, self.TITLES)
        titles = [e.title for e in entries]
        assert "Revision History" in titles
        assert "2.1.1 Example" in titles
        assert len(entries) == 3

    def test_body_prose_after_the_toc_is_never_touched(self) -> None:
        out = nz.strip_legacy_toc(self.BODY, self.TITLES)
        assert out.count("Real prose that must survive.") == 1

    def test_a_content_table_outside_a_toc_region_survives(self) -> None:
        body = "\n".join(
            [
                "## Revision History",
                "",
                "| Date | Revision | Description |",
                "|------|----------|-------------|",
                "| 08/28/2025 | 1.0 | Initial creation |",
                "",
            ]
        )
        assert nz.strip_legacy_toc(body, self.TITLES) == body

    def test_stripping_is_idempotent(self) -> None:
        once = nz.strip_legacy_toc(self.BODY, self.TITLES)
        assert nz.strip_legacy_toc(once, self.TITLES) == once


SPLIT_CELLS = "| 1.4.1 | Intended Audience .................................. | 7 |"


class TestEntrySplitAcrossCells:
    """The real-corpus shape that defeated the first fix: Docling puts the section number and the
    page number in their own columns, so no single cell holds a leader-and-page pair. Scanning the
    row cell by cell found nothing, `has_prose` went true, and one such row bounded the strip —
    leaving 1,197 TOC lines in the Kernel Developer's Guide."""

    def test_an_entry_split_across_cells_is_found(self) -> None:
        assert nz.split_toc_table_row(SPLIT_CELLS) == [
            "1.4.1 Intended Audience .................................. 7"
        ]

    def test_it_is_a_nav_line(self) -> None:
        assert nz._is_toc_nav_line(SPLIT_CELLS) is True

    def test_the_section_number_stays_with_the_title(self) -> None:
        """The number carries the outline depth — losing it costs the hierarchy."""
        (e,) = nz.capture_toc_entries(SPLIT_CELLS)
        assert e.title == "1.4.1 Intended Audience"
        assert e.page == "7"


class TestWholeTocTableIsOneBlock:
    """Docling emits the legacy TOC as a single markdown table, and not every row carries a page
    number of its own: a bare section number (`| 2.5 |`), a title wrapped onto its own row, an
    empty spacer row. Judged line by line those look like prose and bound the strip — which is
    what left 420 of the Blood Bank manual's 423 TOC lines in the body.

    A contiguous table run containing at least one parsable entry IS the TOC. The `has_prose`
    guard still protects everything outside such a run."""

    BODY = "\n".join(
        [
            "## Table of Contents",
            "",
            "| Package Management...... | 19 |",
            "|--------|--------|",
            "| 2.5 |    |",
            "|    |    |",
            "| Functional Description..... |  |",
            "| Blood Bank Module Goals | 3 |",
            "",
            "## Introduction",
            "",
            "Body prose.",
        ]
    )
    TITLES = frozenset({"table of contents", "contents"})

    def test_the_whole_table_is_stripped_not_just_its_first_rows(self) -> None:
        out = nz.strip_legacy_toc(self.BODY, self.TITLES)
        for gone in ("Package Management", "Blood Bank Module Goals", "Functional Description"):
            assert gone not in out, f"{gone!r} survived the strip"
        assert "Body prose." in out and "## Introduction" in out

    def test_parsable_entries_are_still_captured(self) -> None:
        titles = [e.title for e in nz.legacy_toc_entries(self.BODY, self.TITLES)]
        assert "Package Management" in titles

    def test_a_content_table_after_real_prose_still_bounds_the_strip(self) -> None:
        """The guard that stops a flattened document's body being eaten."""
        body = "\n".join(
            [
                "## Table of Contents",
                "",
                "| Intro...... | 1 |",
                "",
                "Real prose in the region.",
                "",
                "| Date | Revision |",
                "| 2025 | 1.0 |",
                "",
            ]
        )
        out = nz.strip_legacy_toc(body, self.TITLES)
        assert "Real prose in the region." in out
        assert "| 2025 | 1.0 |" in out
        assert "Intro" not in out


class TestNothingLeavesUnrecorded:
    """`toc.yaml` is a record, not a body: over-capturing costs a junk row, under-capturing loses
    content silently — which is precisely the failure this corpus has already had. So a TOC-table
    row that is dropped but yields no leader-and-page entry is still recorded, title-only.

    Measured on the 19 PDFs before this: ~10 real entries (`Exported Routines`, `REPORTS TAB`,
    `Appendix E: ...379`) were stripped with no record because their page number had no dot leader.
    """

    def test_a_title_with_no_dot_leader_is_still_captured(self) -> None:
        (e,) = nz.capture_toc_entries("| Exported Routines |  |")
        assert e.title == "Exported Routines" and e.page == ""

    def test_a_glued_page_number_keeps_the_whole_title(self) -> None:
        (e,) = nz.capture_toc_entries("| Appendix E: Exported Values.379 |")
        assert "Appendix E" in e.title

    def test_an_empty_or_separator_row_records_nothing(self) -> None:
        assert nz.capture_toc_entries("|      |      |") == []
        assert nz.capture_toc_entries("|------|------|") == []

    def test_a_pure_leader_row_records_nothing(self) -> None:
        assert nz.capture_toc_entries("| ................................ |") == []

    def test_a_parsable_entry_still_wins_over_the_fallback(self) -> None:
        (e,) = nz.capture_toc_entries("| Introduction......... | 7 |")
        assert e.title == "Introduction" and e.page == "7"


class TestTocIsNotADataTable:
    """Ordering defect found by the Pandoc-vs-Docling comparison on the FileMan Developer's Guide.

    `extract_tables` runs before the legacy-TOC capture, and a Docling TOC *is* a markdown table —
    a tall one, so it qualified for extraction and was filed as `tables/table-01.csv`. The capture
    then found nothing: **619 TOC entries became 0**, silently, on exactly the large documents whose
    outline matters most. The stage already orders revision extraction first for the same reason;
    a TOC table must likewise never be mistaken for data.
    """

    # the separator row matters: without it this is not a GFM table at all, and the test would
    # pass for the wrong reason. The real Docling TOC has one.
    TOC_TABLE = "\n".join(
        ["## Table of Contents", "", "| Section | Page |", "|---|---|"]
        + [f"| Section {i} .................................... | {i} |" for i in range(1, 15)]
        + ["", "## Introduction", "", "prose"]
    )

    def test_a_toc_table_is_not_lifted_to_csv(self) -> None:
        from vdocs.stages.normalize.tables_pure import extract_tables

        body, tables = extract_tables(self.TOC_TABLE)
        assert tables == []
        assert "extracted to CSV" not in body

    def test_the_toc_entries_survive_to_be_captured(self) -> None:
        from vdocs.stages.normalize.tables_pure import extract_tables

        body, _t = extract_tables(self.TOC_TABLE)
        entries = nz.legacy_toc_entries(body, frozenset({"table of contents"}))
        paged = [e for e in entries if e.page]
        assert len(paged) == 14, [e.title for e in entries]
        assert paged[0].title == "Section 1" and paged[0].page == "1"

    def test_a_genuine_data_table_is_still_lifted(self) -> None:
        from vdocs.stages.normalize.tables_pure import extract_tables

        rows = "\n".join(f"| Field {i} | Description {i} | Type {i} |" for i in range(1, 16))
        body, tables = extract_tables(f"## Fields\n\n| A | B | C |\n|---|---|---|\n{rows}\n")
        assert len(tables) == 1
        assert "extracted to CSV" in body
