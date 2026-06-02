"""CLI integration tests — Typer app wiring stages to the orchestrator (ADR-009).

Network stages (crawl/fetch) are exercised in test_bronze_dag with fakes; here we drive the
non-network `catalog` stage through the real CLI to prove the wiring, plus help/failure paths.
"""

import json

from typer.testing import CliRunner

from vdocs.cli.app import app
from vdocs.config import Settings
from vdocs.contracts.registry import CATALOG_RAW
from vdocs.kernel.http import Page
from vdocs.models.stage import StageRun
from vdocs.orchestrator.state import StateStore

runner = CliRunner()

RAW_CATALOG = {
    "sections": [
        {
            "name": "Clinical",
            "url": "https://va.gov/vdl/section.asp?secid=1",
            "applications": [
                {
                    "name": "Admission Discharge Transfer (ADT)",
                    "app_code": "ADT",
                    "url": "https://va.gov/vdl/application.asp?appid=55",
                    "documents": [
                        {
                            "title": "DG*5.3*1057 Installation Guide",
                            "url": "https://va.gov/d/dg_5_3_1057_dibr.docx",
                            "filename": "dg_5_3_1057_dibr.docx",
                            "file_ext": ".docx",
                        }
                    ],
                }
            ],
        }
    ]
}


def _seed_catalog_raw(tmp_path):
    """Place catalog.raw AND record a matching `crawl` completion (as a real crawl would)."""
    cfg = Settings(data_dir=tmp_path)
    raw = cfg.catalog_raw
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text(json.dumps(RAW_CATALOG))
    store = StateStore.open(cfg.state_db)
    store.record(
        StageRun(
            stage="crawl",
            status="ok",
            started_at="t",
            finished_at="t",
            inputs_fp={"vdl": "external:vdl"},
            outputs_fp={CATALOG_RAW.key: CATALOG_RAW.fingerprint(cfg)},
            counts={},
            contract_ver=1,
            tool_ver=cfg.tool_ver,
        )
    )
    store.close()
    return tmp_path


def test_help_lists_stage_subcommands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in (
        "crawl",
        "catalog",
        "serve-inventory",
        "fetch",
        "convert",
        "discover",
        "enrich",
        "inventory",
        "run",
    ):
        assert cmd in result.stdout


def test_catalog_command_enriches(tmp_path):
    _seed_catalog_raw(tmp_path)
    cfg = Settings(data_dir=tmp_path)
    result = runner.invoke(app, ["catalog"], env={"DATA_DIR": str(tmp_path)})
    assert result.exit_code == 0, result.stdout
    enriched = json.loads(cfg.catalog_enriched.read_text())
    assert enriched["records"][0]["patch_id"] == "DG*5.3*1057"


def test_run_only_catalog(tmp_path):
    _seed_catalog_raw(tmp_path)
    result = runner.invoke(app, ["run", "--only", "catalog"], env={"DATA_DIR": str(tmp_path)})
    assert result.exit_code == 0, result.stdout
    assert Settings(data_dir=tmp_path).catalog_enriched.exists()


def test_failure_exits_nonzero_with_remediation(tmp_path):
    # no catalog.raw present → catalog preflight FAILs
    result = runner.invoke(app, ["catalog"], env={"DATA_DIR": str(tmp_path)})
    assert result.exit_code == 1
    assert "crawl" in result.stdout  # remediation mentions the upstream stage


# --- crawl + fetch commands, driven with faked network via build_stages ------
_INDEX = '<a href="section.asp?secid=1">Clinical</a>'
_SECTION = '<a href="application.asp?appid=1">ADT (DG)</a>'
_APP = (
    "<table><tr>"
    "<td>DG*5.3*1 Installation Guide</td>"
    '<td><a href="https://vdl.test/dg_5_3_1_dibr.docx">DOCX</a></td>'
    "</tr></table>"
)
_PAGES = {
    "https://vdl.test/": _INDEX,
    "https://vdl.test/section.asp?secid=1": _SECTION,
    "https://vdl.test/application.asp?appid=1": _APP,
}
_BYTES = {"https://vdl.test/dg_5_3_1_dibr.docx": b"PK\x03\x04 fake"}


