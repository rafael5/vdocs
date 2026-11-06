"""Cross-surface + what-if retrieval measurements on the golden key (read-only).

Surfaces (the real engines): MCP/`ask --json` (Python `lexical_search`), the Go `vdocs search`
binary, and the vdocs-web `/api/candidates` HTTP route. What-if variants run against the same
FTS table (or a scratch porter-stemmed copy) with the production SQL, weights and demotion.
"""

from __future__ import annotations

import json
import random
import sqlite3
import statistics
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

from vdocs.server import search as S
from vdocs.server import search_pure as sp

sys.path.insert(0, str(Path(__file__).parent))

LAKE = Path.home() / "data/vdocs"
DB = LAKE / "index.db"
SCRATCH = (
    Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__import__("tempfile").gettempdir())
)  # porter.db (~180 MB) goes here
GO = Path.home() / "go/bin/vdocs"
WEB = "http://127.0.0.1:8765"
K = 15

Q = yaml.safe_load(open("registries/golden-queries.yaml"))["queries"]
LAB = [q for q in Q if q.get("relevant")]
GRADES = {q["id"]: {r["section_id"]: r["grade"] for r in q["relevant"]} for q in LAB}

STOP = set(
    "a an and are as at be by can do does for from has have how i in is it its my of on or "
    "the their there this to use used using what when where which who why with you your "
    "steps step need needed required".split()
)


# ---------------------------------------------------------------- metrics ---------------------
def dcg(gs):
    import math

    return sum((2**g - 1) / math.log2(i + 2) for i, g in enumerate(gs))


def metrics(qid: str, ranked_sids: list[str], k: int = K) -> dict:
    g = GRADES[qid]
    raw = ranked_sids[:k]
    seen, uniq, dup = set(), [], 0
    for s in raw:
        if s in seen:
            dup += 1
        else:
            seen.add(s)
            uniq.append(s)
    rel_pos = [i for i, s in enumerate(uniq) if s in g]
    mrr = 1 / (rel_pos[0] + 1) if rel_pos else 0.0
    ideal = sorted(g.values(), reverse=True)
    nd10 = dcg([g.get(s, 0) for s in uniq[:10]]) / dcg(ideal[:10])

    def succ(n, min_grade=1):
        return int(any(g.get(s, 0) >= min_grade for s in raw[:n]))

    return {
        "succ@1": succ(1),
        "succ@3": succ(3),
        "succ@5": succ(5),
        "succ@10": succ(10),
        "succ@15": succ(15),
        "ideal@15": succ(15, 3) if 3 in g.values() else None,
        "mrr": mrr,
        "ndcg@10": nd10,
        "recall@10": len({s for s in raw[:10] if s in g}) / len(g),
        "recall@15": len({s for s in raw[:15] if s in g}) / len(g),
        "dup_slots": dup / max(1, len(raw)),
        "unique_sections": len(uniq),
        "n": len(raw),
    }


def rollup(per: dict[str, dict]) -> dict:
    keys = [k for k in next(iter(per.values())) if k not in ("n",)]
    out = {}
    for k in keys:
        vals = [m[k] for m in per.values() if m[k] is not None]
        out[k] = round(statistics.fmean(vals), 4)
    return out


def boot_ci(vals: list[float], n: int = 4000, seed: int = 7) -> tuple[float, float]:
    rnd = random.Random(seed)
    means = sorted(statistics.fmean(rnd.choices(vals, k=len(vals))) for _ in range(n))
    return round(means[int(0.025 * n)], 4), round(means[int(0.975 * n)], 4)


def paired(a: dict, b: dict, key: str) -> dict:
    d = [b[q][key] - a[q][key] for q in a]
    return {
        "delta": round(statistics.fmean(d), 4),
        "ci95": boot_ci(d),
        "wins": sum(x > 1e-9 for x in d),
        "losses": sum(x < -1e-9 for x in d),
    }


# ---------------------------------------------------------------- engines ---------------------
def py_engine(q, k=K, **kw):
    return S.lexical_search(DB, q, k=k, **kw)


def go_engine(q, k=K):
    r = subprocess.run([str(GO), "search", q, "--k", str(k), "--json"], capture_output=True,
                       text=True, timeout=60)  # fmt: skip
    return json.loads(r.stdout)["hits"]


