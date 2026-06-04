#!/usr/bin/env python3
"""Garbage-collect orphaned bodies from the gold history CAS (``gold/_shared/history``).

The history CAS is **write-once / append-only** (``vdocs.kernel.cas.Cas``): the consolidate stage
``put()``s every retained normalized body at ``<sha256>.md`` and never deletes. The pipeline's only
deleter, ``cas.prune_bundles()``, operates on the *bundle* tree (consolidated/normalized/…), never
on this CAS — so a full re-run never reclaims anything here. Over many runs the store accumulates
**orphans**: bodies whose hash is no longer referenced by any live ``history.yaml`` (a re-conversion
produced a new hash, or a member/version was withdrawn). This script reclaims exactly those.

It is deliberately **independent of the vdocs code** — reference scanning is inlined — so it can be
a trustworthy standalone GC. It is conservative: a body is reclaimable ONLY if its digest appears in
no ``*.yaml``/``*.json`` under ``gold/`` outside the store itself. Default mode is a **dry run**
that deletes nothing; pass ``--apply`` to actually reclaim. ``--trash DIR`` moves instead of unlink.

Usage:
    python scripts/gc_history_cas.py                 # dry run: report orphans + reclaimable bytes
    python scripts/gc_history_cas.py --apply         # delete orphaned bodies
    python scripts/gc_history_cas.py --apply --trash ~/data/vdocs/.history-trash  # move not delete
    python scripts/gc_history_cas.py --data-dir /path/to/vdocs
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

# A bare sha256 digest as it appears in frontmatter/manifest YAML+JSON (e.g. ``body_sha256: <hex>``)
_SHA256_RE = re.compile(r"\b[0-9a-f]{64}\b")


def human(n: int) -> str:
    """Bytes → short human string (1 KiB = 1024)."""
    size = float(n)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} TiB"


def referenced_digests(gold: Path, store: Path) -> set[str]:
    """Every sha256 mentioned in any ``*.yaml``/``*.json`` under ``gold/`` EXCEPT inside the store.

    This is the live reference set: history.yaml carries one ``body_sha256`` per member, bundle.yaml
    echoes the anchor body hash, and the corpus manifest indexes them. We scan metadata files only —
    body.md never links a history body by hash — and union *every* 64-hex token we find, so anything
    referenced anywhere is kept (false-keep over false-delete)."""
    refs: set[str] = set()
    for path in gold.rglob("*"):
        if path.suffix not in (".yaml", ".json") or not path.is_file():
            continue
        if store in path.parents:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:  # unreadable metadata must not silently shrink the keep-set
            print(f"  WARN: could not read {path}: {exc}", file=sys.stderr)
            continue
        refs.update(_SHA256_RE.findall(text))
    return refs


def stored_bodies(store: Path) -> dict[str, Path]:
    """digest → path for every ``<sha256>.md`` body currently in the CAS."""
    out: dict[str, Path] = {}
    for path in store.glob("*.md"):
        out[path.stem] = path
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    default_data = os.environ.get("DATA_DIR", "/home/rafael/data/vdocs")
    ap.add_argument(
        "--data-dir",
        default=default_data,
        type=Path,
        help=f"vdocs data root (default: {default_data})",
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="actually reclaim orphans (default: dry run, deletes nothing)",
    )
    ap.add_argument(
        "--trash",
        type=Path,
        default=None,
        help="with --apply, MOVE orphans here instead of deleting them",
    )
    ap.add_argument(
        "--list", action="store_true", help="print every orphan digest, not just a sample"
    )
    args = ap.parse_args()

    gold = args.data_dir / "documents" / "gold"
    store = gold / "_shared" / "history"
    if not store.is_dir():
        print(f"ERROR: history CAS not found: {store}", file=sys.stderr)
        return 2

    print(f"history CAS : {store}")
    print(f"scanning refs under: {gold}  (*.yaml, *.json; excluding the store)")
    refs = referenced_digests(gold, store)
    stored = stored_bodies(store)

    orphans = {d: p for d, p in stored.items() if d not in refs}
    orphan_bytes = sum(p.stat().st_size for p in orphans.values())
    live = len(stored) - len(orphans)

    stored_bytes = sum(p.stat().st_size for p in stored.values())
    print()
    print(f"stored bodies   : {len(stored):>6}   ({human(stored_bytes)})")
    print(f"referenced (kept): {live:>6}")
    print(f"ORPHANS         : {len(orphans):>6}   ({human(orphan_bytes)} reclaimable)")

    if not orphans:
        print("\nNothing to reclaim — the CAS is clean.")
        return 0

    sample = sorted(orphans)[: (len(orphans) if args.list else 10)]
    print("\norphan digests" + ("" if args.list else " (first 10)") + ":")
    for d in sample:
        print(f"  {d}  {human(orphans[d].stat().st_size)}")
    if not args.list and len(orphans) > 10:
        print(f"  … and {len(orphans) - 10} more  (use --list to see all)")

    if not args.apply:
        print(f"\nDRY RUN — nothing deleted. Re-run with --apply to reclaim {human(orphan_bytes)}.")
        return 0

    # --apply
    if args.trash is not None:
        args.trash.mkdir(parents=True, exist_ok=True)
        for p in orphans.values():
            shutil.move(str(p), str(args.trash / p.name))
        print(f"\nMOVED {len(orphans)} orphans → {args.trash}  ({human(orphan_bytes)})")
    else:
        for p in orphans.values():
            p.unlink()
        print(f"\nDELETED {len(orphans)} orphans  ({human(orphan_bytes)} reclaimed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
