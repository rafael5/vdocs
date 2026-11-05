"""The inventory rows the index stage publishes — one per VDL listing (inventory browser §3, §5).

A record is one link on one application page, as ``inventory.json`` holds it; it is not a
document. Neither ``doc_id`` nor the VDL URL is unique across records, and no combination of
listing fields separates every one (a file can be listed twice on one page with every field
identical), so each row carries its own key. Pure functions only — no I/O (§9.2).
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import astuple, dataclass, fields

from vdocs.kernel import personas
from vdocs.kernel.ids import doc_id
from vdocs.models.catalog import EnrichedRecord
from vdocs.stages.fetch.fetch_pure import GatePolicy, sole_survivors
from vdocs.stages.serve_inventory.completeness_pure import (
    classify,
    docx_anchor_keys,
    docx_doc_ids,
)

# The four listing fields of the row key: application page, VDL section, file URL, patch id.
ROW_KEY_FIELDS = ("app_url", "section_name", "doc_url", "patch_id")


def canonical(rec: EnrichedRecord) -> str:
    """A record's full content as one comparable line (sorted-key JSON)."""
    return json.dumps(rec.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)


def row_keys(records: list[EnrichedRecord]) -> list[str]:
    """One key per record: a hash of the four listing fields plus an ordinal among the records
    that share them, assigned by sorting those records on their full canonical content — so a key
    follows the listing's content, not the order VA's page happens to list it in, and changes only
    when the listing itself does."""
    groups: dict[str, list[int]] = defaultdict(list)
    for i, rec in enumerate(records):
        listing = "\x1f".join(str(getattr(rec, f)) for f in ROW_KEY_FIELDS)
        groups[hashlib.sha256(listing.encode("utf-8")).hexdigest()[:16]].append(i)
    keys = [""] * len(records)
    for base, idxs in groups.items():
        for ordinal, i in enumerate(sorted(idxs, key=lambda j: canonical(records[j]))):
            keys[i] = f"{base}:{ordinal}"
    return keys


def inventory_hash(records: list[EnrichedRecord]) -> str:
    """The inventory's content identity, stamped into ``meta``: computed the way the crawl
    snapshot's ``canonical_hash`` is — sorted canonical rows — so the order VA's pages list the
    records in does not move it, and any change to an enriched record does."""
    lines = sorted(canonical(r) for r in records)
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


# The meta keys that stamp which inventory the table was built from (doctor compares the hash).
META_RECORD_COUNT = "inventory_record_count"
META_CONTENT_HASH = "inventory_content_hash"


def meta_rows(records: list[EnrichedRecord]) -> list[tuple[str, str]]:
    """The inventory's ``meta`` rows: its record count and content hash."""
    return [(META_RECORD_COUNT, str(len(records))), (META_CONTENT_HASH, inventory_hash(records))]


def same_code_app_names(records: list[EnrichedRecord]) -> dict[str, str]:
    """Every inventory namespace → the name of the application whose code is the same (the
    first in sort order when VA spells it more than one way), or ``""`` when no application has
    that code — the fallback a namespace takes when the PACKAGE file does not name it."""
    apps: dict[str, set[str]] = defaultdict(set)
    for r in records:
        if r.app_name_full:
            apps[r.app_name_abbrev].add(r.app_name_full)
    return {
        ns: min(apps[ns]) if apps.get(ns) else ""
        for ns in sorted({r.pkg_ns for r in records})
        if ns
    }


@dataclass(frozen=True)
class InventoryRow:
    """One VDL listing as ``v_inventory`` publishes it. Gold status is not a column: it is a
    relation, found by joining ``doc_id`` to ``v_documents``."""

    row_key: str
    doc_id: str  # kernel.ids.doc_id — the join key to v_documents
    app_code: str
    app_name: str  # the VDL's own application name
    section: str  # VDL section code (v_vocab kind 'section')
    doc_type: str
    title: str
    file_name: str
    format: str  # docx | pdf | doc
    patch_id: str
    app_status: str  # VA's lifecycle label (active | archive | decommissioned)
    system_type: str
    doc_url: str  # the file on the VDL
    app_url: str  # the application page that lists it
    app_user: str
    doc_user: str
    software_class: str
    function_category: str
    pkg_ns: str
    disposition: str  # one of completeness_pure.DISPOSITIONS
    reason: str  # the reason string `vdocs completeness` prints
    reason_kind: str  # one of completeness_pure.REASON_KINDS
    reason_value: str
    # D1's stopgap: the id gold still holds this re-filed document under (inventory/refiled.yaml),
    # a label not a join; empty for every other row
    refiled_from: str = ""

    def as_tuple(self) -> tuple[str, ...]:
        return astuple(self)


INVENTORY_COLUMNS: tuple[str, ...] = tuple(f.name for f in fields(InventoryRow))


def inventory_rows(
    records: list[EnrichedRecord],
    policy: GatePolicy,
    maps: personas.ProfileMaps,
    *,
    refiled: Mapping[str, str] | None = None,
) -> list[InventoryRow]:
    """One row per record, in record order: the listing, its four profile tags (through the same
    ``profile_tags`` that tags gold documents), and its disposition from ``classify`` with the same
    inputs ``completeness_report`` gives it — so the rows' counts are the CLI's counts.
    ``refiled`` labels the rows of each listed re-filed document with its gold id (D1)."""
    refiled = refiled or {}
    soles = sole_survivors(records, policy)
    anchors, ids = docx_anchor_keys(records), docx_doc_ids(records)
    rows: list[InventoryRow] = []
    for key, rec in zip(row_keys(records), records, strict=True):
        d = classify(rec, policy, docx_ids=ids, docx_anchors=anchors, sole_survivors=soles)
        tags = personas.profile_tags(rec.app_name_abbrev, rec.doc_code, maps)
        did = doc_id(rec)
        rows.append(
            InventoryRow(
                row_key=key,
                doc_id=did,
                app_code=rec.app_name_abbrev,
                app_name=rec.app_name_full,
                section=rec.section_code,
                doc_type=rec.doc_code,
                title=rec.doc_title,
                file_name=rec.doc_filename,
                format=rec.doc_format,
                patch_id=rec.patch_id,
                app_status=rec.app_status,
                system_type=rec.system_type,
                doc_url=rec.doc_url,
                app_url=rec.app_url,
                app_user=tags.get("app_user", ""),
                doc_user=tags.get("doc_user", ""),
                software_class=tags.get("software_class", ""),
                function_category=tags.get("function_category", ""),
                pkg_ns=rec.pkg_ns,
                disposition=d.status,
                reason=d.reason,
                reason_kind=d.kind,
                reason_value=d.value,
                refiled_from=refiled.get(did, ""),
            )
        )
    return rows
