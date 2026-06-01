"""CrawlStage driver behaviour — polite page fetcher, final-URL base, non-200 skip (B2, §3).

No network: a fake page fetcher returns ``Page`` records (text + final URL + status). These
tests prove the driver (a) resolves doc links against each application page's *final* URL,
(b) skips a non-200 section/app with a WARN instead of aborting, and (c) writes the raw
catalog onto the inventory-bronze path.
"""

from __future__ import annotations

import json

from vdocs.kernel.http import Page
from vdocs.models.catalog import Catalog
from vdocs.orchestrator.engine import Orchestrator
from vdocs.stages.crawl.stage import CrawlStage

INDEX = '<a href="section.asp?secid=1">Clinical</a><a href="section.asp?secid=2">Infra</a>'
SECTION1 = (
    '<a href="application.asp?appid=10">Nursing (NUR)</a>'
    '<a href="application.asp?appid=11">Broken (BRK)</a>'
)
# relative doc href — must resolve against the app page's FINAL url
APP10 = (
    "<table><tr><td>NUR*1.0*1 User Manual</td>"
    '<td><a href="documents/Clinical/NUR/nur_1_0_1_um.docx">DOCX</a></td><td>03/2024</td></tr>'
    "</table>"
)


def _page_for(url: str) -> Page:
    # secid=2 section returns 500 (transient-exhausted) → skipped with a WARN.
    # appid=11 returns 404 → skipped with a WARN.
    if url.endswith("/vdl/"):
        return Page(text=INDEX, url=url, status_code=200)
    if url.endswith("section.asp?secid=1"):
        return Page(text=SECTION1, url=url, status_code=200)
    if url.endswith("section.asp?secid=2"):
        return Page(text="", url=url, status_code=500)
    if url.endswith("application.asp?appid=10"):
        # the page redirected: final URL differs from the requested one
        final = "https://www.va.gov/vdl/application.asp?appid=10"
        return Page(text=APP10, url=final, status_code=200)
    if url.endswith("application.asp?appid=11"):
        return Page(text="", url=url, status_code=404)
    return Page(text="<html></html>", url=url, status_code=200)


def test_crawl_resolves_against_final_url_and_skips_non_200(ctx):
    ctx.cfg = ctx.cfg.model_copy(update={"vdl_base_url": "https://www.va.gov/vdl/"})
    (result,) = Orchestrator([CrawlStage(page_fetcher=_page_for)]).run(ctx, force=True)

    assert result.status == "ok"
    # secid=2 section (500) + appid=11 app (404) are both skipped with a WARN; the BRK app is
    # still a known application (kept with empty documents — inventory keeps the signal).
    assert result.counts == {
        "sections": 2,
        "applications": 2,
        "documents": 1,
        "skipped": 2,
    }

    catalog = Catalog.model_validate_json(ctx.cfg.catalog_raw.read_text())
    by_name = {s.name: s for s in catalog.sections}
    assert by_name["Infra"].applications == []  # non-200 section retained, no apps
    section = by_name["Clinical"]
    by_code = {a.app_code: a for a in section.applications}
    assert by_code["BRK"].documents == []  # skipped app retained, no docs
    (doc,) = by_code["NUR"].documents
    # resolved against the FINAL application-page URL → .../vdl/documents/...
    assert doc.url == "https://www.va.gov/vdl/documents/Clinical/NUR/nur_1_0_1_um.docx"


def test_crawl_index_non_200_yields_empty_catalog(ctx):
    ctx.cfg = ctx.cfg.model_copy(update={"vdl_base_url": "https://www.va.gov/vdl/"})

    def dead_index(url: str) -> Page:
        return Page(text="", url=url, status_code=503)

    (result,) = Orchestrator([CrawlStage(page_fetcher=dead_index)]).run(ctx, force=True)
    assert result.status == "ok"
    assert result.counts == {"sections": 0, "applications": 0, "documents": 0, "skipped": 0}
    assert Catalog.model_validate_json(ctx.cfg.catalog_raw.read_text()).sections == []


def test_crawl_writes_inventory_bronze_path_and_csv(ctx):
    ctx.cfg = ctx.cfg.model_copy(update={"vdl_base_url": "https://www.va.gov/vdl/"})
    Orchestrator([CrawlStage(page_fetcher=_page_for)]).run(ctx, force=True)

    raw = ctx.cfg.catalog_raw
    assert raw == ctx.cfg.inventory_bronze / "catalog.raw.json"
    assert raw.exists()
    csv_view = raw.with_suffix(".csv")
    assert csv_view.name == "catalog.raw.csv"
    assert "nur_1_0_1_um.docx" in csv_view.read_text()
    # json round-trips
    json.loads(raw.read_text())
