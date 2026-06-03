"""Unit tests for the §9.8 template-compliance oracle (fidelity's pure kernel, Phase 5 prep)."""

from __future__ import annotations

from vdocs.stages.discover import discover_pure as dp
from vdocs.stages.fidelity import compliance_pure as cp


def _sec(title, *, required=True, variants=None):
    return cp.ExpectedSection(
        title=title,
        title_pattern=dp.induce_title_pattern(variants or [title]),
        required=required,
    )


def test_pass_when_all_required_sections_present():
    sections = [_sec("Purpose"), _sec("Rollback"), _sec("Glossary", required=False)]
    body = "# Doc\n\n## Purpose\n\nx\n\n## Rollback\n\ny\n"
    v = cp.score_extraction_compliance(body, sections)
    assert v.verdict == cp.PASS
    assert v.score == 1.0
    assert v.expected_required == 2 and v.present_required == 2
    assert v.missing_required == ()


def test_review_when_one_required_section_missing():
    sections = [_sec("Purpose"), _sec("Dependencies"), _sec("Rollback"), _sec("Timeline")]
    body = "# Doc\n\n## Purpose\n\n## Dependencies\n\n## Rollback\n"  # Timeline missing → 3/4
    v = cp.score_extraction_compliance(body, sections)
    assert v.verdict == cp.REVIEW
    assert v.score == 0.75
    assert v.missing_required == ("Timeline",)


def test_quarantine_when_most_required_missing():
    sections = [_sec("Purpose"), _sec("Dependencies"), _sec("Rollback"), _sec("Timeline")]
    body = "# Doc\n\n## Purpose\n"  # 1/4 → 0.25 < 0.5
    v = cp.score_extraction_compliance(body, sections)
    assert v.verdict == cp.QUARANTINE
    assert v.score == 0.25


def test_match_is_numbering_tolerant():
    # the body numbers its headings; the induced title_pattern still matches (§9.8 alignment)
    sections = [_sec("Purpose", variants=["Purpose", "1. Purpose"])]
    body = "# Doc\n\n## 1. Purpose\n\nreal text\n"
    assert cp.score_extraction_compliance(body, sections).verdict == cp.PASS


def test_optional_sections_never_affect_the_score():
    sections = [_sec("Purpose"), _sec("Appendix", required=False)]
    body = "# Doc\n\n## Purpose\n"  # optional Appendix absent → still PASS
    v = cp.score_extraction_compliance(body, sections)
    assert v.verdict == cp.PASS and v.expected_required == 1


def test_no_required_sections_scores_pass():
    v = cp.score_extraction_compliance("# Doc\n\n## Anything\n", [_sec("X", required=False)])
    assert v.verdict == cp.PASS and v.score == 1.0


def test_schema_drift_era_template_vs_canonical():
    # verdict 2 (§9.8): the era-template is scored against the canonical doc_type schema — a
    # source-drift signal, not an extraction bug. The era-template lacks a canonical-required one.
    canonical = [_sec("Purpose"), _sec("Back-Out Procedure"), _sec("Rollback Procedure")]
    era_template = [_sec("Purpose"), _sec("Back-Out Procedure")]  # no Rollback Procedure
    v = cp.score_schema_drift(era_template, canonical)
    assert v.verdict == cp.REVIEW
    assert v.missing_required == ("Rollback Procedure",)


def test_blocks_publish_gate_semantics():
    # §8 validate hard gate: QUARANTINE always blocks; REVIEW blocks unless signed off; PASS never
    assert cp.blocks_publish(cp.QUARANTINE) is True
    assert cp.blocks_publish(cp.QUARANTINE, signed_off=True) is True
    assert cp.blocks_publish(cp.REVIEW) is True
    assert cp.blocks_publish(cp.REVIEW, signed_off=True) is False
    assert cp.blocks_publish(cp.PASS) is False
