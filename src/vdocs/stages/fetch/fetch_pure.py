"""Pure fetch logic — URL derivation, target selection, index entries (§8 fetch, §16).

DOCX is preferred over PDF (richer for conversion). No I/O: the ``stage.py`` driver does
the downloading and content-addressed storage; these functions only decide *what* to fetch
and *how* to address it.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from vdocs.models.catalog import EnrichedRecord

_EXT_RE = re.compile(r"\.(docx|pdf)$", re.I)


def swap_extension(url: str) -> str:
    """Swap ``.docx`` ↔ ``.pdf`` in a URL; return it unchanged if neither extension is present."""
    m = _EXT_RE.search(url)
    if not m:
        return url
    new = "pdf" if m.group(1).lower() == "docx" else "docx"
    return _EXT_RE.sub(f".{new}", url)


def candidate_urls(url: str) -> list[str]:
    """Ordered URLs to try for a document: its own URL, then the other format as fallback."""
    swapped = swap_extension(url)
    return [url] if swapped == url else [url, swapped]


def url_ext(url: str) -> str:
    """The lowercased file extension of a URL (without the dot), or '' if none."""
    name = urlparse(url).path.rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def select_fetch_targets(records: list[EnrichedRecord]) -> list[EnrichedRecord]:
    """One fetch target per logical document (same ``doc_slug``), preferring the DOCX format.

    Only genuine documents are candidates — chrome/forms (``noise_type`` set) are excluded
    here so nothing outside a green inventory row is ever fetched (§9.5).
    """
    best: dict[str, EnrichedRecord] = {}
    for rec in records:
        if rec.noise_type:
            continue
        current = best.get(rec.doc_slug)
        if current is None or (rec.doc_format == "docx" and current.doc_format != "docx"):
            best[rec.doc_slug] = rec
    return list(best.values())


def index_entry(
    *, app_code: str, doc_slug: str, title: str, source_url: str, ext: str
) -> dict[str, str]:
    """A ``raw/index.json`` entry: sha256 → provenance. ``app_code``/``doc_slug`` give the
    downstream bundle path (``<app>/<slug>/`` in ``text@converted``)."""
    return {
        "app_code": app_code,
        "doc_slug": doc_slug,
        "title": title,
        "source_url": source_url,
        "ext": ext,
    }
