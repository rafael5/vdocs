"""Content-addressed store + atomic write (design §5.1, §9.2, ADR-003).

The asset store is **write-once**: binaries live at ``<sha256>.<ext>`` and are never
mutated or copied (they dominate corpus size and never change). ``atomic_write`` is
the shared primitive every stage uses to satisfy the atomicity rule (§7.4): write to a
temp file, then ``os.replace`` into place so a crash never leaves a half-written artifact.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path


def atomic_write(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` atomically (tmp file + rename within the same dir).

    Content-skip (§7.4, R2): if ``path`` already holds byte-identical content, this is a **no-op**
    — the file is left untouched (mtime preserved). That keeps the cheap ``size:mtime_ns``
    fingerprint stable across no-op re-runs, so ``SKIP_IF_UNCHANGED`` actually skips instead of
    being defeated by an unconditional rewrite that bumps mtime."""
    if (
        path.is_file()
        and hashlib.sha256(path.read_bytes()).hexdigest() == hashlib.sha256(data).hexdigest()
    ):
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    try:
        with tmp.open("wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


class Cas:
    """A content-addressed, write-once binary store rooted at ``root``."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def path_for(self, digest: str, *, ext: str) -> Path:
        return self.root / f"{digest}.{ext}"

    def put(self, data: bytes, *, ext: str) -> str:
        """Store ``data``; return its sha256. A no-op if already present (write-once)."""
        digest = hashlib.sha256(data).hexdigest()
        target = self.path_for(digest, ext=ext)
        if not target.exists():
            atomic_write(target, data)
        return digest

    def get(self, digest: str, *, ext: str) -> bytes:
        return self.path_for(digest, ext=ext).read_bytes()

    def has(self, digest: str, *, ext: str) -> bool:
        return self.path_for(digest, ext=ext).exists()
