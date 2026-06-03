"""Unit tests for template_pure — (doc_type, era) STRIP scaffold + stamp template_id (§9.8)."""

from __future__ import annotations

from vdocs.stages.normalize import template_pure as tp

_TEMPLATES = (
    tp.Template(
        template_id="DIBR:2020s:abc12345",
        doc_type="DIBR",
        era="2020s",
        section_titles=frozenset({"purpose", "dependencies", "constraints", "rollback"}),
    ),
)


def test_apply_template_stamps_id_and_strips_empty_scaffold_sections():
    body = (
        "# Deploy Guide\n\n"
        "## Purpose\n\nThis is the real purpose, filled in.\n\n"
        "## Dependencies\n\n"  # empty scaffold section (no content) → stripped
        "## Constraints\n\nReal constraints text.\n\n"
        "## Rollback\n\n"  # empty scaffold section → stripped
    )
    out, template_id = tp.apply_template(body, "DIBR", "2020s", _TEMPLATES)
    assert template_id == "DIBR:2020s:abc12345"
    assert "## Dependencies" not in out  # unfilled scaffold heading removed
    assert "## Rollback" not in out
    assert "## Purpose" in out and "This is the real purpose" in out  # filled sections kept
    assert "## Constraints" in out and "Real constraints text." in out


def test_apply_template_keeps_non_scaffold_and_filled_sections():
    body = "# G\n\n## Purpose\n\ntext\n\n## Notes\n\n"  # Notes is not in the template schema
    out, _ = tp.apply_template(body, "DIBR", "2020s", _TEMPLATES)
    assert "## Notes" in out  # empty but NOT a template-scaffold section → left alone


def test_apply_template_no_match_returns_body_unchanged():
    body = "# G\n\n## Purpose\n\n"
    out, template_id = tp.apply_template(body, "UM", "2020s", _TEMPLATES)  # no UM template
    assert out == body and template_id == ""
    out2, tid2 = tp.apply_template(body, "DIBR", "1990s", _TEMPLATES)  # wrong era
    assert out2 == body and tid2 == ""


def test_apply_template_keeps_scaffold_section_with_subsections():
    # a scaffold heading that has subsection content is NOT empty → retained
    body = "# G\n\n## Dependencies\n\n### Runtime\n\nsome runtime dep\n"
    out, _ = tp.apply_template(body, "DIBR", "2020s", _TEMPLATES)
    assert "## Dependencies" in out  # has children → not an empty scaffold


def test_apply_template_is_idempotent():
    body = "# G\n\n## Purpose\n\ntext\n\n## Rollback\n\n"
    once, tid = tp.apply_template(body, "DIBR", "2020s", _TEMPLATES)
    twice, tid2 = tp.apply_template(once, "DIBR", "2020s", _TEMPLATES)
    assert twice == once and tid2 == tid


def test_strip_ignores_headings_in_code_fences():
    body = "# G\n\n## Purpose\n\ntext\n\n```\n## Rollback\n```\n"
    out = tp.strip_template_scaffold(body, frozenset({"rollback"}))
    assert "## Rollback" in out  # fenced — not a real heading, untouched


def test_strip_with_empty_titles_is_noop():
    body = "# G\n\n## Purpose\n\n"
    assert tp.strip_template_scaffold(body, frozenset()) == body  # nothing to strip


def test_strip_recognizes_oversized_heading():
    # the `#{1,6}` → `#+` unification (B1): upstream emits >6-`#` scaffold headings; strip them too
    body = "# G\n\n########### Rollback\n\n## Body\n\ncontent\n"
    out = tp.strip_template_scaffold(body, frozenset({"rollback"}))
    assert "Rollback" not in out  # the empty oversized scaffold heading is now stripped
    assert "## Body" in out


# --- §6.4 title-page publication-date capture --------------------------------------------------
_LEGACY_COVER = (
    '<img src="logo.png" />\n\n'
    "Initial Release: March 2010\n\n"
    "Revised: February 2018\n\n"
    "Department of Veterans Affairs\n\n"
    "Office of Enterprise Development\n\n"
    "Table of Contents\n\n"
    "[Introduction [1](#introduction)](#introduction)\n\n"
    "# Introduction\n\nReal content.\n"
)


def test_extract_published_lifts_first_title_page_month_year():
    assert tp.extract_published(_LEGACY_COVER) == "2010-03"


def test_extract_published_absent_date_returns_none():
    assert tp.extract_published("# Doc\n\nNo cover date anywhere.\n") is None


def test_extract_published_only_scans_title_page_window():
    body = "cover\n" + "x\n" * 50 + "March 2010\n"  # date past the 40-line window
    assert tp.extract_published(body) is None


# --- §6.4 title-page standardize + gated strip -------------------------------------------------
_FIELDS = tp.TitlePageFields(
    title="Anticoagulation Management Tool Technical Manual",
    version="3.0",
    patch_id="OR*3.0*447",
    published="2018-02",
    source_url="https://www.va.gov/vdl/documents/x.docx",
)


