"""Unit tests for the content-retention gate rule (P3.3, audit R‑5 / [S8]).

`score_retention` has fired since Phase 3 and `blocks_publish` has encoded the rule since then —
but nothing called it, so QUARANTINE documents shipped into gold under a green pipeline. These
tests pin the wiring: which recorded verdicts block, which are excused by a curated sign-off, and
what an *unscored* bundle means (UNKNOWN, never PASS).
"""

from __future__ import annotations

from vdocs.stages.validate import retention_pure as rg


def _f(findings):
    return {(f.kind, f.doc_id) for f in findings}


def test_quarantine_always_blocks():
    findings = rg.gate_retention([("ADT:um", "QUARANTINE", 0.05)], signed_off=frozenset())
    assert _f(findings) == {("retention-quarantine", "ADT:um")}
    assert findings[0].blocking is True
    assert "0.05" in findings[0].detail


def test_quarantine_is_not_excusable_by_signoff():
    # blocks_publish's rule: a sign-off covers REVIEW only. A gutted document is not a
    # judgement call, and letting a registry entry wave it through would defeat the gate.
    findings = rg.gate_retention([("ADT:um", "QUARANTINE", 0.05)], signed_off=frozenset({"ADT:um"}))
    assert [f.blocking for f in findings] == [True]


def test_review_blocks_unless_signed_off():
    unsigned = rg.gate_retention([("ADT:um", "REVIEW", 0.61)], signed_off=frozenset())
    assert _f(unsigned) == {("retention-review-unsigned", "ADT:um")}
    assert unsigned[0].blocking is True
    assert rg.gate_retention([("ADT:um", "REVIEW", 0.61)], signed_off=frozenset({"ADT:um"})) == []


def test_pass_never_blocks():
    assert rg.gate_retention([("ADT:um", "PASS", 0.99)], signed_off=frozenset()) == []


def test_unscored_bundle_is_a_blocking_finding_not_a_pass():
    # a gold bundle whose capture.yaml carries no retention block has NOT been scored; reading
    # that as "fine" is the fail-open shape this remediation exists to remove.
    findings = rg.gate_retention([("ADT:um", "", None)], signed_off=frozenset())
    assert _f(findings) == {("retention-unscored", "ADT:um")}
    assert findings[0].blocking is True


def test_stale_signoff_is_reported_but_does_not_block():
    # the registry keeps a sign-off for a doc that now PASSes: worth cleaning up, not worth
    # reddening the gate — a stale excuse is not a corpus defect (P3.3 ruling).
    findings = rg.gate_retention(
        [("ADT:um", "PASS", 0.99)], signed_off=frozenset({"ADT:um", "PSD:gone"})
    )
    assert _f(findings) == {
        ("retention-signoff-stale", "ADT:um"),
        ("retention-signoff-stale", "PSD:gone"),
    }
    assert not any(f.blocking for f in findings)


def test_findings_are_ordered_by_doc_id():
    findings = rg.gate_retention(
        [("B:x", "QUARANTINE", 0.1), ("A:y", "QUARANTINE", 0.2)], signed_off=frozenset()
    )
    assert [f.doc_id for f in findings] == ["A:y", "B:x"]
