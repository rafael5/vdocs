"""Unit tests for catalog pure enrichment + drift (§8 catalog, §6.6, §7.6)."""

from vdocs.models.catalog import (
    CatalogApplication,
    CatalogDocument,
    CatalogSection,
    DocType,
    DriftStatus,
)
from vdocs.stages.catalog import catalog_pure as cp


# --- patch identity ---------------------------------------------------------
def test_patch_identity_from_title():
    pi = cp.parse_patch_identity("DG*5.3*1057 Deployment Guide", "dg_5_3_1057_dibr.docx")
    assert (pi.pkg_ns, pi.patch_ver, pi.patch_num, pi.patch_id) == (
        "DG",
        "5.3",
        "1057",
        "DG*5.3*1057",
    )


def test_patch_identity_from_filename_when_title_lacks_it():
    pi = cp.parse_patch_identity("Deployment Guide", "or_3_0_350_rn.docx")
    assert pi.pkg_ns == "OR" and pi.patch_ver == "3.0" and pi.patch_num == "350"
    assert pi.patch_id == "OR*3.0*350"


def test_patch_identity_absent():
    pi = cp.parse_patch_identity("Some Generic Title", "document.docx")
    assert pi.patch_id == "" and pi.pkg_ns == ""


# --- doc-type classification (filename before title) ------------------------
def test_classify_filename_suffix_wins():
    assert cp.classify_doc_type("cprsguitm.docx", "CPRS GUI") is DocType.TECHNICAL_MANUAL
    assert cp.classify_doc_type("tiuig.docx", "TIU") is DocType.INSTALLATION_GUIDE


def test_classify_title_fallback():
    assert cp.classify_doc_type("or_3_0_350_rn.docx", "OR Release Notes") is DocType.RELEASE_NOTE
    assert cp.classify_doc_type("doc.docx", "User's Guide") is DocType.USER_MANUAL
    assert (
        cp.classify_doc_type("doc.docx", "Deployment, Installation, Back-Out")
        is DocType.INSTALLATION_GUIDE
    )


def test_classify_unknown():
    assert cp.classify_doc_type("x.docx", "Mystery") is DocType.UNKNOWN


# --- labels / slug / group key / aliases ------------------------------------
def test_doc_label_strips_patch_prefix():
    assert cp.doc_label("DG*5.3*1057 Deployment Guide", "DG*5.3*1057") == "Deployment Guide"
    assert cp.doc_label("Plain Title", "") == "Plain Title"


def test_section_code():
    assert cp.section_code("Clinical") == "CLI"
    assert cp.section_code("Infrastructure") == "INF"


def test_version_group_key_is_version_free():
    # §6.6: the version/patch component is removed — the anchor doc spans all versions.
    assert cp.version_group_key("ADT", "DG", DocType.INSTALLATION_GUIDE) == "ADT:DG:IG"


def test_search_aliases_are_unique_and_nonempty():
    aliases = cp.search_aliases(
        app_code="ADT", pkg_ns="DG", patch_id="DG*5.3*1057", doc_type=DocType.INSTALLATION_GUIDE
    )
    assert "ADT" in aliases and "DG" in aliases and "DG*5.3*1057" in aliases and "IG" in aliases
    assert len(aliases) == len(set(aliases))


# --- full enrichment --------------------------------------------------------
def _triple():
    section = CatalogSection(name="Clinical", url="https://va.gov/vdl/section.asp?secid=1")
    app = CatalogApplication(
        name="Admission Discharge Transfer (ADT)",
        app_code="ADT",
        url="https://va.gov/vdl/application.asp?appid=55",
    )
    doc = CatalogDocument(
        title="DG*5.3*1057 Deployment, Installation, Back-Out, and Rollback Guide",
        url="https://va.gov/documents/Clinical/ADT/dg_5_3_1057_dibr.docx",
        filename="dg_5_3_1057_dibr.docx",
        file_ext=".docx",
        doc_type_label="DOCX",
    )
    return section, app, doc


def test_enrich_document_composes_all_fields():
    section, app, doc = _triple()
    ed = cp.enrich_document(section, app, doc)
    assert ed.app_code == "ADT" and ed.section_code == "CLI"
    assert ed.pkg_ns == "DG" and ed.patch_id == "DG*5.3*1057"
    assert ed.doc_type is DocType.INSTALLATION_GUIDE
    assert ed.group_key == "ADT:DG:IG"
    assert ed.doc_label == "Deployment, Installation, Back-Out, and Rollback Guide"
    assert ed.doc_slug == "dg_5_3_1057_dibr"


# --- drift classification (§7.6) --------------------------------------------
def _ed(num, pkg="DG"):
    low = pkg.lower()
    return cp.enrich_document(
        CatalogSection(name="Clinical", url="u"),
        CatalogApplication(name="ADT", app_code="ADT", url="u"),
        CatalogDocument(
            title=f"{pkg}*5.3*{num} Deployment Installation Guide",
            url=f"https://va.gov/d/{low}_5_3_{num}_dibr.docx",
            filename=f"{low}_5_3_{num}_dibr.docx",
            file_ext=".docx",
        ),
    )


def test_diff_catalog_marks_new_superseded_unchanged_withdrawn():
    prior = [_ed("1057"), _ed("1000")]
    current = [
        _ed("1057"),  # identical → UNCHANGED
        _ed("1099"),  # new patch, group exists → SUPERSEDED
    ]
    report = cp.diff_catalog(current, prior)
    by_id = {d.patch_id: d.drift_status for d in report.documents}
    assert by_id["DG*5.3*1057"] is DriftStatus.UNCHANGED
    assert by_id["DG*5.3*1099"] is DriftStatus.SUPERSEDED
    # the 1000 patch vanished upstream → WITHDRAWN (flagged, kept)
    assert [w.patch_id for w in report.withdrawn] == ["DG*5.3*1000"]


def test_diff_catalog_brand_new_group_is_new():
    report = cp.diff_catalog([_ed("1", pkg="XU")], prior=[])
    assert report.documents[0].drift_status is DriftStatus.NEW
    assert report.withdrawn == []
