"""``vdocs release`` — assemble (and publish) the vdocs ``data-v1`` release (Track D3).

Bundle = the shipped ``index.db`` (``doc_meta_staged`` stripped, ADR-0001) + the gold
corpus (``consolidated/`` + ``_shared/`` + glossary + the gold manifests) + the
IN-BUNDLE ``manifest.json``. Rich assets/tables are **excluded and declared** (F15) —
a v1.x additive follow-up. V7-parity rules:

- ``bundle_sha256`` lives OUTSIDE the bundle: the standalone release-asset manifest =
  in-bundle fields + ``bundle_sha256`` (F5), plus a sha256sum-checkable ``SHA256SUMS``.
- assembly is deterministic — sorted tar entries, pinned mtimes, timestamp-free gzip.
- release refuses unless: the repo tree is clean and HEAD == upstream (F16), the lake
  is quiescent with ``corpus_content_hash`` stable across the assembly window (F15),
  ``doctor`` is GREEN, and the entity-quality floors measure PASS (D2.5).

The per-file ``files`` block covers the flat payload; the ``consolidated/`` tree is
pinned by a single ``tree_sha256`` (the V5 recipe over its relpaths+bytes) — every
byte is still hash-covered without a thousand-entry manifest.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import shutil
import sqlite3
import tarfile
from pathlib import Path

TAG = "data-v1"
BUNDLE_ROOT = "vdocs-data-v1"
BUNDLE_NAME = "vdocs-data-v1.tar.gz"
STANDALONE_NAME = "vdocs-data-v1.manifest.json"
SUMS_NAME = "SHA256SUMS"

# tar entry mtime: fixed epoch — data identity lives in corpus_content_hash, not mtimes
_MTIME = 0


def strip_staged(src_db: Path, dest_db: Path) -> None:
    """Copy ``index.db`` and strip the producer-internal ``doc_meta_staged`` table from
    the shipped copy (ADR-0001) — the source database is never mutated."""
    shutil.copyfile(src_db, dest_db)
    conn = sqlite3.connect(dest_db)
    try:
        conn.executescript("DROP TABLE IF EXISTS doc_meta_staged; VACUUM;")
    finally:
        conn.close()


def tree_hash(files: dict[str, bytes]) -> str:
    """The V5 recipe over a file tree: sha256 of the LF-joined, bytewise-sorted
    ``"<relpath>\\t<sha256(bytes)>"`` lines — order-independent, name-sensitive."""
    lines = "\n".join(
        f"{name}\t{hashlib.sha256(files[name]).hexdigest()}" for name in sorted(files)
    )
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


def release_manifest(
    contract: dict,
    *,
    source_commit: str,
    files: dict[str, dict],
    consolidated: dict,
) -> dict:
    """The in-bundle release manifest: the D1/D2.5 contract manifest + release pinning.
    No ``bundle_sha256`` here — a manifest inside the tarball cannot hash the tarball."""
    return {
        **contract,
        "tag": TAG,
        "source_commit": source_commit,
        "files": files,
        "consolidated": consolidated,
        # decided, not open (F15): the sidecar bundles ship separately in v1.x
        "rich_assets": "excluded",
        "rich_tables": "excluded",
        # the 292MB version-history CAS is provenance, not reading surface — v1.x follow-up
        "history_cas": "excluded",
        # SKL build intermediate; its projections (glossary, entity tables) already ship
        "knowledge_db": "excluded",
    }


def standalone_manifest(in_bundle: dict, bundle_sha256: str) -> dict:
    return {**in_bundle, "bundle_sha256": bundle_sha256}


def _dumps(doc: dict) -> bytes:
    import json

    return (json.dumps(doc, indent=2, sort_keys=True) + "\n").encode("utf-8")


# the gold reading surface: consolidated bodies + the boilerplate their REFERENCE links
# resolve to + the flat gold manifests. _shared/history (CAS) and knowledge.db are
# excluded AND declared in the manifest.
_GOLD_DIRS = ("consolidated", "_shared/boilerplate")
_GOLD_FILES = (
    "glossary.md",
    "corpus-manifest.json",
    "discovery.json",
    "ai-manifest.json",
    "CORPUS.md",
    "contract-manifest.json",
)


def _gold_entries(gold_dir: Path) -> list[tuple[str, bytes]]:
    paths: list[Path] = []
    for d in _GOLD_DIRS:
        paths.extend(p for p in sorted((gold_dir / d).rglob("*")) if p.is_file())
    paths.extend(gold_dir / f for f in _GOLD_FILES if (gold_dir / f).is_file())
    return [(f"{BUNDLE_ROOT}/gold/{p.relative_to(gold_dir)}", p.read_bytes()) for p in paths]


def write_bundle(out_path: Path, *, index_db: Path, gold_dir: Path, manifest: dict) -> str:
    """Deterministic tar.gz; returns its sha256."""
    entries = [(f"{BUNDLE_ROOT}/index.db", index_db.read_bytes())]
    entries += _gold_entries(gold_dir)
    entries.append((f"{BUNDLE_ROOT}/manifest.json", _dumps(manifest)))

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for name, data in sorted(entries):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mtime = _MTIME
            info.mode = 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            tf.addfile(info, io.BytesIO(data))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as f:
        with gzip.GzipFile(filename="", mode="wb", fileobj=f, mtime=0) as gz:
            gz.write(buf.getvalue())
    return hashlib.sha256(out_path.read_bytes()).hexdigest()


def sha256sums(paths: list[Path]) -> str:
    return "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in paths)
