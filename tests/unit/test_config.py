"""Unit tests for config.Settings — typed config off DATA_DIR (§9.1, ADR-005)."""

from pathlib import Path

from vdocs.config import Settings


def test_default_data_dir_is_home_data_vdocs(monkeypatch):
    monkeypatch.delenv("DATA_DIR", raising=False)
    cfg = Settings()
    assert cfg.lake == Path.home() / "data" / "vdocs"


def test_data_dir_env_override(monkeypatch):
    monkeypatch.setenv("DATA_DIR", "/tmp/custom-lake")
    cfg = Settings()
    assert cfg.lake == Path("/tmp/custom-lake")


def test_derived_paths_descend_from_lake(tmp_path):
    cfg = Settings(data_dir=tmp_path)
    assert cfg.bronze == tmp_path / "bronze"
    assert cfg.bronze_raw == tmp_path / "bronze" / "raw"
    assert cfg.assets == tmp_path / "assets"
    assert cfg.silver_text == tmp_path / "silver" / "text"
    assert cfg.gold == tmp_path / "gold"
    assert cfg.gold_shared == tmp_path / "gold" / "_shared"
    assert cfg.publish == tmp_path / "gold" / "publish"
    assert cfg.reports == tmp_path / "reports"


def test_derived_db_paths(tmp_path):
    cfg = Settings(data_dir=tmp_path)
    assert cfg.state_db == tmp_path / "state.db"
    assert cfg.index_db == tmp_path / "index.db"
    assert cfg.vectors_db == tmp_path / "vectors.db"


def test_all_lake_paths_are_under_lake(tmp_path):
    cfg = Settings(data_dir=tmp_path)
    for p in (cfg.bronze, cfg.silver, cfg.gold, cfg.assets, cfg.reports, cfg.state_db):
        assert tmp_path in p.parents or p == tmp_path


def test_tool_ver_matches_package_version(tmp_path):
    from vdocs import __version__

    assert Settings(data_dir=tmp_path).tool_ver == __version__


def test_remaining_derived_paths(tmp_path):
    cfg = Settings(data_dir=tmp_path)
    assert cfg.silver == tmp_path / "silver"
    assert cfg.silver_converted == tmp_path / "silver" / "text" / "01-converted"
    assert cfg.gold_consolidated == tmp_path / "gold" / "consolidated"
    assert cfg.corpus_manifest == tmp_path / "gold" / "corpus-manifest.json"
    assert cfg.discovery_json == tmp_path / "gold" / "discovery.json"
    assert cfg.glossary == tmp_path / "gold" / "glossary.md"


def test_inventory_medallion_paths(tmp_path):
    # The inventory medallion (crawl→catalog→serve-inventory) is its own bronze/silver/gold
    # subtree, separate from the document medallion (§4, §5.3).
    cfg = Settings(data_dir=tmp_path)
    assert cfg.inventory == tmp_path / "inventory"
    assert cfg.inventory_bronze == tmp_path / "inventory" / "bronze"
    assert cfg.inventory_silver == tmp_path / "inventory" / "silver"
    assert cfg.inventory_gold == tmp_path / "inventory" / "gold"
    # the raw scraped catalog (inv-bronze) and the enriched inventory (inv-silver)
    assert cfg.catalog_raw == tmp_path / "inventory" / "bronze" / "catalog.raw.json"
    assert cfg.catalog_enriched == tmp_path / "inventory" / "silver" / "catalog.enriched.json"
    # the json→csv convenience view shares the stem
    assert cfg.catalog_raw.with_suffix(".csv").name == "catalog.raw.csv"


def test_crawl_session_settings(tmp_path):
    cfg = Settings(data_dir=tmp_path)
    assert cfg.crawl_delay == 1.5
    assert cfg.user_agent.startswith("vdocs/")
    assert "github.com/rafael5/vdocs" in cfg.user_agent


def test_crawl_delay_env_override(monkeypatch):
    monkeypatch.setenv("CRAWL_DELAY", "0.25")
    assert Settings().crawl_delay == 0.25
