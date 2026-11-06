"""Adversarial probe sets against the production search engine (the MCP `search` path).

Each probe class has an automatically-derived or hand-verified ground truth; relevance is judged
by exact containment in the hit section's indexed text (or its title), never by the engine.
"""

from __future__ import annotations

import json
import re
import sqlite3
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from vdocs.server import search as S

sys.path.insert(0, str(Path(__file__).parent))
from _common import FILES, PARA, provenance  # noqa: E402

LAKE = Path.home() / "data/vdocs"
DB = LAKE / "index.db"
K = 15
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)

TEXT: dict[str, str] = defaultdict(str)
for sid, t in con.execute("SELECT section_id, text FROM chunks ORDER BY section_id, part"):
    TEXT[sid] += "\n" + t
TITLE = dict(con.execute("SELECT section_id, title FROM doc_sections WHERE is_latest=1"))
APP = dict(con.execute("SELECT doc_key, app_code FROM documents"))
NS = dict(con.execute("SELECT doc_key, pkg_ns FROM documents"))


def search(q, k=K, **kw):
    return S.lexical_search(DB, q, k=k, **kw)


def raw(match, k=K):
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(S._SELECT.format(filters=""), (match, k * 3)).fetchall()]
    con.row_factory = None
    return [S._hit(r) for r in S.sp.demote_restating_parents(rows)[:k]]


def rank_of(hits, pred):
    for i, h in enumerate(hits):
        if pred(h):
            return i + 1
    return None


def summarise(ranks, n=None):
    n = n or len(ranks)
    ok = [r for r in ranks if r]
    return {
        "n": n,
        "succ@1": round(sum(r == 1 for r in ok) / n, 3),
        "succ@5": round(sum(r <= 5 for r in ok) / n, 3),
        "succ@15": round(len(ok) / n, 3),
        "mrr": round(sum(1 / r for r in ok) / n, 3),
    }


out: dict = {"provenance": provenance()}

# ---- A. M API known-item: the section that DEFINES an API, queried by its name -------------
API = re.compile(r"(\${0,2}%?[A-Z][A-Z0-9]*\^%?[A-Z][A-Z0-9]*)")
defs: dict[str, set[str]] = defaultdict(set)
for sid, title in TITLE.items():
    if sid not in TEXT:
        continue
    m = API.match(re.sub(r"^\[+", "", title or ""))
    if m:
        defs[m.group(1)].add(sid)
apis = sorted(defs)
ra, ra_nl, ra_phrase = [], [], []
fails = []
for ref in apis:
    target = defs[ref]
    hits = search(ref)
    r = rank_of(hits, lambda h: h["section_id"] in target)
    ra.append(r)
    if not r and len(fails) < 8:
        fails.append({"ref": ref, "top1": hits[0]["section_title"][:60] if hits else None})
    ra_nl.append(rank_of(search(f"What does {ref} do and what are its input parameters?"),
                         lambda h: h["section_id"] in target))  # fmt: skip
    # what-if: an M-reference-aware query adds the ref as one adjacent-token PHRASE clause
    toks = re.findall(r"[A-Za-z0-9]+", ref)
    base = S.sp.fts_match_query(ref, S.skl_expansions(str(DB)))
    ra_phrase.append(rank_of(raw(f'{base} OR "{" ".join(toks)}"'),
                             lambda h: h["section_id"] in target))  # fmt: skip
out["A_api_known_item"] = {
    "distinct_apis": len(apis),
    "query_is_ref": summarise(ra),
    "query_is_question": summarise(ra_nl),
    "whatif_ref_phrase_clause": summarise(ra_phrase),
    "sample_failures": fails,
}

# ---- B. KIDS patch/build ids (DG*5.3*1029): single-digit parts are dropped from the query ---
builds = [r[0] for r in con.execute("SELECT canonical_name FROM entities WHERE type='build'")]
rb, rb_phrase, pb, pb_phrase = [], [], [], []
for b in builds:

    def contains(h, b=b):
        return b in TEXT.get(h["section_id"], "")

    hits = search(b)
    rb.append(rank_of(hits, contains))
    pb.append(sum(contains(h) for h in hits[:5]) / 5)
    toks = re.findall(r"[A-Za-z0-9]+", b)
    hp = raw(f'"{" ".join(toks)}"')
    rb_phrase.append(rank_of(hp, contains))
    pb_phrase.append(sum(contains(h) for h in hp[:5]) / 5)
out["B_patch_ids"] = {
    "n": len(builds),
    "production": summarise(rb) | {"precision@5": round(statistics.fmean(pb), 3)},
    "whatif_phrase": summarise(rb_phrase) | {"precision@5": round(statistics.fmean(pb_phrase), 3)},
}

