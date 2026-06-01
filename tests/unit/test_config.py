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
    assert cfg.bronze_catalog == tmp_path / "bronze" / "catalog"
    assert cfg.silver == tmp_path / "silver"
    assert cfg.gold_consolidated == tmp_path / "gold" / "consolidated"
    assert cfg.corpus_manifest == tmp_path / "gold" / "corpus-manifest.json"
    assert cfg.discovery_json == tmp_path / "gold" / "discovery.json"
    assert cfg.glossary == tmp_path / "gold" / "glossary.md"
