"""Unit tests for kernel.db — the one place that knows SQLite pragmas (§9.2)."""

import sqlite3
from pathlib import Path

import pytest

from vdocs.kernel import db

_SRC_ROOT = Path(__file__).resolve().parents[3] / "src" / "vdocs"


def test_readonly_uri_is_single_sourced_in_kernel_db():
    """§9.2: the read-only ``file:...?mode=ro`` URI is a connection pragma — it must live in
    exactly one place (``kernel.db.connect``). Any other module re-spelling it is a copy-paste of
    the primitive that bypasses the single connection-pragma authority."""
    offenders = {
        p.relative_to(_SRC_ROOT).as_posix()
        for p in _SRC_ROOT.rglob("*.py")
        if "mode=ro" in p.read_text(encoding="utf-8")
    }
    assert offenders == {"kernel/db.py"}, (
        f"read-only SQLite URI re-inlined outside kernel/db.py: {offenders - {'kernel/db.py'}} "
        "— route through db.connect(path, read_only=True)"
    )


def test_connect_creates_file_and_sets_pragmas(tmp_path):
    path = tmp_path / "x.db"
    conn = db.connect(path)
    try:
        assert path.exists()
        (journal,) = conn.execute("PRAGMA journal_mode").fetchone()
        assert journal.lower() == "wal"
        (fk,) = conn.execute("PRAGMA foreign_keys").fetchone()
        assert fk == 1
    finally:
        conn.close()


def test_connect_row_factory_is_row(tmp_path):
    conn = db.connect(tmp_path / "x.db")
    try:
        db.apply_schema(conn, "CREATE TABLE t (a TEXT, b INTEGER)")
        conn.execute("INSERT INTO t VALUES ('x', 1)")
        row = conn.execute("SELECT * FROM t").fetchone()
        assert row["a"] == "x" and row["b"] == 1
    finally:
        conn.close()


def test_apply_schema_is_idempotent(tmp_path):
    conn = db.connect(tmp_path / "x.db")
    ddl = "CREATE TABLE IF NOT EXISTS t (a TEXT)"
    try:
        db.apply_schema(conn, ddl)
        db.apply_schema(conn, ddl)  # second application must not raise
        assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 0
    finally:
        conn.close()


def test_build_atomic_builds_via_temp_then_renames(tmp_path):
    path = tmp_path / "index.db"

    def build(conn):
        conn.execute("CREATE TABLE t (a TEXT)")
        conn.execute("INSERT INTO t VALUES ('x')")

    db.build_atomic(path, build)
    assert path.exists()
    assert not path.with_name(f".{path.name}.tmp").exists()  # temp swept by the rename
    conn = db.connect(path, read_only=True)
    try:
        assert conn.execute("SELECT a FROM t").fetchone()["a"] == "x"
    finally:
        conn.close()


def test_connect_honors_journal_mode_override(tmp_path):
    # R7: the atomic-build temp opens in DELETE mode so no -wal/-shm sibling can outlive the rename
    conn = db.connect(tmp_path / "x.db", journal_mode="DELETE")
    try:
        (mode,) = conn.execute("PRAGMA journal_mode").fetchone()
        assert mode.lower() == "delete"
    finally:
        conn.close()


def test_build_atomic_leaves_no_wal_or_tmp_siblings(tmp_path):
    # R7: after the build, ONLY the DB file remains — no -wal/-shm/.tmp* orphans beside it
    path = tmp_path / "index.db"

    def build(conn):
        conn.execute("CREATE TABLE t (a TEXT)")
        conn.execute("INSERT INTO t VALUES ('x')")

    db.build_atomic(path, build)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["index.db"]
    conn = db.connect(path, read_only=True)
    try:
        assert conn.execute("SELECT a FROM t").fetchone()["a"] == "x"
    finally:
        conn.close()


