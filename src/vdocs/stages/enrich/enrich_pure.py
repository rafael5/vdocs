"""Pure logic for `enrich` — identity frontmatter + the staged doc-meta row (§6.3, §8).

`enrich` joins each converted bundle with its inventory record and bakes the **identity /
human-curated** metadata into ``body.md`` frontmatter (§6.3) — the small, stable keys that
*define* the document (title, type, app, section, version, source). Computed/derived fields
(word_count, is_latest, …) are **never** baked into the body; they are staged here for
``index.db`` and owned there. These functions are pure: an inventory record (+ body) in,
plain dicts out; the stage does the file/SQLite I/O.
"""

from __future__ import annotations

import re

from vdocs.kernel.ids import doc_id
from vdocs.models.catalog import EnrichedRecord

__all__ = ["doc_id", "identity_frontmatter", "staged_row", "word_count"]

_WORD_RE = re.compile(r"\S+")

# identity frontmatter keys sourced from the inventory record (source_sha256 is added later by
# `normalize`, which has the bronze bytes; computed fields go to index.db, never the body — §6.3)
_FM_FIELDS: tuple[tuple[str, str], ...] = (
    ("title", "doc_title"),
    ("doc_type", "doc_code"),
    ("app_code", "app_name_abbrev"),
    ("section", "section_code"),
    ("pkg_ns", "pkg_ns"),
    ("version", "patch_ver"),
    ("patch_id", "patch_id"),
    ("source_url", "doc_url"),
)


def word_count(body: str) -> int:
    """Whitespace-delimited token count of a body (a computed field — staged, not baked)."""
    return len(_WORD_RE.findall(body))


def identity_frontmatter(record: EnrichedRecord, *, tool_ver: str) -> dict[str, str]:
    """The identity frontmatter mapping for a record — only the non-empty identity keys (§6.3)."""
    fm = {key: getattr(record, attr) for key, attr in _FM_FIELDS}
    fm = {k: v for k, v in fm.items() if v}
    fm["tool_ver"] = tool_ver
    return fm


def staged_row(record: EnrichedRecord, *, body: str, bundle_path: str) -> dict[str, object]:
    """The ``index.db:doc_meta_staged`` row — inventory identity + computed metadata, the bridge
    `index` consumes (the identity is *also* in the body FM; computed fields live only here)."""
    return {
        "doc_id": doc_id(record),
        "app_code": record.app_name_abbrev,
        "doc_slug": record.doc_slug,
        "doc_code": record.doc_code,
        "doc_label": record.doc_label,
        "doc_title": record.doc_title,
        "section_code": record.section_code,
        "pkg_ns": record.pkg_ns,
        "patch_ver": record.patch_ver,
        "patch_id": record.patch_id,
        "group_key": record.group_key,
        "anchor_key": record.anchor_key,
        "noise_type": record.noise_type,
        "source_url": record.doc_url,
        "doc_format": record.doc_format,
        "word_count": word_count(body),
        "bundle_path": bundle_path,
    }


STAGED_COLUMNS: tuple[str, ...] = tuple(
    staged_row(EnrichedRecord(app_name_abbrev="X", doc_slug="y"), body="", bundle_path="").keys()
)
