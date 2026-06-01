"""SQLite helpers — the single place that knows connection pragmas (§9.2, ADR-004).

Every store (``state.db``, ``index.db``, ``vectors.db``) is opened through here so
WAL mode, foreign keys, and the row factory are configured in exactly one place.
"""

from __future__ import annotations

import sqlite3
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
