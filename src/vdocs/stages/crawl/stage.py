"""The `crawl` stage driver — walk the VDL site into the inventory bronze catalog (§8, §3).

Thin I/O around the pure parsers (``crawl_pure``): it fetches each page through a polite
client (``kernel.http.PoliteClient``: descriptive UA, retry/backoff, capped redirects, an
inter-request delay) and resolves every level's links against **that page's final URL**
(post-redirect) — live VDL doc links are relative ("documents/…"), so the application
page's own resolved URL is the correct base (§3.4, lessons §8). A section/app that returns
non-200 is skipped with a WARN, never aborting the whole crawl (§3.6). The assembled raw
catalog lands at ``inventory/bronze/catalog.raw.{json,csv}``. FORCE_ONLY: network crawls
run only when explicitly requested.
"""

from __future__ import annotations

import csv
import io

import structlog

from vdocs.contracts.registry import CATALOG_RAW, VDL
from vdocs.kernel import cas
from vdocs.kernel.http import PageFetcher, PoliteClient
from vdocs.models.catalog import Catalog
from vdocs.models.stage import Idempotency, RunResult
from vdocs.orchestrator.stage import Stage, StageContext

log = structlog.get_logger(__name__)

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
    description = "walk the VDL site (index → sections → applications) into inventory bronze"
    requires = [VDL]
    produces = [CATALOG_RAW]
    idempotency = Idempotency.FORCE_ONLY

    def __init__(self, page_fetcher: PageFetcher | None = None) -> None:
        self._fetch = page_fetcher

    def run(self, ctx: StageContext, force: bool) -> RunResult:
        from vdocs.stages.crawl import crawl_pure as cp

        fetch = (
            self._fetch
            or PoliteClient(user_agent=ctx.cfg.user_agent, delay=ctx.cfg.crawl_delay).get_page
        )

        index = fetch(ctx.cfg.vdl_base_url)
        if index.status_code != 200:
            log.warning("crawl-index-non-200", url=ctx.cfg.vdl_base_url, status=index.status_code)
            sections = []
        else:
            sections = cp.parse_index(index.text, index.url)

        n_apps = n_docs = n_skipped = 0
        for section in sections:
            page = fetch(section.url)
            if page.status_code != 200:
                log.warning("crawl-section-skipped", url=section.url, status=page.status_code)
                n_skipped += 1
                continue
            apps = cp.parse_section_page(page.text, base_url=page.url)
            for app in apps:
                app_page = fetch(app.url)
                if app_page.status_code != 200:
                    log.warning("crawl-app-skipped", url=app.url, status=app_page.status_code)
                    n_skipped += 1
                    continue
                app.documents = cp.parse_application_page(app_page.text, base_url=app_page.url)
                n_docs += len(app.documents)
            section.applications = apps
            n_apps += len(apps)

        catalog = Catalog(sections=sections)
        cas.atomic_write(ctx.cfg.catalog_raw, catalog.model_dump_json(indent=2).encode("utf-8"))
        cas.atomic_write(ctx.cfg.catalog_raw.with_suffix(".csv"), _to_csv(catalog).encode("utf-8"))
        return RunResult(
            counts={
                "sections": len(sections),
                "applications": n_apps,
                "documents": n_docs,
                "skipped": n_skipped,
            }
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
