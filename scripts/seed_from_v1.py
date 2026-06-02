#!/usr/bin/env python3
"""Seed vdocs' document-bronze from v1's real fetched docs — for real-corpus development.

The document-medallion stages (convert/discover/enrich/normalize/…) need *real* VA documents,
not synthetic fixtures, to be developed against — real Word XML, images, tables, and mess are
the requirement. Rather than crawl the live VDL, this maps each genuine gold-inventory record
to its already-fetched file in v1's ``raw/<APP>/<doc_filename>``, stores the bytes in vdocs'
bronze CAS, writes ``raw/index.json`` + ``acquisitions``, and records a ``fetch`` completion —
so ``vdocs convert`` (and downstream) can run on actual documents, entirely offline.

Usage:
    python scripts/seed_from_v1.py [--per-app N] [--full APP[,APP...]] [--v1-raw PATH]

Requires a populated gold inventory (``vdocs crawl/catalog/serve-inventory`` first).
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from vdocs.config import Settings
from vdocs.contracts.registry import RAW_INDEX, RAW_TREE
from vdocs.kernel.cas import Cas, atomic_write
from vdocs.models.catalog import EnrichedInventory
from vdocs.models.stage import Acquisition, StageRun
from vdocs.orchestrator.state import StateStore


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--per-app", type=int, default=3, help="docs per app (breadth)")
    ap.add_argument("--full", default="CPRS", help="comma-separated apps taken in full")
    ap.add_argument(
        "--v1-raw",
        type=Path,
        default=Path.home() / "data" / "vista-docs" / "raw",
        help="v1 raw/ tree (raw/<APP>/<filename>)",
    )
    args = ap.parse_args()
    full_apps = {a.strip() for a in args.full.split(",") if a.strip()}

    cfg = Settings()
    inv = EnrichedInventory.model_validate_json(cfg.gold_inventory_json.read_text(encoding="utf-8"))

    # dedup to logical docx docs that have a real v1 file (genuine rows only)
    logical: dict[tuple[str, str], object] = {}
    for r in inv.records:
        if r.noise_type or r.doc_format != "docx":
            continue
        if (args.v1_raw / r.app_name_abbrev / r.doc_filename).is_file():
            logical.setdefault((r.app_name_abbrev, r.doc_slug), r)

    by_app: dict[str, list] = defaultdict(list)
    for r in logical.values():
        by_app[r.app_name_abbrev].append(r)
    sample = []
    for app, recs in by_app.items():
        recs.sort(key=lambda r: (r.doc_code, r.doc_slug))
        sample.extend(recs if app in full_apps else recs[: args.per_app])

    store = StateStore.open(cfg.state_db)
    raw_cas = Cas(cfg.bronze_raw)
    now = "1970-01-01T00:00:00Z"  # fixed stamp — deterministic seed (no Date.now in scripts)
    index: dict[str, dict[str, str]] = {}
    for r in sample:
        data = (args.v1_raw / r.app_name_abbrev / r.doc_filename).read_bytes()
        sha = raw_cas.put(data, ext="docx")
        index[sha] = {
            "app_code": r.app_name_abbrev,
            "doc_slug": r.doc_slug,
            "title": r.doc_title,
            "source_url": r.doc_url,
            "ext": "docx",
        }
        store.record_acquisition(
            Acquisition(
                doc_id=f"{r.app_name_abbrev}:{r.doc_slug}",
                source_url=r.doc_url,
                status="fetched",
                sha256=sha,
                bytes=len(data),
                attempts=1,
                first_attempt_at=now,
                last_attempt_at=now,
                fetched_at=now,
                tool_ver=cfg.tool_ver,
            )
        )
    atomic_write(cfg.raw_index, json.dumps(index, indent=2).encode("utf-8"))
    store.record(
        StageRun(
            stage="fetch",
            scope="",
            status="ok",
            started_at="seed",
            finished_at="seed",
            inputs_fp={},
            outputs_fp={
                RAW_TREE.key: RAW_TREE.fingerprint(cfg),
                RAW_INDEX.key: RAW_INDEX.fingerprint(cfg),
            },
            counts={"targets": len(sample), "fetched": len(sample), "failed": 0},
            contract_ver=1,
            tool_ver=cfg.tool_ver,
        )
    )
    store.close()
    print(f"seeded {len(sample)} real docx docs across {len(by_app)} apps into {cfg.bronze_raw}")


if __name__ == "__main__":
    main()
