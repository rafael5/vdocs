"""Stable identifiers — the one place the inventory ``doc_id`` is built (§5.5, §9.2).

``doc_id`` is *the* join key across the pipeline: the gold inventory, ``acquisitions``,
the fetch index, and (Phase 4) ``index.db`` all key on it. Per the anti-duplication rule
(§9.2/§11), the ``app_code:doc_slug`` formula lives here exactly once and every stage
imports it rather than re-spelling the f-string. The kernel stays model-free: the input is
duck-typed via a Protocol, so this never imports ``models``.
"""

from __future__ import annotations

from typing import Protocol


class HasIdentity(Protocol):
    """Anything carrying the inventory identity fields (e.g. ``EnrichedRecord``)."""

    app_name_abbrev: str
    doc_slug: str


def doc_id(record: HasIdentity) -> str:
    """The inventory's stable id — ``app_code:doc_slug`` (§5.5). The DOCX/PDF rows of one
    logical document share it (they share ``doc_slug``)."""
    return f"{record.app_name_abbrev}:{record.doc_slug}"


__all__ = ["HasIdentity", "doc_id"]
