"""Property tests for `consolidate` pure invariants (§6.6, §12).

Hypothesis-generated version groups exercise two load-bearing properties: ``order_members`` is a
total, deterministic order, and ``merge_history`` is genuinely **append-only + idempotent** — a
fold of the same membership rewrites nothing, and folding a superset only ever appends.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from vdocs.stages.consolidate import consolidate_pure as cp


def _member(slug: str, num, date: str) -> cp.Member:
    patch_id = "NS*3.0" if num is None else f"NS*3.0*{num}"
    return cp.Member(
        anchor_key="A:B:C",
        app_code="A",
        pkg_ns="B",
        doc_code="C",
        doc_slug=slug,
        doc_id=f"A:{slug}",
        version="3.0",
        patch_id=patch_id,
        patch_num=num,
        official_date=date,
        source_sha256=f"s-{slug}",
        body_sha256=f"b-{slug}",
        revisions=[],
    )


# distinct slugs (the stable id) so a "group" is a set of distinct members
_members = st.lists(
    st.tuples(
        st.text(alphabet="abcdefghijklmnop", min_size=1, max_size=4),
        st.one_of(st.none(), st.integers(min_value=0, max_value=999)),
        st.sampled_from(["", "2018-01", "2020-06", "2023-09"]),
    ),
    min_size=1,
    max_size=8,
    unique_by=lambda t: t[0],
).map(lambda rows: [_member(s, n, d) for s, n, d in rows])


@given(_members)
def test_order_members_is_deterministic_and_total(members):
    once = [m.doc_slug for m in cp.order_members(members)]
    twice = [m.doc_slug for m in cp.order_members(list(reversed(members)))]
    assert once == twice  # order is independent of input order
    assert sorted(once) == sorted(m.doc_slug for m in members)  # a permutation — nothing dropped


@given(_members)
def test_merge_history_idempotent_on_same_membership(members):
    ordered = cp.order_members(members)
    fresh = cp.build_history("A:B:C", ordered)
    # folding the same chain into itself adds nothing and re-points is_latest identically
    assert cp.merge_history(fresh, fresh) == fresh


@given(_members, _members)
def test_merge_history_is_append_only(base_members, extra_members):
    existing = cp.build_history("A:B:C", cp.order_members(base_members))
    # the superset = the base members plus the extras (deduped by stable doc_id)
    by_id = {m.doc_id: m for m in [*base_members, *extra_members]}
    fresh = cp.build_history("A:B:C", cp.order_members(list(by_id.values())))
    merged = cp.merge_history(existing, fresh)

    def _facts(e):  # the captured facts, minus the derived is_latest pointer
        return {k: v for k, v in e.items() if k != "is_latest"}

    # every previously-captured member survives in its original position with facts untouched
    n = len(existing["members"])
    assert [_facts(e) for e in merged["members"][:n]] == [_facts(e) for e in existing["members"]]
    # exactly one newest, and the member set is the union (nothing dropped, nothing duplicated)
    assert sum(m["is_latest"] for m in merged["members"]) == 1
    assert {m["doc_id"] for m in merged["members"]} == set(by_id)
