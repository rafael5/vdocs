"""Unit tests for `consolidate` pure core — version-group grouping + ordering + append-only
lineage (§6.6). Zero I/O: plain `Member` values in, plain dicts out.

Grounded in real-corpus shapes (catalog `anchor_key` = ``app:pkg:doc_code``; members of a group
differ by parsed ``patch_num`` even when the ``patch_ver`` string differs — e.g. ``OR*3*190`` vs
``OR*3.0*539`` — and a group can carry several members with an identical ``patch_id``, so ordering
needs a stable final tiebreaker).
"""

from __future__ import annotations

from vdocs.kernel.ids import anchor_key
from vdocs.stages.consolidate import consolidate_pure as cp


def _member(
    *,
    doc_slug: str,
    app="CPRS",
    pkg="OR",
    doc_code="RN",
    version="3.0",
    patch_id="",
    official_date="",
    source_sha256="",
    body_sha256="",
    revisions=(),
):
    ak = anchor_key(app, pkg, doc_code)
    return cp.Member(
        anchor_key=ak,
        app_code=app,
        pkg_ns=pkg,
        doc_code=doc_code,
        doc_slug=doc_slug,
        doc_id=f"{app}:{doc_slug}",
        version=version,
        patch_id=patch_id,
        patch_num=cp.parse_patch_num(patch_id),
        official_date=official_date,
        source_sha256=source_sha256,
        body_sha256=body_sha256,
        revisions=list(revisions),
    )


# --- anchor_key (the kernel primitive shared with catalog) ---


def test_anchor_key_formula():
    assert anchor_key("CPRS", "OR", "RN") == "CPRS:OR:RN"
    assert anchor_key("PRCA", "PRCA", "DIBR") == "PRCA:PRCA:DIBR"


def test_anchor_key_empty_without_doc_code():
    # version-free identity needs a doc_code; without one there is no version group (§9.4)
    assert anchor_key("CPRS", "OR", "") == ""


def test_anchor_key_folds_slug_stem_to_fix_b1_over_grouping():
    # B1: distinct Kernel guides share app:pkg:doc_code but must NOT share a version group —
    # the version-stripped slug stem keeps them apart.
    alerts = anchor_key("XU", "XU", "UG", "krn_8_0_dg_alerts_ug")
    hygiene = anchor_key("XU", "XU", "UG", "krn_8_0_dg_address_hygiene_ug")
    assert alerts == "XU:XU:UG:krn_dg_alerts_ug"
    assert hygiene == "XU:XU:UG:krn_dg_address_hygiene_ug"
    assert alerts != hygiene  # no longer collapsed into one XU:XU:UG group
    # but true versions of ONE doc (same stem) still share the key → still consolidate together
    v1 = anchor_key("ADT", "DG", "UM", "dg_5_3_1057_um")
    v2 = anchor_key("ADT", "DG", "UM", "dg_5_4_2000_um")
    assert v1 == v2 == "ADT:DG:UM:dg_um"


def test_official_date_prefers_revision_then_published():
    assert cp.official_date("2018-02", "2010-03") == "2018-02"  # revision table wins
    assert cp.official_date("", "2010-03") == "2010-03"  # no revision table → cover date fallback
    assert cp.official_date("", "") == ""  # neither → empty (genuinely undated)


# --- anchor_relpath (the version-free output path) ---


def test_anchor_relpath_is_version_free():
    # grouped docs collapse to one path keyed on pkg_ns + doc_code, not the versioned doc_slug
    assert cp.anchor_relpath("CPRS", "OR", "RN") == "CPRS/or_rn"
    assert cp.anchor_relpath("PRCA", "PRCA", "DIBR") == "PRCA/prca_dibr"


def test_anchor_relpath_standalone_doc_keeps_its_own_slug():
    # no doc_code ⇒ no version group ⇒ the doc is its own anchor at its own slug
    assert cp.anchor_relpath("ADT", "", "", doc_slug="some_doc") == "ADT/some_doc"


def test_anchor_relpath_uses_logical_doc_stem_so_distinct_guides_dont_collide():
    # B1: distinct guides under XU:XU:UG must NOT share an anchor path (was XU/xu_ug for all)
    a = cp.anchor_relpath("XU", "XU", "UG", doc_slug="krn_8_0_dg_alerts_ug")
    b = cp.anchor_relpath("XU", "XU", "UG", doc_slug="krn_8_0_dg_address_hygiene_ug")
    assert a == "XU/krn_dg_alerts_ug" and b == "XU/krn_dg_address_hygiene_ug" and a != b
    # versions of one doc share the (version-stable) stem path
    assert cp.anchor_relpath("ADT", "DG", "UM", doc_slug="dg_5_3_1057_um") == "ADT/dg_um"
    assert cp.anchor_relpath("ADT", "DG", "UM", doc_slug="dg_5_4_2000_um") == "ADT/dg_um"


# --- parse_patch_num ---


def test_parse_patch_num_variants():
    assert cp.parse_patch_num("OR*3*190") == 190
    assert cp.parse_patch_num("OR*3.0*539") == 539  # patch_ver string differs, patch_num governs
    assert cp.parse_patch_num("PRCA*4.5*321") == 321
    assert cp.parse_patch_num("OR*3*0") == 0  # an explicit patch 0 is a real number, not "missing"


def test_parse_patch_num_absent_is_none():
    assert cp.parse_patch_num("CPRS*3.0") is None  # no third segment → no patch number
    assert cp.parse_patch_num("") is None
    assert cp.parse_patch_num("OR*3*x") is None  # non-numeric → not a patch number


# --- group_by_anchor_key ---


