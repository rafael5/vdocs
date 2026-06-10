"""Unit tests for the pure enrichment engine (Phase C) — ported v1 logic, made pure.

Drives each sub-function against the spec's documented examples and ordering traps (§4, §6,
§8), plus an end-to-end ``enrich_rows`` over a small corpus exercising the corpus-global
passes: companion pairing, shared-URL noise, peer inference, manual overrides, canonical
label collapse, anchor_key, and system classification. Uses the real in-repo registries.
"""

from __future__ import annotations

import pytest

from vdocs.config import Settings
from vdocs.stages.catalog import enrich_pure as ep
from vdocs.stages.catalog import registries as rg


@pytest.fixture(scope="module")
def reg():
    return rg.load_registries(Settings().registries)


@pytest.fixture(scope="module")
def compiled(reg):
    return ep.compile_doc_types(reg.doc_type_patterns)


# --- small helpers ----------------------------------------------------------
def _raw(title, filename, app_name="Admission Discharge Transfer (ADT)", **kw):
    base = {
        "doc_title": title,
        "filename": filename,
        "file_ext": "." + filename.rsplit(".", 1)[-1],
        "app_name": app_name,
        "section_name": "Clinical",
        "app_status": "active",
        "decommission_date": "",
        "doc_url": f"https://www.va.gov/vdl/documents/Clinical/ADT/{filename}",
        "app_url": "https://www.va.gov/vdl/application.asp?appid=55",
    }
    base.update(kw)
    return base


# --- patch identity (C1) ----------------------------------------------------
def _parse(reg, compiled, title, filename, abbrev=""):
    """parse_row on a post-pass1 row (doc_filename + app_name_abbrev set)."""
    row = {"doc_title": title, "doc_filename": filename, "app_name_abbrev": abbrev}
    return ep.parse_row(row, compiled, reg.slug_suffix_map, reg.app_specific_suffix)


def test_patch_a_full_identity(reg, compiled):
    p = _parse(
        reg,
        compiled,
        "DG*5.3*1057 Deployment, Installation, Back-Out, and Rollback Guide",
        "x.docx",
    )
    assert (p["pkg_ns"], p["patch_ver"], p["patch_num"]) == ("DG", "5.3", "1057")
    assert p["doc_code"] == "DIBR"
    assert p["multi_ns"] == "0"


def test_multi_namespace(reg, compiled):
    p = _parse(reg, compiled, "SD*5.3*603/WEBP*1*1 Installation Guide", "x.docx")
    assert p["multi_ns"] == "1"
    assert p["patch_id_full"] == "SD*5.3*603/WEBP*1*1"
    assert p["pkg_ns"] == "SD" and p["patch_num"] == "603"


def test_patch_b_version_and_filename_patch(reg, compiled):
    # non-VistA version form + filename patch number
    p = _parse(reg, compiled, "PAID Version 4.0 User Manual", "prs_4_0_p123_um.docx", abbrev="PRS")
    assert p["patch_ver"] == "4.0"
    assert p["patch_num"] == "123"
    assert p["doc_code"] == "UM"


def test_vba_form_override(reg, compiled):
    p = _parse(reg, compiled, "21-0958 Notice of Disagreement", "vba210958.pdf")
    assert p["doc_code"] == "FORM" and p["doc_label"] == "VBA Form"
    assert p["pkg_ns"] == "" and p["patch_ver"] == ""


# --- doc-type classification ordering traps (C2) ---------------------------
def test_doc_type_ordering_traps(compiled):
    assert (
        ep.classify_doc_type("Deployment, Installation, Back-Out, and Rollback Guide", compiled)[0]
        == "DIBR"
    )
    assert ep.classify_doc_type("Installation Guide", compiled)[0] == "IG"
    assert ep.classify_doc_type("User Manual", compiled)[0] == "UM"
    assert ep.classify_doc_type("User's Guide", compiled)[0] == "UG"  # possessive
    assert ep.classify_doc_type("nothing here", compiled) == ("", "")
    # bare "TM" abbreviation (last-resort) → Technical Manual (e.g. "… TM ADDENDUM 941")
    assert ep.classify_doc_type("SD PIMS Version 5.3 TM ADDENDUM 941", compiled)[0] == "TM"
    # …but a full-phrase doc-type still wins over the bare abbrev (ordering safety)
    assert ep.classify_doc_type("Foo TM User Manual", compiled)[0] == "UM"


def test_filename_suffix_tg_is_training_not_technical(reg):
    assert ep.classify_by_filename(
        "foo_tg.docx", "", reg.slug_suffix_map, reg.app_specific_suffix
    ) == (
        "TRG",
        "Training Guide",
    )


