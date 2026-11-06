"""Contract conformance: does each front door honour keyword / "exact phrase" / AND OR NOT?

For each construct, a seeded sample of queries built from the corpus's own section titles, run
through (a) the MCP engine (lexical_search, also the Go CLI's parse minus expansion) and (b) the
vdocs-web MATCH string (ftsSanitize, ported verbatim). A result conforms when its section's indexed
text (title + doc_title + section_path + body, all chunks) satisfies the construct. Section-level
checking is lenient to the engines (a phrase in any chunk of the section counts).
"""

from __future__ import annotations

import json
import random
import re
import sqlite3
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

from vdocs.server import search as S

sys.path.insert(0, str(Path(__file__).parent))
from _common import DB, provenance  # noqa: E402

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
TOK = re.compile(r"[a-z0-9]+")
HAY: dict[str, list[str]] = defaultdict(list)
TITLES: list[str] = []
for sid, t, dt, sp, b in con.execute(
    "SELECT section_id, title, doc_title, section_path, body FROM chunks_fts"
):
    if not HAY[sid]:
        HAY[sid].append(" ".join(x or "" for x in (t, dt, sp)))
        TITLES.append(t or "")
    HAY[sid].append(b or "")
NORM = {sid: " " + " ".join(TOK.findall(" ".join(v).lower())) + " " for sid, v in HAY.items()}
DOCFREQ = Counter(w for s in NORM.values() for w in set(s.split()))
N = len(NORM)

STOP = set(
    "a an and are as at be by can do does for from how in is it of on or the to what "
    "when where which who why with not this that use using via into new".split()
)


def has_phrase(sid: str, words: list[str]) -> bool:
    return f" {' '.join(words)} " in NORM.get(sid, "")


def has_word(sid: str, w: str) -> bool:
    return f" {w} " in NORM.get(sid, "")


def web_match(q: str) -> str:  # vdocs-web internal/index/filter.go ftsSanitize, verbatim port
    return " ".join('"' + f.replace('"', '""') + '"' for f in q.split())


def run(match: str, k: int = 10) -> list[str]:
    if not match:
        return []
    sql = f"SELECT section_id FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY {S._BM25} LIMIT ?"
    try:
        return [r[0] for r in con.execute(sql, (match, k))]
    except sqlite3.OperationalError:
        return []


def count(match: str) -> int:
    try:
        return con.execute(
            "SELECT COUNT(DISTINCT section_id) FROM chunks_fts WHERE chunks_fts MATCH ?", (match,)
        ).fetchone()[0]
    except sqlite3.OperationalError:
        return 0


def mcp(q: str, k: int = 10) -> list[str]:
    return [h["section_id"] for h in S.lexical_search(DB, q, k=k)]


def words_of(title: str) -> list[str]:
    ws = TOK.findall(title.lower())
    return [w for w in ws if len(w) >= 3 and w not in STOP and not w.isdigit()]


rng = random.Random(20261106)
titles = [t for t in TITLES if len(words_of(t)) >= 2]
rng.shuffle(titles)


def frac(xs: list[float]) -> float | None:
    return round(statistics.fmean(xs), 3) if xs else None


out: dict = {"provenance": provenance(), "sections_indexed": N}

# --- 1. "exact phrase": every result must contain the words adjacent, in order ----------------
phr = []
for t in titles:
    ws = TOK.findall(t.lower())
    for i in range(len(ws) - 1):
        a, b = ws[i], ws[i + 1]
        if a in STOP or b in STOP or len(a) < 3 or len(b) < 3 or a.isdigit() or b.isdigit():
            continue
        # phrase must be rarer than its words' co-occurrence, else the test is vacuous
        if 20 <= count(f'"{a} {b}"') and count(f'"{a}" AND "{b}"') >= 2 * count(f'"{a} {b}"'):
            phr.append([a, b])
        break
    if len(phr) == 60:
        break
r = defaultdict(list)
for ws in phr:
    q = f'"{" ".join(ws)}"'
    m_hits, m_bare = mcp(q), mcp(" ".join(ws))
    w_hits = run(web_match(q))
    r["mcp_conform"].append(frac([has_phrase(s, ws) for s in m_hits]) or 0)
    r["mcp_quotes_change_nothing"].append(m_hits == m_bare)
    r["web_conform"].append(frac([has_phrase(s, ws) for s in w_hits]) or 0)
    r["native_phrase_sections"].append(count(f'"{" ".join(ws)}"'))
