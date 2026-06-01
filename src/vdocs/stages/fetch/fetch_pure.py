"""Pure fetch logic — URL derivation, target selection, index entries (§8 fetch, §16).

DOCX is preferred over PDF (richer for conversion). No I/O: the ``stage.py`` driver does
the downloading and content-addressed storage; these functions only decide *what* to fetch
and *how* to address it.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from vdocs.models.catalog import EnrichedDocument

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


def select_fetch_targets(docs: list[EnrichedDocument]) -> list[EnrichedDocument]:
    """One fetch target per logical document (same ``doc_slug``), preferring the DOCX format."""
    best: dict[str, EnrichedDocument] = {}
    for doc in docs:
        current = best.get(doc.doc_slug)
        if current is None or (doc.file_ext == ".docx" and current.file_ext != ".docx"):
            best[doc.doc_slug] = doc
    return list(best.values())


def index_entry(*, app_code: str, title: str, source_url: str, ext: str) -> dict[str, str]:
    """A ``raw/index.json`` entry: sha256 → (app_code, title, source_url, ext)."""
    return {"app_code": app_code, "title": title, "source_url": source_url, "ext": ext}
