#!/usr/bin/env python3
"""Phase 0.4 baseline — lexical retrieval quality on the golden query set.

Runs the **production lexical search** (`server/search.py` → FTS5 + BM25, the only retrieval mode
live today) over `registries/golden-queries.yaml` and reports the §10.5 metrics that every later
phase (semantic, hybrid RRF) is measured against:

    nDCG@k · MRR · recall@k   (over the graded relevance labels)
    redundancy@k              (near-duplicate content among the top-k hits)

The retrieval path is imported (we measure the real engine); the metric math is **inlined** here
as an independent oracle (same discipline as `scripts/audit_gold_cleanup.py`). Deterministic.

Scoring choices (documented so the number is reproducible and comparable):
  * Hits are *chunks*; we reduce each query's ranked hits to the ranked list of unique `section_id`s
    (first appearance wins), since citations resolve at the section level. nDCG/MRR/recall are
    computed over that unique-section list truncated at k.
  * Gain = 2**grade - 1 (grade 3/2/1; unjudged sections contribute 0). IDCG uses the ideal ordering
    of the query's judged grades.
  * recall@k = judged-relevant sections present in the top-k ÷ all judged-relevant for the query.
  * redundancy@k = the design's "no near-duplicate hits" metric (§8). Over the *raw* top-k chunk
    hits, the fraction whose text is a near-duplicate (word-shingle Jaccard ≥ 0.85) of some
    higher-ranked hit in the same top-k. 0 = every hit is novel. Reported for *all* queries
    (including the unlabeled near-dup probe). This counts duplicated *content*, not distinct
    sections of one document (which are legitimately different answers).

Usage:
    python scripts/baseline_golden.py [--data-dir DIR] [--queries FILE] [--k N] [--out REPORT.md]

Writes a markdown report and a sibling JSON (machine-readable), and prints the rollup to stdout.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
from pathlib import Path
from typing import Any

import yaml

from vdocs.server.search import lexical_search


def _dcg(grades: list[int]) -> float:
    """Discounted cumulative gain with exponential gain 2**g - 1, rank discount log2(i+1)."""
    return sum((2**g - 1) / math.log2(i + 2) for i, g in enumerate(grades))


def _ndcg(ranked_grades: list[int], judged_grades: list[int], k: int) -> float:
    dcg = _dcg(ranked_grades[:k])
    idcg = _dcg(sorted(judged_grades, reverse=True)[:k])
    return dcg / idcg if idcg > 0 else 0.0


def _unique_sections(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reduce ranked chunk hits to ranked unique sections (first appearance wins)."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for h in hits:
        sid = h["section_id"]
        if sid not in seen:
            seen.add(sid)
            out.append(h)
    return out


def _shingles(text: str, n: int = 3) -> set[str]:
    """Word n-gram shingles for near-duplicate detection."""
    words = text.split()
    if len(words) < n:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i : i + n]) for i in range(len(words) - n + 1)}


def _near_dup(a: set[str], b: set[str], thresh: float = 0.85) -> bool:
    if not a or not b:
        return False
    inter = len(a & b)
    union = len(a | b)
    return union > 0 and inter / union >= thresh


def _redundancy_at_k(hit_texts: list[str], k: int) -> float:
    """Fraction of the raw top-k chunk hits that near-duplicate a higher-ranked hit (§8)."""
    top = hit_texts[:k]
    if not top:
        return 0.0
    shingled = [_shingles(t) for t in top]
    redundant = 0
    for i in range(1, len(shingled)):
        if any(_near_dup(shingled[i], shingled[j]) for j in range(i)):
            redundant += 1
    return redundant / len(top)


def _section_texts(index_db: Path, section_ids: list[str]) -> dict[str, str]:
    """section_id → concatenated chunk text (all parts, in order)."""
    if not section_ids:
        return {}
    conn = sqlite3.connect(index_db)
    try:
        ph = ",".join("?" for _ in set(section_ids))
        rows = conn.execute(
            f"SELECT section_id, text FROM chunks WHERE section_id IN ({ph}) ORDER BY part",
            list(set(section_ids)),
        ).fetchall()
    finally:
        conn.close()
    out: dict[str, str] = {}
    for sid, text in rows:
        out[sid] = (out.get(sid, "") + " " + text).strip()
    return out


def evaluate(
    data_dir: Path, queries_path: Path, k_override: int | None, *, expand: bool = True
) -> dict[str, Any]:
    index_db = data_dir / "index.db"
    spec = yaml.safe_load(queries_path.read_text(encoding="utf-8"))
    k = k_override or int(spec.get("k", 10))
    # expand=True (default) → SKL-grounded query expansion (S3.4, the merge `entity_skl` table);
    # expand=False → {} disables it (the pre-S3.4 lexical-only baseline, for an apples-to-apples
    # comparison on the same lake).
    expansions = None if expand else {}

    per_query: list[dict[str, Any]] = []
    ndcgs: list[float] = []
    mrrs: list[float] = []
    recalls: list[float] = []
    for q in spec["queries"]:
        judged = {r["section_id"]: int(r["grade"]) for r in (q.get("relevant") or [])}
        raw_hits = lexical_search(index_db, q["query"], k=max(k, 10), expansions=expansions)
        # redundancy is measured over the RAW top-k chunk hits (their text); nDCG/MRR/recall over
        # the unique-section reduction.
        texts = _section_texts(index_db, [h["section_id"] for h in raw_hits[:k]])
        redundancy = _redundancy_at_k([texts.get(h["section_id"], "") for h in raw_hits[:k]], k)
        hits = _unique_sections(raw_hits)
        ranked_ids = [h["section_id"] for h in hits]
        ranked_grades = [judged.get(sid, 0) for sid in ranked_ids]

        entry: dict[str, Any] = {
            "id": q["id"],
            "axis": q.get("axis"),
            "n_judged": len(judged),
            "hits": len(hits),
            "redundancy@k": round(redundancy, 4),
            "top5": [
                {
                    "rank": i + 1,
                    "section_id": h["section_id"],
                    "grade": judged.get(h["section_id"], 0),
                }
                for i, h in enumerate(hits[:5])
            ],
        }
        if judged:  # graded metrics only where we have labels
            ndcg = _ndcg(ranked_grades, list(judged.values()), k)
            rel_ranks = [i + 1 for i, g in enumerate(ranked_grades[:k]) if g >= 1]
            mrr = 1.0 / rel_ranks[0] if rel_ranks else 0.0
            found = sum(1 for sid in ranked_ids[:k] if sid in judged)
            recall = found / len(judged)
            entry.update(
                {"ndcg@k": round(ndcg, 4), "mrr": round(mrr, 4), "recall@k": round(recall, 4)}
            )
            ndcgs.append(ndcg)
            mrrs.append(mrr)
            recalls.append(recall)
        per_query.append(entry)

    n = len(ndcgs)
    rollup = {
        "k": k,
        "labeled_queries": n,
        "total_queries": len(spec["queries"]),
        "mean_ndcg@k": round(sum(ndcgs) / n, 4) if n else None,
        "mean_mrr": round(sum(mrrs) / n, 4) if n else None,
        "mean_recall@k": round(sum(recalls) / n, 4) if n else None,
        "mean_redundancy@k": round(sum(e["redundancy@k"] for e in per_query) / len(per_query), 4)
        if per_query
        else None,
        "mode": "lexical (FTS5+BM25)",
    }
    return {"rollup": rollup, "queries": per_query}


def _render_md(result: dict[str, Any], data_dir: Path) -> str:
    r = result["rollup"]
    lines = [
        "# Phase 0.4 baseline — lexical retrieval quality (golden set)",
        "",
        f"- **Lake:** `{data_dir}`  ·  **mode:** {r['mode']}  ·  **k:** {r['k']}",
        f"- **Labeled queries:** {r['labeled_queries']} of {r['total_queries']}",
        f"- **mean nDCG@{r['k']}:** {r['mean_ndcg@k']}",
        f"- **mean MRR:** {r['mean_mrr']}",
        f"- **mean recall@{r['k']}:** {r['mean_recall@k']}",
        f"- **mean redundancy@{r['k']}:** {r['mean_redundancy@k']} (all queries)",
        "",
        "## Per-query",
        "",
        f"| query | axis | nDCG@{r['k']} | MRR | recall@{r['k']} | redundancy@{r['k']} | hits |",
        "|---|---|---|---|---|---|---|",
    ]
    for e in result["queries"]:
        lines.append(
            f"| {e['id']} | {e.get('axis') or ''} | {e.get('ndcg@k', '—')} | "
            f"{e.get('mrr', '—')} | {e.get('recall@k', '—')} | {e['redundancy@k']} | {e['hits']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    default_dir = os.environ.get("DATA_DIR", str(Path.home() / "data/vdocs-dev"))
    ap.add_argument("--data-dir", default=default_dir)
    ap.add_argument("--queries", default="registries/golden-queries.yaml")
    ap.add_argument("--k", type=int, default=None)
    ap.add_argument("--out", default="reports/baseline-phase0.md")
    ap.add_argument(
        "--no-expand",
        action="store_true",
        help="disable SKL query expansion (the pre-S3.4 lexical-only baseline)",
    )
    args = ap.parse_args()

    data_dir = Path(args.data_dir).expanduser()
    result = evaluate(data_dir, Path(args.queries), args.k, expand=not args.no_expand)

    out_md = Path(args.out)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(_render_md(result, data_dir), encoding="utf-8")
    out_json = out_md.with_suffix(".json")
    out_json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(result["rollup"], indent=2))
    print(f"\nwrote {out_md} and {out_json}")


if __name__ == "__main__":
    main()
