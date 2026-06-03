"""Unit tests for validate/reconcile_pure — corpus sidecar reconciliation (§5.2, FF C2).

Turns the per-bundle capture.yaml manifests + the emitted stage_runs[normalize].counts into typed
findings: per-doc absent-unexpected (Step 1's signal), corpus-zero (a whole-detector failure), and
count-drop (a regression vs. the prior validate run over a same-or-larger corpus).
"""

from __future__ import annotations

from vdocs.stages.validate import reconcile_pure as rc


def _manifest(doc_id, **outcomes):
    return {"doc_id": doc_id, "captures": {k: {"outcome": v} for k, v in outcomes.items()}}


def test_no_findings_on_a_healthy_corpus():
    manifests = [_manifest("a", refs="captured", tables="captured", revisions="absent-expected")]
    counts = {"documents": 1, "refs_sidecars": 1, "tables_sidecars": 1}
    assert (
        rc.reconcile(manifests=manifests, current_counts=counts, prior_counts=None, corpus_min=50)
        == []
    )


def test_per_doc_absent_unexpected_is_flagged():
    manifests = [_manifest("a", refs="captured", revisions="absent-unexpected")]
    counts = {"documents": 1, "refs_sidecars": 1}
    findings = rc.reconcile(
        manifests=manifests, current_counts=counts, prior_counts=None, corpus_min=50
    )
    assert any(f.kind == "absent-unexpected" and f.sidecar == "revisions" for f in findings)


def test_corpus_zero_for_expected_nonzero_kind_on_large_corpus():
    # zero tables across a large corpus ⇒ the §5.2 whole-detector-failure signal
    manifests = [_manifest(f"d{i}", tables="absent-expected") for i in range(60)]
    counts = {"documents": 60, "refs_sidecars": 60, "tables_sidecars": 0}
    findings = rc.reconcile(
        manifests=manifests, current_counts=counts, prior_counts=None, corpus_min=50
    )
    assert any(f.kind == "corpus-zero" and f.sidecar == "tables_sidecars" for f in findings)


def test_corpus_zero_not_flagged_on_small_corpus():
    # a small selection may legitimately have no qualifying tables — not a whole-detector failure
    manifests = [_manifest("a", tables="absent-expected")]
    counts = {"documents": 3, "refs_sidecars": 3, "tables_sidecars": 0}
    findings = rc.reconcile(
        manifests=manifests, current_counts=counts, prior_counts=None, corpus_min=50
    )
    assert not any(f.kind == "corpus-zero" for f in findings)


def test_count_drop_vs_prior_same_or_larger_corpus():
    counts = {"documents": 60, "refs_sidecars": 60, "tables_sidecars": 40}
    prior = {"documents": 60, "refs_sidecars": 60, "tables_sidecars": 55}
    findings = rc.reconcile(manifests=[], current_counts=counts, prior_counts=prior, corpus_min=50)
    assert any(f.kind == "count-drop" and f.sidecar == "tables_sidecars" for f in findings)


def test_count_drop_ignored_when_corpus_shrank():
    # fewer documents this run (a smaller selection) → a lower count is expected, not a regression
    counts = {"documents": 10, "tables_sidecars": 5}
    prior = {"documents": 60, "tables_sidecars": 55}
    findings = rc.reconcile(manifests=[], current_counts=counts, prior_counts=prior, corpus_min=50)
    assert not any(f.kind == "count-drop" for f in findings)