def _faked_stages():
    from vdocs.stages.catalog.stage import CatalogStage
    from vdocs.stages.convert.convert_pure import ConvertedDoc
    from vdocs.stages.convert.stage import ConvertStage
    from vdocs.stages.crawl.stage import CrawlStage
    from vdocs.stages.discover.stage import DiscoverStage
    from vdocs.stages.enrich.stage import EnrichStage
    from vdocs.stages.fetch.stage import FetchStage
    from vdocs.stages.serve_inventory.stage import ServeInventoryStage

    def page(u: str) -> Page:
        return Page(text=_PAGES.get(u, "<html></html>"), url=u, status_code=200)

    return [
        CrawlStage(page_fetcher=page),
        CatalogStage(),
        ServeInventoryStage(),
        FetchStage(fetch_bytes=_BYTES.get),
        ConvertStage(convert=lambda data, ext: ConvertedDoc(markdown="# Converted\n")),
        DiscoverStage(),
        EnrichStage(),
    ]


def test_crawl_catalog_fetch_commands_in_sequence(tmp_path, monkeypatch):
    monkeypatch.setattr("vdocs.cli.app.build_stages", _faked_stages)
    cfg = Settings(data_dir=tmp_path)
    env = {"DATA_DIR": str(tmp_path), "VDL_BASE_URL": "https://vdl.test/"}

    assert runner.invoke(app, ["crawl"], env=env).exit_code == 0
    assert cfg.catalog_raw.exists()

    assert runner.invoke(app, ["catalog"], env=env).exit_code == 0
    assert cfg.catalog_enriched.exists()

    assert runner.invoke(app, ["serve-inventory"], env=env).exit_code == 0
    assert cfg.gold_inventory_json.exists() and cfg.gold_inventory_db.exists()

    assert runner.invoke(app, ["fetch"], env=env).exit_code == 0
    assert json.loads(cfg.raw_index.read_text())

    # the inventory ⋈ acquisitions status view reflects the fetched document
    status = runner.invoke(app, ["inventory", "--status"], env=env)
    assert status.exit_code == 0
    assert "fetched=1" in status.stdout and "total=1" in status.stdout

    # the bare inventory command reports record + genuine-document counts
    plain = runner.invoke(app, ["inventory"], env=env)
    assert plain.exit_code == 0 and "genuine documents" in plain.stdout

    # convert turns the fetched doc into a text@converted bundle
    assert runner.invoke(app, ["convert"], env=env).exit_code == 0
    bodies = list(cfg.silver_converted.rglob("body.md"))
    assert len(bodies) == 1 and bodies[0].read_text() == "# Converted\n"
    assert bodies[0].parent.name == "dg_5_3_1_dibr"  # <app>/<slug>/body.md

    # discover mines the converted corpus into the candidate-patterns report
    assert runner.invoke(app, ["discover"], env=env).exit_code == 0
    assert cfg.patterns_report.exists()

    # enrich bakes identity frontmatter onto the converted bundle
    assert runner.invoke(app, ["enrich"], env=env).exit_code == 0
    enriched = list(cfg.silver_enriched.rglob("body.md"))
    assert len(enriched) == 1
    from vdocs.kernel import frontmatter

    meta, _ = frontmatter.parse(enriched[0].read_text())
    assert meta["app_code"] == "DG" and meta["title"].startswith("DG*5.3*1")


def test_inventory_status_without_gold_inventory_errors(tmp_path):
    result = runner.invoke(app, ["inventory", "--status"], env={"DATA_DIR": str(tmp_path)})
    assert result.exit_code == 1
    assert "serve-inventory" in result.stdout