def raw_match(match: str, k: int, table: str = "chunks_fts", con=None):
    """Production SELECT + demotion, with an arbitrary MATCH string (for what-if variants)."""
    own = con is None
    if own:
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    sql = S._SELECT.format(filters="")
    if table != "chunks_fts":
        sql = sql.replace("chunks_fts", table).replace("JOIN documents", "JOIN src.documents")
    rows = [dict(r) for r in con.execute(sql, (match, k * S._OVERFETCH)).fetchall()]
    if own:
        con.close()
    return [S._hit(r) for r in sp.demote_restating_parents(rows)[:k]]


def toks(q):
    return [t for t in sp._TOKEN.findall(q) if len(t) >= 2]


def match_or(ts, exp=True):
    return sp.fts_match_query(" ".join(ts), S.skl_expansions(str(DB)) if exp else None)


def v_stop(q, k=K):
    return raw_match(match_or([t for t in toks(q) if t.lower() not in STOP]), k)


def v_and_then_or(q, k=K):
    ts = [t for t in toks(q) if t.lower() not in STOP]
    hits = raw_match(" AND ".join(f'"{t}"' for t in ts), k) if ts else []
    if len(hits) < k:
        seen = {h["chunk_id"] if "chunk_id" in h else h["uri"] for h in hits}
        for h in raw_match(match_or(ts), k):
            if h["uri"] not in seen:
                hits.append(h)
                seen.add(h["uri"])
    return hits[:k]


def v_prefix(q, k=K):
    ts = [t for t in toks(q) if t.lower() not in STOP]
    parts = [f'"{t[:-2]}"*' if len(t) >= 6 and t.isalpha() else f'"{t}"' for t in ts]
    return raw_match(" OR ".join(parts), k)


def v_collapse(q, k=K):
    hits = py_engine(q, k=k * 3)
    seen, out = set(), []
    for h in hits:
        if h["section_id"] not in seen:
            seen.add(h["section_id"])
            out.append(h)
    return out[:k]


def v_doccap(q, k=K, cap=3):
    hits = v_collapse(q, k=k * 3)
    per, out = {}, []
    for h in hits:
        per[h["doc_key"]] = per.get(h["doc_key"], 0) + 1
        if per[h["doc_key"]] <= cap:
            out.append(h)
    return out[:k]


def build_porter() -> sqlite3.Connection:
    p = SCRATCH / "porter.db"
    con = sqlite3.connect(f"file:{p}", uri=True)
    con.execute(f"ATTACH 'file:{DB}?mode=ro' AS src")
    have = con.execute("SELECT name FROM sqlite_master WHERE name='pfts'").fetchone()
    if not have:
        con.execute(
            "CREATE VIRTUAL TABLE pfts USING fts5(chunk_id UNINDEXED, section_id UNINDEXED, "
            "doc_key UNINDEXED, title, doc_title, section_path, body, "
            "tokenize='porter unicode61')"
        )
        con.execute(
            "INSERT INTO pfts SELECT chunk_id, section_id, doc_key, title, doc_title, "
            "section_path, body FROM src.chunks_fts"
        )
        con.commit()
    return con


def v_porter(q, k=K, con=None):
    return raw_match(match_or(toks(q)), k, table="pfts", con=con)


def v_porter_stop(q, k=K, con=None):
    return raw_match(match_or([t for t in toks(q) if t.lower() not in STOP]), k, "pfts", con)


def web_engine(q):
    url = f"{WEB}/api/candidates?q={urllib.parse.quote(q)}"
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read()) or []