def test_filename_app_specific_suffix(reg):
    assert (
        ep.classify_by_filename(
            "prc_signed.docx", "PRC", reg.slug_suffix_map, reg.app_specific_suffix
        )[0]
        == "POM"
    )
    assert (
        ep.classify_by_filename(
            "tmp_signed.docx", "TMP", reg.slug_suffix_map, reg.app_specific_suffix
        )[0]
        == "RS"
    )


# --- text fixers (C3) -------------------------------------------------------
def test_fix_mojibake_and_typo(reg):
    assert ep.fix_mojibake("") == ""
    text, aliases = ep.apply_typo_corrections(
        "Staph Aurerus Tracking", "doc_title", reg.typo_corrections
    )
    assert text == "Staph Aureus Tracking"
    assert aliases == ["Staph Aurerus"]


# --- small derivations ------------------------------------------------------
def test_normalize_date_and_split_ver():
    assert ep.normalize_date("DEC 2019") == "2019-12"
    assert ep.normalize_date("garbage") == "garbage"
    assert ep.split_patch_ver("5.3") == ("5", "3")
    assert ep.split_patch_ver("3") == ("3", "0")
    assert ep.split_patch_ver("") == ("", "")


def test_normalize_date_uses_shared_kernel_month_table():
    """§9.2: ``normalize_date`` must derive its month→number mapping from the shared
    ``kernel.text.month_year_iso`` (one month table for the corpus), not a private copy — while
    keeping catalog's strict ``MON YYYY`` anchoring (a date *field*, not a free-text search)."""
    from vdocs.kernel.text import month_year_iso

    # every recognised three-letter month agrees with the kernel primitive
    for raw in ("JAN 2001", "Jun 2018", "dec 2019", "MAY 2020"):
        assert ep.normalize_date(raw) == month_year_iso(raw)
    # anchored-only: a month embedded in a longer string is NOT a date field → unchanged
    assert ep.normalize_date("Released DEC 2019 build") == "Released DEC 2019 build"
    # a 4+ letter spelling is not the strict MON-YYYY field shape → unchanged
    assert ep.normalize_date("March 2019") == "March 2019"
    # anchored shape but not a real month → unchanged (not coerced)
    assert ep.normalize_date("ABC 2019") == "ABC 2019"
    assert ep.normalize_date("") == ""


def test_classify_noise(reg):
    assert ep.classify_noise("https://www.vba.va.gov/forms/x.pdf", reg.vba_form_hosts) == "vba_form"
    assert (
        ep.classify_noise("https://www.va.gov/strategic/plan.pdf", reg.vba_form_hosts) == "va_ref"
    )
    assert ep.classify_noise("https://www.va.gov/vdl/documents/x.pdf", reg.vba_form_hosts) == ""


def test_make_doc_slug():
    assert ep.make_doc_slug("DG_5.3_1057_DIBR.docx") == "dg_5_3_1057_dibr"


def test_split_url_ext():
    assert ep._split_url_ext("https://va.gov/a/b.DOCX") == ("https://va.gov/a/b", ".docx")
    assert ep._split_url_ext("https://va.gov/a/page") == ("https://va.gov/a/page", "")


# --- end-to-end pipeline ----------------------------------------------------
def test_enrich_rows_end_to_end(reg):
    docx = _raw(
        "DG*5.3*1057 Deployment, Installation, Back-Out, and Rollback Guide",
        "dg_5_3_1057_dibr.docx",
    )
    pdf = _raw(
        "DG*5.3*1057 Deployment, Installation, Back-Out, and Rollback Guide", "dg_5_3_1057_dibr.pdf"
    )
    # a shared VBA chrome URL appearing on two pages → noise
    vba_url = "https://www.vba.va.gov/pubs/forms/21-0958.pdf"
    vba1 = _raw("21-0958 Notice of Disagreement", "21-0958.pdf", doc_url=vba_url)
    vba2 = _raw("21-0958 Notice of Disagreement", "21-0958.pdf", doc_url=vba_url)

    out = ep.enrich_rows([docx, pdf, vba1, vba2], reg)
    by_slug = {(r["doc_slug"], r["doc_format"]): r for r in out}

    d = by_slug[("dg_5_3_1057_dibr", "docx")]
    p = by_slug[("dg_5_3_1057_dibr", "pdf")]
    # companion pairing: docx ↔ pdf share a slug, cross-link companion_url
    assert d["doc_slug"] == p["doc_slug"]
    assert d["companion_url"] == p["doc_url"] and p["companion_url"] == d["doc_url"]
    # identity + classification + canonical label
    assert d["patch_id"] == "DG*5.3*1057" and d["doc_layer"] == "patch"
    assert d["doc_code"] == "DIBR"
    assert d["doc_label"].startswith("Deployment, Installation")
    # package-master canon + section + anchor_key + system class
    assert d["section_code"] == "CLI"
    assert d["canonical_pkg"] == "ADT"
    assert d["anchor_key"] == "ADT:DG:DIBR:dg_dibr"
    assert d["group_key"] == "ADT:DG:5.3"
    assert d["system_type"] == "VistA" and d["cots_dependent"] is False
    # the shared VBA url is flagged noise (both rows), never deleted
    noise_rows = [r for r in out if r["noise_type"]]
    assert len(noise_rows) == 2 and {r["noise_type"] for r in noise_rows} == {"vba_form"}
    # 1:1 rows preserved
    assert len(out) == 4


