"""Unit tests for kernel.db — the one place that knows SQLite pragmas (§9.2)."""

import sqlite3

import pytest

from vdocs.kernel import db


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
