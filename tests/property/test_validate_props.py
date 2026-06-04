"""Property tests for validate's pure cores — refs resolution + reconciliation (§5.2, §5.5, §12).

Invariants for any input:
  * resolve_refs only ever reports outbound keys, classes each non-resolved ref correctly, and
    never reports a ref that resolves to a live anchor;
  * reconcile surfaces exactly the absent-unexpected outcomes present in the manifests.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from vdocs.stages.validate import reconcile_pure as rc
from vdocs.stages.validate import refs_pure as rp

_slugs = st.lists(st.sampled_from(["a", "b", "c", "d"]), max_size=4, unique=True)
_targets = st.sampled_from(["a", "b", "c", "d", "gone", rp.UNRESOLVED])


@given(
    anchors=_slugs,
    # mix _Toc… (heading) and _Ref… (non-heading) bookmarks so both UNRESOLVED branches fire
    outbound=st.dictionaries(
        st.sampled_from(["_Toc1", "_Toc2", "_Ref1", "_Ref2"]), _targets, max_size=4
    ),
)
def test_resolve_refs_classifies_consistently(anchors, outbound):
    refs = {"doc_id": "x", "anchors": [{"slug": s} for s in anchors], "outbound": outbound}
    live = set(anchors)
    findings = rp.resolve_refs(refs)
    reported = {f.bookmark for f in findings}
    # only outbound keys are reported; a resolved (live, non-UNRESOLVED) target is never reported
    assert reported <= set(outbound)
    for bm, tgt in outbound.items():
        if tgt != rp.UNRESOLVED and tgt in live:
            assert bm not in reported
    for f in findings:
        if f.target == rp.UNRESOLVED:
            # _Toc… → recoverable UNMAPPED (C5 class); any other bookmark → EXPECTED_UNMAPPED
            is_toc = f.bookmark.startswith(rp.TOC_BOOKMARK_PREFIX)
            expect = rp.UNMAPPED if is_toc else rp.EXPECTED_UNMAPPED
        else:
            expect = rp.SEVERED
        assert f.kind == expect


@given(
    outcomes=st.lists(
        st.sampled_from(["captured", "absent-expected", "absent-unexpected", "failed"]),
        max_size=6,
    )
)
def test_reconcile_surfaces_every_absent_unexpected(outcomes):
    manifests = [
        {"doc_id": f"d{i}", "captures": {f"k{i}": {"outcome": o}}} for i, o in enumerate(outcomes)
    ]
    # small corpus + no prior → only the per-doc absent-unexpected findings can fire
    findings = rc.reconcile(
        manifests=manifests,
        current_counts={"documents": len(manifests)},
        prior_counts=None,
        corpus_min=50,
    )
    expected = sum(1 for o in outcomes if o == "absent-unexpected")
    assert sum(1 for f in findings if f.kind == rc.ABSENT_UNEXPECTED) == expected
