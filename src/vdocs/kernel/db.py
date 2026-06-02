"""SQLite helpers — the single place that knows connection pragmas (§9.2, ADR-004).

Every store (``state.db``, ``index.db``, ``vectors.db``) is opened through here so
WAL mode, foreign keys, and the row factory are configured in exactly one place.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable
from pathlib import Path


def connect(
    path: Path, *, read_only: bool = False, journal_mode: str = "WAL"
) -> sqlite3.Connection:
    """Open a SQLite connection with the project's standard pragmas.

    ``read_only=True`` opens via a ``file:...?mode=ro`` URI — the mode the MCP
    server uses against the derived stores (§14.5). ``journal_mode`` defaults to ``WAL`` (the
    long-lived stores); :func:`build_atomic` overrides it to ``DELETE`` for the throwaway build
    temp so no ``-wal``/``-shm`` sibling can outlive the atomic rename (§7.4, R7).
    """
    if read_only:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(path)
        conn.execute(f"PRAGMA journal_mode={journal_mode}")
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
    (``serve-inventory`` now; ``index``/``relate``/``embed`` next).

    WAL hardening (R7): the temp is built in ``journal_mode=DELETE`` so SQLite never creates a
    ``.<name>.tmp-wal``/``.tmp-shm`` sibling that the single-file ``os.replace`` would orphan; any
    such siblings (and a stale ``.tmp`` from a prior crash) are swept on both the success and
    failure paths."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    wal_siblings = (
        path.with_name(f".{path.name}.tmp-wal"),
        path.with_name(f".{path.name}.tmp-shm"),
    )

    def _sweep() -> None:
        for sib in wal_siblings:
            sib.unlink(missing_ok=True)

    tmp.unlink(missing_ok=True)  # discard a leftover temp from a prior crash
    _sweep()  # …and any orphaned WAL siblings beside it
    conn = connect(tmp, journal_mode="DELETE")
    try:
        build(conn)
        conn.commit()
    except BaseException:
        conn.close()
        tmp.unlink(missing_ok=True)
        _sweep()
        raise
    else:
        conn.close()
    _sweep()
    os.replace(tmp, path)
