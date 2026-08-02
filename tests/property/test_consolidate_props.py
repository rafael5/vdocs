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


@given(_members, st.lists(st.booleans(), min_size=8, max_size=8))
def test_merge_history_never_discards_a_captured_body(members, changed):
    """P5.1's thesis as a property: re-processing any subset of a group's members refreshes the
    top-level facts, and **every** previously-captured ``body_sha256`` is still reachable — in
    place or demoted onto ``superseded``. Nothing is discarded, ever."""
    ordered = cp.order_members(members)
    existing = cp.build_history("A:B:C", ordered)
    fresh = cp.build_history(
        "A:B:C",
        [
            cp.Member(**{**m.__dict__, "body_sha256": f"{m.body_sha256}-NEW"}) if flag else m
            for m, flag in zip(ordered, changed, strict=False)
        ],
    )
    merged = cp.merge_history(existing, fresh)

    by_id = {e["doc_id"]: e for e in merged["members"]}
    for old, flag in zip(existing["members"], changed, strict=False):
        entry = by_id[old["doc_id"]]
        expected = f"{old['body_sha256']}-NEW" if flag else old["body_sha256"]
        assert entry["body_sha256"] == expected  # the record describes the CURRENT body
        captured = [entry["body_sha256"], *(p["body_sha256"] for p in entry.get("superseded", []))]
        assert old["body_sha256"] in captured  # …and the prior one is still on file
    # a second fold of the same fresh chain adds nothing (no per-run growth)
    assert cp.merge_history(merged, fresh) == merged


@given(_members, _members)
def test_merge_history_is_append_only(base_members, extra_members):
    existing = cp.build_history("A:B:C", cp.order_members(base_members))
    # the superset = the base members plus the extras (deduped by stable doc_id)
    by_id = {m.doc_id: m for m in [*base_members, *extra_members]}
    fresh = cp.build_history("A:B:C", cp.order_members(list(by_id.values())))
    merged = cp.merge_history(existing, fresh)

    def _facts(e):  # the captured facts, minus the derived is_latest pointer
        return {k: v for k, v in e.items() if k != "is_latest"}

    # every previously-captured member survives with facts untouched (a late-arriving OLDER
    # patch may re-order the lineage, so match by doc_id, not position)
    merged_facts = {e["doc_id"]: _facts(e) for e in merged["members"]}
    for e in existing["members"]:
        assert merged_facts[e["doc_id"]] == _facts(e)
    # lineage stays oldest → newest by the canonical key
    keys = [cp._entry_sort_key(e) for e in merged["members"]]
    assert keys == sorted(keys)
    # exactly one newest — the LAST member — and the set is the union (nothing dropped/duplicated)
    flags = [m["is_latest"] for m in merged["members"]]
    assert flags == [False] * (len(flags) - 1) + [True]
    assert {m["doc_id"] for m in merged["members"]} == set(by_id)
