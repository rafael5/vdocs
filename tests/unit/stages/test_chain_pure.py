"""Unit tests for the acquisition-chain reconciliation (P1.2, audit R-3).

The audit's systemic finding: every seam from the admission gate to the silver tree
*self*-reports, and **no gate joins them**. Six documents measurably fell out of
`raw/index.json` (sha-keyed collapse) and raised a finding nowhere. These tests pin the join
itself — one COUNT chain, five seams — so a silent loss of that whole class is impossible.
"""

from vdocs.stages.validate import chain_pure as cp

# A healthy chain: everything admitted was fetched, indexed, converted and normalized.
HEALTHY = {
    "admitted": {"ADT:a_um", "ADT:b_tm"},
    "fetched": {"ADT:a_um", "ADT:b_tm"},
    "raw_index": {"ADT:a_um", "ADT:b_tm"},
    "converted": {"ADT:a_um", "ADT:b_tm"},
    "normalized": {"ADT:a_um", "ADT:b_tm"},
}


def _kinds(findings):
    return sorted(f.kind for f in findings)


def test_a_healthy_chain_has_no_findings():
    assert cp.reconcile_chain(**HEALTHY) == []


def test_a_fetched_doc_the_gate_no_longer_admits_is_a_finding():
    # audit R-10: the corpus over-states the live library until the doc is reconciled away.
    state = HEALTHY | {
        "fetched": HEALTHY["fetched"] | {"LR:old_um"},
        "raw_index": HEALTHY["raw_index"] | {"LR:old_um"},
        "converted": HEALTHY["converted"] | {"LR:old_um"},
        "normalized": HEALTHY["normalized"] | {"LR:old_um"},
    }
    findings = cp.reconcile_chain(**state)
    assert _kinds(findings) == [cp.FETCHED_NOT_ADMITTED]
    assert findings[0].doc_id == "LR:old_um"


def test_a_fetched_doc_missing_from_the_raw_index_is_a_finding():
    # THE measured defect (six docs): fetched, reported fetched, but no index entry → no bundle.
    state = HEALTHY | {
        "raw_index": {"ADT:a_um"},
        "converted": {"ADT:a_um"},
        "normalized": {"ADT:a_um"},
    }
    findings = cp.reconcile_chain(**state)
    assert cp.FETCHED_NOT_INDEXED in _kinds(findings)
    assert any(f.doc_id == "ADT:b_tm" for f in findings)


def test_an_index_entry_with_no_fetched_acquisition_is_a_finding():
    # the inverse seam: an entry the acquisitions cannot account for (hand-edited / stale file).
    state = HEALTHY | {"raw_index": HEALTHY["raw_index"] | {"ADT:ghost_um"}}
    findings = cp.reconcile_chain(**state)
    assert cp.INDEXED_NOT_FETCHED in _kinds(findings)
    assert any(f.doc_id == "ADT:ghost_um" for f in findings)


def test_an_indexed_doc_with_no_converted_bundle_is_a_finding():
    state = HEALTHY | {"converted": {"ADT:a_um"}, "normalized": {"ADT:a_um"}}
    findings = cp.reconcile_chain(**state)
    assert cp.INDEXED_NOT_CONVERTED in _kinds(findings)


def test_the_silver_trees_must_agree_in_both_directions():
    dropped = cp.reconcile_chain(**(HEALTHY | {"normalized": {"ADT:a_um"}}))
    assert cp.CONVERTED_NOT_NORMALIZED in _kinds(dropped)

    orphan = cp.reconcile_chain(**(HEALTHY | {"normalized": HEALTHY["normalized"] | {"X:y"}}))
    assert cp.NORMALIZED_NOT_CONVERTED in _kinds(orphan)


def test_findings_are_deterministic_and_carry_a_readable_detail():
    state = HEALTHY | {"raw_index": set(), "converted": set(), "normalized": set()}
    findings = cp.reconcile_chain(**state)
    assert findings == sorted(findings, key=lambda f: (f.kind, f.doc_id))  # stable report order
    assert all(f.detail for f in findings)
    # every fetched doc is reported individually — a count alone hides WHICH doc was lost
    assert {f.doc_id for f in findings if f.kind == cp.FETCHED_NOT_INDEXED} == HEALTHY["fetched"]
