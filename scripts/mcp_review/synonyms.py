"""Fix 3 as built: the synonym table in index.db, measured through the production engines.

MEASUREMENT, not production code. Everything runs the shipped code paths:
- MCP and `vdocs ask`: `server.search.lexical_search`, with the index's synonym table (default)
  and with it turned off (`NO_SYNONYMS`), section level;
- web console: the running vdocs-web's `/api/candidates` (http://127.0.0.1:8765), document level,
  which applies the same table. The web console cannot turn the table off, so its "before" figures
  are the proposal's (fix 1 and 2 built, no table).

Checks, against the proposal's §4 targets:
- the six plain-English keyword searches (axis plain-english): a judged manual on web page 1 (top
  10 documents) and a judged section in the MCP top 10;
- the 24 judged keyword forms: no loss with the table on (MCP rank of the first judged section;
  web rank of the first judged manual);
- the plain-English package names of the registry: a manual of that application on web page 1 /
  a section of it in the MCP top 10;
- application found by its code (typed in capitals): a manual of it in the web top 10;
- patch ids and `file #N` in the MCP top 5: unchanged with the table on.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

import yaml

from vdocs.server import search as S

sys.path.insert(0, str(Path(__file__).parent))
from _common import DB, FILES, provenance  # noqa: E402

WEB = "http://127.0.0.1:8765/api/candidates?q="
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
SEC_DOC = dict(con.execute("SELECT section_id, doc_key FROM doc_sections"))
DOC_APP = dict(con.execute("SELECT doc_key, app_code FROM documents"))
G = yaml.safe_load(open("registries/golden-queries.yaml"))["queries"]
REG = yaml.safe_load(open("registries/search-synonyms.yaml"))
OFF = S.sp.NO_SYNONYMS


def web(q: str) -> list[str]:
    with urllib.request.urlopen(WEB + urllib.parse.quote(q)) as r:
        d = json.load(r)
    return [x["DocKey"] for x in d["Docs"]]


def mcp(q: str, syn: S.sp.Synonyms | None = None, k: int = 15) -> list[str]:
    seen: list[str] = []
    for h in S.lexical_search(DB, q, k=k, synonyms=syn):
        if h["section_id"] not in seen:
            seen.append(h["section_id"])
    return seen


def rank(lst: list[str], rel: set[str]) -> int | None:
    return next((i + 1 for i, d in enumerate(lst) if d in rel), None)


def within(r: int | None, n: int) -> bool:
    return r is not None and r <= n


def main() -> None:
    out: dict = {"provenance": provenance()}
    res: dict[str, list] = defaultdict(list)
    per_plain = {}
    for q in G:
        if not q.get("relevant"):
            continue
        rels = {r["section_id"] for r in q["relevant"]}
        reld = {SEC_DOC[s] for s in rels if s in SEC_DOC}
        kw = q["keywords"]
        w, m_on, m_off = rank(web(kw), reld), rank(mcp(kw), rels), rank(mcp(kw, OFF), rels)
        group = "plain" if q.get("axis") == "plain-english" else "judged"
        res[f"{group}_web"].append(w)
        res[f"{group}_mcp_on"].append(m_on)
        res[f"{group}_mcp_off"].append(m_off)
        if group == "plain":
            per_plain[kw] = {"web_rank": w, "mcp_rank_on": m_on, "mcp_rank_off": m_off}
        elif m_on != m_off:
            res["judged_moved"].append(f"{q['id']}: {m_off}→{m_on}")
    out["plain_english_searches"] = per_plain

    def summ(rs: list, n: int = 10) -> dict:
        return {"n": len(rs), f"top{n}": sum(within(r, n) for r in rs),
                "first": sum(r == 1 for r in rs)}  # fmt: skip

    out["summary"] = {k: summ(v) for k, v in res.items() if k != "judged_moved"}
    out["judged_questions_that_moved_in_the_mcp"] = res["judged_moved"]

    names = [(c, n) for c, ns in REG["packages"].items() for n in ns]
    found = defaultdict(int)
    for code, name in names:
        found["web"] += any(DOC_APP.get(d) == code for d in web(name)[:10])
        sec = mcp(name, k=10)
        found["mcp"] += any(DOC_APP.get(SEC_DOC.get(s, "")) == code for s in sec)
    out["plain_package_names"] = {"names": len(names), "web_page1": found["web"],
                                  "mcp_top10": found["mcp"]}  # fmt: skip

    codes = sorted({c for (c,) in con.execute("SELECT app_code FROM documents WHERE is_latest=1")})
    out["application_by_code_web_top10"] = (
        f"{sum(any(DOC_APP.get(d) == c for d in web(c)[:10]) for c in codes)}/{len(codes)}"
    )

    text: dict[str, str] = defaultdict(str)
    for sid, t in con.execute("SELECT section_id, text FROM chunks"):
        text[sid] += "\n" + t
    ids = defaultdict(int)
    builds = [r[0] for r in con.execute("SELECT canonical_name FROM entities WHERE type='build'")]
    for b in builds:
        ids["patch_on"] += any(b in text[s] for s in mcp(b, k=5))
        ids["patch_off"] += any(b in text[s] for s in mcp(b, OFF, k=5))
    for num, nm in FILES.items():
        pat = re.compile(rf"(#|file\s*#?\s*){re.escape(num)}(?![\d.])", re.I)
        for tag, syn in (("on", None), ("off", OFF)):
            top = mcp(f"file #{num}", syn, k=5)
            ids[f"file_{tag}"] += any(
                nm.lower() in text[s].lower() and pat.search(text[s]) for s in top
            )
    out["identifiers_mcp_top5"] = {
        "patch_ids": f"on {ids['patch_on']}/{len(builds)}, off {ids['patch_off']}/{len(builds)}",
        "file_numbers": f"on {ids['file_on']}/{len(FILES)}, off {ids['file_off']}/{len(FILES)}",
    }
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
