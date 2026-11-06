"""Token cost of the search response under alternative shapes (4 chars/token heuristic)."""

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
from _common import provenance  # noqa: E402

DB = Path.home() / "data/vdocs/index.db"
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
TEXT = defaultdict(str)
for sid, t in con.execute("SELECT section_id, text FROM chunks ORDER BY section_id, part"):
    TEXT[sid] += "\n" + t
CHROME = re.compile(r"\[↑ Back to Contents\]\([^)]*\)")
Q = [q for q in yaml.safe_load(open("registries/golden-queries.yaml"))["queries"]]


def tk(s: str) -> float:
    return len(s) / 4  # ≈ tokens (4 chars/token heuristic)


cur, compact, collapsed_long, read3, sect_tokens = [], [], [], [], []
for q in Q:
    hits = S.lexical_search(DB, q["query"], k=15)
    env = S.search_envelope(hits)
    cur.append(tk(json.dumps(env, indent=1, ensure_ascii=False)))
    # compact: no indent, drop derivable uri/doc_id, body_path once per doc, chrome out of snippet
    docs = {}
    rows = []
    for h in hits:
        docs.setdefault(h["doc_key"], {"title": h["doc_title"], "body_path": h["body_path"]})
        rows.append(
            {
                "section_id": h["section_id"],
                "section_title": h["section_title"],
                "score": h["score"],
                "snippet": CHROME.sub("", h["snippet"]).strip(),
            }
        )
    compact.append(
        tk(json.dumps({"docs": docs, "hits": rows}, ensure_ascii=False, separators=(",", ":")))
    )
    # section-collapsed + ~64-token passage instead of a 16-token snippet
    seen, rows2 = set(), []
    for h in S.lexical_search(DB, q["query"], k=45):
        if h["section_id"] in seen:
            continue
        seen.add(h["section_id"])
        body = CHROME.sub("", TEXT.get(h["section_id"], "")).strip()
        rows2.append(
            {
                "section_id": h["section_id"],
                "section_title": h["section_title"],
                "score": h["score"],
                "passage": body[:260],
            }
        )
        if len(rows2) == 15:
            break
    collapsed_long.append(
        tk(json.dumps({"docs": docs, "hits": rows2}, ensure_ascii=False, separators=(",", ":")))
    )
    secs = [CHROME.sub("", TEXT.get(h["section_id"], "")) for h in hits[:3]]
    read3.append(sum(tk(s) for s in secs))
    sect_tokens += [tk(CHROME.sub("", TEXT.get(h["section_id"], ""))) for h in hits]


def m(v: list[float]) -> int:
    return round(statistics.median(v))


print(
    json.dumps(
        {
            "provenance": provenance(),
            "current_k15_median_tokens": m(cur),
            "compact_same_content": m(compact),
            "collapsed_with_260char_passages": m(collapsed_long),
            "read_top3_sections_full": m(read3),
            "section_tokens_median": m(sect_tokens),
            "section_tokens_p90": round(sorted(sect_tokens)[int(0.9 * len(sect_tokens))]),
        },
        indent=1,
    )
)
