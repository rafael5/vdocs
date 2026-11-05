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

from vdocs.models.catalog import EnrichedRecord

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
        fields = "\x1f".join(str(getattr(rec, f)) for f in ROW_KEY_FIELDS)
        groups[hashlib.sha256(fields.encode("utf-8")).hexdigest()[:16]].append(i)
    keys = [""] * len(records)
    for base, idxs in groups.items():
        for ordinal, i in enumerate(sorted(idxs, key=lambda j: canonical(records[j]))):
            keys[i] = f"{base}:{ordinal}"
    return keys