def test_standardize_title_page_replaces_cover_with_block():
    out = tp.standardize_title_page(_LEGACY_COVER, _FIELDS)
    # the raw cover furniture is gone
    assert "Department of Veterans Affairs" not in out
    assert "Initial Release: March 2010" not in out
    assert "<img" not in out.split("# Introduction")[0]
    # the standardized block (from frontmatter) is present
    assert "Anticoagulation Management Tool Technical Manual" in out
    assert "2018-02" in out and "OR*3.0*447" in out
    # everything from the first real marker onward is preserved
    assert "Table of Contents" in out and "# Introduction" in out and "Real content." in out


def test_standardize_title_page_blocked_when_published_missing():
    fields = tp.TitlePageFields(title="X", version="1", patch_id="", published="", source_url="u")
    # capture-gate: no published date → the cover is NOT removed (retain + flag elsewhere)
    assert tp.standardize_title_page(_LEGACY_COVER, fields) == _LEGACY_COVER


def test_standardize_title_page_noop_without_cover_signal():
    # a doc that already starts with content (no DVA/img/blank-page furniture) is untouched
    body = "# Introduction\n\nStraight into content with no legacy cover.\n"
    assert tp.standardize_title_page(body, _FIELDS) == body


def test_standardize_title_page_is_idempotent():
    once = tp.standardize_title_page(_LEGACY_COVER, _FIELDS)
    twice = tp.standardize_title_page(once, _FIELDS)
    assert twice == once


def test_standardize_title_page_surgically_strips_all_bold_flat_cover():
    # an all-bold flat cover with no ATX/TOC boundary (the ACR shape): the VA imprint + the bare
    # `Month YYYY` cover-date line are dropped, the title/body lines kept
    body = (
        "**Scheduling V. 5.3 Installation Guide**\n\n"
        "**Patches SD\\*5.3\\*66**\n\n"
        "**January 1998**\n\n"
        "Department of Veterans Affairs\n\n"
        "**Introduction**\n\nReal body content here.\n"
    )
    out = tp.standardize_title_page(body, _FIELDS)
    assert "January 1998" not in out  # captured cover date removed (gated on published)
    assert "Department of Veterans Affairs" not in out
    assert "**Introduction**" in out and "Real body content here." in out  # content kept


def test_strip_title_image_removes_logo_in_title_area_only():
    # the per-doc VA logo at the top (before the first heading/TOC) is noise → removed
    body = (
        '<img src="seal.png" style="width:2in" />\n\n'
        "**Some Manual**\n\n"
        "March 2010\n\n"
        "# Introduction\n\nText with a real figure:\n\n"
        "![screenshot](shot.png)\n\nmore text.\n"
    )
    out = tp.strip_title_image(body)
    assert "seal.png" not in out  # title-area logo gone
    assert "![screenshot](shot.png)" in out  # content figure (below the title area) kept
    assert "# Introduction" in out and "**Some Manual**" in out


def test_strip_title_image_markdown_and_html_forms_and_multiple():
    body = '![](a.jpeg)\n\n<img src="b.png" />\n\n# Heading\n\nbody\n'
    out = tp.strip_title_image(body)
    assert "a.jpeg" not in out and "b.png" not in out  # both title-area images removed


def test_strip_title_image_noop_when_no_title_area_image():
    # a doc whose first image is a content figure well below the title area is untouched
    body = "# Doc\n\nlots of prose here.\n\n## Section\n\n![fig](f.png)\n\ntail.\n"
    assert tp.strip_title_image(body) == body
    # a doc that opens straight into content (no leading image) is untouched
    assert tp.strip_title_image("# Intro\n\nplain text\n") == "# Intro\n\nplain text\n"


def test_strip_title_image_flat_doc_leading_logo():
    # an old-gen flat doc (no heading boundary): a leading logo before the title text is removed,
    # but a deep content image is not
    body = (
        '<img src="logo.gif" />\n\nPlain Title Manual\n\n' + "body line\n" * 50 + "![deep](d.png)\n"
    )
    out = tp.strip_title_image(body)
    assert "logo.gif" not in out
    assert "![deep](d.png)" in out


def test_standardize_title_page_strips_va_imprint_authored_as_heading():
    # the late-gen shape: the VA imprint + cover date are authored as ATX headings (so they would
    # otherwise become `## Contents` entries). Treat them as cover furniture, not a boundary.
    body = (
        '<img src="seal.png" />\n\n'
        "# Department of Veterans Affairs Office of Information and Technology\n\n"
        "# January 1998\n\n"
        "# Introduction\n\nReal content.\n"
    )
    out = tp.standardize_title_page(body, _FIELDS)
    assert "Department of Veterans Affairs" not in out
    assert "January 1998" not in out
    assert "# Introduction" in out and "Real content." in out


def test_strip_cover_furniture_idempotent_and_window_bounded():
    # a Month YYYY *deep* in the body (past the title-page window) is real content — never touched
    body = "**Cover**\n\n**March 2010**\n\n" + "x\n" * 80 + "Released June 2011 in the field.\n"
    out = tp.standardize_title_page(body, _FIELDS)
    assert "March 2010" not in out  # in the cover window → stripped
    assert "Released June 2011 in the field." in out  # deep prose date → kept
