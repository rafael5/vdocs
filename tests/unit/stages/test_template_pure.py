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
