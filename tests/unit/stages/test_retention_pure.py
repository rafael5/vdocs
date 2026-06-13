"""Unit tests for the content-retention guardrail (catches a normalize step that deletes the body
whole — the blind spot of the over-strip gate, which scores 0/0 → PASS on a gutted doc)."""

from __future__ import annotations

from vdocs.stages.fidelity import retention_pure as rp


def test_full_body_kept_passes():
    v = rp.score_retention(1000, 980)
    assert v.verdict == rp.PASS and v.retention >= 0.97


def test_table_relocation_not_penalised():
    # A table-heavy TM: most of the body moved to tables/*.csv sidecars. Counting relocated words as
    # retained keeps it PASS — not a false positive.
    v = rp.score_retention(90000, 20000, relocated_words=70000)
    assert v.verdict == rp.PASS and v.kept_words == 90000


def test_gutted_body_quarantines():
    # The Prosthetics defect: 37,960-word body collapsed to 56 by an unbounded TOC strip.
    v = rp.score_retention(37960, 56)
    assert v.verdict == rp.QUARANTINE and v.retention < 0.01


def test_partial_loss_reviews():
    v = rp.score_retention(1000, 600)
    assert v.verdict == rp.REVIEW


def test_trivial_body_passes():
    assert rp.score_retention(0, 0).verdict == rp.PASS
    assert rp.score_retention(1, 1).verdict == rp.PASS


def test_blocks_publish_rule():
    assert rp.blocks_publish(rp.QUARANTINE) is True
    assert rp.blocks_publish(rp.REVIEW) is True
    assert rp.blocks_publish(rp.REVIEW, signed_off=True) is False
    assert rp.blocks_publish(rp.PASS) is False
