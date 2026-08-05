"""Snapshot identity and naming (VO.2) — pure, no I/O.

The lake used to hold exactly one inventory, overwritten by every crawl, so no earlier state of
the VDL existed anywhere and none could be reconstructed. A snapshot fixes that, but only if it
behaves like evidence:

* **Identity is canonical content, not bytes.** The catalog's JSON follows the order VA happened
  to list pages in; a reorder is not history. Hashing sorted rows means a crawl that found the
  same thing is recognised as such and does not fabricate a second snapshot.
* **Every row counts, including the empty ones.** ``Catalog.walk`` yields nothing for an
  application with no documents, so the hash is built from the hierarchy directly — an
  application appearing (or losing its last document) is a change.
* **A name is never reused.** Two crawls in one day get two directories; overwriting the first
  would destroy exactly what this exists to keep.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from vdocs.models.catalog import Catalog


def _rows(catalog: Catalog) -> list[str]:
    """Every section, application and document as one comparable line.

    Each row carries its parent's URL, so the same document under a different application is a
    different row — URLs (which carry the VDL's own ``secid``/``appid``) are the identity, never
    the display names.
    """
    rows: list[str] = []
    for section in catalog.sections:
        rows.append("\t".join(("S", section.url, section.name)))
        for app in section.applications:
            rows.append(
                "\t".join(
                    (
                        "A",
                        section.url,
                        app.url,
                        app.name,
                        app.app_code,
                        app.status,
                        app.decommission_date,
                    )
                )
            )
            for doc in app.documents:
                rows.append(
                    "\t".join(
                        (
                            "D",
                            app.url,
                            doc.url,
                            doc.title,
                            doc.filename,
                            doc.file_ext,
                            doc.doc_type_label,
                            doc.file_date,
                        )
                    )
                )
    return rows


def canonical_hash(catalog: Catalog) -> str:
    """The catalog's content identity — stable under any reordering of the source pages."""
    return hashlib.sha256("\n".join(sorted(_rows(catalog))).encode("utf-8")).hexdigest()


def snapshot_name(day: str, taken: Iterable[str]) -> str:
    """``day``, or ``day-2``, ``day-3``… when that directory is already evidence."""
    seen = set(taken)
    if day not in seen:
        return day
    n = 2
    while f"{day}-{n}" in seen:
        n += 1
    return f"{day}-{n}"


def snapshot_order(name: str) -> tuple[str, int]:
    """Sort key putting ``2026-06-10`` before ``2026-06-10-2`` before ``2026-06-10-10``.

    Lexical sorting gets the double-digit case wrong, and the newest snapshot is what a new crawl
    is deduplicated against — so a wrong "newest" would silently drop a real change.
    """
    parts = name.split("-")
    if len(parts) == 4 and parts[3].isdigit():
        return ("-".join(parts[:3]), int(parts[3]))
    return (name, 1)
