#!/usr/bin/env python3
"""Prototype: what would a `--latest-only` fetch selector save, on the REAL inventory?

`--latest-only` would fetch one version per logical document instead of the whole lineage
(inverting the §5.6 version-completeness invariant), so consolidate has nothing to collapse.
This measures the fetch/convert saving AND surfaces a correctness caveat: `anchor_key`
(app:pkg:doc_code) over-groups *distinct* documents that merely share a doc-type, so
latest-by-anchor would delete real manuals. We therefore also group by a finer "logical
document" key (anchor + a version-stripped slug stem) for the SAFE saving.

Read-only; prints a report. Usage: python scripts/proto_latest_only.py
"""

from __future__ import annotations

import collections
import json
import re
from pathlib import Path

import yaml

LAKE = Path.home() / "data" / "vdocs"
REG = Path(__file__).resolve().parent.parent / "registries"

# A slug is '_'-delimited; underscores are \w so regex \b won't split _123 — tokenize on '_'.
_DROP_TOKEN = re.compile(
    r"^(?:\d+|p\d+|v\d+|r\d+|patch|release|addendum|rev|ver|version|build)$", re.IGNORECASE
)


def slug_stem(slug: str) -> str:
    """A version-free 'logical document' stem: drop pure version / patch tokens, keep the rest."""
    return "_".join(t for t in slug.split("_") if not _DROP_TOKEN.match(t))


def version_key(rec: dict) -> tuple:
    """Best-effort 'newest wins' ordering: (parsed patch version tuple, trailing slug digits)."""
    parts: list[int] = []
    for tok in re.split(r"[._]", rec.get("patch_ver", "") or ""):
        if tok.isdigit():
            parts.append(int(tok))
    trail = re.findall(r"\d+", rec.get("doc_slug", ""))
    return (tuple(parts), tuple(int(t) for t in trail))


def main() -> None:
    recs = json.loads((LAKE / "inventory/silver/catalog.enriched.json").read_text())["records"]
    pol = yaml.safe_load((REG / "inventory/doctype-policy.yaml").read_text())["doctypes"]
    omit = {c for c, v in pol.items() if v["decision"] == "omit"}

    # mirror the gate: genuine + in-scope VistA + kept doc-type; one row per doc_slug (DOCX dedup)
    seen: set[str] = set()
    gated: list[dict] = []
    for r in recs:
        if r.get("noise_type") or r.get("out_of_scope_reason"):
            continue
        if not r.get("system_type", "").startswith("VistA"):
            continue
        if r.get("app_status") == "decommissioned":
            continue
        if r.get("doc_code") in omit:
            continue
        slug = r.get("doc_slug", "")
        if slug in seen:
            continue
        seen.add(slug)
        gated.append(r)

    def latest_per(keyfn) -> int:
        groups: dict[object, dict] = {}
        for r in gated:
            k = keyfn(r)
            if k not in groups or version_key(r) > version_key(groups[k]):
                groups[k] = r
        return len(groups)

    current = len(gated)
    by_anchor = latest_per(lambda r: r.get("anchor_key") or r.get("doc_slug"))
    by_logical = latest_per(lambda r: (r.get("anchor_key"), slug_stem(r.get("doc_slug", ""))))

    # over-grouping: anchors whose members span >1 logical-document stem
    stems_per_anchor: dict[str, set] = collections.defaultdict(set)
    for r in gated:
        ak = r.get("anchor_key") or r.get("doc_slug")
        stems_per_anchor[ak].add(slug_stem(r.get("doc_slug", "")))
    overgrouped = {a: s for a, s in stems_per_anchor.items() if len(s) > 1}

    pct = lambda n: f"{100 * n // current}%"  # noqa: E731
    print(f"gated fetch targets now (all versions):           {current}")
    print(
        f"--latest-only BY ANCHOR (consolidate's key, UNSAFE): {by_anchor}"
        f"   'saves' {current - by_anchor} ({pct(current - by_anchor)})"
    )
    print(
        f"--latest-only BY LOGICAL DOC (anchor+stem, SAFE):    {by_logical}"
        f"   saves {current - by_logical} ({pct(current - by_logical)})"
    )
    print()
    print(
        f"over-grouped anchors (>1 distinct logical doc):   "
        f"{len(overgrouped)} of {len(stems_per_anchor)}"
    )
    print("  → by-anchor latest-only would DELETE distinct manuals here; the gap between the two")
    print(f"    rows above ({by_logical - by_anchor} docs) is distinct documents, not versions.")
    worst = sorted(overgrouped.items(), key=lambda kv: -len(kv[1]))[:5]
    for a, s in worst:
        print(f"    {a:14} groups {len(s)} distinct logical docs, e.g. {sorted(s)[:3]}")


if __name__ == "__main__":
    main()
