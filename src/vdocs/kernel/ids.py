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


def anchor_key(app_code: str, pkg_ns: str, doc_code: str) -> str:
    """The **version-group key** — ``app:pkg:doc_code``, version-free (§6.6/§9.4).

    The one place the formula lives (§9.2): ``catalog`` computes it over an enriched row, and
    ``consolidate`` reconstructs it from a normalized bundle's identity frontmatter
    (``app_code``/``pkg_ns``/``doc_type``); both must agree exactly so the group a doc lands in is
    stable end-to-end. Empty ``doc_code`` ⇒ no version group (``""``): the document is a standalone
    anchor of one."""
    return f"{app_code}:{pkg_ns}:{doc_code}" if doc_code else ""


__all__ = ["HasIdentity", "anchor_key", "doc_id"]
