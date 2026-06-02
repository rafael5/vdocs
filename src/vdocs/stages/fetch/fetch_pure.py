"""Pure fetch logic — target selection + index entries (§8 fetch, §16).

The pipeline is **DOCX-only** (§1): DOCX is the richer, structure-preserving source and the
only format converted/normalized/published. PDF is out of scope — there is no format fallback,
and a document published only as PDF is never a fetch target. No I/O: the ``stage.py`` driver
does the downloading and content-addressed storage; these functions only decide *what* to fetch
and *how* to address it.
"""

from __future__ import annotations

from urllib.parse import urlparse

from vdocs.models.catalog import EnrichedRecord


def url_ext(url: str) -> str:
    """The lowercased file extension of a URL (without the dot), or '' if none."""
    name = urlparse(url).path.rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def select_fetch_targets(records: list[EnrichedRecord]) -> list[EnrichedRecord]:
    """One fetch target per logical document (same ``doc_slug``) — the DOCX representation.

    Two filters, both narrowing: genuine documents only (chrome/forms with ``noise_type`` set
    are excluded, §9.5) and in-scope only (``out_of_scope_reason`` set ⇒ a non-DOCX
    representation, §1 — a PDF-only logical document has no in-scope row and so yields no target).
    """
    best: dict[str, EnrichedRecord] = {}
    for rec in records:
        if rec.noise_type or rec.out_of_scope_reason:
            continue
        best.setdefault(rec.doc_slug, rec)
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
