"""Property tests for capture_pure — typed capture-attempt classification (§6.4, §12).

Invariants that must hold for *any* combination of detector counts + residue signals:
  * every capture kind is always classified (no kind silently omitted);
  * every outcome is one of the four typed verdicts;
  * a positive count always yields `captured` (a present sidecar is never mis-reported absent);
  * scan_residue is deterministic + idempotent on the body.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from vdocs.stages.normalize import capture_pure as cp

_OUTCOMES = {cp.CAPTURED, cp.FAILED, cp.ABSENT_EXPECTED, cp.ABSENT_UNEXPECTED}
_KINDS = {"revisions", "tables", "refs", "toc", "title_date"}
_TOC_TITLES = frozenset({"table of contents", "contents"})

_counts = st.integers(min_value=0, max_value=50)
_bools = st.booleans()


@given(
    revisions_count=_counts,
    revision_failed=_bools,
    tables_count=_counts,
    refs_count=_counts,
    toc_count=_counts,
    title_date_captured=_bools,
    rev_h=_bools,
    toc_h=_bools,
    head=_bools,
    qtables=_counts,
)
def test_classify_total_and_typed(
    revisions_count,
    revision_failed,
    tables_count,
    refs_count,
    toc_count,
    title_date_captured,
    rev_h,
    toc_h,
    head,
    qtables,
):
    residue = cp.Residue(
        revision_heading_present=rev_h,
        legacy_toc_heading_present=toc_h,
        heading_present=head,
        qualifying_table_count=qtables,
    )
    out = cp.classify(
        revisions_count=revisions_count,
        revision_failed=revision_failed,
        tables_count=tables_count,
        refs_count=refs_count,
        toc_count=toc_count,
        title_date_captured=title_date_captured,
        residue=residue,
    )
    assert set(out) == _KINDS  # every kind classified
    assert all(o.outcome in _OUTCOMES for o in out.values())  # every outcome typed
    # a positive count is always `captured` — a present sidecar is never mis-reported as absent
    for kind, count in (
        ("revisions", revisions_count),
        ("tables", tables_count),
        ("refs", refs_count),
        ("toc", toc_count),
    ):
        if count > 0:
            assert out[kind] == cp.CaptureOutcome(cp.CAPTURED, count)


@given(
    headings=st.lists(
        st.sampled_from(["## Setup", "## Change History", "## Table of Contents", "Prose line."]),
        max_size=8,
    )
)
def test_scan_residue_idempotent(headings):
    body = "# Title\n\n" + "\n\n".join(headings) + "\n"
    assert cp.scan_residue(body, _TOC_TITLES) == cp.scan_residue(body, _TOC_TITLES)