out["phrase"] = {
    "n": len(phr),
    "mcp_top10_containing_phrase": frac(r["mcp_conform"]),
    "mcp_identical_with_and_without_quotes": frac(r["mcp_quotes_change_nothing"]),
    "web_top10_containing_phrase": frac(r["web_conform"]),
    "native_fts5_phrase_median_sections": statistics.median(r["native_phrase_sections"]),
    "examples": [" ".join(p) for p in phr[:6]],
}

# --- 2. AND (bare words): share of results holding every word ----------------------------------
pairs = []
for t in titles[200:]:
    ws = words_of(t)
    a, b = ws[0], ws[-1]
    both = count(f'"{a}" AND "{b}"')
    if a != b and both >= 10 and count(f'"{a}" OR "{b}"') >= 3 * both:
        pairs.append((a, b))
    if len(pairs) == 60:
        break
r = defaultdict(list)
for a, b in pairs:
    for eng, hits in (("mcp", mcp(f"{a} {b}")), ("web", run(web_match(f"{a} {b}")))):
        r[eng].append(frac([has_word(s, a) and has_word(s, b) for s in hits]) or 0)
    typed = mcp(f"{a} AND {b}")
    r["mcp_explicit_AND"].append(frac([has_word(s, a) and has_word(s, b) for s in typed]) or 0)
out["and"] = {
    "n": len(pairs),
    "mcp_top10_with_all_words": frac(r["mcp"]),
    "mcp_top10_with_all_words_when_AND_typed": frac(r["mcp_explicit_AND"]),
    "web_top10_with_all_words": frac(r["web"]),
}

# --- 3. NOT: no result may contain the excluded word -------------------------------------------
nots = []
for a, b in pairs:
    if count(f'"{a}" NOT "{b}"') >= 10:
        nots.append((a, b))
r = defaultdict(list)
for a, b in nots:
    q = f"{a} NOT {b}"
    m, w = mcp(q), run(web_match(q))
    r["mcp_leak"].append(frac([has_word(s, b) for s in m]) or 0)
    r["web_leak"].append(frac([has_word(s, b) for s in w]) or 0)
    r["web_requires_word_not"].append(all(has_word(s, "not") for s in w) if w else True)
    r["native_leak"].append(frac([has_word(s, b) for s in run(f'"{a}" NOT "{b}"')]) or 0)
out["not"] = {
    "n": len(nots),
    "mcp_top10_containing_excluded_word": frac(r["mcp_leak"]),
    "web_top10_containing_excluded_word": frac(r["web_leak"]),
    "web_results_all_contain_the_word_not": frac(r["web_requires_word_not"]),
    "native_fts5_NOT_leak": frac(r["native_leak"]),
    "native_note": "FTS5 NOT excludes per passage; checking per section counts the other "
    "passages of a section that do contain the word, so the native figure is not 0",
}

# --- 4. OR: results for "a OR b" vs the true union --------------------------------------------
r = defaultdict(list)
for a, b in pairs:
    q = f"{a} OR {b}"
    true_union = count(f'"{a}" OR "{b}"')
    r["web_found_share_of_union"].append(count(web_match(q)) / true_union)
    r["mcp_top10_with_either"].append(frac([has_word(s, a) or has_word(s, b) for s in mcp(q)]) or 0)
out["or"] = {
    "n": len(pairs),
    "web_sections_found_as_share_of_true_union": frac(r["web_found_share_of_union"]),
    "mcp_top10_with_either_word": frac(r["mcp_top10_with_either"]),
    "docfreq_of_word_or_pct": round(100 * DOCFREQ["or"] / N, 1),
    "docfreq_of_word_not_pct": round(100 * DOCFREQ["not"] / N, 1),
    "docfreq_of_word_and_pct": round(100 * DOCFREQ["and"] / N, 1),
}

# --- 5. identifiers typed as one quoted string ---------------------------------------------------
ids = [r[0] for r in con.execute("SELECT canonical_name FROM entities WHERE type='build'")]
ids = [i for i in ids if re.fullmatch(r"[A-Z][A-Z0-9]{0,6}\*\d+(\.\d+)?\*\d+", i)]
rng.shuffle(ids)
ids = ids[:150]
r = defaultdict(list)
for i in ids:
    lit = i.lower()

    def ok(s: str, lit: str = lit) -> bool:
        return lit in " ".join(HAY.get(s, [])).lower()

    r["mcp"].append(any(ok(s) for s in mcp(f'"{i}"', k=5)))
    r["web"].append(any(ok(s) for s in run(web_match(f'"{i}"'), k=5)))
out["patch_id_quoted_top5_contains_literal"] = {
    "n": len(ids),
    "mcp": frac(r["mcp"]),
    "web": frac(r["web"]),
}
print(json.dumps(out, indent=1))
