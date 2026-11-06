"""What-if: identifier-aware query parsing (one combined rule), checked for regressions.

Adds an adjacent-token PHRASE clause (single digits kept) for each identifier-shaped span in the
query — M references (TAG^ROUTINE), KIDS patch ids (NS*V*P), and FileMan file numbers after
"file"/"#" — OR'd onto the unchanged production MATCH. Run over the golden key and the three
identifier probe sets.
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
from _common import FILES  # noqa: E402
from surfaces import LAB, metrics, paired  # noqa: E402

DB = Path.home() / "data/vdocs/index.db"
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
TEXT: dict[str, str] = defaultdict(str)
for sid, t in con.execute("SELECT section_id, text FROM chunks ORDER BY section_id, part"):
    TEXT[sid] += "\n" + t
TITLE = dict(con.execute("SELECT section_id, title FROM doc_sections WHERE is_latest=1"))

M_REF = re.compile(r"\${0,2}%?[A-Za-z][A-Za-z0-9]*\^%?[A-Za-z][A-Za-z0-9]*")
PATCH = re.compile(r"\b[A-Za-z][A-Za-z0-9]{0,6}\*\d+(?:\.\d+)?\*\d+\b")
FILENUM = re.compile(r"(?:\bfile\s*\(?#?|#)\s*(\d+(?:\.\d+)?)", re.I)


def id_phrases(q: str) -> list[str]:
    out = []
    for m in M_REF.finditer(q):
        out.append(" ".join(re.findall(r"[A-Za-z0-9]+", m.group(0))))
    for m in PATCH.finditer(q):
        out.append(" ".join(re.findall(r"[A-Za-z0-9]+", m.group(0))))
    for m in FILENUM.finditer(q):
        out.append("file " + " ".join(re.findall(r"\d+", m.group(1))))
    return [p.lower() for p in dict.fromkeys(out) if " " in p]


MAX_CONTEXT_TOKENS = 3  # v2: fire only when the identifier IS the query (known-item lookup)


def id_phrases_v2(q: str) -> list[str]:
    spans = [m.span() for r in (M_REF, PATCH, FILENUM) for m in r.finditer(q)]
    rest = q
    for a, b in sorted(spans, reverse=True):
        rest = rest[:a] + " " + rest[b:]
    if len(re.findall(r"[A-Za-z0-9]{2,}", rest)) > MAX_CONTEXT_TOKENS:
        return []
    skl = S.skl_expansions(str(DB))
    return [
        p for p in id_phrases(q) if not (p.startswith("file ") and p[5:].replace(" ", ".") in skl)
    ]


V2 = "v2" in sys.argv


def idaware(q: str, k: int = 15):
    base = S.sp.fts_match_query(q, S.skl_expansions(str(DB)))
    extra = id_phrases_v2(q) if V2 else id_phrases(q)
    match = " OR ".join([base] + [f'"{p}"' for p in extra]) if base else ""
    if not match:
        return []
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(S._SELECT.format(filters=""), (match, k * 3)).fetchall()]
    con.row_factory = None
    return [S._hit(r) for r in S.sp.demote_restating_parents(rows)[:k]]


def prod(q, k=15):
    return S.lexical_search(DB, q, k=k)


from _common import provenance  # noqa: E402

out: dict = {
    "provenance": provenance(),
    "variant": "v2" if V2 else "v1",
    "golden": {},
    "probes": {},
}
# --- golden key: no regression allowed ---------------------------------------------------------
per = {e: {} for e in ("production", "idaware")}
fired = 0
for q in LAB:
    fired += bool(id_phrases_v2(q["query"]) if V2 else id_phrases(q["query"]))
    per["production"][q["id"]] = metrics(q["id"], [h["section_id"] for h in prod(q["query"])])
    per["idaware"][q["id"]] = metrics(q["id"], [h["section_id"] for h in idaware(q["query"])])
for e, p in per.items():
    out["golden"][e] = {
        k: round(statistics.fmean(m[k] for m in p.values()), 4)
        for k in ("ndcg@10", "mrr", "recall@15", "succ@1", "succ@5")
    }
out["golden"]["queries_where_rule_fired"] = fired
out["golden"]["paired"] = {
    k: paired(per["production"], per["idaware"], k) for k in ("ndcg@10", "recall@15", "mrr")
}


def rank_of(hits, pred):
    return next((i + 1 for i, h in enumerate(hits) if pred(h)), None)


def summ(ranks):
    n = len(ranks)
    ok = [r for r in ranks if r]
    return {
        "n": n,
        "succ@1": round(sum(r == 1 for r in ok) / n, 3),
        "succ@5": round(sum(r <= 5 for r in ok) / n, 3),
        "mrr": round(sum(1 / r for r in ok) / n, 3),
    }  # noqa: E501


# --- probes: M refs, patch ids, file numbers ---------------------------------------------------
API = re.compile(r"(\${0,2}%?[A-Z][A-Z0-9]*\^%?[A-Z][A-Z0-9]*)")
defs: dict[str, set[str]] = defaultdict(set)
for sid, title in TITLE.items():
    if sid in TEXT:
        m = API.match(re.sub(r"^\[+", "", title or ""))
        if m:
            defs[m.group(1)].add(sid)
for eng, fn in (("production", prod), ("idaware", idaware)):
    ra = [rank_of(fn(r), lambda h, t=defs[r]: h["section_id"] in t) for r in sorted(defs)]
    out["probes"].setdefault("api_known_item", {})[eng] = summ(ra)
    builds = [r[0] for r in con.execute("SELECT canonical_name FROM entities WHERE type='build'")]
    rb = [rank_of(fn(b), lambda h, b=b: b in TEXT.get(h["section_id"], "")) for b in builds]
    out["probes"].setdefault("patch_ids", {})[eng] = summ(rb)
    rf = []
    for num, name in FILES.items():
        pat = re.compile(rf"(#|file\s*#?\s*){re.escape(num)}(?![\d.])", re.I)
        rf.append(
            rank_of(
                fn(f"FileMan file #{num}"),
                lambda h, n=name, p=pat: (
                    n.lower() in TEXT.get(h["section_id"], "").lower()
                    and bool(p.search(TEXT.get(h["section_id"], "")))
                ),
            )
        )  # noqa: E501
    out["probes"].setdefault("file_numbers", {})[eng] = summ(rf)
print(json.dumps(out, indent=1))
