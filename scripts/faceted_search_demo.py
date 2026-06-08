#!/usr/bin/env python3
"""Faceted (focused) search prototype — demonstrate the layered narrow-then-search flow.

Mirrors the human "focused information retrieval" method: declare structured constraints first,
collapsing the corpus to a tiny homogeneous set, *then* run content search within it. Each layer is
an exact filter on `index.db` columns the pipeline ALREADY produces — no pipeline/index change.

  Layer 1  doc_type           (UM/TM/DIBR…)  + derived audience (clinical/technical/admin)
  Layer 2  package            (app_code / pkg_ns)
  Layer 3  version / latest    + entity (file#/RPC/routine/option…)
  Layer 4  content            BM25 over chunks_fts, restricted to the narrowed doc set

This is a SPIKE to see the flow end-to-end before committing (not production code). The within-facet
ranking reuses the shipped lexical ranker (`search_pure`) so it matches `vdocs ask`.

Usage:
    python scripts/faceted_search_demo.py [--data-dir DIR]            # runs the built-in demo
    python scripts/faceted_search_demo.py --type UM --app RA "cancel exam"
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path
from typing import Any

from vdocs.server import search_pure as sp

# doc_type → audience facet (the "differentiate users/usage" roll-up). Curated; would live in a
# tiny registry (registries/inventory/audiences.yaml) in the real implementation.
AUDIENCE = {
    "UM": "clinical", "UG": "clinical", "TM": "technical", "DG": "technical", "API": "technical",
    "PDD": "technical", "INT": "technical", "IG": "admin", "IG-IMP": "admin", "DIBR": "admin",
    "SM": "admin", "CFG": "admin", "SG": "admin", "SG-SET": "admin", "AG": "admin", "SUP": "admin",
    "RN": "any", "QRG": "any", "REF": "any", "TRG": "clinical", "POM": "admin", "FAQ": "any",
}  # fmt: skip

_BM25 = sp.bm25_expr("chunks_fts")


def facet_catalog(db: Path) -> dict[str, list[tuple[str, int]]]:
    """The navigable facets (value → #docs) over latest docs — what a UI presents so the user picks
    instead of guesses. Cheap: a GROUP BY per column the pipeline already populated."""
    conn = sqlite3.connect(db)
    try:
        out: dict[str, list[tuple[str, int]]] = {}
        for col in ("doc_type", "app_code", "pkg_ns"):
            out[col] = conn.execute(
                f"SELECT {col}, COUNT(*) c FROM documents WHERE is_latest=1 AND {col}<>'' "
                f"GROUP BY {col} ORDER BY c DESC"
            ).fetchall()
        rows = conn.execute(
            "SELECT doc_type, COUNT(*) FROM documents WHERE is_latest=1 GROUP BY doc_type"
        ).fetchall()
        aud: dict[str, int] = {}
        for dt, c in rows:
            aud[AUDIENCE.get(dt, "any")] = aud.get(AUDIENCE.get(dt, "any"), 0) + c
        out["audience"] = sorted(aud.items(), key=lambda x: -x[1])
        out["entity_type"] = conn.execute(
            "SELECT type, COUNT(*) FROM entities GROUP BY type ORDER BY 2 DESC"
        ).fetchall()
        return out
    finally:
        conn.close()


def faceted_search(
    db: Path,
    *,
    doc_type: list[str] | None = None,
    app: list[str] | None = None,
    pkg_ns: list[str] | None = None,
    audience: str | None = None,
    entity: str | None = None,
    query: str | None = None,
    k: int = 10,
) -> dict[str, Any]:
    """Narrow (layers 1–3) → content-search (layer 4). Returns the per-layer candidate counts (so
    the flow is visible) + the ranked hits within the narrowed set (or the doc list if no query)."""
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        where = ["is_latest=1"]
        params: list[Any] = []
        trail = [("L0 all latest", "SELECT COUNT(*) FROM documents WHERE is_latest=1", [])]
        if doc_type:
            where.append(f"doc_type IN ({','.join('?' * len(doc_type))})")
            params += doc_type
        if audience:
            codes = [c for c, a in AUDIENCE.items() if a == audience]
            where.append(f"doc_type IN ({','.join('?' * len(codes))})")
            params += codes
        if app:
            where.append(f"app_code IN ({','.join('?' * len(app))})")
            params += app
        if pkg_ns:
            where.append(f"pkg_ns IN ({','.join('?' * len(pkg_ns))})")
            params += pkg_ns
        w = " AND ".join(where)
        doc_keys = [r[0] for r in conn.execute(f"SELECT doc_key FROM documents WHERE {w}", params)]
        trail.append((f"L1-2 doc_type/app/pkg/audience → {len(doc_keys)} docs", "", []))
        if entity:  # layer 3: restrict to docs mentioning the entity
            ek = {
                r[0]
                for r in conn.execute(
                    "SELECT DISTINCT doc_key FROM entity_mentions WHERE entity_id=?", (entity,)
                )
            }
            doc_keys = [d for d in doc_keys if d in ek]
            trail.append((f"L3 entity={entity} → {len(doc_keys)} docs", "", []))
        if not doc_keys:
            return {"trail": trail, "candidate_docs": 0, "hits": []}
        ph = ",".join("?" * len(doc_keys))
        if query:
            match = sp.fts_match_query(query)
            rows = conn.execute(
                f"SELECT f.section_id, f.doc_key, d.title AS doc_title, "
                f"snippet(chunks_fts,{sp.FTS_COLUMNS.index('body')},'[',']',' … ',12) AS snip, "
                f"{_BM25} AS bm25 FROM chunks_fts f JOIN documents d ON d.doc_key=f.doc_key "
                f"WHERE chunks_fts MATCH ? AND f.doc_key IN ({ph}) ORDER BY {_BM25} LIMIT ?",
                [match, *doc_keys, k],
            ).fetchall()
            hits = [dict(r) for r in rows]
            trail.append(
                (f"L4 content '{query}' within {len(doc_keys)} docs → {len(hits)} hits", "", [])
            )
        else:  # pure browse: list the narrowed docs
            rows = conn.execute(
                f"SELECT doc_key, title AS doc_title FROM documents WHERE doc_key IN ({ph}) "
                f"ORDER BY doc_key LIMIT ?",
                [*doc_keys, k],
            ).fetchall()
            hits = [dict(r) for r in rows]
        return {"trail": trail, "candidate_docs": len(doc_keys), "hits": hits}
    finally:
        conn.close()


def _demo(db: Path) -> None:
    cat = facet_catalog(db)
    print(f"=== FACET CATALOG (dev lake: {db}) ===")
    print(
        f"  doc_type ({len(cat['doc_type'])}): "
        + " ".join(f"{v}({c})" for v, c in cat["doc_type"][:10])
    )
    print("  audience: " + " ".join(f"{v}({c})" for v, c in cat["audience"]))
    print("  packages (app_code, top): " + " ".join(f"{v}({c})" for v, c in cat["app_code"][:10]))
    print("  entity facets: " + " ".join(f"{v}({c})" for v, c in cat["entity_type"]))
    examples = [
        {
            "label": "User Manual · Radiology · 'cancel exam'",
            "doc_type": ["UM"],
            "app": ["RA"],
            "query": "cancel exam",
        },
        {
            "label": "Technical audience · 'web service' (HWSC)",
            "audience": "technical",
            "query": "web service client",
        },
        {
            "label": "Installation/admin · KAAJEE · 'weblogic'",
            "audience": "admin",
            "app": ["KAAJEE"],
            "query": "weblogic",
        },
        {
            "label": "Any doc mentioning FileMan file #60",
            "entity": "fileman_file:60",
            "query": "audit",
        },
    ]
    for ex in examples:
        label = ex.pop("label")
        print(f"\n=== {label} ===")
        res = faceted_search(db, **ex, k=3)
        for step, _, _ in res["trail"]:
            print(f"  {step}")
        for h in res["hits"]:
            sid = h.get("section_id") or h.get("doc_key")
            print(f"     • {sid}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--data-dir", default=os.environ.get("DATA_DIR", str(Path.home() / "data/vdocs-dev"))
    )
    ap.add_argument("--type", action="append")
    ap.add_argument("--app", action="append")
    ap.add_argument("--audience")
    ap.add_argument("--entity")
    ap.add_argument("query", nargs="?")
    a = ap.parse_args()
    db = Path(a.data_dir).expanduser() / "index.db"
    if not (a.type or a.app or a.audience or a.entity or a.query):
        _demo(db)
        return
    res = faceted_search(
        db, doc_type=a.type, app=a.app, audience=a.audience, entity=a.entity, query=a.query
    )
    for step, _, _ in res["trail"]:
        print(step)
    for h in res["hits"]:
        print("  •", h.get("section_id") or h.get("doc_key"))


if __name__ == "__main__":
    main()
