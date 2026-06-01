"""Bronze catalog boundary types (§5.3, §8).

The crawl hierarchy is Section → Application → Document (the real VDL shape). ``catalog``
then derives an :class:`EnrichedDocument` per file — patch identity, doc-type, version-group
key, drift status. All are Pydantic boundary types: they serialize to ``catalog/raw.json``
and ``catalog/enriched.json`` and validate on read.
"""

from __future__ import annotations

from collections.abc import Iterator
from enum import StrEnum

from pydantic import BaseModel, Field


class DocType(StrEnum):
    """Coarse VDL doc-type buckets (the classifier target; values are the VA codes)."""

    RELEASE_NOTE = "RN"
    INSTALLATION_GUIDE = "IG"
    USER_MANUAL = "UM"
    TECHNICAL_MANUAL = "TM"
    QUICK_REF = "QRG"
    SUPPLEMENT = "SUP"
    CHANGE_PAGE = "CP"
    SECURITY_GUIDE = "SEC"
    HL7 = "HL7"
    SETUP = "SETUP"
    DEVELOPER = "DEV"
    IMPLEMENTATION = "IMPL"
    UNKNOWN = "UNK"


class DriftStatus(StrEnum):
    """How a document changed relative to the prior catalog (§7.6 drift detection)."""

    NEW = "new"
    SUPERSEDED = "superseded"  # a newer patch/version of an existing group
    CHANGED_IN_PLACE = "changed_in_place"  # same identity, different bytes
    UNCHANGED = "unchanged"
    WITHDRAWN = "withdrawn"  # gone upstream — flagged, never deleted (bronze immutable)


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


class PatchIdentity(BaseModel):
    """The VA patch coordinate parsed from a title/filename, e.g. ``DG*5.3*1057``."""

    model_config = {"frozen": True}

    pkg_ns: str = ""  # "DG"
    patch_ver: str = ""  # "5.3"
    patch_num: str = ""  # "1057"
    patch_id: str = ""  # "DG*5.3*1057"


class EnrichedDocument(BaseModel):
    """A catalog document with derived identity/classification (the ``catalog.enriched`` unit)."""

    # --- carried from crawl ---
    title: str
    url: str
    filename: str
    file_ext: str
    doc_type_label: str = ""
    file_date: str = ""
    # --- section / application context ---
    section_code: str = ""
    section_name: str = ""
    app_code: str = ""
    app_name: str = ""
    app_status: str = "active"
    app_url: str = ""
    # --- derived patch identity ---
    pkg_ns: str = ""
    patch_ver: str = ""
    patch_num: str = ""
    patch_id: str = ""
    # --- derived classification / grouping ---
    doc_type: DocType = DocType.UNKNOWN
    doc_label: str = ""
    doc_slug: str = ""
    group_key: str = ""  # version-free document identity (§6.6)
    search_aliases: list[str] = Field(default_factory=list)
    # --- drift (§7.6) ---
    drift_status: DriftStatus = DriftStatus.NEW


class EnrichedCatalog(BaseModel):
    """The ``catalog.enriched`` artifact: current documents + WITHDRAWN priors (§7.6)."""

    documents: list[EnrichedDocument] = Field(default_factory=list)
    withdrawn: list[EnrichedDocument] = Field(default_factory=list)
