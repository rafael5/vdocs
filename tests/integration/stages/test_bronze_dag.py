"""End-to-end bronze DAG: crawl → catalog → fetch, driven by the orchestrator (§8, §17.2).

No live network — a fake text fetcher serves fixture VDL HTML and a fake byte fetcher serves
document bytes. Proves the three real stages run through the same preflight→run→postflight
spine, produce the bronze artifacts, and skip correctly on a clean re-run.
"""

import json

import pytest

from vdocs.models.catalog import DriftStatus, EnrichedCatalog
from vdocs.orchestrator.engine import Orchestrator
from vdocs.stages.catalog.stage import CatalogStage
from vdocs.stages.crawl.stage import CrawlStage
from vdocs.stages.fetch.stage import FetchStage

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


def fake_text(url: str) -> str:
    return PAGES.get(url, "<html></html>")


def fake_bytes(url: str) -> bytes | None:
    return DOC_BYTES.get(url)


@pytest.fixture
def bronze_ctx(ctx):
    # point crawl at the fake VDL base
    ctx.cfg = ctx.cfg.model_copy(update={"vdl_base_url": "https://vdl.test/"})
    return ctx


def _stages():
    return [
        CrawlStage(fetch_text=fake_text),
        CatalogStage(),
        FetchStage(fetch_bytes=fake_bytes),
    ]


def test_bronze_dag_runs_end_to_end(bronze_ctx):
    ctx = bronze_ctx
    results = Orchestrator(_stages()).run(ctx, force=True)

    assert [r.stage for r in results] == ["crawl", "catalog", "fetch"]
    assert all(r.status == "ok" for r in results)

    # crawl wrote catalog.raw with the ADT doc pair
    assert ctx.cfg.catalog_raw.exists()
    crawl_run = ctx.state.get("crawl")
    assert crawl_run.counts == {"sections": 2, "applications": 1, "documents": 2}

    # catalog enriched both docs as NEW with the version-free group key
    ecat = EnrichedCatalog.model_validate_json(ctx.cfg.catalog_enriched.read_text())
    assert len(ecat.documents) == 2
    assert {d.patch_id for d in ecat.documents} == {"DG*5.3*1057"}
    assert {d.group_key for d in ecat.documents} == {"ADT:DG:IG"}
    assert all(d.drift_status is DriftStatus.NEW for d in ecat.documents)

    # fetch stored one logical doc (DOCX preferred) into the CAS + wrote the index
    fetch_run = ctx.state.get("fetch")
    assert fetch_run.counts == {"targets": 1, "fetched": 1, "failed": 0}
    index = json.loads(ctx.cfg.raw_index.read_text())
    assert len(index) == 1
    (entry,) = index.values()
    assert entry["app_code"] == "ADT" and entry["ext"] == "docx"
    assert list(ctx.cfg.bronze_raw.glob("*.docx"))  # the content-addressed file exists


def test_bronze_dag_skips_on_clean_rerun(bronze_ctx):
    ctx = bronze_ctx
    orch = Orchestrator(_stages())
    orch.run(ctx, force=True)
    second = orch.run(ctx)  # no force

    # crawl is FORCE_ONLY → skipped; catalog & fetch SKIP_IF_UNCHANGED → skipped
    assert second == [None, None, None]


def test_fetch_falls_back_to_pdf_when_docx_missing(bronze_ctx):
    ctx = bronze_ctx
    # only the PDF is available upstream
    pdf_url = DOCX_URL.replace(".docx", ".pdf")
    Orchestrator(
        [
            CrawlStage(fetch_text=fake_text),
            CatalogStage(),
            FetchStage(fetch_bytes={pdf_url: b"%PDF-1.5 fake"}.get),
        ]
    ).run(ctx, force=True)

    index = json.loads(ctx.cfg.raw_index.read_text())
    (entry,) = index.values()
    assert entry["ext"] == "pdf"  # candidate_urls swapped .docx → .pdf


def test_fetch_records_failure_when_no_format_available(bronze_ctx):
    ctx = bronze_ctx
    # neither DOCX nor PDF is available upstream → the doc is counted failed, not stored
    Orchestrator(
        [CrawlStage(fetch_text=fake_text), CatalogStage(), FetchStage(fetch_bytes=lambda u: None)]
    ).run(ctx, force=True)

    assert ctx.state.get("fetch").counts == {"targets": 1, "fetched": 0, "failed": 1}
    assert json.loads(ctx.cfg.raw_index.read_text()) == {}
