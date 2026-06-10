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
        "normalize",
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


def _seed_gold_inventory(tmp_path):
    """A gold inventory with one genuine DOCX, its PDF twin (out of scope), and a noise row."""
    from vdocs.models.catalog import EnrichedInventory, EnrichedRecord

    def rec(slug, fmt, *, noise="", app="ADT"):
        return EnrichedRecord(
            doc_title="T",
            doc_url=f"https://va.gov/d/{slug}.{fmt}",
            doc_filename=f"{slug}.{fmt}",
            doc_format=fmt,
            app_name_abbrev=app,
            app_name_full=f"{app} App ({app})",
            section_code="CLIN",
            system_type="VistA",  # admitted by the app-scope gate
            doc_slug=slug,
            doc_code="UM",  # admitted by the doc-type gate (Tier-A reference core)
            anchor_key=f"{app}:DG:UM",
            noise_type=noise,
        )

    cfg = Settings(data_dir=tmp_path)
    cfg.inventory_gold.mkdir(parents=True, exist_ok=True)
    records = [rec("d1", "docx"), rec("d1", "pdf"), rec("form", "docx", noise="vba_form")]
    cfg.gold_inventory_json.write_text(EnrichedInventory(records=records).model_dump_json())
    return cfg


def test_fetch_no_selection_fetches_nothing_and_reports_count(tmp_path):
    _seed_gold_inventory(tmp_path)
    env = {"DATA_DIR": str(tmp_path)}
    result = runner.invoke(app, ["fetch"], env=env)
    assert result.exit_code == 0
    # no blind download (§5.6): nothing fetched, the available count is reported
    assert "1 genuine" in result.stdout and "--all" in result.stdout
    assert not Settings(data_dir=tmp_path).raw_index.exists()


def test_fetch_dry_run_reports_match_count_without_fetching(tmp_path):
    _seed_gold_inventory(tmp_path)
    env = {"DATA_DIR": str(tmp_path)}
    result = runner.invoke(app, ["fetch", "--all", "--dry-run"], env=env)
    assert result.exit_code == 0
    assert "matches 1" in result.stdout
    assert not Settings(data_dir=tmp_path).raw_index.exists()


def test_fetch_non_matching_selection_fetches_nothing(tmp_path):
    _seed_gold_inventory(tmp_path)
    env = {"DATA_DIR": str(tmp_path)}
    result = runner.invoke(app, ["fetch", "--app", "NOPE"], env=env)
    assert result.exit_code == 0
    assert "0 of 1" in result.stdout
    assert not Settings(data_dir=tmp_path).raw_index.exists()


def test_fetch_select_file_is_read(tmp_path):
    _seed_gold_inventory(tmp_path)
    ids = tmp_path / "ids.txt"
    ids.write_text("# a curated list\nADT:d1\n\n")  # blank + comment lines ignored
    env = {"DATA_DIR": str(tmp_path)}
    result = runner.invoke(app, ["fetch", "--select", str(ids), "--dry-run"], env=env)
    assert result.exit_code == 0
    assert "matches 1" in result.stdout


def test_read_select_file_strips_inline_comments(tmp_path):
    # A curated select file may annotate each id with a trailing `# rationale` (the documented
    # "'#' comments allowed" — registries/dev-corpus.txt relies on this). Inline comments and
    # surrounding whitespace are stripped; full-line comments and blanks are ignored.
    from vdocs.cli.app import _read_select_file

    f = tmp_path / "sel.txt"
    f.write_text(
        "# header comment\n"
        "ADT:d1   # flattened legacy UM\n"
        "\n"
        "XU:krn_8_0_tm# no space before hash\n"
        "  AR/WS:wsuser  \n"  # slashes in app code survive; no inline comment here
    )
    assert _read_select_file(str(f)) == frozenset({"ADT:d1", "XU:krn_8_0_tm", "AR/WS:wsuser"})


def test_fetch_without_gold_inventory_errors(tmp_path):
    result = runner.invoke(app, ["fetch", "--all"], env={"DATA_DIR": str(tmp_path)})
    assert result.exit_code == 1
    assert "serve-inventory" in result.stdout


def test_run_only_catalog(tmp_path):
    _seed_catalog_raw(tmp_path)
    result = runner.invoke(app, ["run", "--only", "catalog"], env={"DATA_DIR": str(tmp_path)})
    assert result.exit_code == 0, result.stdout
    assert Settings(data_dir=tmp_path).catalog_enriched.exists()


