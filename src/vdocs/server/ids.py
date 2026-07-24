"""Stable-ID, MCP-URI, and gold-path resolution — shared by the stages and the serving layer (§11).

The stable IDs are *the* contract (§14.5): the anchor a citation names, the gold file it resolves
to, and the MCP resource URI are all derived here, in one place, so a citation an agent returns
resolves identically from the AI card (`manifest`), the `vdocs ask` query path (`search`), and the
published GitHub corpus. No stage re-derives these (§9.2).
"""

from __future__ import annotations

from vdocs.stages.consolidate.consolidate_pure import anchor_relpath


def _anchor_rel(app_code: str, pkg_ns: str, doc_type: str, doc_key: str) -> str:
    """The version-free ``<app>/<slug>`` anchor path of a `documents` row — the one derivation both
    the gold body and its rich-table sidecars hang off, so the two can never name different
    bundles. `doc_slug` (only used for standalone docs with no version group) is the URL-safe tail
    of `doc_key`."""
    doc_slug = (doc_key or "").split("/", 1)[-1]
    return anchor_relpath(app_code or "", pkg_ns or "", doc_type or "", doc_slug=doc_slug)


def gold_body_relpath(app_code: str, pkg_ns: str, doc_type: str, doc_key: str) -> str:
    """The lake-relative gold anchor body (`documents/gold/consolidated/<app>/<slug>/body.md`) for a
    `documents` row. Reuses `consolidate`'s `anchor_relpath` (the version-free anchor path), so the
    path here is byte-identical to where `consolidate` actually wrote the bundle."""
    return f"documents/gold/consolidated/{_anchor_rel(app_code, pkg_ns, doc_type, doc_key)}/body.md"


def gold_tables_reldir(app_code: str, pkg_ns: str, doc_type: str, doc_key: str) -> str:
    """The lake-relative rich-table sidecar dir (`rich-tables/<app>/<slug>/tables`) for a
    `documents` row — the CSVs `publish-rich-tables` copied out of the gold bundle.

    The **second** fallback source when the index returns nothing: a `container`/`hollow` section's
    lead-in prose is never chunked, and in a reference manual that lead-in is the API contract
    whose Input-Parameter/flag tables land here as `table-NN.csv`. Same `_anchor_rel` derivation as
    the body path, so body and tables always resolve to the same bundle."""
    return f"rich-tables/{_anchor_rel(app_code, pkg_ns, doc_type, doc_key)}/tables"


def section_uri(section_id: str) -> str:
    """The MCP resource URI for a section/chunk anchor (§14.3): `vdocs://section/<section_id>`."""
    return f"vdocs://section/{section_id}"