def test_enrich_peer_inference_and_manual_override(reg):
    # two docs in the same group_key (XU:XU:8.0); one labelled RN, one unlabelled →
    # peer inference adopts RN.
    labelled = _raw("XU*8.0*1 Release Notes", "xu_8_0_1_rn.docx", app_name="Kernel (XU)")
    unlabelled = _raw("XU*8.0*2 Miscellaneous", "xu_8_0_2_zz.docx", app_name="Kernel (XU)")
    out = ep.enrich_rows([labelled, unlabelled], reg)
    codes = {r["doc_slug"]: r["doc_code"] for r in out}
    assert codes["xu_8_0_1_rn"] == "RN"
    assert codes["xu_8_0_2_zz"] == "RN"  # adopted by unanimous peer consensus


def test_enrich_manual_noise_tag(reg):
    # a slug in MANUAL_NOISE is tagged test_document and stripped of code/label
    row = _raw("Some Placeholder", "test_document_vdl.docx", app_name="Scheduling (SD)")
    (out,) = ep.enrich_rows([row], reg)
    assert out["doc_slug"] == "test_document_vdl"
    assert out["noise_type"] == "test_document"
    assert out["doc_code"] == "" and out["doc_labelling"] == "manual"


# --- branch coverage for the ported helpers --------------------------------
def test_clean_doc_subject_rules():
    cds = ep.clean_doc_subject
    assert cds("", "ADT", "t", "l") == ""  # empty
    assert cds("   ", "ADT", "t", "l") == ""  # whitespace
    assert cds("ADT", "ADT", "t", "l") == ""  # app echo (case-insensitive)
    assert cds("My Title", "ADT", "My Title", "l") == ""  # title echo
    assert cds("User Guide", "ADT", "t", "User Guide") == ""  # label echo
    assert cds("/WEBP*1*1", "ADT", "t", "l") == ""  # multi-NS continuation
    assert cds("2019", "ADT", "t", "l") == ""  # bare year
    assert cds("5.3", "ADT", "t", "l") == ""  # bare version
    assert cds(" - , ", "ADT", "t", "l") == ""  # punctuation
    assert cds("*123", "ADT", "t", "l") == ""  # patch artifact
    assert cds("DG*5.3*1057", "ADT", "t", "l") == ""  # full patch id
    assert cds(".1", "ADT", "t", "l") == ""  # ≤2 chars, no letters
    assert cds("Agent Cashier", "ADT", "t", "l") == "Agent Cashier"  # genuine qualifier kept


def test_extract_subject_strips_prefix_label_and_dibr():
    out = ep.extract_subject(
        "DG*5.3*1057 Deployment, Installation, Back-Out, and Rollback Guide ADT",
        "DG*5.3*1057",
        "Deployment, Installation, Back-Out, and Rollback Guide",
    )
    assert out == "ADT"


def test_edge_cases(reg):
    assert ep.apply_typo_corrections("", "doc_title", reg.typo_corrections) == ("", [])
    assert ep.split_patch_ver("abc") == ("", "")  # non-numeric
    # no recognisable filename suffix → no classification
    assert ep.classify_by_filename("x", "", reg.slug_suffix_map, reg.app_specific_suffix) == (
        "",
        "",
    )
    # unknown abbrev → unclassified, not COTS-dependent
    assert ep.classify_system("NOPE", reg) == ("unclassified", False)


def test_enrich_unknown_package_keeps_abbrev_as_canonical(reg):
    # an app with no package-master entry: canonical_pkg falls back to the abbrev,
    # doc_subject_raw stays empty (the else branch of pass-2 canonicalization).
    row = _raw("ZZZ*1.0*1 User Manual", "zzz_1_0_1_um.docx", app_name="Unknown App (ZZZ)")
    (out,) = ep.enrich_rows([row], reg)
    assert out["app_name_abbrev"] == "ZZZ"
    assert out["canonical_pkg"] == "ZZZ"
    assert out["doc_subject_raw"] == ""
    assert out["system_type"] == "unclassified"


def test_enrich_abbrev_fallback(reg):
    # no parens code on the app name, but a known fallback maps it (APP_ABBREV_FALLBACK)
    row = _raw("Home Telehealth program overview", "dht_overview.pdf", app_name="Home Telehealth")
    (out,) = ep.enrich_rows([row], reg)
    assert out["app_name_abbrev"] == "DHT"