def test_build_atomic_sweeps_orphaned_wal_siblings_from_prior_crash(tmp_path):
    # a crashed prior run can leave .index.db.tmp-wal / .tmp-shm next to the temp; the next build
    # must sweep them (the fix unlinks them up front), not leave them to corrupt the new temp
    path = tmp_path / "index.db"
    path.with_name(".index.db.tmp-wal").write_bytes(b"stale-wal")
    path.with_name(".index.db.tmp-shm").write_bytes(b"stale-shm")
    db.build_atomic(path, lambda conn: conn.execute("CREATE TABLE t (a TEXT)"))
    assert sorted(p.name for p in tmp_path.iterdir()) == ["index.db"]


def test_build_atomic_makes_parent_dirs(tmp_path):
    path = tmp_path / "nested" / "deeper" / "index.db"
    db.build_atomic(path, lambda conn: conn.execute("CREATE TABLE t (a TEXT)"))
    assert path.exists()


def test_build_atomic_leaves_no_partial_on_failure(tmp_path):
    """A build that raises mid-way must not leave a half-written DB at the real path (§7.4)."""
    path = tmp_path / "index.db"

    def boom(conn):
        conn.execute("CREATE TABLE t (a TEXT)")
        raise RuntimeError("mid-build failure")

    with pytest.raises(RuntimeError):
        db.build_atomic(path, boom)
    assert not path.exists()  # the real artifact never appeared
    assert not path.with_name(f".{path.name}.tmp").exists()  # temp cleaned up


def test_build_atomic_overwrites_stale_temp(tmp_path):
    """A leftover temp from a crashed prior run must not block the next build."""
    path = tmp_path / "index.db"
    stale = path.with_name(f".{path.name}.tmp")
    stale.write_bytes(b"garbage")
    db.build_atomic(path, lambda conn: conn.execute("CREATE TABLE t (a TEXT)"))
    assert path.exists() and not stale.exists()


def test_connect_read_only_refuses_writes(tmp_path):
    path = tmp_path / "x.db"
    rw = db.connect(path)
    db.apply_schema(rw, "CREATE TABLE t (a TEXT)")
    rw.close()

    ro = db.connect(path, read_only=True)
    try:
        with pytest.raises(sqlite3.OperationalError):
            ro.execute("INSERT INTO t VALUES ('x')")
    finally:
        ro.close()


def test_replace_table_atomic_swaps_and_preserves_siblings(tmp_path):
    """The named table is replaced; other tables in the store survive untouched (§9.2)."""
    path = tmp_path / "index.db"
    conn = db.connect(path)
    db.apply_schema(conn, "CREATE TABLE keep (x TEXT); INSERT INTO keep VALUES ('survivor');")
    conn.execute("CREATE TABLE rel (a TEXT)")
    conn.execute("INSERT INTO rel VALUES ('old')")
    conn.commit()
    conn.close()

    def build_new(c, new):
        c.execute(f"CREATE TABLE {new} (a TEXT)")
        c.executemany(f"INSERT INTO {new} VALUES (?)", [("new1",), ("new2",)])

    db.replace_table_atomic(path, "rel", build_new)

    ro = db.connect(path, read_only=True)
    try:
        assert ro.execute("SELECT count(*) FROM rel").fetchone()[0] == 2  # replaced
        vals = [r[0] for r in ro.execute("SELECT a FROM rel ORDER BY a")]
        assert vals == ["new1", "new2"]
        assert ro.execute("SELECT x FROM keep").fetchone()[0] == "survivor"  # sibling intact
        # no leftover side table
        names = {r[0] for r in ro.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "rel__new" not in names
    finally:
        ro.close()


def test_replace_table_atomic_preserves_old_on_failed_build(tmp_path):
    """If build_new raises, the live table is untouched (no swap happened)."""
    path = tmp_path / "index.db"
    conn = db.connect(path)
    db.apply_schema(conn, "CREATE TABLE rel (a TEXT); INSERT INTO rel VALUES ('keep');")
    conn.close()

    def boom(c, new):
        c.execute(f"CREATE TABLE {new} (a TEXT)")
        raise RuntimeError("build failed")

    with pytest.raises(RuntimeError):
        db.replace_table_atomic(path, "rel", boom)

    ro = db.connect(path, read_only=True)
    try:
        assert ro.execute("SELECT a FROM rel").fetchone()[0] == "keep"  # prior table survives
    finally:
        ro.close()
