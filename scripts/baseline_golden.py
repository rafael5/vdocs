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


def _live_sections(index_db: Path) -> set[str]:
    """Every `is_latest` section id in the corpus — used to tell a retrieval failure (the answer is
    indexed and we did not find it) from scope rot (the answer is not in the corpus at all)."""
    conn = sqlite3.connect(f"file:{index_db}?mode=ro", uri=True)
    try:
        return {r[0] for r in conn.execute("SELECT section_id FROM doc_sections WHERE is_latest=1")}
    finally:
        conn.close()


def _corpus_provenance(index_db: Path) -> dict[str, Any]:
    """What corpus produced this number — the fields that make a report self-identifying.

    `corpus_content_hash` fingerprints the **document set**, not the index build — two indexes over
    the same documents with different chunking carry the same hash (measured: 48,769 vs 57,895
    chunks, one hash). So it answers "same corpus?" and `chunks` answers "same index?"; both are
    recorded because a retrieval number needs both to be comparable."""
    conn = sqlite3.connect(f"file:{index_db}?mode=ro", uri=True)
    try:
        meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
        return {
            "index_db": str(index_db),
            "documents": conn.execute("SELECT count(*) FROM documents").fetchone()[0],
            "chunks": conn.execute("SELECT count(*) FROM chunks").fetchone()[0],
            "corpus_content_hash": meta.get("corpus_content_hash", ""),
        }
    finally:
        conn.close()


def evaluate(
    data_dir: Path, queries_path: Path, k_override: int | None, *, expand: bool = True
) -> dict[str, Any]:
    index_db = data_dir / "index.db"
    if not index_db.is_file():
        # Refuse rather than crash mid-query or silently measure nothing: a missing index is an
        # operator error (wrong --data-dir), and the answer to it is a sentence, not a traceback.
        raise SystemExit(f"no index.db at {index_db} — pass --data-dir <lake> (run `vdocs index`?)")
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
    live_sections = _live_sections(index_db)
    for q in spec["queries"]:
        judged = {r["section_id"]: int(r["grade"]) for r in (q.get("relevant") or [])}
        # SCOPE ROT (2026-08-02): a query whose judged sections are ALL absent from the corpus
        # cannot score above 0 no matter how good retrieval is — it is measuring the label set, not
        # the engine. Six of 24 queries had rotted this way (they cite XOBW/HWSC, KAAJEE and LEX,
        # three applications the admission gate excludes as non-VistA `system_type`), and they were
        # silently dragging the reported mean down by ~13 points. Excluded from the means and
        # reported loudly: a zero you cannot act on is not a measurement.
        unscoreable = bool(judged) and not any(s in live_sections for s in judged)
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
        entry["unscoreable"] = unscoreable
        if judged and not unscoreable:  # graded metrics only where the corpus CAN answer
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
        # PROVENANCE — a retrieval number without its corpus is not a measurement (2026-08-02).
        # The markdown named the lake; the JSON rollup did not, and the rollup is what gets pasted
        # into trackers and compared across runs. Three P6 measurements were quoted as evidence for
        # a change on the PRODUCTION lake while the harness was silently reading a stale 451-doc
        # `~/data/vdocs-dev` (the old default). Every report now carries what it read.
        **_corpus_provenance(index_db),
        "labeled_queries": n,
        "unscoreable_queries": sum(1 for e in per_query if e.get("unscoreable")),
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


def gate_exit_code(rollup: dict[str, Any]) -> int:
    """RC.3 (R‑19's real fix): unscoreable labelled queries are a FAILURE, not a footnote.

    A labelled question whose every judged section is outside the collection measures label rot,
    not the engine — six of them silently depressed every published number by ~13 points before
    2026-08-02, and detection alone let them sit in the key for another day. Non-zero when any
    are present; the caller still writes the full report first, because a red gate that reports
    honest means beats one that refuses to produce a number."""
    return 1 if rollup.get("unscoreable_queries") else 0


def _render_md(result: dict[str, Any], data_dir: Path) -> str:
    r = result["rollup"]
    lines = [
        "# Phase 0.4 baseline — lexical retrieval quality (golden set)",
        "",
        f"- **Lake:** `{data_dir}`  ·  **mode:** {r['mode']}  ·  **k:** {r['k']}",
        f"- **Labeled queries:** {r['labeled_queries']} of {r['total_queries']}"
        + (
            f"  ·  ⚠️ **{r['unscoreable_queries']} UNSCOREABLE** (every judged section is "
            f"outside corpus scope — excluded from the means; re-label or retire them)"
            if r.get("unscoreable_queries")
            else ""
        ),
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
    # Default to the SAME lake every other vdocs command uses (Settings honours $DATA_DIR). It used
    # to default to `~/data/vdocs-dev`, so an operator who had just rebuilt the real lake measured a
    # stale dev copy instead — silently, because the printed rollup named no corpus. That produced
    # three wrong P6 measurements before the provenance fields above caught it.
    from vdocs.config import Settings

    default_dir = str(Settings().data_dir)
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

    code = gate_exit_code(result["rollup"])
    if code:
        n = result["rollup"]["unscoreable_queries"]
        print(
            f"\nGOLDEN KEY: RED — {n} labelled quer{'y is' if n == 1 else 'ies are'} unscoreable "
            "(every judged section is outside this collection). The key is measuring label rot, "
            "not the engine: re-point or retire them in registries/golden-queries.yaml "
            "(see the retired: block there for the recorded precedent)."
        )
        raise SystemExit(code)


if __name__ == "__main__":
    main()
