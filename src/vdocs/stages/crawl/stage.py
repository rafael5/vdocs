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

import json
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
from vdocs.stages.crawl.snapshot_pure import canonical_hash, snapshot_name, snapshot_order

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
        payload = catalog.model_dump_json(indent=2).encode("utf-8")
        cas.atomic_write(ctx.cfg.catalog_raw, payload)
        cas.atomic_write(ctx.cfg.catalog_raw.with_suffix(".csv"), _to_csv(catalog).encode("utf-8"))
        _keep_snapshot(ctx.cfg.inventory_snapshots, catalog, payload, taken_at=ctx.clock())
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


def _keep_snapshot(root: Path, catalog: Catalog, payload: bytes, *, taken_at: str) -> str | None:
    """Preserve this crawl as dated, immutable evidence (VO.2); ``None`` when it duplicates.

    Deduplicated against the **newest** snapshot's canonical content hash, so a crawl that found
    the same thing (or the same thing in a different page order) does not fabricate history —
    while a VDL that reverts to an earlier state still records that it did. Nothing already in
    ``root`` is ever rewritten: the name is chosen to be free.
    """
    existing = (
        sorted((p.name for p in root.iterdir() if p.is_dir()), key=snapshot_order)
        if root.exists()
        else []
    )
    digest = canonical_hash(catalog)
    if existing and _recorded_hash(root / existing[-1]) == digest:
        log.info("crawl-snapshot-unchanged", newest=existing[-1], canonical_hash=digest[:12])
        return None

    name = snapshot_name(taken_at[:10], existing)
    cas.atomic_write(root / name / "catalog.raw.json", payload)
    cas.atomic_write(
        root / name / "SNAPSHOT.json",
        json.dumps(
            {
                "taken_at": taken_at,
                "canonical_hash": digest,
                "sections": len(catalog.sections),
                "applications": sum(len(s.applications) for s in catalog.sections),
                "documents": sum(
                    len(a.documents) for s in catalog.sections for a in s.applications
                ),
            },
            indent=2,
            sort_keys=True,
        ).encode("utf-8"),
    )
    log.info("crawl-snapshot-kept", snapshot=name, canonical_hash=digest[:12])
    return name


def _recorded_hash(snapshot: Path) -> str:
    """The canonical hash a snapshot recorded, or '' when it has none (unreadable/legacy)."""
    meta = snapshot / "SNAPSHOT.json"
    if not meta.is_file():
        return ""
    try:
        value = json.loads(meta.read_text(encoding="utf-8")).get("canonical_hash", "")
    except (ValueError, OSError):
        log.warning("crawl-snapshot-meta-unreadable", path=str(meta))
        return ""
    return str(value)


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