def test_failure_exits_nonzero_with_remediation(tmp_path):
    # no catalog.raw present → catalog preflight FAILs (step 1: required input missing)
    result = runner.invoke(app, ["catalog"], env={"DATA_DIR": str(tmp_path)})
    assert result.exit_code == 1
    assert "crawl" in result.stdout  # remediation mentions the upstream stage


def test_catalog_runs_from_present_raw_without_a_crawl_record(tmp_path):
    # F4: place catalog.raw on disk but record NO `crawl` stage_run (as if state.db was wiped).
    # catalog must still run off the present, valid artifact — no cryptic "crawl not completed ok".
    cfg = Settings(data_dir=tmp_path)
    cfg.catalog_raw.parent.mkdir(parents=True, exist_ok=True)
    cfg.catalog_raw.write_text(json.dumps(RAW_CATALOG))
    result = runner.invoke(app, ["catalog"], env={"DATA_DIR": str(tmp_path)})
    assert result.exit_code == 0, result.stdout
    assert cfg.catalog_enriched.exists()


def test_postflight_failure_exits_one_without_traceback(tmp_path, monkeypatch):
    # A deep-gate/postflight failure must render a clean ERROR + exit 1, never a raw Python
    # traceback (the §2.6 defect: PostflightError used to escape _drive uncaught).
    from vdocs.contracts.registry import VDL
    from vdocs.kernel import cas
    from vdocs.models.artifact import ArtifactContract, Kind, StorageClass
    from vdocs.models.stage import PostflightResult, RunResult
    from vdocs.orchestrator.stage import Stage

    out = ArtifactContract(
        key="solo", kind=Kind.FILE, storage_class=StorageClass.TEXT_VERSIONED,
        produced_by="gated", relpath="solo.bin",
    )  # fmt: skip

    class Gated(Stage):
        name = "gated"
        requires = [VDL]
        produces = [out]

        def run(self, ctx, force):
            cas.atomic_write(out.locate(ctx.cfg).path, b"x")
            return RunResult()

        def deep_gate(self, ctx):
            return PostflightResult(ok=False, reason="synthetic gate failure")

    monkeypatch.setattr("vdocs.cli.app.build_stages", lambda: [Gated()])
    result = runner.invoke(app, ["run", "--only", "gated"], env={"DATA_DIR": str(tmp_path)})
    assert result.exit_code == 1
    assert "Traceback" not in result.stdout
    assert "gated" in result.stdout


# --- crawl + fetch commands, driven with faked network via build_stages ------
_INDEX = '<a href="section.asp?secid=1">Clinical</a>'
_SECTION = '<a href="application.asp?appid=1">Admission Discharge Transfer (ADT)</a>'
_APP = (
    "<table><tr>"
    "<td>DG*5.3*1 User Manual</td>"
    '<td><a href="https://vdl.test/dg_5_3_1_um.docx">DOCX</a></td>'
    "</tr></table>"
)
_PAGES = {
    "https://vdl.test/": _INDEX,
    "https://vdl.test/section.asp?secid=1": _SECTION,
    "https://vdl.test/application.asp?appid=1": _APP,
}
_BYTES = {"https://vdl.test/dg_5_3_1_um.docx": b"PK\x03\x04 fake"}


