"""Unit tests for models.artifact — ArtifactContract locate/validate/fingerprint (§7.1)."""

import sqlite3

from vdocs.config import Settings
from vdocs.models.artifact import (
    ArtifactContract,
    CheckResult,
    Kind,
    StorageClass,
)


def _cfg(tmp_path):
    return Settings(data_dir=tmp_path)


def test_file_contract_locate_resolves_under_lake(tmp_path):
    cfg = _cfg(tmp_path)
    c = ArtifactContract(
        key="bronze/x",
        kind=Kind.FILE,
        storage_class=StorageClass.ASSET_WRITE_ONCE,
        relpath="bronze/x.txt",
    )
    assert c.locate(cfg).path == tmp_path / "bronze" / "x.txt"


def test_file_contract_validate_reflects_existence(tmp_path):
    cfg = _cfg(tmp_path)
    c = ArtifactContract(
        key="bronze/x",
        kind=Kind.FILE,
        storage_class=StorageClass.ASSET_WRITE_ONCE,
        relpath="bronze/x.txt",
    )
    assert c.validate(cfg).ok is False
    (tmp_path / "bronze").mkdir()
    (tmp_path / "bronze" / "x.txt").write_text("hi")
    assert c.validate(cfg).ok is True


def test_file_contract_fingerprint_changes_with_content(tmp_path):
    cfg = _cfg(tmp_path)
    (tmp_path / "bronze").mkdir()
    f = tmp_path / "bronze" / "x.txt"
    f.write_text("a")
    c = ArtifactContract(
        key="bronze/x",
        kind=Kind.FILE,
        storage_class=StorageClass.ASSET_WRITE_ONCE,
        relpath="bronze/x.txt",
    )
    before = c.fingerprint(cfg, verify=True)
    f.write_text("bb")
    assert c.fingerprint(cfg, verify=True) != before


def test_tree_text_validate_requires_non_empty_dir(tmp_path):
    cfg = _cfg(tmp_path)
    c = ArtifactContract(
        key="silver/text@x",
        kind=Kind.TREE_TEXT,
        storage_class=StorageClass.TEXT_VERSIONED,
        relpath="silver/text/x",
    )
    assert c.validate(cfg).ok is False  # missing
    (tmp_path / "silver" / "text" / "x").mkdir(parents=True)
    assert c.validate(cfg).ok is False  # empty → fails min cardinality
    (tmp_path / "silver" / "text" / "x" / "body.md").write_text("# doc")
    assert c.validate(cfg).ok is True


def test_sqlite_table_contract(tmp_path):
    cfg = _cfg(tmp_path)
    db = tmp_path / "index.db"
    c = ArtifactContract(
        key="index.db:documents",
        kind=Kind.SQLITE_TABLE,
        storage_class=StorageClass.STATE,
        db="index.db",
        table="documents",
    )
    assert c.validate(cfg).ok is False  # no db yet
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE documents (id TEXT)")
    conn.execute("INSERT INTO documents VALUES ('d1')")
    conn.commit()
    conn.close()
    assert c.validate(cfg).ok is True
    loc = c.locate(cfg)
    assert loc.path == db and loc.table == "documents"


def test_tree_contract_fingerprint(tmp_path):
    cfg = _cfg(tmp_path)
    tree = tmp_path / "silver" / "text" / "x"
    tree.mkdir(parents=True)
    (tree / "body.md").write_text("# doc")
    c = ArtifactContract(
        key="silver/text@x",
        kind=Kind.TREE_TEXT,
        storage_class=StorageClass.TEXT_VERSIONED,
        relpath="silver/text/x",
    )
    before = c.fingerprint(cfg, verify=True)
    (tree / "body.md").write_text("# changed")
    assert c.fingerprint(cfg, verify=True) != before


def test_sqlite_contract_fingerprint(tmp_path):
    cfg = _cfg(tmp_path)
    db = tmp_path / "index.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE documents (id TEXT)")
    conn.execute("INSERT INTO documents VALUES ('d1')")
    conn.commit()
    conn.close()
    c = ArtifactContract(
        key="index.db:documents",
        kind=Kind.SQLITE_TABLE,
        storage_class=StorageClass.STATE,
        db="index.db",
        table="documents",
    )
    assert c.fingerprint(cfg) == c.fingerprint(cfg)


def test_sqlite_view_validate(tmp_path):
    cfg = _cfg(tmp_path)
    db = tmp_path / "index.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE t (id TEXT)")
    conn.execute("CREATE VIEW latest AS SELECT * FROM t")
    conn.commit()
    conn.close()
    c = ArtifactContract(
        key="index.db:latest",
        kind=Kind.SQLITE_VIEW,
        storage_class=StorageClass.STATE,
        db="index.db",
        table="latest",
    )
    assert c.validate(cfg).ok is True


def test_external_contract_always_validates_and_is_constant(tmp_path):
    cfg = _cfg(tmp_path)
    c = ArtifactContract(
        key="vdl",
        kind=Kind.EXTERNAL,
        storage_class=StorageClass.EXTERNAL,
        produced_by=None,
    )
    assert c.validate(cfg).ok is True
    assert c.fingerprint(cfg) == c.fingerprint(cfg)
    # an external artifact has no lake location
    assert c.locate(cfg).path is None


def test_check_result_is_a_value_type():
    r = CheckResult(ok=True, detail="fine")
    assert r.ok and r.detail == "fine"
