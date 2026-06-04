"""Unit tests for validate/refs_pure — outbound cross-ref resolution (§5.5, FF C5).

Resolve every outbound ref in a bundle's refs.yaml against its live anchor set; a target slug
absent from the live set is a SEVERED dead anchor (hard floor 0); an UNRESOLVED marker is the
already-flagged UNMAPPED class (bounded by the C5 cross-ref dead-anchor rate).
"""

from __future__ import annotations

from vdocs.stages.validate import refs_pure as rp


def _refs(anchors, outbound, doc_id="ADT/doc"):
    return {
        "doc_id": doc_id,
        "anchors": [{"slug": s, "title": s} for s in anchors],
        "outbound": outbound,
    }


def test_resolved_refs_yield_no_findings():
    refs = _refs(["intro", "setup"], {"_Toc1": "intro", "_Toc2": "setup"})
    assert rp.resolve_refs(refs) == []


def test_severed_ref_when_target_slug_not_live():
    # a ref pointing at a slug that is not in the live anchor set — the DITA severed-conref case
    refs = _refs(["intro"], {"_Toc1": "intro", "_Toc9": "gone-section"})
    findings = rp.resolve_refs(refs)
    assert [f.kind for f in findings] == [rp.SEVERED]
    assert findings[0].bookmark == "_Toc9" and findings[0].target == "gone-section"


def test_unresolved_toc_bookmark_is_unmapped_not_severed():
    # a _Toc… bookmark targets a heading → the C5-bounded, recoverable resolvability class
    refs = _refs(["intro"], {"_Toc1": "intro", "_Toc7": rp.UNRESOLVED})
    findings = rp.resolve_refs(refs)
    assert [f.kind for f in findings] == [rp.UNMAPPED]
    assert findings[0].bookmark == "_Toc7"


def test_unresolved_ref_bookmark_is_expected_unmapped():
    # a _Ref… bookmark is a Word cross-reference to a NON-heading target (figure/table/numbered
    # item/page span) — unmappable to a heading anchor by construction. It must be classified
    # EXPECTED_UNMAPPED (reported, outside the C5 heading-resolvability rate), not lumped with the
    # recoverable _Toc class (corpus triage 2026-06-03: 0 of 844 _Ref refs ever resolve).
    refs = _refs(["intro"], {"_Ref123": rp.UNRESOLVED, "_Toc7": rp.UNRESOLVED})
    findings = {f.bookmark: f.kind for f in rp.resolve_refs(refs)}
    assert findings == {"_Ref123": rp.EXPECTED_UNMAPPED, "_Toc7": rp.UNMAPPED}


def test_live_anchor_slugs_extracted():
    refs = _refs(["a", "b", "c"], {})
    assert rp.live_anchor_slugs(refs) == {"a", "b", "c"}


def test_empty_outbound_is_clean():
    assert rp.resolve_refs(_refs(["a"], {})) == []


def test_missing_keys_do_not_crash():
    # a refs.yaml with no anchors/outbound (defensive) resolves to nothing
    assert rp.resolve_refs({"doc_id": "x"}) == []


def test_ref_to_existing_empty_slug_anchor_is_not_severed():
    # real-corpus case: a heading titled ";" slugifies to "" — a degenerate but REAL anchor row.
    # A ref targeting it resolves (the heading exists); it must NOT be mis-flagged as severed.
    refs = {
        "doc_id": "AR_WS/wstech",
        "anchors": [{"slug": "intro"}, {"slug": "", "title": ";"}],
        "outbound": {"_Toc1": "intro", "_Toc2": ""},
    }
    assert rp.resolve_refs(refs) == []
    assert "" in rp.live_anchor_slugs(refs)