def _faked_stages():
    from vdocs.stages.catalog.stage import CatalogStage
    from vdocs.stages.convert.convert_pure import ConvertedDoc
    from vdocs.stages.convert.stage import ConvertStage
    from vdocs.stages.crawl.stage import CrawlStage
    from vdocs.stages.discover.stage import DiscoverStage
    from vdocs.stages.enrich.stage import EnrichStage
    from vdocs.stages.fetch.stage import FetchStage
    from vdocs.stages.normalize.stage import NormalizeStage
    from vdocs.stages.serve_inventory.stage import ServeInventoryStage

    def page(u: str) -> Page:
        return Page(text=_PAGES.get(u, "<html></html>"), url=u, status_code=200)

    return [
        CrawlStage(page_fetcher=page),
        CatalogStage(),
        ServeInventoryStage(),
        FetchStage(fetch_bytes=_BYTES.get),
        ConvertStage(convert=lambda d, e: ConvertedDoc(markdown="# Converted\n\n## Setup\n\nx\n")),
        DiscoverStage(),
        EnrichStage(),
        NormalizeStage(),
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

    assert runner.invoke(app, ["fetch", "--all"], env=env).exit_code == 0
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
    assert len(bodies) == 1 and bodies[0].read_text().startswith("# Converted")
    assert bodies[0].parent.name == "dg_5_3_1_um"  # <app>/<slug>/body.md

    # discover mines the converted corpus into the candidate-patterns report
    assert runner.invoke(app, ["discover"], env=env).exit_code == 0
    assert cfg.patterns_report.exists()

    # enrich bakes identity frontmatter onto the converted bundle
    assert runner.invoke(app, ["enrich"], env=env).exit_code == 0
    enriched = list(cfg.silver_enriched.rglob("body.md"))
    assert len(enriched) == 1
    from vdocs.kernel import frontmatter

    meta, _ = frontmatter.parse(enriched[0].read_text())
    assert meta["app_code"] == "ADT" and meta["title"].startswith("DG*5.3*1")

    # normalize regenerates the TOC + stamps source_sha256
    assert runner.invoke(app, ["normalize"], env=env).exit_code == 0
    (normalized,) = list(cfg.silver_normalized.rglob("body.md"))
    meta, body = frontmatter.parse(normalized.read_text())
    assert "source_sha256" in meta and "## Contents" in body and "- [Setup](#setup)" in body


def test_inventory_status_without_gold_inventory_errors(tmp_path):
    result = runner.invoke(app, ["inventory", "--status"], env={"DATA_DIR": str(tmp_path)})
    assert result.exit_code == 1
    assert "serve-inventory" in result.stdout


def _seed_index_for_ask(tmp_path):
    """A minimal index.db with the chunks_fts search surface — what `vdocs ask` queries (§14.7)."""
    from vdocs.kernel import db

    cfg = Settings(data_dir=tmp_path)
    cfg.lake.mkdir(parents=True, exist_ok=True)
    conn = db.connect(cfg.index_db)
    conn.executescript(
        """
        CREATE TABLE documents (
          doc_key TEXT PRIMARY KEY, doc_id TEXT, title TEXT, app_code TEXT, doc_type TEXT,
          pkg_ns TEXT, is_latest INTEGER
        );
        CREATE VIRTUAL TABLE chunks_fts USING fts5(
          chunk_id UNINDEXED, section_id UNINDEXED, doc_key UNINDEXED, title, doc_title,
          section_path, body
        );
        """
    )
    conn.execute(
        "INSERT INTO documents VALUES ('KAAJEE/dibr','KAAJEE:dibr','KAAJEE DIBR','KAAJEE','','',1)"
    )
    conn.execute(
        "INSERT INTO chunks_fts "
        "(chunk_id, section_id, doc_key, title, doc_title, section_path, body) "
        "VALUES ('KAAJEE/dibr/intro','KAAJEE/dibr/intro','KAAJEE/dibr','Introduction',"
        "'KAAJEE DIBR','KAAJEE','KAAJEE is the Kernel Authentication and Authorization broker.')"
    )
    conn.commit()
    conn.close()


def test_ask_without_index_errors(tmp_path):
    result = runner.invoke(app, ["ask", "what is KAAJEE"], env={"DATA_DIR": str(tmp_path)})
    assert result.exit_code == 1
    assert "vdocs index" in result.stdout


def test_ask_returns_cited_hits(tmp_path):
    _seed_index_for_ask(tmp_path)
    result = runner.invoke(app, ["ask", "KAAJEE authentication"], env={"DATA_DIR": str(tmp_path)})
    assert result.exit_code == 0, result.stdout
    assert "KAAJEE DIBR" in result.stdout
    assert "vdocs://section/KAAJEE/dibr/intro" in result.stdout
    assert "documents/gold/consolidated/KAAJEE/dibr/body.md" in result.stdout


def test_ask_json_output_is_machine_readable(tmp_path):
    _seed_index_for_ask(tmp_path)
    result = runner.invoke(
        app, ["ask", "KAAJEE authentication", "--json"], env={"DATA_DIR": str(tmp_path)}
    )
    assert result.exit_code == 0
    hits = json.loads(result.stdout)
    assert hits[0]["section_id"] == "KAAJEE/dibr/intro"
    assert hits[0]["body_path"] == "documents/gold/consolidated/KAAJEE/dibr/body.md"


def test_ask_no_match_reports_clearly(tmp_path):
    _seed_index_for_ask(tmp_path)
    result = runner.invoke(app, ["ask", "zz"], env={"DATA_DIR": str(tmp_path)})
    assert result.exit_code == 0
    assert "no match" in result.stdout.lower()
