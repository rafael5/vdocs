#!/usr/bin/env python3
"""LF.6 — faceted vs open-ended retrieval on the golden set.

Simulates the focused-search scenario: for each golden query, an expert supplies the facet implied
by the answer, then content-searches within it. The facet is derived from the top-graded relevant
section's document:
  * --facet app   (default)  → package only (app_code) — keeps all doc_types in the package
  * --facet typeapp          → doc_type + app — strictest; can EXCLUDE valid cross-doc-type answers

Reports mean nDCG@10 for open-ended vs faceted, per query, so the trade-off is visible. This is a
*ceiling* measure (the facet is chosen from the answer): how much focused narrowing can buy when the
user knows what they want, not what a blind ranker achieves.

Usage:  python scripts/faceted_eval.py [--data-dir DIR] [--facet app|typeapp] [--out REPORT.md]
"""

from __future__ import annotations

import argparse
import math
import os
import sqlite3
from pathlib import Path
from typing import Any

import yaml

from vdocs.server.facets import faceted_search
from vdocs.server.search import lexical_search


def _ndcg(ranked_grades: list[int], judged_grades: list[int], k: int) -> float:
    """nDCG@k with exponential gain 2**g-1, log2 discount (same oracle as baseline_golden)."""

    def dcg(gs: list[int]) -> float:
        return sum((2**g - 1) / math.log2(i + 2) for i, g in enumerate(gs))

    idcg = dcg(sorted(judged_grades, reverse=True)[:k])
    return dcg(ranked_grades[:k]) / idcg if idcg > 0 else 0.0


def _unique_sections(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ranked hits reduced to ranked unique sections (first appearance wins)."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for h in hits:
        if h["section_id"] not in seen:
            seen.add(h["section_id"])
            out.append(h)
    return out


def evaluate(data_dir: Path, facet: str) -> dict:
    db = data_dir / "index.db"
    conn = sqlite3.connect(db)
    spec = yaml.safe_load((Path("registries/golden-queries.yaml")).read_text(encoding="utf-8"))
    rows, opens, facs = [], [], []
    for q in spec["queries"]:
        judged = {r["section_id"]: int(r["grade"]) for r in (q.get("relevant") or [])}
        if not judged:
            continue
        doc_key = max(judged, key=lambda s: judged[s]).rsplit("/", 1)[0]
        r = conn.execute(
            "SELECT doc_type, app_code FROM documents WHERE doc_key = ?", (doc_key,)
        ).fetchone()
        dt, app = r if r else (None, None)
        oh = _unique_sections(lexical_search(db, q["query"], k=10))
        o = _ndcg([judged.get(h["section_id"], 0) for h in oh], list(judged.values()), 10)
        kw = {"app": [app]} if facet == "app" else {"doc_type": [dt], "app": [app]}
        fr = faceted_search(db, query=q["query"], k=10, **kw)
        fh = _unique_sections(fr["hits"])
        f = _ndcg([judged.get(h["section_id"], 0) for h in fh], list(judged.values()), 10)
        rows.append((q["id"], round(o, 4), round(f, 4), f"{dt}+{app}", fr["candidate_docs"]))
        opens.append(o)
        facs.append(f)
    return {
        "facet": facet,
        "mean_open": round(sum(opens) / len(opens), 4),
        "mean_faceted": round(sum(facs) / len(facs), 4),
        "rows": rows,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--data-dir", default=os.environ.get("DATA_DIR", str(Path.home() / "data/vdocs-dev"))
    )
    ap.add_argument("--facet", choices=["app", "typeapp"], default="app")
    ap.add_argument("--out", default="reports/faceted-eval.md")
    a = ap.parse_args()
    res = evaluate(Path(a.data_dir).expanduser(), a.facet)
    lines = [
        f"# LF.6 faceted vs open-ended (facet={res['facet']})",
        "",
        f"- mean nDCG@10 open-ended: **{res['mean_open']}**",
        f"- mean nDCG@10 faceted:    **{res['mean_faceted']}**",
        "",
        "| query | open | faceted | facet | docs |",
        "|---|---|---|---|---|",
    ]
    lines += [f"| {i} | {o} | {f} | {fc} | {n} |" for i, o, f, fc, n in res["rows"]]
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"open {res['mean_open']}  faceted {res['mean_faceted']}  → wrote {out}")


if __name__ == "__main__":
    main()
