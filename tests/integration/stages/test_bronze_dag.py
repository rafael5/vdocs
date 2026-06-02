"""End-to-end bronze DAG: crawl → catalog → fetch, driven by the orchestrator (§8, §17.2).

No live network — a fake text fetcher serves fixture VDL HTML and a fake byte fetcher serves
document bytes. Proves the three real stages run through the same preflight→run→postflight
spine, produce the bronze artifacts, and skip correctly on a clean re-run.
"""

import json

import pytest

from vdocs.kernel.http import Page
from vdocs.models.catalog import EnrichedInventory
from vdocs.orchestrator.engine import Orchestrator
from vdocs.stages.catalog.stage import CatalogStage
from vdocs.stages.crawl.stage import CrawlStage
from vdocs.stages.fetch.stage import FetchStage
from vdocs.stages.serve_inventory.stage import ServeInventoryStage

INDEX_HTML = """
<a href="section.asp?secid=1">Clinical</a>
<a href="section.asp?secid=2">Infrastructure</a>
"""
SECTION1_HTML = """
<a href="application.asp?appid=55">Admission Discharge Transfer (ADT)</a>
"""
# RELATIVE doc hrefs, exactly as live VDL serves them — must resolve against the app-page URL.
APP_HTML = """
<table>
  <tr><td>DG*5.3*1057 Deployment, Installation, Back-Out, and Rollback Guide</td>
      <td><a href="documents/Clinical/ADT/dg_5_3_1057_dibr.docx">DOCX</a></td><td>03/2024</td></tr>
  <tr><td>DG*5.3*1057 Deployment, Installation, Back-Out, and Rollback Guide</td>
      <td><a href="documents/Clinical/ADT/dg_5_3_1057_dibr.pdf">PDF</a></td><td>03/2024</td></tr>
</table>
"""

PAGES = {
    "https://vdl.test/": INDEX_HTML,
    "https://vdl.test/section.asp?secid=1": SECTION1_HTML,
    "https://vdl.test/section.asp?secid=2": "<html></html>",
    "https://vdl.test/application.asp?appid=55": APP_HTML,
}
# relative href resolves against the app-page URL (.../application.asp?appid=55)
DOCX_URL = "https://vdl.test/documents/Clinical/ADT/dg_5_3_1057_dibr.docx"
DOC_BYTES = {DOCX_URL: b"PK\x03\x04 fake docx bytes"}


def fake_page(url: str) -> Page:
    return Page(text=PAGES.get(url, "<html></html>"), url=url, status_code=200)


def fake_bytes(url: str) -> bytes | None:
    return DOC_BYTES.get(url)


@pytest.fixture
def bronze_ctx(ctx):
    # point crawl at the fake VDL base
    ctx.cfg = ctx.cfg.model_copy(update={"vdl_base_url": "https://vdl.test/"})
    return ctx


def _stages():
    return [
        CrawlStage(page_fetcher=fake_page),
        CatalogStage(),
        ServeInventoryStage(),
        FetchStage(fetch_bytes=fake_bytes),
    ]


def test_bronze_dag_runs_end_to_end(bronze_ctx):
    ctx = bronze_ctx
    results = Orchestrator(_stages()).run(ctx, force=True)

    assert [r.stage for r in results] == ["crawl", "catalog", "serve-inventory", "fetch"]
    assert all(r.status == "ok" for r in results)

    # crawl wrote catalog.raw with the ADT doc pair
    assert ctx.cfg.catalog_raw.exists()
    crawl_run = ctx.state.get("crawl")
    assert crawl_run.counts == {"sections": 2, "applications": 1, "documents": 2, "skipped": 0}

    # catalog enriched both docs (DOCX + PDF) with full identity + the dual keys
    inv = EnrichedInventory.model_validate_json(ctx.cfg.catalog_enriched.read_text())
    assert len(inv.records) == 2
    assert {r.patch_id for r in inv.records} == {"DG*5.3*1057"}
    assert {r.doc_code for r in inv.records} == {"DIBR"}
    assert {r.group_key for r in inv.records} == {"ADT:DG:5.3"}  # v1 version key
    assert {r.anchor_key for r in inv.records} == {"ADT:DG:DIBR"}  # version-free (vdocs §9.4)
    assert all(r.noise_type == "" for r in inv.records)

    # fetch stored one logical doc (DOCX preferred) into the CAS + wrote the index
    fetch_run = ctx.state.get("fetch")
    assert fetch_run.counts == {"targets": 1, "fetched": 1, "failed": 0}
    index = json.loads(ctx.cfg.raw_index.read_text())
    assert len(index) == 1
    (entry,) = index.values()
    assert entry["app_code"] == "ADT" and entry["ext"] == "docx"
    assert list(ctx.cfg.bronze_raw.glob("*.docx"))  # the content-addressed file exists

    # fetch recorded the per-document acquisition status (§5.5) keyed by doc_id
    acq = ctx.state.get_acquisition("ADT:dg_5_3_1057_dibr")
    assert acq is not None and acq.status == "fetched"
    assert acq.sha256 and acq.bytes and acq.fetched_at


def test_bronze_dag_skips_on_clean_rerun(bronze_ctx):
    ctx = bronze_ctx
    orch = Orchestrator(_stages())
    orch.run(ctx, force=True)
    second = orch.run(ctx)  # no force

    # crawl is FORCE_ONLY → skipped; catalog/serve-inventory/fetch SKIP_IF_UNCHANGED → skipped
    assert second == [None, None, None, None]


def test_fetch_does_not_fall_back_to_pdf(bronze_ctx):
    ctx = bronze_ctx
    # only the PDF is downloadable upstream — but PDF is out of scope (§1), so fetch targets
    # the DOCX only and records a failure rather than grabbing the PDF.
    pdf_url = DOCX_URL.replace(".docx", ".pdf")
    Orchestrator(
        [
            CrawlStage(page_fetcher=fake_page),
            CatalogStage(),
            ServeInventoryStage(),
            FetchStage(fetch_bytes={pdf_url: b"%PDF-1.5 fake"}.get),
        ]
    ).run(ctx, force=True)

    assert ctx.state.get("fetch").counts == {"targets": 1, "fetched": 0, "failed": 1}
    assert json.loads(ctx.cfg.raw_index.read_text()) == {}  # the PDF was never stored
    acq = ctx.state.get_acquisition("ADT:dg_5_3_1057_dibr")
    assert acq is not None and acq.status == "failed"


def test_fetch_records_failure_when_docx_unavailable(bronze_ctx):
    ctx = bronze_ctx
    # the DOCX is not downloadable upstream → the doc is counted failed, not stored
    Orchestrator(
        [
            CrawlStage(page_fetcher=fake_page),
            CatalogStage(),
            ServeInventoryStage(),
            FetchStage(fetch_bytes=lambda u: None),
        ]
    ).run(ctx, force=True)

    assert ctx.state.get("fetch").counts == {"targets": 1, "fetched": 0, "failed": 1}
    acq = ctx.state.get_acquisition("ADT:dg_5_3_1057_dibr")
    assert acq is not None and acq.status == "failed" and acq.error == "docx unavailable"
    assert json.loads(ctx.cfg.raw_index.read_text()) == {}
