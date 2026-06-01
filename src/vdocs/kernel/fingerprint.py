"""Artifact fingerprints — the single content-signature primitive (§7.3, §9.2).

Two strengths, chosen by the orchestrator's ``--verify`` flag:

* **cheap** (default): size + mtime for files; row count for tables. This is the
  one mtime-cache mechanism (v1 had three) — fast enough to run on every preflight.
* **strong** (``verify=True``): sha256 of the actual content; used by CI / paranoid
  runs to prove byte-level idempotency (§7.4).

Pure except for reading the artifacts it is asked to sign.
"""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterator
from pathlib import Path

_CHUNK = 1 << 16


def iter_files(root: Path) -> Iterator[Path]:
    """Yield every file under ``root`` in deterministic (sorted-relpath) order.

    The single incremental-walk helper; deterministic ordering is what makes tree
    fingerprints reproducible across machines and runs.
    """
    files = (p for p in root.rglob("*") if p.is_file())
    yield from sorted(files, key=lambda p: p.relative_to(root).as_posix())


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def file_fingerprint(path: Path, *, verify: bool = False) -> str:
    """Signature of a single file. Cheap = size:mtime_ns; strong = sha256(content)."""
    if verify:
        return _sha256_file(path)
    st = path.stat()
    return f"{st.st_size}:{st.st_mtime_ns}"


def tree_fingerprint(path: Path, *, verify: bool = False) -> str:
    """Signature of a directory tree: sha256 over (relpath, per-file fingerprint)."""
    h = hashlib.sha256()
    for member in iter_files(path):
        rel = member.relative_to(path).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(file_fingerprint(member, verify=verify).encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def sqlite_fingerprint(db_path: Path, table: str, *, verify: bool = False) -> str:
    """Signature of a SQLite table. Cheap = row count; strong = sha256 of all rows."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        if not verify:
            (count,) = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            return f"rows:{count}"
        h = hashlib.sha256()
        cursor = conn.execute(f"SELECT * FROM {table} ORDER BY 1")
        for row in cursor:
            h.update(repr(row).encode("utf-8"))
            h.update(b"\n")
        return h.hexdigest()
    finally:
        conn.close()
