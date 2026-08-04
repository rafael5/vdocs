"""RR.3 — a parent heading stops displacing the child that holds the content.

MEASURED on the production collection before writing any of this: 784 parent/child title-twin
pairs exist; 120 have a searchable parent whose whole indexed text is under 300 characters while
its child carries at least 3× more; and probing each with the child's own heading as the query,
**68 return the parent ahead of the child** — often far ahead (child at rank 15 while the parent
sits at 1). VBECS alone contributes 71 of the structural pairs, an artefact of its use-case-numbered
headings ("… UC_61" above "…").

The fix reorders; it never excludes. Making parent lead-ins unsearchable is what made 6,779
sections findable in the first place, and a parent that matches on its own still ranks on its own.
"""

from __future__ import annotations

from vdocs.server import search_pure as sp


def _hit(section_id, title, section_path, body_len, **kw):
    return {"section_id": section_id, "section_title": title, "section_path": section_path,
            "body_len": body_len, **kw}  # fmt: skip


PARENT = _hit(
    "VBECS/ug/accept-orders-cancel-a-pending-order-uc_61",
    "Accept Orders: Cancel a Pending Order UC_61",
    "Processing Orders",
    118,
)
CHILD = _hit(
    "VBECS/ug/accept-orders-cancel-a-pending-order",
    "Accept Orders: Cancel a Pending Order",
    "Processing Orders > Accept Orders: Cancel a Pending Order UC_61",
    1769,
)


def test_a_restating_parent_is_placed_behind_its_own_child() -> None:
    out = sp.demote_restating_parents([PARENT, CHILD])
    assert [h["section_id"] for h in out] == [CHILD["section_id"], PARENT["section_id"]]


def test_the_child_is_promoted_into_the_parents_slot_from_far_down() -> None:
    # The measured shape: the parent holds rank 1 while its child sits at 15. The child takes the
    # slot, so a caller reading a short list sees the substance instead of the restated heading.
    filler = [_hit(f"XX/d/s{i}", f"Other {i}", "XX", 900) for i in range(13)]
    out = sp.demote_restating_parents([PARENT, *filler, CHILD])
    assert out[0]["section_id"] == CHILD["section_id"]
    assert out[1]["section_id"] == PARENT["section_id"]
    assert [h["section_id"] for h in out[2:]] == [f["section_id"] for f in filler]


def test_a_parent_with_its_own_substantive_content_keeps_its_place() -> None:
    # The guard the plan asks for: only a parent whose indexed text is a short restatement is
    # demoted. A parent that says something of its own outranks its child on its own merits.
    substantive = {**PARENT, "body_len": 4200}
    out = sp.demote_restating_parents([substantive, CHILD])
    assert [h["section_id"] for h in out] == [substantive["section_id"], CHILD["section_id"]]


def test_an_unrelated_short_section_above_a_long_one_is_untouched() -> None:
    # Not a twin: different titles, and neither is the other's parent. Nothing moves — this rule
    # must not become a general "prefer longer sections" bias.
    short = _hit("XX/d/intro", "Introduction", "XX", 120)
    long_ = _hit("XX/d/detail", "Configuration Detail", "XX > Introduction", 5000)
    assert sp.demote_restating_parents([short, long_]) == [short, long_]


def test_a_parent_alone_in_the_results_is_left_alone() -> None:
    # Coverage is preserved: with no child to defer to, the parent is still the answer.
    assert sp.demote_restating_parents([PARENT]) == [PARENT]


def test_the_child_ahead_already_is_a_no_op() -> None:
    assert sp.demote_restating_parents([CHILD, PARENT]) == [CHILD, PARENT]


def test_reorder_is_stable_for_everything_it_does_not_touch() -> None:
    a = _hit("XX/d/a", "Alpha", "XX", 800)
    b = _hit("XX/d/b", "Beta", "XX", 800)
    assert sp.demote_restating_parents([a, b, PARENT, CHILD]) == [a, b, CHILD, PARENT]
