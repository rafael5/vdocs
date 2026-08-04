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

from pathlib import Path

import structlog

from vdocs.contracts.registry import CATALOG_RAW, VDL
from vdocs.kernel import cas
from vdocs.kernel import csv as kcsv
from vdocs.kernel.http import PageFetcher, PoliteClient
from vdocs.models.catalog import Catalog
from vdocs.models.stage import Idempotency, RunResult
from vdocs.orchestrator.stage import PostflightError, Stage, StageContext
from vdocs.stages.crawl.floor_pure import CrawlYield, check_floor, yield_of

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

    def __init__(
        self, page_fetcher: PageFetcher | None = None, *, accept_shrink: bool = False
    ) -> None:
        self._fetch = page_fetcher
        # CI.1: the cheap acknowledgement of a genuinely smaller VDL — lets one below-floor
        # crawl through (loudly) so it becomes the new baseline. Wired to `vdocs crawl
        # --accept-shrink`; never the default.
        self.accept_shrink = accept_shrink

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
        # CI.1 completeness floor (audit R‑4): compare against the last good crawl — the file on
        # disk, which is always the last crawl that passed — BEFORE overwriting it. Failing here,
        # ahead of the writes, is what makes the gate fail closed on the artifact.
        verdict = check_floor(
            self._prior_yield(ctx.cfg.catalog_raw),
            yield_of(catalog),
            floor_ratio=ctx.cfg.crawl_floor_ratio,
        )
        if not verdict.ok:
            if not self.accept_shrink:
                raise PostflightError(
                    f"crawl completeness floor: {verdict.reason} — the previous good catalog "
                    "is left in place. A genuinely smaller VDL is accepted with: "
                    "vdocs crawl --accept-shrink"
                )
            log.warning("crawl-shrink-accepted", reason=verdict.reason)
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

    @staticmethod
    def _prior_yield(catalog_raw: Path) -> CrawlYield | None:
        """The last good crawl's yield, from the artifact on disk (``None`` on a first crawl).

        An unreadable file is loud-warned and treated as no baseline — bronze is written
        atomically, so a corrupt file is already a damaged lake, and letting it brick every
        future crawl would compound the damage instead of repairing it."""
        if not catalog_raw.exists():
            return None
        try:
            return yield_of(Catalog.model_validate_json(catalog_raw.read_text(encoding="utf-8")))
        except ValueError:
            log.warning("crawl-baseline-unreadable", path=str(catalog_raw))
            return None


def _to_csv(catalog: Catalog) -> str:
    rows = (
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
        for section, app, doc in catalog.walk()
    )
    return kcsv.to_csv(_CSV_COLUMNS, rows)
