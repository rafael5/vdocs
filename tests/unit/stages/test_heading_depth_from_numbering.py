"""VO.8c — give a flat document its outline back from its own section numbering.

Docling detects headings in a PDF but assigns every one of them the same level: its JSON document
model labels all 2,291 headings in the Kernel Developer's Guide `level: 1`. `infer_heading_levels`
cannot help — it removes *gaps* in an existing hierarchy, so a flat tree stays flat — and a flat
tree means a regenerated `## Contents` of hundreds of siblings, a degenerate `section_path`, and no
outline to navigate.

The documents carry the answer themselves: `2.6.10.1.1 Example 1` is five levels deep and says so.

**Guarded to flat documents only.** Re-deriving levels for a document that already has a heading
tree would rewrite the structure of all 1,040 existing DOCX-derived documents from a heuristic —
a much worse trade than the flat case it fixes.
"""

from vdocs.stages.normalize.normalize_pure import level_headings_from_numbering


def heads(body: str) -> list[str]:
    return [ln for ln in body.split("\n") if ln.startswith("#")]


class TestDepthFromNumbering:
    FLAT = "\n".join(
        [
            "## Introduction",
            "",
            "## 1 Orientation",
            "",
            "## 1.4 Intended Audience",
            "",
            "## 2.6.10.1.1 Example 1",
            "",
            "prose",
        ]
    )

    def test_depth_follows_the_section_number(self) -> None:
        assert heads(level_headings_from_numbering(self.FLAT)) == [
            "## Introduction",
            "## 1 Orientation",
            "### 1.4 Intended Audience",
            "###### 2.6.10.1.1 Example 1",
        ]

    def test_an_unnumbered_heading_stays_at_the_base_level(self) -> None:
        """`Revision History` and friends are top-level sections, not orphans of the numbering."""
        out = level_headings_from_numbering("## Revision History\n\n## 2.1 Foo\n")
        assert heads(out) == ["## Revision History", "### 2.1 Foo"]

    def test_depth_is_capped_at_markdown_s_six_levels(self) -> None:
        out = level_headings_from_numbering("## A\n\n## 1.2.3.4.5.6.7.8 Deep\n")
        assert heads(out)[1].startswith("###### ")

    def test_the_document_root_level_is_preserved(self) -> None:
        """An H1-rooted flat doc stays H1-rooted — H1 is never fabricated or discarded."""
        out = level_headings_from_numbering("# A\n\n# 1.1 B\n")
        assert heads(out) == ["# A", "## 1.1 B"]

    def test_it_is_idempotent(self) -> None:
        once = level_headings_from_numbering(self.FLAT)
        assert level_headings_from_numbering(once) == once


class TestGuards:
    def test_a_document_that_already_has_a_tree_is_untouched(self) -> None:
        """The 1,040 existing documents must not have their structure re-derived."""
        body = "## Overview\n\n### 2.1 Detail\n\n#### 2.1.1 Deeper\n"
        assert level_headings_from_numbering(body) == body

    def test_a_document_with_no_numbering_is_untouched(self) -> None:
        body = "## Introduction\n\n## Installation\n\n## Glossary\n"
        assert level_headings_from_numbering(body) == body

    def test_a_document_with_no_headings_is_untouched(self) -> None:
        assert level_headings_from_numbering("just prose\n") == "just prose\n"

    def test_numbering_inside_a_code_fence_is_not_a_heading(self) -> None:
        body = "## A\n\n```\n## 1.2 not a heading\n```\n\n## 1.3 B\n"
        out = level_headings_from_numbering(body)
        assert "## 1.2 not a heading" in out  # untouched inside the fence
        assert "### 1.3 B" in out

    def test_a_version_like_number_does_not_create_absurd_depth(self) -> None:
        """`1.2` in a title is depth 2, but the cap plus the flat-only guard keep the blast radius
        small; this pins the behaviour rather than leaving it accidental."""
        out = level_headings_from_numbering("## A\n\n## 1.2 Kernel Patch\n")
        assert heads(out) == ["## A", "### 1.2 Kernel Patch"]
