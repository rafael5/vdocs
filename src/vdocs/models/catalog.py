"""Inventory-medallion boundary types (§5.3, §8).

The crawl hierarchy is Section → Application → Document (the real VDL shape) — the inv-bronze
``catalog.raw`` artifact. ``catalog`` then enriches each document link into an
:class:`EnrichedRecord` (the full §5 column set — patch identity, doc-type/labels, noise
classification, companion pairing, group/anchor keys, system classification) — the inv-silver
``catalog.enriched`` artifact. All are Pydantic boundary types: they serialize to JSON and
validate on read. Drift is **not** here — it is a temporal property decided at ``fetch`` and
recorded in ``state.db:acquisitions`` (§7.6, §9.5), not baked into this deterministic artifact.
"""

from __future__ import annotations

from collections.abc import Iterator

from pydantic import BaseModel, ConfigDict, Field


class CatalogDocument(BaseModel):
    """A single document entry parsed from a VDL application page."""

    title: str
    url: str
    filename: str
    file_ext: str
    doc_type_label: str = ""  # raw VDL label ("DOCX"/"PDF")
    file_date: str = ""


class CatalogApplication(BaseModel):
    """A VistA application (package) under a VDL section."""

    name: str
    app_code: str
    url: str
    status: str = "active"
    decommission_date: str = ""
    documents: list[CatalogDocument] = Field(default_factory=list)


class CatalogSection(BaseModel):
    """A top-level VDL section (e.g. 'Clinical')."""

    name: str
    url: str
    applications: list[CatalogApplication] = Field(default_factory=list)


class Catalog(BaseModel):
    """The full crawled catalog hierarchy — the ``catalog.raw`` artifact."""

    sections: list[CatalogSection] = Field(default_factory=list)

    def walk(self) -> Iterator[tuple[CatalogSection, CatalogApplication, CatalogDocument]]:
        """Yield every (section, application, document) triple in the catalog."""
        for section in self.sections:
            for app in section.applications:
                for doc in app.documents:
                    yield section, app, doc


class EnrichedRecord(BaseModel):
    """One fully-enriched inventory row — the §5 column set (v1's 34 + system_type/
    cots_dependent + the vdocs-native ``anchor_key``). Built from an ``enrich_rows`` dict
    (extra intermediate keys are ignored). The on-disk column order is :data:`ENRICHED_COLUMNS`.
    """

    model_config = ConfigDict(extra="ignore")

    # section / application context
    section_name: str = ""
    section_code: str = ""
    app_name_full: str = ""
    app_name_abbrev: str = ""
    canonical_pkg: str = ""
    doc_subject_raw: str = ""
    doc_search_aliases: str = ""
    app_status: str = "active"
    # system classification (Stage C)
    system_type: str = ""
    cots_dependent: bool = False
    # patch identity
    decommission_date: str = ""
    pkg_ns: str = ""
    patch_ver: str = ""
    patch_ver_major: str = ""
    patch_ver_minor: str = ""
    patch_num: str = ""
    patch_id: str = ""
    patch_id_full: str = ""
    multi_ns: str = "0"  # "0"/"1"
    group_key: str = ""  # app:pkg:patch_ver (v1)
    anchor_key: str = ""  # app:pkg:doc_code (version-free, vdocs §9.4)
    # document identity / classification
    doc_code: str = ""
    doc_label: str = ""
    doc_subtitle: str = ""
    doc_layer: str = "plain"  # anchor | patch | plain
    doc_labelling: str = "code"  # code | manual
    doc_title: str = ""
    doc_filename: str = ""
    doc_slug: str = ""
    doc_format: str = ""  # pdf | docx | doc
    doc_subject: str = ""
    noise_type: str = ""  # "" | vba_form | va_ref | test_document
    # urls
    app_url: str = ""
    doc_url: str = ""
    companion_url: str = ""
    github_md_url: str = ""
    github_md_raw_url: str = ""


# The fixed on-disk column order (§5; the CSV convenience view uses this).
ENRICHED_COLUMNS = list(EnrichedRecord.model_fields.keys())


class EnrichedInventory(BaseModel):
    """The ``catalog.enriched`` artifact: every document link as one enriched record (1:1)."""

    records: list[EnrichedRecord] = Field(default_factory=list)