# ---------------------------------------------------------------- run -------------------------
def main() -> None:
    from _common import provenance

    res: dict = {
        "provenance": provenance(),
        "corpus": None,
        "engines": {},
        "paired_vs_mcp": {},
        "web": {},
        "go_overlap": {},
    }
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    res["corpus"] = dict(con.execute("SELECT key, value FROM meta").fetchall())
    pcon = build_porter()
    engines = {
        "mcp_k15 (production)": lambda q: py_engine(q),
        "go_cli_k15": lambda q: go_engine(q),
        "variant_section_collapse": v_collapse,
        "variant_collapse_doccap3": v_doccap,
        "variant_stopwords": v_stop,
        "variant_and_then_or": v_and_then_or,
        "variant_prefix": v_prefix,
        "variant_porter": lambda q: v_porter(q, con=pcon),
        "variant_porter_stopwords": lambda q: v_porter_stop(q, con=pcon),
    }
    per_engine: dict[str, dict] = {}
    raw_hits: dict[str, dict] = {}
    for name, fn in engines.items():
        per, lat, hitlists = {}, [], {}
        for q in LAB:
            t0 = time.perf_counter()
            hits = fn(q["query"])
            lat.append((time.perf_counter() - t0) * 1000)
            hitlists[q["id"]] = hits
            per[q["id"]] = metrics(q["id"], [h["section_id"] for h in hits])
        per_engine[name] = per
        raw_hits[name] = hitlists
        r = rollup(per)
        r["ndcg@10_ci95"] = boot_ci([m["ndcg@10"] for m in per.values()])
        r["recall@15_ci95"] = boot_ci([m["recall@15"] for m in per.values()])
        r["latency_ms_p50"] = round(statistics.median(lat), 1)
        r["latency_ms_p95"] = round(sorted(lat)[int(0.95 * (len(lat) - 1))], 1)
        r["zero_hit_queries"] = sum(1 for h in hitlists.values() if not h)
        res["engines"][name] = r
    base = per_engine["mcp_k15 (production)"]
    for name, per in per_engine.items():
        if name.startswith("mcp"):
            continue
        res["paired_vs_mcp"][name] = {
            k: paired(base, per, k) for k in ("ndcg@10", "recall@15", "mrr", "succ@5")
        }
    # Go vs Python result-list agreement (same query, same k)
    ov = []
    for q in LAB:
        a = [h["section_id"] for h in raw_hits["mcp_k15 (production)"][q["id"]]][:10]
        b = [h["section_id"] for h in raw_hits["go_cli_k15"][q["id"]]][:10]
        ov.append(len(set(a) & set(b)) / max(1, len(set(a) | set(b))))
    res["go_overlap"] = {
        "mean_jaccard_top10": round(statistics.fmean(ov), 3),
        "identical_top10_lists": sum(
            1
            for q in LAB
            if [h["section_id"] for h in raw_hits["mcp_k15 (production)"][q["id"]]][:10]
            == [h["section_id"] for h in raw_hits["go_cli_k15"][q["id"]]][:10]
        ),
    }
    # vdocs-web candidates: doc-level, title-ordered, implicit AND of whitespace tokens
    wz, wn, wfirst, wtop10, mcp_doc10 = 0, [], [], 0, 0
    for q in LAB:
        rel_docs = {s.rsplit("/", 1)[0] for s in GRADES[q["id"]]}
        docs = [d["DocKey"] for d in web_engine(q["query"])]
        wn.append(len(docs))
        if not docs:
            wz += 1
        pos = next((i for i, d in enumerate(docs) if d in rel_docs), None)
        wfirst.append(pos)
        wtop10 += int(pos is not None and pos < 10)
        mdocs = []
        for h in raw_hits["mcp_k15 (production)"][q["id"]]:
            if h["doc_key"] not in mdocs:
                mdocs.append(h["doc_key"])
        mcp_doc10 += int(any(d in rel_docs for d in mdocs[:10]))
    # the same, with stopwords stripped (what a person would type into the box)
    wz2, wtop2 = 0, 0
    for q in LAB:
        rel_docs = {s.rsplit("/", 1)[0] for s in GRADES[q["id"]]}
        kw = " ".join(t for t in toks(q["query"]) if t.lower() not in STOP)
        docs = [d["DocKey"] for d in web_engine(kw)]
        wz2 += int(not docs)
        pos = next((i for i, d in enumerate(docs) if d in rel_docs), None)
        wtop2 += int(pos is not None and pos < 10)
    res["web"] = {
        "queries": len(LAB),
        "nl_zero_result_queries": wz,
        "nl_candidates_median": statistics.median(wn),
        "nl_relevant_doc_in_first10": wtop10,
        "nl_first_relevant_positions": wfirst,
        "keyword_zero_result_queries": wz2,
        "keyword_relevant_doc_in_first10": wtop2,
        "mcp_relevant_doc_in_first10_distinct_docs": mcp_doc10,
    }
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
