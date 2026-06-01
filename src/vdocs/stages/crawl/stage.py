"""The `crawl` stage driver — walk the VDL site into ``catalog.raw`` (§8).

Thin I/O around the pure parsers: it fetches each page (via an injected text fetcher, so
tests need no network) and writes the assembled catalog as JSON + a flat CSV. FORCE_ONLY:
network crawls run only when explicitly requested.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Callable

from vdocs.contracts.registry import CATALOG_RAW, VDL
from vdocs.kernel import cas, http
from vdocs.models.catalog import Catalog
from vdocs.models.stage import Idempotency, RunResult
from vdocs.orchestrator.stage import Stage, StageContext

TextFetcher = Callable[[str], str]

_CSV_COLUMNS = [
    "section_name",
    "app_code",
    "app_name",
    "app_status",
    "title",
    "url",
    "filename",
    "file_ext",
    "doc_type_label",
    "file_date",
]


class CrawlStage(Stage):
    name = "crawl"
    description = "walk the VDL site (index → sections → applications) into catalog.raw"
    requires = [VDL]
    produces = [CATALOG_RAW]
    idempotency = Idempotency.FORCE_ONLY

    def __init__(self, fetch_text: TextFetcher | None = None) -> None:
        self._get = fetch_text or http.get_text

    def run(self, ctx: StageContext, force: bool) -> RunResult:
        base = ctx.cfg.vdl_base_url
        from vdocs.stages.crawl import crawl_pure as cp

        sections = cp.parse_index(self._get(base), base)
        n_apps = n_docs = 0
        for section in sections:
            apps = cp.parse_section_page(self._get(section.url), base)
            for app in apps:
                app.documents = cp.parse_application_page(self._get(app.url))
                n_docs += len(app.documents)
            section.applications = apps
            n_apps += len(apps)

        catalog = Catalog(sections=sections)
        cas.atomic_write(ctx.cfg.catalog_raw, catalog.model_dump_json(indent=2).encode("utf-8"))
        cas.atomic_write(ctx.cfg.catalog_raw.with_suffix(".csv"), _to_csv(catalog).encode("utf-8"))
        return RunResult(
            counts={"sections": len(sections), "applications": n_apps, "documents": n_docs}
        )


def _to_csv(catalog: Catalog) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_CSV_COLUMNS)
    writer.writeheader()
    for section, app, doc in catalog.walk():
        writer.writerow(
            {
                "section_name": section.name,
                "app_code": app.app_code,
                "app_name": app.name,
                "app_status": app.status,
                "title": doc.title,
                "url": doc.url,
                "filename": doc.filename,
                "file_ext": doc.file_ext,
                "doc_type_label": doc.doc_type_label,
                "file_date": doc.file_date,
            }
        )
    return buf.getvalue()
