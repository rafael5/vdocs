"""Pure catalog enrichment + drift detection (§8 catalog, §6.6, §7.6; ported from v1 §16).

Derives, per document: VA patch identity, doc-type, version-free group key (§6.6),
labels, search aliases — and classifies each against the prior catalog for drift (§7.6).
No I/O; the ``stage.py`` driver reads/writes the catalog artifacts.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from vdocs.models.catalog import (
    CatalogApplication,
    CatalogDocument,
    CatalogSection,
    DocType,
    DriftStatus,
    EnrichedDocument,
    PatchIdentity,
)

# Patch coordinate "NMSP*ver*patch" in a title, e.g. "DG*5.3*1057".
_PATCH_TITLE_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,4})\*(\d+(?:\.\d+)?)\*(\d+)")
# Same coordinate flattened into a filename, e.g. "dg_5_3_1057_...".
_PATCH_FILE_RE = re.compile(r"\b([a-z][a-z0-9]{1,4})_(\d+)_(\d+)_(\d+)_", re.I)

# Doc-type classification rules (filename first, then title) — §16 classify/rules.py.
_FILENAME_RULES: list[tuple[re.Pattern[str], DocType]] = [
    (re.compile(r"(tm\.|technical.?manual)", re.I), DocType.TECHNICAL_MANUAL),
    (re.compile(r"(um\.|user.?manual)", re.I), DocType.USER_MANUAL),
    (re.compile(r"(ig\.|install|dibr)", re.I), DocType.INSTALLATION_GUIDE),
    (re.compile(r"(rn\.|release.?note|patch.*rn)", re.I), DocType.RELEASE_NOTE),
    (re.compile(r"(qr\.|qrg\.|quick.?ref)", re.I), DocType.QUICK_REF),
    (re.compile(r"cp\.", re.I), DocType.CHANGE_PAGE),
    (re.compile(r"sp\.", re.I), DocType.SUPPLEMENT),
]
_TITLE_RULES: list[tuple[re.Pattern[str], DocType]] = [
    (re.compile(r"technical.?manual", re.I), DocType.TECHNICAL_MANUAL),
    (re.compile(r"user.?manual", re.I), DocType.USER_MANUAL),
    (re.compile(r"adpac.?guide", re.I), DocType.USER_MANUAL),
    (re.compile(r"manager.?s?\s+manual", re.I), DocType.USER_MANUAL),
    (re.compile(r"administrator.?s?\s+guide|admin\s+guide", re.I), DocType.USER_MANUAL),
    (re.compile(r"systems?\s+management", re.I), DocType.USER_MANUAL),
    (re.compile(r"user.?s?\s+guide", re.I), DocType.USER_MANUAL),
    (
        re.compile(r"installation.?guide|deployment.*installation|dibr", re.I),
        DocType.INSTALLATION_GUIDE,
    ),
    (re.compile(r"\binstall\s+guide\b", re.I), DocType.INSTALLATION_GUIDE),
    (re.compile(r"deploy\w*\s+guide", re.I), DocType.INSTALLATION_GUIDE),
    (re.compile(r"rollback|back-?out", re.I), DocType.INSTALLATION_GUIDE),
    (re.compile(r"conversion\s+guide|installation\s+manual", re.I), DocType.INSTALLATION_GUIDE),
    (re.compile(r"release.?note", re.I), DocType.RELEASE_NOTE),
    (re.compile(r"read.?me(\s+(file|guide))?", re.I), DocType.RELEASE_NOTE),
    (
        re.compile(r"quick.?ref|getting\s+started|quick\s+start|\btutorial\b", re.I),
        DocType.QUICK_REF,
    ),
    (re.compile(r"change.?page", re.I), DocType.CHANGE_PAGE),
    (re.compile(r"\bsupplement\b|\bglossary\b|troubl.{0,3}shoot", re.I), DocType.SUPPLEMENT),
    (re.compile(r"training\s+guide|workflow\b|\bchecklist\b|\bpom\b", re.I), DocType.SUPPLEMENT),
    (re.compile(r"security", re.I), DocType.SECURITY_GUIDE),
    (re.compile(r"hl7|interface.?spec", re.I), DocType.HL7),
    (re.compile(r"set.?up|configuration", re.I), DocType.SETUP),
    (re.compile(r"developer|programming|programmer|\bapi\s+manual", re.I), DocType.DEVELOPER),
    (re.compile(r"implementation", re.I), DocType.IMPLEMENTATION),
    (re.compile(r"\bmanual\b", re.I), DocType.USER_MANUAL),
]


def parse_patch_identity(title: str, filename: str) -> PatchIdentity:
    """Extract the VA patch coordinate from the title, falling back to the filename."""
    m = _PATCH_TITLE_RE.search(title)
    if m:
        ns, ver, num = m.group(1), m.group(2), m.group(3)
        return PatchIdentity(pkg_ns=ns, patch_ver=ver, patch_num=num, patch_id=f"{ns}*{ver}*{num}")
    m = _PATCH_FILE_RE.search(filename)
    if m:
        ns = m.group(1).upper()
        ver = f"{m.group(2)}.{m.group(3)}"
        num = m.group(4)
        return PatchIdentity(pkg_ns=ns, patch_ver=ver, patch_num=num, patch_id=f"{ns}*{ver}*{num}")
    return PatchIdentity()


def classify_doc_type(filename: str, title: str) -> DocType:
    """Classify a document by filename (VA naming convention) then title fallback (§16)."""
    stem = filename.lower()
    for pattern, doc_type in _FILENAME_RULES:
        if pattern.search(stem):
            return doc_type
    title_lower = title.lower()
    for pattern, doc_type in _TITLE_RULES:
        if pattern.search(title_lower):
            return doc_type
    return DocType.UNKNOWN


def doc_label(title: str, patch_id: str) -> str:
    """The human label: the title with any leading patch coordinate stripped."""
    label = title
    m = _PATCH_TITLE_RE.match(title.strip())
    if m:
        label = title.strip()[m.end() :]
    return label.strip()


def section_code(section_name: str) -> str:
    """A short, stable section code: the first three alphanumerics, uppercased."""
    alnum = [c for c in section_name if c.isalnum()]
    return "".join(alnum[:3]).upper()


def doc_slug(filename: str) -> str:
    """The filename stem (no extension) — the bundle/document slug."""
    return filename.rsplit(".", 1)[0] if "." in filename else filename


def version_group_key(app_code: str, pkg_ns: str, doc_type: DocType) -> str:
    """Version-free document identity (§6.6): ``app:pkg:doctype``, version/patch removed."""
    return f"{app_code}:{pkg_ns}:{doc_type.value}"


def search_aliases(*, app_code: str, pkg_ns: str, patch_id: str, doc_type: DocType) -> list[str]:
    """Distinct, non-empty discovery aliases for a document."""
    out: list[str] = []
    for candidate in (app_code, pkg_ns, patch_id, doc_type.value):
        if candidate and candidate not in out:
            out.append(candidate)
    return out


def enrich_document(
    section: CatalogSection, app: CatalogApplication, doc: CatalogDocument
) -> EnrichedDocument:
    """Compose a fully-enriched document from its (section, application, document) triple."""
    pi = parse_patch_identity(doc.title, doc.filename)
    doc_type = classify_doc_type(doc.filename, doc.title)
    return EnrichedDocument(
        title=doc.title,
        url=doc.url,
        filename=doc.filename,
        file_ext=doc.file_ext,
        doc_type_label=doc.doc_type_label,
        file_date=doc.file_date,
        section_code=section_code(section.name),
        section_name=section.name,
        app_code=app.app_code,
        app_name=app.name,
        app_status=app.status,
        app_url=app.url,
        pkg_ns=pi.pkg_ns,
        patch_ver=pi.patch_ver,
        patch_num=pi.patch_num,
        patch_id=pi.patch_id,
        doc_type=doc_type,
        doc_label=doc_label(doc.title, pi.patch_id),
        doc_slug=doc_slug(doc.filename),
        group_key=version_group_key(app.app_code, pi.pkg_ns, doc_type),
        search_aliases=search_aliases(
            app_code=app.app_code, pkg_ns=pi.pkg_ns, patch_id=pi.patch_id, doc_type=doc_type
        ),
    )


def _identity(ed: EnrichedDocument) -> str:
    """Stable per-document identity for drift comparison: the patch id, else the URL."""
    return ed.patch_id or ed.url


class DriftReport(BaseModel):
    """Outcome of a catalog diff: current docs with drift status + withdrawn priors (§7.6)."""

    documents: list[EnrichedDocument] = Field(default_factory=list)
    withdrawn: list[EnrichedDocument] = Field(default_factory=list)


def diff_catalog(current: list[EnrichedDocument], prior: list[EnrichedDocument]) -> DriftReport:
    """Classify each current doc NEW/SUPERSEDED/UNCHANGED vs ``prior``; flag WITHDRAWN priors.

    Metadata-level drift (the §7.6 pre-filter). CHANGED_IN_PLACE — same identity, different
    bytes — is determined later by ``fetch`` from the content hash, the authoritative signal.
    """
    prior_ids = {_identity(p) for p in prior}
    prior_groups = {p.group_key for p in prior}
    current_ids = {_identity(c) for c in current}

    documents: list[EnrichedDocument] = []
    for cur in current:
        if _identity(cur) in prior_ids:
            status = DriftStatus.UNCHANGED
        elif cur.group_key in prior_groups:
            status = DriftStatus.SUPERSEDED
        else:
            status = DriftStatus.NEW
        documents.append(cur.model_copy(update={"drift_status": status}))

    withdrawn = [
        p.model_copy(update={"drift_status": DriftStatus.WITHDRAWN})
        for p in prior
        if _identity(p) not in current_ids
    ]
    return DriftReport(documents=documents, withdrawn=withdrawn)
