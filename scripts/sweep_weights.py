#!/usr/bin/env python3
"""RR.2 — grid-search the bm25 field weights against the golden key, on the production collection.

The shipped weights (`search_pure.FTS_WEIGHTS`: doc_title 2.5 / title 2.0 / section_path 1.5 /
body 1.0) were fitted on the **451-document development collection**. Production is 2.3× larger,
and inter-document competition — exactly what field weighting balances — is the thing that scaled.
This re-fits them where they are actually used.

It measures the real engine: every candidate is scored by calling `server.search.lexical_search`
with a `weights` override, never by re-implementing its query. Metric math is `baseline_golden`'s,
imported for the same reason.

**Adoption rule (this is the point of the script, not the ranking):** a candidate is only a
CANDIDATE. A win on the mean is not a win — the mean has hidden two questions falling to 0.000 in
this repo before. The script therefore reports, for the best candidates, how many questions
improve, how many regress, and by how much, so a human can apply the per-question rule. With 24
questions, a large single-question gain is a warning about overfitting, not a result.

Usage:
    python scripts/sweep_weights.py [--data-dir DIR] [--k 10] [--out reports/rr2-weight-sweep.md]
"""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
from typing import Any

import yaml
from baseline_golden import _ndcg, _unique_sections  # noqa: E402  (sibling script, same dir)

from vdocs.server import search
from vdocs.server import search_pure as sp

# The grid: each field's weight relative to `body`, which is pinned at 1.0 (only ratios matter to
# bm25 ordering, so sweeping body too would just duplicate points). Kept deliberately coarse and
# explicable — 24 questions cannot support fine tuning, and the shipped point is inside the grid so
# "no change wins" is a reachable, reportable outcome.
GRID: dict[str, tuple[float, ...]] = {
    "doc_title": (1.0, 1.5, 2.0, 2.5, 3.0, 4.0),
    "title": (1.0, 1.5, 2.0, 2.5, 3.0),
    "section_path": (0.5, 1.0, 1.5, 2.0),
}


def _score(
    index_db: Path, spec: dict[str, Any], k: int, weights: dict[str, float]
) -> dict[str, Any]:
    """Per-question nDCG@k for one weight vector (unscoreable questions are already impossible —
    RC.3 gates on that — so every labelled question here contributes)."""
    per: dict[str, float] = {}
    for q in spec["queries"]:
        judged = {r["section_id"]: int(r["grade"]) for r in (q.get("relevant") or [])}
        if not judged:
            continue
        hits = _unique_sections(
            search.lexical_search(index_db, q["query"], k=max(k, 10), weights=weights)
        )
        ranked = [judged.get(h["section_id"], 0) for h in hits]
        per[q["id"]] = _ndcg(ranked, list(judged.values()), k)
    return {"weights": weights, "per_query": per, "mean": sum(per.values()) / len(per)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    from vdocs.config import Settings

    ap.add_argument("--data-dir", default=str(Settings().data_dir))
    ap.add_argument("--queries", default="registries/golden-queries.yaml")
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--out", default="reports/rr2-weight-sweep.md")
    args = ap.parse_args()

    index_db = Path(args.data_dir).expanduser() / "index.db"
    spec = yaml.safe_load(Path(args.queries).read_text(encoding="utf-8"))

    shipped = _score(index_db, spec, args.k, dict(sp.FTS_WEIGHTS))
    results = []
    for dt, ti, sp_w in itertools.product(*GRID.values()):
        w = {"doc_title": dt, "title": ti, "section_path": sp_w, "body": 1.0}
        results.append(shipped if w == dict(sp.FTS_WEIGHTS) else _score(index_db, spec, args.k, w))
    results.sort(key=lambda r: -r["mean"])

    def compare(cand: dict[str, Any]) -> dict[str, Any]:
        better = {q: v for q, v in cand["per_query"].items() if v > shipped["per_query"][q] + 1e-9}
        worse = {q: v for q, v in cand["per_query"].items() if v < shipped["per_query"][q] - 1e-9}
        return {
            "weights": cand["weights"],
            "mean": round(cand["mean"], 4),
            "delta_mean": round(cand["mean"] - shipped["mean"], 4),
            "improved": len(better),
            "regressed": len(worse),
            "worst_regression": round(
                min((v - shipped["per_query"][q] for q, v in worse.items()), default=0.0), 4
            ),
            "regressed_queries": sorted(worse),
        }

    top = [compare(r) for r in results[:10]]
    clean = [t for t in top if t["regressed"] == 0 and t["delta_mean"] > 0]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# RR.2 — bm25 field-weight sweep on the production collection",
        "",
        f"- **Lake:** `{index_db}` · **k:** {args.k} · **grid points:** {len(results)}",
        f"- **Shipped weights** {dict(sp.FTS_WEIGHTS)} → mean nDCG@{args.k} "
        f"**{shipped['mean']:.4f}**",
        f"- **Candidates beating it on the mean AND regressing no question:** {len(clean)}",
        "",
        "A candidate is adoptable only if it regresses **no** question. The mean is reported "
        "first because it is what a sweep optimises, and second because it is not the rule.",
        "",
        f"| rank | doc_title | title | section_path | mean nDCG@{args.k} | Δmean | improved | "
        "regressed | worst regression |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for i, t in enumerate(top, 1):
        w = t["weights"]
        lines.append(
            f"| {i} | {w['doc_title']} | {w['title']} | {w['section_path']} | {t['mean']:.4f} | "
            f"{t['delta_mean']:+.4f} | {t['improved']} | {t['regressed']} | "
            f"{t['worst_regression']:+.4f} |"
        )
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out.with_suffix(".json").write_text(
        json.dumps({"shipped": shipped, "top": top, "clean": clean}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"shipped_mean": round(shipped["mean"], 4), "top": top[:5]}, indent=2))
    print(f"\nwrote {out} and {out.with_suffix('.json')}")


if __name__ == "__main__":
    main()
