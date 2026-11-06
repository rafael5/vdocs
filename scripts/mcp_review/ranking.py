"""Simple ranking changes on top of the keyword-search proposal (fixes 1–3), measured.

MEASUREMENT PROTOTYPE, not production code. The base is what the proposal would ship: the prototype
reader from package_names.py with the plain-English package-name table on, all words in the web
console (documents ordered by their best passage), any word in the MCP (sections, the MCP's own
column weights and parent demotion).

Candidates, each one change against that base:
- phrase_bonus: also OR in the bare words as one phrase, so passages holding them together score
  higher. The matching set is unchanged in the web console (a phrase implies all its words).
- title_first: documents whose title holds every query word come first (web only).
- passages_sum3: a document scores the sum of its best three passages instead of its best one
  (web only, and only when all words are required; the any-word fallback keeps the best passage).
- passages_decay: the same three passages weighted 1, 1/2, 1/4. Tried AFTER seeing passages_sum3
  push the one-passage HL7 Package Security Guide off page 1, so it is tuned on this key.
- package_first: when the query names an application (its code or a product abbreviation typed in
  capitals, or its name / plain-English name), that application's results come first.
- section_collapse: one result per section in the MCP (the 2026-11-06 review's free win).

Test sets: the 24 judged questions in keyword form and as sentences (relevant = judged sections, or
their documents for the web console), and the 242 plain-English package names with the table OFF
(relevant = any document of that application), as a larger, cruder check of document ordering.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import yaml

from vdocs.server import search as S

sys.path.insert(0, str(Path(__file__).parent))
import package_names as P  # noqa: E402
from _common import provenance  # noqa: E402

con = P.con
TABLE = P.build_table()
G = {q["id"]: q for q in yaml.safe_load(open("registries/golden-queries.yaml"))["queries"]}
JUDGED = [q for q in G if G[q].get("relevant")]
KW = P._keyword_forms()
APP = P.DOC_APP

# what names an application: codes / namespaces / product abbreviations (capitals), names (any case)
_rows = con.execute(
    "SELECT DISTINCT app_code, pkg_ns, product_abbr, app_name, product_full FROM documents "
    "WHERE is_latest=1"
).fetchall()
CODES: dict[str, set[str]] = defaultdict(set)
NAMES: dict[str, set[str]] = defaultdict(set)
for code, ns, abbr, aname, pfull in _rows:
    for c in (code, ns, abbr):
        if c and c.upper() == c and c not in ("OR", "AND", "NOT"):
            CODES[c].add(code)
    for n in (P.clean(aname), P.clean(pfull)):
        if P.norm(n) and " " in P.norm(n):
            NAMES[P.norm(n)].add(code)
for code, names in P.PLAIN.items():
    for n in names:
        NAMES[P.norm(n)].add(code)
for code, names, tg in P.PARTS:
    for n in [*names, *tg]:
        NAMES[P.norm(n)].add(code)


def named_apps(q: str) -> set[str]:
    out: set[str] = set()
    for w in re.findall(r"[A-Za-z0-9/]+", q):
        out |= CODES.get(w, set())
    nq = f" {P.norm(q)} "
    for n, apps in NAMES.items():
        if f" {n} " in nq:
            out |= apps
    return out


def bare_phrase(q: str) -> str | None:
    """The unquoted, non-operator words as one phrase, when there are at least two."""
    words = [w for w in re.sub(r'"[^"]*"?', " ", q).split() if w not in ("AND", "OR", "NOT")]
    toks = [t for w in words for t in P.ALNUM.findall(w)]
    return " ".join(toks) if len(toks) >= 2 else None


def match(q: str, default: str, phrase: bool, table: dict | None = TABLE) -> str:
    m = P.reader(q, table, default)
    ph = bare_phrase(q) if phrase else None
    return f'({m}) OR "{ph}"' if (m and ph) else m


# --- web console: documents
AGG = {
    "best": lambda v: v[0],
    "sum3": lambda v: sum(v[:3]),
    "decay": lambda v: sum(x / 2**i for i, x in enumerate(v[:3])),
}


def web(
    q: str, *, phrase=False, title=False, agg="best", package=False, table=TABLE, default="AND"
) -> list[str]:
    m = match(q, default, phrase, table)
    if not m:
        return []
    per: dict[str, list[float]] = defaultdict(list)
    for dk, sc in con.execute(
        "SELECT doc_key, bm25(chunks_fts) FROM chunks_fts WHERE chunks_fts MATCH ?", (m,)
    ):
        if dk in P.LATEST:
            per[dk].append(sc)
    score = {d: AGG[agg](sorted(v)) for d, v in per.items()}
    toks = {t.lower() for t in P.ALNUM.findall(re.sub(r"\b(AND|OR|NOT)\b", " ", q)) if len(t) > 1}
    apps = named_apps(q) if package else set()

    def key(d: str) -> tuple:
        ttoks = {t.lower() for t in P.ALNUM.findall(P.TITLE.get(d) or "")}
        return (
            not (title and toks <= ttoks),
            not (package and APP.get(d) in apps),
            score[d],
        )

    return sorted(score, key=key)


# --- MCP: sections
def mcp(q: str, *, phrase=False, package=False, collapse=False, k=15) -> list[str]:
    m = match(q, "OR", phrase)
    if not m:
        return []
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(S._SELECT.format(filters=""), (m, k * 3))]
    con.row_factory = None
    rows = S.sp.demote_restating_parents(rows)
    if package and (apps := named_apps(q)):
        rows = sorted(rows, key=lambda r: r["app_code"] not in apps)  # stable: keeps score order
    out: list[str] = []
    for r in rows:
        if collapse and r["section_id"] in out:
            continue
        out.append(r["section_id"])
    return out[:k]


def summ(rs: list[int | None]) -> dict:
    ok = [r for r in rs if r]
    return {"n": len(rs), "top10": sum(r <= 10 for r in ok), "first": sum(r == 1 for r in ok),
            "mrr": round(sum(1 / r for r in ok) / len(rs), 3)}  # fmt: skip


def main() -> None:
    out: dict = {"provenance": provenance()}
    web_variants = {
        "base": {},
        "phrase_bonus": {"phrase": True},
        "title_first": {"title": True},
        "passages_sum3": {"agg": "sum3"},
        "passages_decay": {"agg": "decay"},
        "package_first": {"package": True},
    }
    mcp_variants = {
        "base": {},
        "phrase_bonus": {"phrase": True},
        "package_first": {"package": True},
        "section_collapse": {"collapse": True},
    }
    res: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    moved: dict[str, list[str]] = defaultdict(list)
    for qid in JUDGED:
        rels = {r["section_id"] for r in G[qid]["relevant"]}
        reld = {P.SEC_DOC[s] for s in rels if s in P.SEC_DOC}
        for form, text in (("keywords", KW[qid]), ("sentences", G[qid]["query"])):

            def web_with_fallback(kw: dict, text: str = text) -> list[str]:
                if hits := web(text, **kw):
                    return hits  # the proposal's any-word fallback keeps the best passage:
                return web(text, **{**kw, "agg": "best"}, default="OR")

            base_w = P.rank(web_with_fallback({}), reld)
            for name, kw in web_variants.items():
                r = P.rank(web_with_fallback(kw), reld)
                res[f"web_{form}"][name].append(r)
                if name != "base" and r != base_w:
                    moved[f"web_{form}_{name}"].append(f"{qid}: {base_w}→{r}")
            base_m = P.rank(mcp(text), rels)
            for name, kw in mcp_variants.items():
                r = P.rank(mcp(text, **kw), rels)
                res[f"mcp_{form}"][name].append(r)
                if name != "base" and r != base_m:
                    moved[f"mcp_{form}_{name}"].append(f"{qid}: {base_m}→{r}")
    for code, name in [(c, n) for c, ns in P.PLAIN.items() for n in ns]:
        appdocs = {d for d in P.LATEST if APP.get(d) == code}
        for vname, kw in web_variants.items():
            res["web_plain_names_table_off"][vname].append(
                P.rank(web(name, table=None, **kw), appdocs)
            )
    out["results"] = {
        s: {v: summ(rs) for v, rs in vs.items()} for s, vs in res.items()
    }  # fmt: skip
    out["judged_questions_that_moved"] = moved
    out["named_apps_examples"] = {
        KW[q]: sorted(named_apps(KW[q])) for q in JUDGED if named_apps(KW[q])
    }
    out["note"] = (
        "24 judged questions: one question moving is 1/24 of a count and up to ~0.04 of MRR; "
        "read small differences as noise."
    )
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
