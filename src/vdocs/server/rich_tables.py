"""``vdocs publish-rich-tables`` — the rich-reading **table** distribution (tables proposal P3).

The reading consumer (``vdocs-web``) renders a doc's extracted-table ``tables/*.csv`` sidecars
(read contract v1.4 + ``GET /api/table``). On a **downloaded-only** install (just ``index.db``, no
co-located gold tree) it has no tables to serve; this collects every gold bundle's ``tables/*.csv``
into a structure-preserving distribution dir (``DATA_DIR/rich-tables/``) that rides *alongside*
``index.db``.

Unlike the 1.2 GB figure bundle, the whole-corpus table set is small (~10 MB), so it is **not
curated** — every doc's tables ship. The on-disk layout ``<app>/<slug>/tables/<name>`` mirrors the
gold tree, so ``vdocs-web``'s same ``/api/table`` handler serves the downloaded copy by pointing its
tables dir at the cache. Each CSV carries a sha256 in the manifest (CSVs aren't content-addressed
the way figures are, so integrity is explicit).

The pure planner (:func:`plan_tables`) takes already-read bytes, so it is unit-tested without the
lake; :func:`build_tables_bundle` is the thin driver that copies the CSVs + writes the manifest.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass

# Bump when the manifest's shape changes (a consumer reads this to know it can parse the bundle).
MANIFEST_VER = 1


@dataclass(frozen=True)
class TableEntry:
    """One distributed table CSV: its bundle-relative path + integrity digest + size."""

    path: str  # bundle-relative posix, "<app>/<slug>/tables/table-NN.csv"
    sha256: str
    bytes: int


@dataclass(frozen=True)
class TablesPlan:
    """The planned distribution: the per-CSV entries (sorted) + corpus totals."""

    tables: list[TableEntry]
    total_bytes: int
    doc_count: int  # distinct gold bundle dirs contributing a table


def plan_tables(files: Mapping[str, bytes]) -> TablesPlan:
    """Plan the distribution from ``{bundle-relative path → csv bytes}``. Pure: hashes + counts,
    entries sorted by path; ``doc_count`` is the number of distinct ``<app>/<slug>`` dirs."""
    entries = [
        TableEntry(path=p, sha256=hashlib.sha256(b).hexdigest(), bytes=len(b))
        for p, b in sorted(files.items())
    ]
    docs = {p.split("/tables/", 1)[0] for p in files}
    return TablesPlan(
        tables=entries, total_bytes=sum(e.bytes for e in entries), doc_count=len(docs)
    )


def build_tables_bundle(cfg) -> TablesPlan:  # type: ignore[no-untyped-def]
    """Copy every gold bundle's ``tables/*.csv`` into ``cfg.rich_tables`` (structure-preserving),
    prune any CSV (and emptied dir) no longer present, write the manifest, and return the plan."""
    gold = cfg.gold_consolidated
    files = {
        p.relative_to(gold).as_posix(): p.read_bytes()
        for p in gold.rglob("*.csv")
        if p.parent.name == "tables"
    }
    plan = plan_tables(files)

    cfg.rich_tables.mkdir(parents=True, exist_ok=True)
    for rel, data in files.items():  # content-stable ⇒ rewrite only on change
        dst = cfg.rich_tables / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists() or dst.read_bytes() != data:
            dst.write_bytes(data)
    wanted = set(files)
    for existing in cfg.rich_tables.rglob("*.csv"):  # prune stale CSVs from a prior, larger run
        if existing.relative_to(cfg.rich_tables).as_posix() not in wanted:
            existing.unlink()
    for sub in sorted((p for p in cfg.rich_tables.rglob("*") if p.is_dir()), reverse=True):
        if not any(sub.iterdir()):  # drop a dir emptied by the prune
            sub.rmdir()

    _write_manifest(cfg, plan)
    return plan


def _write_manifest(cfg, plan: TablesPlan) -> None:  # type: ignore[no-untyped-def]
    """Write ``manifest.json`` describing the distribution (the descriptor a consumer reads)."""
    manifest = {
        "contract_ver": MANIFEST_VER,
        "doc_count": plan.doc_count,
        "table_count": len(plan.tables),
        "total_bytes": plan.total_bytes,
        "tables": [{"path": e.path, "sha256": e.sha256, "bytes": e.bytes} for e in plan.tables],
    }
    cfg.rich_tables_manifest.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
