"""Unit tests for fetch pure logic — the selection surface + index (§5.6, §8 fetch, §16).

The pipeline is **DOCX-only** (§1): PDF is out of scope, so there is no format fallback and
PDF-only documents are never fetch targets. Selection (§5.6) narrows the genuine in-scope
inventory; it never reaches noise or out-of-scope rows.
"""

from vdocs.models.catalog import EnrichedRecord
from vdocs.stages.fetch import fetch_pure as fp

ALL = fp.Selection(all_=True)


def test_url_ext():
    assert fp.url_ext("https://va.gov/a/b.DOCX") == "docx"
    assert fp.url_ext("https://va.gov/a/b") == ""


def _rec(
    slug,
    fmt="docx",
    *,
    noise="",
    app="ADT",
    app_full="Admission Discharge Transfer (ADT)",
    section="CLIN",
    status="active",
    doc_code="DIBR",
    group_key="ADT:DG:5.3",
    anchor_key="ADT:DG:DIBR",
):
    return EnrichedRecord(
        doc_title="T",
        doc_url=f"https://va.gov/d/{slug}.{fmt}",
        doc_filename=f"{slug}.{fmt}",
        doc_format=fmt,
        app_name_abbrev=app,
        app_name_full=app_full,
        section_code=section,
        app_status=status,
        doc_slug=slug,
        doc_code=doc_code,
        group_key=group_key,
        anchor_key=anchor_key,
        noise_type=noise,
    )


# --- the admission gate (app scope + doc-type policy) ---

_VISTA_GATE = fp.GatePolicy(
    allowed_system_prefixes=("VistA",),
    denied_app_status=frozenset({"decommissioned"}),
    omitted_doc_codes=frozenset({"RN", "DIBR"}),
)


def test_gate_app_scope_admits_vista_denies_cots_and_decommissioned():
    g = _VISTA_GATE
    assert g.app_in_scope(_rec("a", doc_code="UM").model_copy(update={"system_type": "VistA"}))
    assert g.app_in_scope(
        _rec("a", doc_code="UM").model_copy(update={"system_type": "VistA + GUI"})
    )
    assert not g.app_in_scope(
        _rec("a", doc_code="UM").model_copy(update={"system_type": "Web client"})
    )
    assert not g.app_in_scope(
        _rec("a", doc_code="UM").model_copy(
            update={"system_type": "VistA", "app_status": "decommissioned"}
        )
    )


def test_gate_doctype_policy_omits_listed_codes():
    g = _VISTA_GATE
    keep = _rec("a", doc_code="UM").model_copy(update={"system_type": "VistA"})
    omit = _rec("a", doc_code="RN").model_copy(update={"system_type": "VistA"})
    assert g.doctype_kept(keep) and g.admits(keep)
    assert not g.doctype_kept(omit) and not g.admits(omit)


def test_select_fetch_targets_enforces_gate_even_under_all():
    recs = [
        _rec("keep_um", doc_code="UM").model_copy(update={"system_type": "VistA"}),
        _rec("omit_rn", doc_code="RN").model_copy(update={"system_type": "VistA"}),  # omitted type
        _rec("cots_um", doc_code="UM").model_copy(
            update={"system_type": "COTS product"}
        ),  # OOS app
    ]
    # without a policy: all three genuine docx rows are targets (back-compat default)
    assert len(fp.select_fetch_targets(recs, ALL)) == 3
    # with the gate: only the in-scope VistA + kept-doctype row survives
    gated = fp.select_fetch_targets(recs, ALL, _VISTA_GATE)
    assert [t.doc_slug for t in gated] == ["keep_um"]


# --- the two always-on narrowing filters (noise gate + DOCX scope, §5.6 invariants) ---


def test_select_all_picks_docx_per_logical_doc():
    # a logical doc published as both DOCX and PDF → the DOCX record is the only target
    docs = [_rec("dg_5_3_1057_dibr", "pdf"), _rec("dg_5_3_1057_dibr", "docx")]
    targets = fp.select_fetch_targets(docs, ALL)
    assert len(targets) == 1
    assert targets[0].doc_format == "docx"


def test_select_excludes_pdf_only_doc():
    # PDF is out of scope (§1): a doc with no DOCX representation is never a target
    assert fp.select_fetch_targets([_rec("only_pdf", "pdf")], ALL) == []


def test_select_excludes_noise_even_under_all():
    # chrome/forms (noise_type set) are never fetched — even --all only sees green rows (§9.5)
    docs = [_rec("vba_form_x", noise="vba_form"), _rec("real_doc")]
    assert [t.doc_slug for t in fp.select_fetch_targets(docs, ALL)] == ["real_doc"]


# --- the no-blind-download default (§5.6) ---


def test_empty_selection_matches_nothing():
    assert fp.Selection().is_empty
    assert fp.select_fetch_targets([_rec("a"), _rec("b")], fp.Selection()) == []


def test_all_is_not_empty():
    assert not ALL.is_empty


# --- dimension filters: AND across dimensions, OR within (§5.6) ---


