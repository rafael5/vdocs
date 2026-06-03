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


def test_unresolved_marker_is_unmapped_not_severed():
    refs = _refs(["intro"], {"_Toc1": "intro", "_Toc7": rp.UNRESOLVED})
    findings = rp.resolve_refs(refs)
    assert [f.kind for f in findings] == [rp.UNMAPPED]
    assert findings[0].bookmark == "_Toc7"


def test_live_anchor_slugs_extracted():
    refs = _refs(["a", "b", "c"], {})
    assert rp.live_anchor_slugs(refs) == {"a", "b", "c"}


def test_empty_outbound_is_clean():
    assert rp.resolve_refs(_refs(["a"], {})) == []


def test_missing_keys_do_not_crash():
    # a refs.yaml with no anchors/outbound (defensive) resolves to nothing
    assert rp.resolve_refs({"doc_id": "x"}) == []
