"""Artifact fingerprints — the single content-signature primitive (§7.3, §9.2).

Two strengths, chosen by the orchestrator's ``--verify`` flag:

* **cheap** (default): size + mtime for files and trees. This is the one mtime-cache
  mechanism (v1 had three) — fast enough to run on every preflight.
* **strong** (``verify=True``): sha256 of the actual content; used by CI / paranoid
  runs to prove byte-level idempotency (§7.4).

**SQLite tables have one strength, not two** (P4.1, audit R‑1): always the canonical content
hash. A row count cannot see a content-only change, and the measured cost of hashing every
contracted table in the lake is ~1.1 s — so the cheap variant bought nothing and cost
correctness. ``verify`` is accepted and ignored on that path.

Pure except for reading the artifacts it is asked to sign.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator
from pathlib import Path

from vdocs.kernel import db

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


#: A recorded fingerprint in the retired ``rows:<count>`` format (the P4.2 migration predicate).
_LEGACY_SQLITE_RE = re.compile(r"^rows:\d+$")


def is_legacy_sqlite_fingerprint(value: str) -> bool:
    """Whether ``value`` is a recorded fingerprint in the retired ``rows:<count>`` format.

    Such a value predates P4.1 and is **not comparable** to the content hash
    :func:`sqlite_fingerprint` now returns — so a consumer must read it as *format-migrated*
    (accept once, re-record), never as upstream drift (see ``Stage.preflight``)."""
    return bool(_LEGACY_SQLITE_RE.match(value))


def sqlite_fingerprint(db_path: Path, table: str, *, verify: bool = False) -> str:
    """Signature of a SQLite table: **always** the canonical content hash (P4.1, audit R‑1).

    The cheap path used to be ``rows:<count>``, which cannot see a content-only change — so a
    consumer's ``SKIP_IF_UNCHANGED`` preflight decided "nothing changed" over a table whose every
    cell may have changed, and shipped stale metadata no gate could red. (It bit for real during
    P3's acceptance run: ``index`` rebuilt its tables with identical row counts, so ``merge``
    skipped and its SKL projection stayed the empty shell ``index`` had just recreated.)

    There is no cost argument for keeping the cheap variant: measured on the live lake, the largest
    contracted table (``relations``, 203,272 rows) hashes in 0.33 s and *every* contracted table
    together in ~1.1 s. ``verify`` is accepted and ignored here — it keeps its meaning for files
    and trees, where the cheap size:mtime signature is honest.

    A pure function of the table's row *content*, independent of insert/row order: each row is
    encoded from its typed cell values (not ``repr(row)``, which is fragile) and the encoded rows
    are sorted, giving a canonical content order. NULL is encoded distinctly from the empty string
    so a NULL↔``''`` change is still detected.
    """
    conn = db.connect(db_path, read_only=True)
    try:
        h = hashlib.sha256()
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        encoded = [
            "\x01".join("\x00NULL\x00" if v is None else str(v) for v in row) for row in rows
        ]
        for line in sorted(encoded):
            h.update(line.encode("utf-8"))
            h.update(b"\n")
        return h.hexdigest()
    finally:
        conn.close()
