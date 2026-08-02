"""Unit tests for the `validate` lineage check (Step 4 extension, P5.2).

The invariant: a gold bundle's `history.yaml` entry flagged `is_latest` must record the sha256 of
the `body.md` sitting beside it. `bundle.yaml` cannot see this — it is recomputed from the parts on
disk, so a lineage that misdescribes those parts verifies happily (audit [S9]a). This is the check
that makes that class of drift impossible to ship.
"""

from __future__ import annotations

import hashlib

from vdocs.stages.validate import lineage_pure as lp

BODY = b"# Doc\n\nthe body actually in the bundle\n"
SHA = hashlib.sha256(BODY).hexdigest()


def _history(*members):
    return {"anchor_key": "ADT:ADT:UM", "member_count": len(members), "members": list(members)}


def _member(sha, *, is_latest=True, doc_id="ADT:doc"):
    return {"doc_id": doc_id, "body_sha256": sha, "is_latest": is_latest}


def test_latest_member_matching_the_body_is_clean():
    assert lp.check_lineage(_history(_member(SHA)), BODY) == []


def test_only_the_latest_member_is_checked():
    # prior members legitimately record OTHER bodies — they are the retained versions
    hist = _history(_member("older-sha", is_latest=False), _member(SHA))
    assert lp.check_lineage(hist, BODY) == []


def test_stale_latest_member_is_a_blocking_finding_naming_the_doc_id():
    (finding,) = lp.check_lineage(_history(_member("b1-STALE", doc_id="PSJ:psj_5_tm")), BODY)
    assert finding.kind == lp.STALE_LINEAGE
    assert finding.doc_id == "PSJ:psj_5_tm"
    assert "b1-STALE" in finding.detail and SHA[:12] in finding.detail


def test_a_superseded_record_does_not_excuse_a_stale_latest_member():
    # P5.1 demotes prior facts onto `superseded`; the TOP-LEVEL record is what must be current,
    # so finding the real sha one level down is not a pass
    entry = {**_member("b1-STALE"), "superseded": [{"body_sha256": SHA}]}
    (finding,) = lp.check_lineage(_history(entry), BODY)
    assert finding.kind == lp.STALE_LINEAGE


def test_history_with_no_latest_member_is_unverifiable_not_skipped():
    (finding,) = lp.check_lineage(_history(_member(SHA, is_latest=False)), BODY)
    assert finding.kind == lp.UNVERIFIABLE_LINEAGE
    assert "no member" in finding.detail


def test_two_members_flagged_latest_is_unverifiable():
    hist = _history(_member(SHA, doc_id="ADT:a"), _member(SHA, doc_id="ADT:b"))
    (finding,) = lp.check_lineage(hist, BODY)
    assert finding.kind == lp.UNVERIFIABLE_LINEAGE
    assert "2 members" in finding.detail


def test_absent_history_is_unverifiable_never_a_silent_pass():
    # a gold bundle with no history.yaml at all: absence is UNKNOWN, never OK (the P3.3 lesson)
    assert lp.check_lineage(None, BODY)[0].kind == lp.UNVERIFIABLE_LINEAGE
    assert lp.check_lineage({}, BODY)[0].kind == lp.UNVERIFIABLE_LINEAGE
    assert lp.check_lineage(_history(), BODY)[0].kind == lp.UNVERIFIABLE_LINEAGE


def test_a_member_without_a_recorded_sha_is_unverifiable():
    (finding,) = lp.check_lineage(_history({"doc_id": "ADT:doc", "is_latest": True}), BODY)
    assert finding.kind == lp.UNVERIFIABLE_LINEAGE


# --- retained bodies: the prior members are the whole point of a replay source (adversarial
# --- review 2026-08-02 — P5.2 verified only the `is_latest` member, so the bodies the lineage
# --- exists to replay were checked by nothing at all).


def test_a_missing_retained_body_is_a_blocking_finding():
    hist = _history(_member("older", is_latest=False, doc_id="ADT:v1"), _member(SHA))
    findings = lp.check_lineage(hist, BODY, retained={SHA}.__contains__)
    assert [f.kind for f in findings] == [lp.MISSING_RETAINED_BODY]
    assert findings[0].doc_id == "ADT:v1" and "older" in findings[0].detail


def test_a_superseded_entry_body_must_be_retained_too():
    # P5.1 demotes prior facts rather than deleting them — the promise is that the body is still
    # in the CAS "by construction". This is the check that makes it a fact rather than a promise.
    entry = {**_member(SHA), "superseded": [{"doc_id": "ADT:doc", "body_sha256": "demoted"}]}
    findings = lp.check_lineage(_history(entry), BODY, retained={SHA}.__contains__)
    assert [f.kind for f in findings] == [lp.MISSING_RETAINED_BODY]
    assert "demoted" in findings[0].detail


def test_all_bodies_retained_is_clean():
    entry = {**_member(SHA), "superseded": [{"doc_id": "ADT:doc", "body_sha256": "old"}]}
    hist = _history(_member("older", is_latest=False, doc_id="ADT:v1"), entry)
    assert lp.check_lineage(hist, BODY, retained={SHA, "older", "old"}.__contains__) == []


def test_retention_is_not_checked_when_the_store_is_not_supplied():
    # the pure function stays pure: no `retained` predicate ⇒ no claim about the CAS
    hist = _history(_member("older", is_latest=False, doc_id="ADT:v1"), _member(SHA))
    assert lp.check_lineage(hist, BODY) == []
