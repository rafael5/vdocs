"""SQLite helpers — the single place that knows connection pragmas (§9.2, ADR-004).

Every store (``state.db``, ``index.db``, ``vectors.db``) is opened through here so
WAL mode, foreign keys, and the row factory are configured in exactly one place.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable
from pathlib import Path


def connect(path: Path, *, read_only: bool = False) -> sqlite3.Connection:
    """Open a SQLite connection with the project's standard pragmas.

    ``read_only=True`` opens via a ``file:...?mode=ro`` URI — the mode the MCP
    server uses against the derived stores (§14.5).
    """
    if read_only:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def apply_schema(conn: sqlite3.Connection, ddl: str) -> None:
    """Apply a DDL script (idempotent when the DDL uses ``IF NOT EXISTS``)."""
    conn.executescript(ddl)
    conn.commit()


def build_atomic(path: Path, build: Callable[[sqlite3.Connection], None]) -> None:
    """Build a fresh SQLite store atomically (temp + rename, §7.4).

    Opens a connection to a sibling ``.<name>.tmp``, runs ``build(conn)`` (which issues the
    DDL/inserts), commits, closes, then ``os.replace``s the temp onto ``path`` — so a crash or a
    raising ``build`` never leaves a half-written DB at the real path that preflight would mistake
    for complete. A leftover temp from a prior crash is discarded first. The single shared
    atomic-DB-build primitive (§9.2) for every stage that *rebuilds* a derived store
    (``serve-inventory`` now; ``index``/``relate``/``embed`` next)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    if tmp.exists():
        tmp.unlink()
    conn = connect(tmp)
    try:
        build(conn)
        conn.commit()
    except BaseException:
        conn.close()
        if tmp.exists():
            tmp.unlink()
        raise
    else:
        conn.close()
    os.replace(tmp, path)
