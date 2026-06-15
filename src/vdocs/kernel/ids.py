"""Stable identifiers — the one place the inventory ``doc_id`` is built (§5.5, §9.2).

``doc_id`` is *the* join key across the pipeline: the gold inventory, ``acquisitions``,
the fetch index, and (Phase 4) ``index.db`` all key on it. Per the anti-duplication rule
(§9.2/§11), the ``app_code:doc_slug`` formula lives here exactly once and every stage
imports it rather than re-spelling the f-string. The kernel stays model-free: the input is
duck-typed via a Protocol, so this never imports ``models``.
"""

from __future__ import annotations

import re
from typing import Protocol

from vdocs.kernel.text import safe_component

# A doc_slug is '_'-delimited; these tokens are version/patch noise, not part of the document's
# identity. Stripping them yields a version-free **stem** that is the same for every version of one
# document and *different* for distinct documents — the disambiguator the version-group key needs
# so ``app:pkg:doc_code`` doesn't over-group unrelated manuals (B1). (Underscores are \w, so a regex
# \b won't split ``_123``; we tokenize on '_' instead.)
_VERSION_SLUG_TOKEN = re.compile(
    r"^(?:\d+|p\d+|v\d+|r\d+|patch|release|addendum|rev|ver|version|build)$", re.IGNORECASE
)


class HasIdentity(Protocol):
    """Anything carrying the inventory identity fields (e.g. ``EnrichedRecord``)."""

    app_name_abbrev: str
    doc_slug: str


def doc_id(record: HasIdentity) -> str:
    """The inventory's stable id — ``app_code:doc_slug`` (§5.5). The DOCX/PDF rows of one
    logical document share it (they share ``doc_slug``)."""
    return f"{record.app_name_abbrev}:{record.doc_slug}"


def slug_stem(doc_slug: str) -> str:
    """The version-free stem of a ``doc_slug`` — drop pure version/patch tokens, keep the rest.

    ``dg_5_3_1057_um`` & ``dg_5_4_2000_um`` → ``dg_um`` (versions of one doc collapse);
    ``krn_8_0_dg_alerts_ug`` → ``krn_dg_alerts_ug`` (distinct Kernel guides stay distinct). This is
    the logical-document identity folded into :func:`anchor_key` to fix B1 over-consolidation."""
    return "_".join(t for t in doc_slug.split("_") if not _VERSION_SLUG_TOKEN.match(t))


def anchor_key(app_code: str, pkg_ns: str, doc_code: str, doc_slug: str = "") -> str:
    """The **version-group key** — ``app:pkg:doc_code:<stem>``, version-free (§6.6/§9.4).

    The one place the formula lives (§9.2): ``catalog`` computes it over an enriched row, and
    ``consolidate`` reconstructs it from a normalized bundle (identity frontmatter +
    ``doc_slug``); both pass the same ``doc_slug`` so the group a doc lands in is stable end-to-end.
    The ``<stem>`` (version-stripped ``doc_slug``, :func:`slug_stem`) is what keeps *distinct*
    documents that share an ``app:pkg:doc_code`` from collapsing into one version group (B1). Empty
    ``doc_code`` ⇒ no version group (``""``): a standalone anchor of one. A ``doc_slug`` that strips
    to nothing falls back to the bare ``app:pkg:doc_code``."""
    if not doc_code:
        return ""
    stem = slug_stem(doc_slug)
    return f"{app_code}:{pkg_ns}:{doc_code}:{stem}" if stem else f"{app_code}:{pkg_ns}:{doc_code}"


def bundle_key(app_code: str, doc_slug: str) -> tuple[str, str]:
    """The canonical **convert-bundle identity** — ``(safe app, safe slug)`` (§9.2).

    A converted/normalized document lives at ``<safe app_code>/<safe doc_slug>/`` (see
    ``convert_pure.bundle_dir``); a slash in the app code is sanitised (``AR/WS`` → ``AR_WS``) to
    stay filesystem-safe. The stages that join *back* to that layout (``enrich`` records,
    ``discover`` doc-types, ``normalize`` source-shas) all key on this tuple — built here once so
    the identity can't drift across them."""
    return (safe_component(app_code), safe_component(doc_slug))


def bundle_path(app_code: str, doc_slug: str) -> str:
    """The convert-bundle identity as a ``"<app>/<slug>"`` path string (``"/".join`` of
    :func:`bundle_key`) — for callers that key on the path form rather than the tuple."""
    return "/".join(bundle_key(app_code, doc_slug))


__all__ = ["HasIdentity", "anchor_key", "bundle_key", "bundle_path", "doc_id", "slug_stem"]
