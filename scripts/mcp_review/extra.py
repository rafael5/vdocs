"""Extra probes: number-as-phrase what-if, and whether anything in a response predicts failure."""

from __future__ import annotations

import json
import re
import sqlite3
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import yaml

from vdocs.server import search as S

sys.path.insert(0, str(Path(__file__).parent))
LAKE = Path.home() / "data/vdocs"
DB = LAKE / "index.db"
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
TEXT: dict[str, str] = defaultdict(str)
for sid, t in con.execute("SELECT section_id, text FROM chunks ORDER BY section_id, part"):
    TEXT[sid] += "\n" + t


def raw(match, k=15):
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(S._SELECT.format(filters=""), (match, k * 3)).fetchall()]
    con.row_factory = None
    return [S._hit(r) for r in S.sp.demote_restating_parents(rows)[:k]]


from _common import pre_fix2_match, provenance  # noqa: E402

out: dict = {"provenance": provenance()}
# ---- C': FileMan file numbers with the number kept as an adjacent-token phrase -------------
from _common import FILES  # noqa: E402

res = defaultdict(list)
for num, name in FILES.items():
    grp = "decimal" if "." in num else "integer"
    pat = re.compile(rf"(#|file\s*#?\s*){re.escape(num)}(?![\d.])", re.I)

    def about(h, name=name, pat=pat):
        t = TEXT.get(h["section_id"], "")
        return name.lower() in t.lower() and bool(pat.search(t))

    q = f"FileMan file #{num}"
    base = pre_fix2_match(q, S.skl_expansions(str(DB)))
    numtoks = " ".join(re.findall(r"\d+", num))
    hp = raw(f'{base} OR "file {numtoks}"')
    res[grp + "_phrase_succ@5"].append(int(any(about(h) for h in hp[:5])))
    res[grp + "_phrase_prec@5"].append(sum(about(h) for h in hp[:5]) / 5)
out["C_whatif_number_phrase"] = {k: round(statistics.fmean(v), 3) for k, v in res.items()}

# ---- G: does anything in the response separate a useful list from a useless one? ----------
G = {q["id"]: q for q in yaml.safe_load(open("registries/golden-queries.yaml"))["queries"]}
from _common import PARA  # noqa: E402

STOP = set("a an and are as at be by can do does for from how i in is it of on or the to what "
           "when where which who why with you your my there their this that".split())  # fmt: skip
rows = []
for qid, q in G.items():
    if not q.get("relevant"):
        continue
    rel = {r["section_id"] for r in q["relevant"]}
    for text in (q["query"], PARA.get(qid)):
        if not text:
            continue
        hits = S.lexical_search(DB, text, k=15)
        ok = any(h["section_id"] in rel for h in hits)
        terms = {t.lower() for t in re.findall(r"[A-Za-z0-9]{2,}", text)} - STOP
        top = " ".join(TEXT.get(h["section_id"], "") for h in hits[:3]).lower()
        cov = sum(1 for t in terms if re.search(rf"\b{re.escape(t)}\b", top)) / max(1, len(terms))
        rows.append({"ok": ok, "score": hits[0]["score"] if hits else 0.0, "cov": cov})


def auc(rows, key):
    pos = [r[key] for r in rows if r["ok"]]
    neg = [r[key] for r in rows if not r["ok"]]
    pairs = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return round(pairs / (len(pos) * len(neg)), 3) if pos and neg else None


out["G_failure_signal"] = {
    "queries": len(rows),
    "failures": sum(not r["ok"] for r in rows),
    "auc_top1_bm25_score": auc(rows, "score"),
    "auc_query_term_coverage_top3": auc(rows, "cov"),
    "median_cov_ok": statistics.median(r["cov"] for r in rows if r["ok"]),
    "median_cov_fail": statistics.median(r["cov"] for r in rows if not r["ok"]),
}

# ---- H: "NOT" is searched for, not obeyed --------------------------------------------------
h = S.lexical_search(DB, "KIDS NOT install", k=15)
out["H_not_operator"] = {
    "top15_hits_containing_install": sum(
        "install" in TEXT.get(x["section_id"], "").lower() for x in h
    ),  # fmt: skip
}
print(json.dumps(out, indent=1))