def test_app_filter_by_code_and_full_name_substring():
    adt = _rec("a", app="ADT", app_full="Admission Discharge Transfer (ADT)")
    lab = _rec("b", app="LR", app_full="Laboratory (LR)", anchor_key="LR:LAB:UM")
    sel_code = fp.Selection(apps=frozenset({"ADT"}))
    assert [t.doc_slug for t in fp.select_fetch_targets([adt, lab], sel_code)] == ["a"]
    sel_name = fp.Selection(apps=frozenset({"Laboratory"}))  # substring of app_name_full
    assert [t.doc_slug for t in fp.select_fetch_targets([adt, lab], sel_name)] == ["b"]


def test_or_within_dimension():
    adt = _rec("a", app="ADT", anchor_key="ADT:DG:DIBR")
    lab = _rec("b", app="LR", anchor_key="LR:LAB:UM")
    sel = fp.Selection(apps=frozenset({"ADT", "LR"}))
    assert {t.doc_slug for t in fp.select_fetch_targets([adt, lab], sel)} == {"a", "b"}


def test_and_across_dimensions():
    # section CLIN AND doc-type UM → only the row matching both
    a = _rec("a", section="CLIN", doc_code="UM", anchor_key="ADT:DG:UM")
    b = _rec("b", section="CLIN", doc_code="DIBR", anchor_key="ADT:DG:DIBR")
    c = _rec("c", section="INFRA", doc_code="UM", anchor_key="LR:DG:UM")
    sel = fp.Selection(sections=frozenset({"CLIN"}), doc_types=frozenset({"UM"}))
    assert [t.doc_slug for t in fp.select_fetch_targets([a, b, c], sel)] == ["a"]


def test_section_status_group_and_id_dimensions():
    rec = _rec("a", section="CLIN", status="decommissioned", group_key="ADT:DG:5.3")
    assert fp.select_fetch_targets([rec], fp.Selection(sections=frozenset({"CLIN"})))
    assert fp.select_fetch_targets([rec], fp.Selection(statuses=frozenset({"decommissioned"})))
    assert not fp.select_fetch_targets([rec], fp.Selection(statuses=frozenset({"active"})))
    assert fp.select_fetch_targets([rec], fp.Selection(groups=frozenset({"ADT:DG:5.3"})))
    assert fp.select_fetch_targets([rec], fp.Selection(groups=frozenset({"ADT:DG:DIBR"})))  # anchor
    assert not fp.select_fetch_targets([rec], fp.Selection(groups=frozenset({"OTHER:X:9.9"})))
    assert fp.select_fetch_targets([rec], fp.Selection(ids=frozenset({"ADT:a"})))


# --- version completeness (§5.6 invariant 2): selecting one version pulls the whole lineage ---


def test_selecting_one_doc_id_pulls_every_version_in_its_anchor_group():
    v1 = _rec("dg_5_3_1_um", group_key="ADT:DG:5.3", anchor_key="ADT:DG:UM", doc_code="UM")
    v2 = _rec("dg_5_4_2_um", group_key="ADT:DG:5.4", anchor_key="ADT:DG:UM", doc_code="UM")
    other = _rec("dg_5_3_1_dibr", anchor_key="ADT:DG:DIBR", doc_code="DIBR")
    # select only v1 by id → both versions of the UM anchor come along, the DIBR anchor does not
    sel = fp.Selection(ids=frozenset({"ADT:dg_5_3_1_um"}))
    got = {t.doc_slug for t in fp.select_fetch_targets([v1, v2, other], sel)}
    assert got == {"dg_5_3_1_um", "dg_5_4_2_um"}


def test_unclassified_row_with_no_anchor_is_selected_as_a_singleton():
    # a genuine row with no anchor_key (doc_code unresolved) still matches directly, alone
    rec = _rec("loose", doc_code="", anchor_key="")
    sel = fp.Selection(ids=frozenset({"ADT:loose"}))
    assert [t.doc_slug for t in fp.select_fetch_targets([rec], sel)] == ["loose"]


# --- selection fingerprint (§5.6/§7.3): order-independent, value-sensitive ---


def test_selection_fingerprint_is_order_independent():
    a = fp.Selection(apps=frozenset({"ADT", "LR"}), doc_types=frozenset({"UM"}))
    b = fp.Selection(apps=frozenset({"LR", "ADT"}), doc_types=frozenset({"UM"}))
    assert a.fingerprint() == b.fingerprint()


def test_selection_fingerprint_changes_with_the_predicate():
    base = fp.Selection(apps=frozenset({"ADT"}))
    assert base.fingerprint() != fp.Selection(apps=frozenset({"ADT", "LR"})).fingerprint()
    assert base.fingerprint() != fp.Selection().fingerprint()
    assert base.fingerprint() != ALL.fingerprint()


# --- index entry shape (unchanged) ---


def test_index_entry_shape():
    entry = fp.index_entry(
        app_code="ADT", doc_slug="x_um", title="T", source_url="https://va.gov/x.docx", ext="docx"
    )
    assert entry == {
        "app_code": "ADT",
        "doc_slug": "x_um",
        "title": "T",
        "source_url": "https://va.gov/x.docx",
        "ext": "docx",
    }