def test_group_by_anchor_key_partitions_members():
    a = _member(doc_slug="a", doc_code="RN")
    b = _member(doc_slug="b", doc_code="RN")
    c = _member(doc_slug="c", doc_code="IG")
    groups = cp.group_by_anchor_key([a, b, c])
    assert set(groups) == {"CPRS:OR:RN", "CPRS:OR:IG"}
    assert [m.doc_slug for m in groups["CPRS:OR:RN"]] == ["a", "b"]
    assert [m.doc_slug for m in groups["CPRS:OR:IG"]] == ["c"]


def test_group_by_anchor_key_keeps_standalone_docs_separate():
    # two unrelated docs with no doc_code (empty anchor_key) must NOT collapse into one group
    x = _member(doc_slug="x", doc_code="")
    y = _member(doc_slug="y", doc_code="")
    groups = cp.group_by_anchor_key([x, y])
    assert len(groups) == 2
    assert all(len(v) == 1 for v in groups.values())


# --- order_members ---


def test_order_members_by_patch_num_oldest_first():
    members = [
        _member(doc_slug="p539", patch_id="OR*3.0*539"),
        _member(doc_slug="p190", patch_id="OR*3*190"),
        _member(doc_slug="p0", patch_id="OR*3*0"),
    ]
    assert [m.doc_slug for m in cp.order_members(members)] == ["p0", "p190", "p539"]


def test_order_members_base_doc_without_patch_sorts_first():
    base = _member(doc_slug="cprsig", patch_id="")  # no patch → the initial release
    patch = _member(doc_slug="p190", patch_id="OR*3*190")
    assert [m.doc_slug for m in cp.order_members([patch, base])] == ["cprsig", "p190"]


def test_order_members_tiebreaks_identical_patch_id_deterministically():
    # CPRS:CPRS:TM real case — several members share one patch_id; order must still be total
    m1 = _member(doc_slug="tm_b", patch_id="CPRS*3.0", official_date="2010-01")
    m2 = _member(doc_slug="tm_a", patch_id="CPRS*3.0", official_date="2010-01")
    m3 = _member(doc_slug="tm_c", patch_id="CPRS*3.0", official_date="2009-01")
    # oldest official_date first, then doc_slug as the final stable tiebreak
    assert [m.doc_slug for m in cp.order_members([m1, m2, m3])] == ["tm_c", "tm_a", "tm_b"]


# --- build_history ---


def test_build_history_flags_only_newest_is_latest():
    ordered = cp.order_members(
        [
            _member(doc_slug="v51", patch_id="DG*5.3*1", source_sha256="s51", body_sha256="b51"),
            _member(doc_slug="v52", patch_id="DG*5.3*2", source_sha256="s52", body_sha256="b52"),
            _member(doc_slug="v53", patch_id="DG*5.3*3", source_sha256="s53", body_sha256="b53"),
        ]
    )
    hist = cp.build_history("CPRS:OR:RN", ordered)
    assert hist["anchor_key"] == "CPRS:OR:RN"
    assert hist["member_count"] == 3
    assert [e["patch_id"] for e in hist["members"]] == ["DG*5.3*1", "DG*5.3*2", "DG*5.3*3"]
    assert [e["is_latest"] for e in hist["members"]] == [False, False, True]
    assert hist["members"][-1]["body_sha256"] == "b53"  # CAS ref to the retained newest body


def test_build_history_folds_member_revisions():
    rev = [{"date": "2023-05", "version": "WV*1.0*28", "change": "x"}]
    ordered = [_member(doc_slug="v1", patch_id="WV*1.0*28", revisions=rev)]
    hist = cp.build_history("WV:WV:UM", ordered)
    assert hist["members"][0]["revisions"] == rev  # each member's revisions.yaml is folded in


# --- merge_history (APPEND-ONLY, §6.6) ---


def test_merge_history_none_existing_returns_fresh():
    ordered = [_member(doc_slug="v1", patch_id="DG*5.3*1")]
    fresh = cp.build_history("CPRS:OR:RN", ordered)
    assert cp.merge_history(None, fresh) == fresh


def test_merge_history_appends_new_patch_preserving_prior_entries():
    a = _member(doc_slug="v1", patch_id="DG*5.3*1", source_sha256="s1", body_sha256="b1")
    b = _member(doc_slug="v2", patch_id="DG*5.3*2", source_sha256="s2", body_sha256="b2")
    existing = cp.build_history("CPRS:OR:RN", cp.order_members([a, b]))
    c = _member(doc_slug="v3", patch_id="DG*5.3*3", source_sha256="s3", body_sha256="b3")
    fresh = cp.build_history("CPRS:OR:RN", cp.order_members([a, b, c]))

    merged = cp.merge_history(existing, fresh)
    assert [e["patch_id"] for e in merged["members"]] == ["DG*5.3*1", "DG*5.3*2", "DG*5.3*3"]
    # prior captured facts are untouched (append-only); only the derived is_latest pointer moves
    assert merged["members"][0]["source_sha256"] == "s1"
    assert merged["members"][1]["body_sha256"] == "b2"
    assert [e["is_latest"] for e in merged["members"]] == [False, False, True]
    assert merged["member_count"] == 3


def test_merge_history_is_idempotent_on_unchanged_inputs():
    a = _member(doc_slug="v1", patch_id="DG*5.3*1")
    b = _member(doc_slug="v2", patch_id="DG*5.3*2")
    fresh = cp.build_history("CPRS:OR:RN", cp.order_members([a, b]))
    # re-running with the same membership rewrites nothing and adds nothing
    assert cp.merge_history(fresh, fresh) == fresh
