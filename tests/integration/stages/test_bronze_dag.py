"""End-to-end bronze DAG: crawl → catalog → fetch, driven by the orchestrator (§8, §17.2).

No live network — a fake text fetcher serves fixture VDL HTML and a fake byte fetcher serves
document bytes. Proves the three real stages run through the same preflight→run→postflight
spine, produce the bronze artifacts, and skip correctly on a clean re-run.
"""

import json

import pytest

from vdocs.kernel.http import Page
from vdocs.models.catalog import EnrichedInventory
from vdocs.models.stage import Acquisition
from vdocs.orchestrator.engine import Orchestrator
from vdocs.stages.catalog.stage import CatalogStage
from vdocs.stages.crawl.stage import CrawlStage
from vdocs.stages.fetch import fetch_pure as fp
from vdocs.stages.fetch.fetch_pure import Selection
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
  <tr><td>DG*5.3*1057 User Manual</td>
      <td><a href="documents/Clinical/ADT/dg_5_3_1057_um.docx">DOCX</a></td><td>03/2024</td></tr>
  <tr><td>DG*5.3*1057 User Manual</td>
      <td><a href="documents/Clinical/ADT/dg_5_3_1057_um.pdf">PDF</a></td><td>03/2024</td></tr>
</table>
"""

PAGES = {
    "https://vdl.test/": INDEX_HTML,
    "https://vdl.test/section.asp?secid=1": SECTION1_HTML,
    "https://vdl.test/section.asp?secid=2": "<html></html>",
    "https://vdl.test/application.asp?appid=55": APP_HTML,
}
# relative href resolves against the app-page URL (.../application.asp?appid=55)
DOCX_URL = "https://vdl.test/documents/Clinical/ADT/dg_5_3_1057_um.docx"
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
        FetchStage(fetch_bytes=fake_bytes, selection=Selection(all_=True)),
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
    assert {r.doc_code for r in inv.records} == {"UM"}
    assert {r.group_key for r in inv.records} == {"ADT:DG:5.3"}  # v1 version key
    assert {r.anchor_key for r in inv.records} == {"ADT:DG:UM:dg_um"}  # version-free (vdocs §9.4)
    assert all(r.noise_type == "" for r in inv.records)

    # fetch stored one logical doc (DOCX preferred) into the CAS + wrote the index
    fetch_run = ctx.state.get("fetch")
    assert fetch_run.counts == {
        "targets": 1,
        "indexed": 1,
        "retained": 0,
        "fetched": 1,
        "skipped": 0,
        "failed": 0,
        "permanent_missing": 0,
        "bad_content": 0,
    }
    # the index is doc_id-keyed and DERIVED from acquisitions ⋈ admitted targets (P1.1)
    index = fp.parse_raw_index(json.loads(ctx.cfg.raw_index.read_text()))
    assert list(index) == ["ADT:dg_5_3_1057_um"]
    (entry,) = index.values()
    assert entry["app_code"] == "ADT" and entry["ext"] == "docx" and entry["sha256"]
    assert list(ctx.cfg.bronze_raw.glob("*.docx"))  # the content-addressed file exists

    # fetch recorded the per-document acquisition status (§5.5) keyed by doc_id
    acq = ctx.state.get_acquisition("ADT:dg_5_3_1057_um")
    assert acq is not None and acq.status == "fetched"
    assert acq.sha256 and acq.bytes and acq.fetched_at


def test_bronze_dag_skips_on_clean_rerun(bronze_ctx):
    ctx = bronze_ctx
    orch = Orchestrator(_stages())
    orch.run(ctx, force=True)
    second = orch.run(ctx)  # no force

    # crawl is FORCE_ONLY → skipped; catalog/serve-inventory/fetch SKIP_IF_UNCHANGED → skipped
    assert second == [None, None, None, None]


def test_fetch_reruns_when_selection_changes(bronze_ctx):
    ctx = bronze_ctx
    # bring the inventory track up and fetch everything once
    Orchestrator(_stages()).run(ctx, force=True)

    # re-running fetch with the SAME (--all) selection, no force → skipped (inputs unchanged)
    same = Orchestrator([FetchStage(fetch_bytes=fake_bytes, selection=Selection(all_=True))])
    assert same.run(ctx) == [None]

    # a DIFFERENT selection changes fetch's input fingerprint (§5.6) → the stage re-runs (not an
    # orchestrator skip), but the doc is already in the CAS so it's skipped, not re-downloaded (F2).
    narrowed = Orchestrator(
        [FetchStage(fetch_bytes=fake_bytes, selection=Selection(apps=frozenset({"ADT"})))]
    )
    (sr,) = narrowed.run(ctx)
    assert sr is not None and sr.status == "ok"
    assert sr.counts["fetched"] == 0 and sr.counts["skipped"] == 1  # idempotent resume


def test_fetch_accrues_attempts_across_retries(bronze_ctx):
    ctx = bronze_ctx
    # bring only the inventory track up (no successful fetch yet)
    Orchestrator([CrawlStage(page_fetcher=fake_page), CatalogStage(), ServeInventoryStage()]).run(
        ctx, force=True
    )

    # the DOCX is unavailable; force two retry runs of fetch alone
    failing = lambda u: None  # noqa: E731
    Orchestrator([FetchStage(fetch_bytes=failing, selection=Selection(all_=True))]).run(
        ctx, force=True
    )
    first = ctx.state.get_acquisition("ADT:dg_5_3_1057_um")
    assert first.status == "failed" and first.attempts == 1

    Orchestrator([FetchStage(fetch_bytes=failing, selection=Selection(all_=True))]).run(
        ctx, force=True
    )
    second = ctx.state.get_acquisition("ADT:dg_5_3_1057_um")
    # attempts accrue; first_attempt_at is preserved, last_attempt_at advances (§5.5)
    assert second.attempts == 2
    assert second.first_attempt_at == first.first_attempt_at
    assert second.last_attempt_at > first.last_attempt_at


def _inventory_only(ctx):
    Orchestrator([CrawlStage(page_fetcher=fake_page), CatalogStage(), ServeInventoryStage()]).run(
        ctx, force=True
    )


def test_fetch_skips_already_present_doc_on_forced_rerun(bronze_ctx):
    # F2: a forced re-run must NOT re-download a doc already in the CAS — the byte fetcher is not
    # called a second time; the doc is counted skipped, not fetched.
    ctx = bronze_ctx
    _inventory_only(ctx)
    calls: list[str] = []

    def counting(u: str) -> bytes | None:
        calls.append(u)
        return DOC_BYTES.get(u)

    sel = Selection(all_=True)
    Orchestrator([FetchStage(fetch_bytes=counting, selection=sel)]).run(ctx, force=True)
    assert len(calls) == 1  # fetched once
    (sr,) = Orchestrator([FetchStage(fetch_bytes=counting, selection=sel)]).run(ctx, force=True)
    assert len(calls) == 1  # forced re-run did NOT re-GET — CAS hit
    assert sr.counts["skipped"] == 1 and sr.counts["fetched"] == 0


def test_refetch_redownloads_already_present_doc(bronze_ctx):
    ctx = bronze_ctx
    _inventory_only(ctx)
    calls: list[str] = []

    def counting(u: str) -> bytes | None:
        calls.append(u)
        return DOC_BYTES.get(u)

    sel = Selection(all_=True)
    Orchestrator([FetchStage(fetch_bytes=counting, selection=sel)]).run(ctx, force=True)
    (sr,) = Orchestrator([FetchStage(fetch_bytes=counting, selection=sel, refetch=True)]).run(
        ctx, force=True
    )
    assert len(calls) == 2  # --refetch re-downloaded the CAS-present doc
    assert sr.counts["fetched"] == 1 and sr.counts["skipped"] == 0


def test_fetch_gives_up_after_attempt_cap_and_warns(bronze_ctx):
    # F3: a persistently-unavailable DOCX becomes permanent_missing after MAX_FETCH_ATTEMPTS, the
    # run WARNs (with the URL), and subsequent runs no longer re-attempt it (the loop terminates).
    from vdocs.orchestrator.report import RunReporter, Status
    from vdocs.stages.fetch.fetch_pure import MAX_FETCH_ATTEMPTS

    ctx = bronze_ctx
    _inventory_only(ctx)
    failing = lambda _u: None  # noqa: E731
    sel = Selection(all_=True)
    rep = RunReporter(echo=lambda _s: None)
    for _ in range(MAX_FETCH_ATTEMPTS):
        Orchestrator([FetchStage(fetch_bytes=failing, selection=sel)]).run(
            ctx, force=True, reporter=rep
        )

    acq = ctx.state.get_acquisition("ADT:dg_5_3_1057_um")
    assert acq.status == "permanent_missing" and acq.attempts == MAX_FETCH_ATTEMPTS
    assert rep.reports[-1].status is Status.WARN
    assert any("permanently unavailable" in w for w in rep.reports[-1].warnings)
    assert any(DOCX_URL in w for w in rep.reports[-1].warnings)  # the operator gets the URL

    # a further forced run does NOT re-attempt the permanently-missing doc
    calls: list[str] = []

    def counting(u: str) -> bytes | None:
        calls.append(u)
        return None

    (sr,) = Orchestrator([FetchStage(fetch_bytes=counting, selection=sel)]).run(ctx, force=True)
    assert calls == []  # skipped permanent — no GET
    assert sr.counts["permanent_missing"] == 1


def test_a_narrow_refetch_keeps_every_previously_fetched_doc_in_the_index(bronze_ctx):
    ctx = bronze_ctx
    # R1's requirement, under P1.1's mechanism: the index is DERIVED from the whole admitted
    # target set ⋈ acquisitions, so a narrow selection re-fetch can never strand a document
    # fetched by an earlier run. (Pre-P1.1 this was a merge of the prior file; the merge also
    # kept stale entries alive forever, which the derivation now correctly drops.)
    Orchestrator([CrawlStage(page_fetcher=fake_page), CatalogStage(), ServeInventoryStage()]).run(
        ctx, force=True
    )
    Orchestrator([FetchStage(fetch_bytes=fake_bytes, selection=Selection(all_=True))]).run(
        ctx, force=True
    )
    assert list(fp.parse_raw_index(json.loads(ctx.cfg.raw_index.read_text()))) == [
        "ADT:dg_5_3_1057_um"
    ]

    # now a *narrow* run that selects nothing this document matches: it is already in the CAS,
    # so it must STILL be indexed afterwards (a SKIP_PRESENT doc is re-emitted, not dropped).
    narrow = Selection(apps=frozenset({"NOSUCHAPP"}))
    Orchestrator([FetchStage(fetch_bytes=fake_bytes, selection=narrow)]).run(ctx, force=True)
    index = fp.parse_raw_index(json.loads(ctx.cfg.raw_index.read_text()))
    assert list(index) == ["ADT:dg_5_3_1057_um"]
    assert index["ADT:dg_5_3_1057_um"]["app_code"] == "ADT"


def test_raw_index_drops_a_doc_the_gate_no_longer_admits(bronze_ctx):
    ctx = bronze_ctx
    # Derivation, not merge (audit R-10): an acquisition for a document that is no longer an
    # admitted target leaves the index, so convert stops regenerating its stale bundle.
    Orchestrator([CrawlStage(page_fetcher=fake_page), CatalogStage(), ServeInventoryStage()]).run(
        ctx, force=True
    )
    ctx.state.record_acquisition(
        Acquisition(
            doc_id="LR:lr_um",
            source_url="https://vdl.test/lr.docx",
            status="fetched",
            sha256="deadbeef",
            tool_ver="test",
        )
    )
    Orchestrator([FetchStage(fetch_bytes=fake_bytes, selection=Selection(all_=True))]).run(
        ctx, force=True
    )
    index = fp.parse_raw_index(json.loads(ctx.cfg.raw_index.read_text()))
    assert "LR:lr_um" not in index  # never an admitted target → not in the corpus
    assert list(index) == ["ADT:dg_5_3_1057_um"]


def test_a_fetched_doc_survives_a_lifecycle_relabel(bronze_ctx):
    # CI.2 master-set retention: VA relabelling the application DECOMMISSIONED removes it from
    # the admitted set (denied_app_status) — but a document we already fetched must stay in the
    # index. Deprecation does not remove the code from VistA; the relabel is metadata, never a
    # reason to drop the manual. Driven end-to-end through a real re-crawl of a relabelled VDL.
    ctx = bronze_ctx
    Orchestrator(_stages()).run(ctx, force=True)
    assert list(fp.parse_raw_index(json.loads(ctx.cfg.raw_index.read_text()))) == [
        "ADT:dg_5_3_1057_um"
    ]

    relabelled = dict(
        PAGES,
        **{
            "https://vdl.test/section.asp?secid=1": (
                '<a href="application.asp?appid=55">'
                "Admission Discharge Transfer (ADT) - DECOMMISSIONED</a>"
            )
        },
    )

    def relabelled_page(url: str) -> Page:
        return Page(text=relabelled.get(url, "<html></html>"), url=url, status_code=200)

    (sr,) = (
        r
        for r in Orchestrator(
            [
                CrawlStage(page_fetcher=relabelled_page),
                CatalogStage(),
                ServeInventoryStage(),
                FetchStage(fetch_bytes=fake_bytes, selection=Selection(all_=True)),
            ]
        ).run(ctx, force=True)
        if r is not None and r.stage == "fetch"
    )

    # the gate now admits nothing — and the document is still there, marked retained
    assert sr.counts["targets"] == 0
    assert sr.counts["retained"] == 1
    index = fp.parse_raw_index(json.loads(ctx.cfg.raw_index.read_text()))
    assert list(index) == ["ADT:dg_5_3_1057_um"]
    assert index["ADT:dg_5_3_1057_um"]["sha256"]  # the CAS pointer survives with it


def test_a_v1_prior_index_is_rederived_without_retention(bronze_ctx):
    # The P1.1 migration path must still work: a legacy sha-keyed index cannot be read, so it
    # contributes no retained entries — the fetch re-derives a fresh format-2 index instead of
    # dying on its own remediation advice.
    ctx = bronze_ctx
    _inventory_only(ctx)
    ctx.cfg.raw_index.parent.mkdir(parents=True, exist_ok=True)
    ctx.cfg.raw_index.write_text(json.dumps({"deadbeef": {"app_code": "ADT"}}))
    (sr,) = Orchestrator([FetchStage(fetch_bytes=fake_bytes, selection=Selection(all_=True))]).run(
        ctx, force=True
    )
    assert sr.status == "ok" and sr.counts["fetched"] == 1 and sr.counts["retained"] == 0
    assert list(fp.parse_raw_index(json.loads(ctx.cfg.raw_index.read_text()))) == [
        "ADT:dg_5_3_1057_um"
    ]


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
            FetchStage(fetch_bytes={pdf_url: b"%PDF-1.5 fake"}.get, selection=Selection(all_=True)),
        ]
    ).run(ctx, force=True)

    assert (
        ctx.state.get("fetch").counts["failed"] == 1
        and ctx.state.get("fetch").counts["fetched"] == 0
    )
    # the PDF was never stored: a well-formed (format-2) index with no documents in it
    assert fp.parse_raw_index(json.loads(ctx.cfg.raw_index.read_text())) == {}
    acq = ctx.state.get_acquisition("ADT:dg_5_3_1057_um")
    assert acq is not None and acq.status == "failed"


def test_fetch_records_failure_when_docx_unavailable(bronze_ctx):
    ctx = bronze_ctx
    # the DOCX is not downloadable upstream → the doc is counted failed, not stored
    Orchestrator(
        [
            CrawlStage(page_fetcher=fake_page),
            CatalogStage(),
            ServeInventoryStage(),
            FetchStage(fetch_bytes=lambda u: None, selection=Selection(all_=True)),
        ]
    ).run(ctx, force=True)

    assert ctx.state.get("fetch").counts["failed"] == 1
    acq = ctx.state.get_acquisition("ADT:dg_5_3_1057_um")
    assert acq is not None and acq.status == "failed" and acq.error == "docx unavailable"
    assert fp.parse_raw_index(json.loads(ctx.cfg.raw_index.read_text())) == {}


def test_fetch_refuses_a_non_docx_payload_at_the_cas_door(bronze_ctx):
    # P1.3 (audit R-8): VA can serve an error/WAF page with a 200. Storing it would put a
    # permanent non-document in the write-once CAS and surface much later as an isolated convert
    # error, leaving the corpus quietly one document smaller. Refuse at the door instead.
    ctx = bronze_ctx
    _inventory_only(ctx)
    html = lambda _u: b"<!DOCTYPE html><html>403 Forbidden</html>"  # noqa: E731

    from vdocs.orchestrator.report import RunReporter, Status

    rep = RunReporter(echo=lambda _s: None)
    (sr,) = Orchestrator([FetchStage(fetch_bytes=html, selection=Selection(all_=True))]).run(
        ctx, force=True, reporter=rep
    )
    assert sr.counts["bad_content"] == 1 and sr.counts["fetched"] == 0
    assert not list(ctx.cfg.bronze_raw.glob("*.docx"))  # nothing entered the write-once store
    acq = ctx.state.get_acquisition("ADT:dg_5_3_1057_um")
    assert acq.status == "bad_content" and acq.sha256 is None
    assert "not a DOCX" in acq.error
    # the operator is told loudly, with the URL — never a silent drop
    assert rep.reports[-1].status is Status.WARN
    assert any("non-DOCX payload" in w and DOCX_URL in w for w in rep.reports[-1].warnings)
    # …and it is NOT indexed: only `fetched` acquisitions reach raw/index.json
    assert fp.parse_raw_index(json.loads(ctx.cfg.raw_index.read_text())) == {}


def test_a_bad_content_doc_is_retried_like_a_transient_failure(bronze_ctx):
    # a WAF hiccup must not permanently blacklist a real document: the next run re-GETs it and,
    # when the real bytes come back, it fetches normally.
    ctx = bronze_ctx
    _inventory_only(ctx)
    html = lambda _u: b"<html>error</html>"  # noqa: E731
    Orchestrator([FetchStage(fetch_bytes=html, selection=Selection(all_=True))]).run(
        ctx, force=True
    )
    assert ctx.state.get_acquisition("ADT:dg_5_3_1057_um").status == "bad_content"

    (sr,) = Orchestrator([FetchStage(fetch_bytes=fake_bytes, selection=Selection(all_=True))]).run(
        ctx, force=True
    )
    assert sr.counts["fetched"] == 1
    acq = ctx.state.get_acquisition("ADT:dg_5_3_1057_um")
    assert acq.status == "fetched" and acq.attempts == 2  # attempts accrued across both runs