# ---- C. FileMan files by NUMBER vs by NAME (relevance = the hit text names the file) --------
cres = {"integer": defaultdict(list), "decimal": defaultdict(list)}
for num, name in FILES.items():
    grp = "decimal" if "." in num else "integer"
    pat = re.compile(rf"(#|file\s*#?\s*){re.escape(num)}(?![\d.])", re.I)

    def about(h, name=name, pat=pat):
        t = TEXT.get(h["section_id"], "")
        return name.lower() in t.lower() and bool(pat.search(t))

    for label, q in (("by_number", f"FileMan file #{num}"), ("by_name", f"{name} file")):
        hits = search(q)
        cres[grp][label + "_succ@5"].append(int(any(about(h) for h in hits[:5])))
        cres[grp][label + "_prec@5"].append(sum(about(h) for h in hits[:5]) / 5)
out["C_fileman_numbers"] = {
    g: {k: round(statistics.fmean(v), 3) for k, v in d.items()} | {"n": len(d["by_name_succ@5"])}
    for g, d in cres.items()
}

# ---- D. application codes / namespaces as queries -------------------------------------------
apps = con.execute(
    "SELECT app_code, MIN(app_name), MIN(pkg_ns) FROM documents WHERE is_latest=1 "
    "AND app_name <> '' GROUP BY app_code"
).fetchall()
dres = defaultdict(list)
short = []
for code, name, ns in apps:
    h = search(code)
    p = sum(APP.get(x["doc_key"]) == code for x in h[:5]) / 5 if h else 0.0
    dres["code_prec@5"].append(p)
    if len(code) <= 2:
        short.append((code, round(p, 2), len(h)))
    hn = search(name)
    dres["name_prec@5"].append(sum(APP.get(x["doc_key"]) == code for x in hn[:5]) / 5 if hn else 0)
    a = {x["doc_key"] for x in h}
    b = {x["doc_key"] for x in hn}
    dres["code_vs_name_doc_jaccard"].append(len(a & b) / max(1, len(a | b)))
out["D_app_codes"] = {k: round(statistics.fmean(v), 3) for k, v in dres.items()} | {
    "n_apps": len(apps),
    "two_letter_codes(code, prec@5, hits)": short,
}
# the namespace "OR" (CPRS) is also the FTS5 keyword / English word "or"
h = search("OR namespace routines")
out["D_or_namespace"] = {"top5_pkg_ns": [NS.get(x["doc_key"]) for x in h[:5]]}

# ---- E. paraphrase robustness: golden questions re-worded without their key nouns -----------
import yaml  # noqa: E402

G = {q["id"]: q for q in yaml.safe_load(open("registries/golden-queries.yaml"))["queries"]}


def golden_metrics(qid, hits):
    g = {r["section_id"]: r["grade"] for r in G[qid]["relevant"]}
    ids = [h["section_id"] for h in hits]
    first = next((i + 1 for i, s in enumerate(ids) if s in g), None)
    return {"succ@15": int(first is not None), "rr": 1 / first if first else 0.0,
            "recall@15": len(set(ids) & set(g)) / len(g)}  # fmt: skip


orig, para = [], []
for qid, p in PARA.items():
    orig.append(golden_metrics(qid, search(G[qid]["query"])))
    para.append(golden_metrics(qid, search(p)))


def mean(rows, k):
    return round(statistics.fmean(r[k] for r in rows), 3)


out["E_paraphrase"] = {
    "n": len(PARA),
    "original": {k: mean(orig, k) for k in ("succ@15", "rr", "recall@15")},
    "paraphrased": {k: mean(para, k) for k in ("succ@15", "rr", "recall@15")},
}

# ---- F. syntax the user may assume works ---------------------------------------------------
f = {}
for a, b in (('"input transform"', "input transform"), ("KIDS NOT install", "KIDS install"),
             ("FIND^DIC", "FIND DIC"), ("$$GET1^DIQ", "GET1 DIQ")):  # fmt: skip
    ha = [h["section_id"] for h in search(a)]
    hb = [h["section_id"] for h in search(b)]
    f[f"{a!r} vs {b!r}"] = "identical results" if ha == hb else "different"
out["F_operator_syntax"] = f
long_q = " ".join(G["kids-install-build"]["notes"].split()[:180])
import time  # noqa: E402

t0 = time.perf_counter()
search(long_q)
out["F_long_query_ms"] = round((time.perf_counter() - t0) * 1000, 1)

json.dump(out, sys.stdout, indent=1)
