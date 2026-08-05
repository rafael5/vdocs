"""Every successful crawl leaves a dated, immutable snapshot (VO.2) — through the real stage.

Before this, the lake held exactly one inventory and each crawl overwrote it, so no earlier state
of the VDL existed anywhere and none could be reconstructed. These tests hold the three properties
that make a snapshot evidence: it is kept, it is never rewritten, and a crawl that found the same
thing does not fabricate a second one.

Bronze only, deliberately: bronze is VA's raw statement, while gold carries our own registry-driven
classification, so a delta over gold would conflate VDL change with a change in how we read it.
"""

from __future__ import annotations

from vdocs.kernel.http import Page
from vdocs.models.catalog import Catalog
from vdocs.orchestrator.engine import Orchestrator
from vdocs.stages.crawl.stage import CrawlStage

INDEX = '<a href="section.asp?secid=1">Clinical</a>'
SECTION = '<a href="application.asp?appid=10">Nursing (NUR)</a>'

DOC_A = ("NUR*1.0*1 User Manual", "documents/Clinical/NUR/nur_1_0_1_um.docx")
DOC_B = ("NUR*1.0*1 Technical Manual", "documents/Clinical/NUR/nur_1_0_1_tm.docx")
DOC_C = ("NUR*1.0*2 Release Notes", "documents/Clinical/NUR/nur_1_0_2_rn.docx")


def _app_page(docs: list[tuple[str, str]]) -> str:
    rows = "".join(
        f"<tr><td>{title}</td><td><a href='{href}'>DOCX</a></td><td>03/2024</td></tr>"
        for title, href in docs
    )
    return f"<table>{rows}</table>"


def _fetcher(docs: list[tuple[str, str]]):
    def fetch(url: str) -> Page:
        if url.endswith("/vdl/"):
            return Page(text=INDEX, url=url, status_code=200)
        if url.endswith("section.asp?secid=1"):
            return Page(text=SECTION, url=url, status_code=200)
        if url.endswith("application.asp?appid=10"):
            return Page(text=_app_page(docs), url=url, status_code=200)
        return Page(text="<html></html>", url=url, status_code=200)

    return fetch


def _crawl(ctx, docs: list[tuple[str, str]]) -> None:
    ctx.cfg = ctx.cfg.model_copy(update={"vdl_base_url": "https://www.va.gov/vdl/"})
    (result,) = Orchestrator([CrawlStage(page_fetcher=_fetcher(docs))]).run(ctx, force=True)
    assert result.status == "ok"


def _snapshots(ctx) -> list[str]:
    root = ctx.cfg.inventory_snapshots
    return sorted(p.name for p in root.iterdir() if p.is_dir()) if root.exists() else []


def test_a_crawl_leaves_a_dated_snapshot_of_bronze(ctx) -> None:
    _crawl(ctx, [DOC_A, DOC_B])

    (name,) = _snapshots(ctx)
    snapshot = ctx.cfg.inventory_snapshots / name / "catalog.raw.json"
    assert snapshot.exists()
    assert snapshot.read_bytes() == ctx.cfg.catalog_raw.read_bytes()
    # the snapshot is self-describing: which crawl, and the identity it was deduplicated on
    assert (ctx.cfg.inventory_snapshots / name / "SNAPSHOT.json").exists()


def test_two_different_crawls_leave_two_snapshots_and_the_first_is_untouched(ctx) -> None:
    _crawl(ctx, [DOC_A, DOC_B])
    (first,) = _snapshots(ctx)
    original = (ctx.cfg.inventory_snapshots / first / "catalog.raw.json").read_bytes()

    _crawl(ctx, [DOC_A, DOC_B, DOC_C])

    assert len(_snapshots(ctx)) == 2
    # the earlier snapshot is evidence: byte-identical after a later crawl overwrote bronze
    assert (ctx.cfg.inventory_snapshots / first / "catalog.raw.json").read_bytes() == original
    assert Catalog.model_validate_json(original.decode()).sections[0].applications[0].documents
    assert len(ctx.cfg.catalog_raw.read_bytes()) != len(original)


def test_a_crawl_that_found_the_same_thing_does_not_fabricate_a_snapshot(ctx) -> None:
    """Identity is canonical content, not bytes — a VDL page reorder is not history."""
    _crawl(ctx, [DOC_A, DOC_B])
    before = _snapshots(ctx)

    _crawl(ctx, [DOC_B, DOC_A])

    assert _snapshots(ctx) == before
