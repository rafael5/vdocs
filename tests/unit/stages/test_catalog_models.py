"""Unit tests for models.catalog — the bronze catalog boundary types (§5.3, §8)."""

from vdocs.models.catalog import (
    Catalog,
    CatalogApplication,
    CatalogDocument,
    CatalogSection,
    DocType,
    DriftStatus,
    EnrichedDocument,
    PatchIdentity,
)


def _doc(title="T", url="https://va.gov/x.docx", filename="x.docx", ext=".docx"):
    return CatalogDocument(title=title, url=url, filename=filename, file_ext=ext)


def test_catalog_round_trips_through_json():
    cat = Catalog(
        sections=[
            CatalogSection(
                name="Clinical",
                url="https://va.gov/vdl/section.asp?secid=1",
                applications=[
                    CatalogApplication(
                        name="Admission Discharge Transfer (ADT)",
                        app_code="ADT",
                        url="https://va.gov/vdl/application.asp?appid=55",
                        documents=[_doc()],
                    )
                ],
            )
        ]
    )
    again = Catalog.model_validate_json(cat.model_dump_json())
    assert again == cat


def test_catalog_walk_yields_section_app_doc_triples():
    cat = Catalog(
        sections=[
            CatalogSection(
                name="Clinical",
                url="u",
                applications=[
                    CatalogApplication(
                        name="ADT",
                        app_code="ADT",
                        url="u",
                        documents=[_doc(), _doc(filename="y.pdf", ext=".pdf")],
                    )
                ],
            )
        ]
    )
    triples = list(cat.walk())
    assert len(triples) == 2
    section, app, doc = triples[0]
    assert section.name == "Clinical" and app.app_code == "ADT" and doc.filename == "x.docx"


def test_drift_status_members():
    assert {d.value for d in DriftStatus} == {
        "new",
        "superseded",
        "changed_in_place",
        "unchanged",
        "withdrawn",
    }


def test_patch_identity_defaults_empty():
    pi = PatchIdentity()
    assert pi.patch_id == "" and pi.pkg_ns == ""


def test_enriched_document_carries_derived_fields():
    ed = EnrichedDocument(
        title="DG*5.3*1057 DIBR Guide",
        url="https://va.gov/x.docx",
        filename="dg_5_3_1057_dibr.docx",
        file_ext=".docx",
        section_code="CLI",
        section_name="Clinical",
        app_code="ADT",
        app_name="Admission Discharge Transfer (ADT)",
        pkg_ns="DG",
        patch_ver="5.3",
        patch_num="1057",
        patch_id="DG*5.3*1057",
        doc_type=DocType.INSTALLATION_GUIDE,
        group_key="ADT:DG:IG",
    )
    assert ed.doc_type is DocType.INSTALLATION_GUIDE
    assert ed.drift_status is DriftStatus.NEW  # default
    assert ed.group_key == "ADT:DG:IG"
