"""VO.8f — one `toc.yaml` shape whichever converter produced the body.

`toc.yaml` records the document's original table of contents: title, printed page, the anchor it
pointed at, and whether that anchor resolved to a derived heading. The DOCX/Pandoc path fills all
four, because a Word TOC carries `](#_Toc…)` links.

The Docling/PDF path carried none. A PDF's TOC is printed text — `Introduction .......... 1` — with
no link of any kind, so every captured entry landed as `anchor: ''`, `resolved: false`. Same file,
same schema, but the anchor and resolved columns were dead on one path and live on the other, which
makes the sidecar unusable as a navigation index for PDFs and makes `resolved` mean two things.

The fix composes what is already in hand: the entry gives a title, the derived tree gives
title → slug. That is the same correlation `correlate_bookmarks_by_title` does for Word bookmarks;
here the key is the title itself.

**P3.1 must hold**: an anchorless entry that matches no heading stays anchorless and is NOT counted
as unresolved. It never pointed anywhere, so flagging it would manufacture a fidelity finding out of
printed pagination.
"""

from vdocs.stages.normalize.anchors_pure import Heading
from vdocs.stages.normalize.normalize_pure import (
    LegacyTocEntry,
    normalize_body,
    resolve_toc_anchors_by_title,
)


def h(text: str, slug: str, level: int = 2) -> Heading:
    return Heading(level=level, text=text, slug=slug, bookmark=None, stable_id=f"d/{slug}")


class TestResolveByTitle:
    HEADINGS = [h("Introduction", "introduction"), h("Package Management", "package-management")]

    def test_an_anchorless_entry_gains_its_heading_anchor(self) -> None:
        (e,) = resolve_toc_anchors_by_title(
            [LegacyTocEntry("Introduction", "1", "")], self.HEADINGS
        )
        assert e.anchor == "#introduction"
        assert e.title == "Introduction" and e.page == "1"

    def test_matching_is_slug_based_so_case_and_punctuation_do_not_matter(self) -> None:
        (e,) = resolve_toc_anchors_by_title(
            [LegacyTocEntry("PACKAGE MANAGEMENT", "19", "")], self.HEADINGS
        )
        assert e.anchor == "#package-management"

    def test_an_entry_that_matches_nothing_stays_anchorless(self) -> None:
        """P3.1 — it never pointed anywhere; inventing an anchor would be worse than none."""
        (e,) = resolve_toc_anchors_by_title([LegacyTocEntry("Nowhere", "3", "")], self.HEADINGS)
        assert e.anchor == ""

    def test_an_entry_that_already_has_an_anchor_is_untouched(self) -> None:
        """The Word path is authoritative — a real `_Toc` bookmark is not second-guessed."""
        (e,) = resolve_toc_anchors_by_title(
            [LegacyTocEntry("Introduction", "1", "#_Toc12345")], self.HEADINGS
        )
        assert e.anchor == "#_Toc12345"

    def test_it_is_idempotent(self) -> None:
        once = resolve_toc_anchors_by_title(
            [LegacyTocEntry("Introduction", "1", "")], self.HEADINGS
        )
        assert resolve_toc_anchors_by_title(once, self.HEADINGS) == once


class TestSidecarConvergence:
    """End to end through `normalize_body`, which is what actually writes the sidecar."""

    PDF_BODY = "\n".join(
        [
            "# Manual",
            "",
            "## Table of Contents",
            "",
            "| Introduction................ | 1 |",
            "| Package Management......... | 19 |",
            "| Missing Section............ | 40 |",
            "",
            "## Introduction",
            "",
            "prose",
            "",
            "## Package Management",
            "",
            "more prose",
            "",
        ]
    )
    TITLES = frozenset({"table of contents", "contents"})

    def _entries(self) -> list[dict]:
        _body, amap = normalize_body(self.PDF_BODY, frozenset(), toc_titles=self.TITLES)
        return amap.legacy_toc

    def test_a_pdf_entry_now_carries_a_resolved_anchor(self) -> None:
        by_title = {e["title"]: e for e in self._entries()}
        assert by_title["Introduction"]["anchor"] == "#introduction"
        assert by_title["Introduction"]["resolved"] is True
        assert by_title["Introduction"]["page"] == "1"

    def test_the_printed_page_number_is_still_the_captured_one(self) -> None:
        by_title = {e["title"]: e for e in self._entries()}
        assert by_title["Package Management"]["page"] == "19"

    def test_an_entry_with_no_matching_heading_stays_unresolved_but_recorded(self) -> None:
        by_title = {e["title"]: e for e in self._entries()}
        assert by_title["Missing Section"]["anchor"] == ""
        assert by_title["Missing Section"]["resolved"] is False

    def test_an_unmatched_paper_entry_is_not_counted_as_a_fidelity_flag(self) -> None:
        """P3.1: `toc_unresolved` is for anchors that pointed somewhere and missed."""
        _body, amap = normalize_body(self.PDF_BODY, frozenset(), toc_titles=self.TITLES)
        assert amap.toc_unresolved == []
