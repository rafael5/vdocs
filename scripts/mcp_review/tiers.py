"""Three tiered-search candidates, measured on top of the keyword-search proposal (fixes 1–3).

MEASUREMENT PROTOTYPE, not production code. Base = ranking.py's base: the prototype reader with the
plain-English package-name table on; the web console requires all words and orders documents by
their best passage, falling back to any word when nothing has all the words; the MCP uses any word
and the MCP's own section ranking.

1. A generated DOCUMENT CARD per latest document, searched as its own small full-text table:
   title + package name/code/namespace + plain-English names + doc type + the package's Monograph
   purpose + the document's level-1/2 headings + the first 80 words of its Introduction/Purpose/
   Overview section + its 10 most distinctive words (frequent in it, rare elsewhere). Combined with
   the full-text order three ways:
   - card_rrf: same matching documents, order = reciprocal-rank fusion of the full-text order and
     the card order (standard RRF, k=60, equal weight; no tuning);
   - card_rrf_union: the same, but a document whose card matches is added even if no passage does;
   - card_tier: the literal first pass: documents whose card matches come first (card order), then
     the remaining full-text matches.
   For the MCP, a section's document card rank is fused with the section's own rank.
2. PSEUDO-RELEVANCE FEEDBACK: take the top results, pick the 10 words they share most distinctively,
   search again with those words OR'd in. Web console: only when the any-word fallback fires. MCP:
   on every query (its default is already any word). Two forms: the expanded search alone, and RRF
   of the first and expanded searches.
3. LINK COUNT as a mild prior. index.db's doc→doc `xref` links are SHARED-ENTITY links (two
   documents mention the same significant entity), not citations, so this measures how connected a
   document is. score × (1 + λ·log(1+links)/log(1+max links)), λ = 0.1 and 0.3.

Test sets as in ranking.py: 24 judged questions as keywords and as sentences; for the web console
also the 238 plain-English package names with the table OFF and, to avoid a circular result, cards
built WITHOUT the plain-English names.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import yaml

from vdocs.server import search as S

sys.path.insert(0, str(Path(__file__).parent))
import ranking as R  # noqa: E402
from _common import provenance  # noqa: E402

P = R.P
con = P.con
TOK = re.compile(r"[a-z0-9]+")
RRF_K = 60

# --- corpus statistics over latest documents --------------------------------------------------
LATEST = sorted(P.LATEST)
doc_tf: dict[str, Counter] = defaultdict(Counter)
chunk_text: dict[str, str] = {}
for cid, dk, text in con.execute(
    "SELECT c.chunk_id, c.doc_key, c.text FROM chunks c JOIN documents d ON d.doc_key = c.doc_key "
    "WHERE d.is_latest = 1"
):
    chunk_text[cid] = text
    doc_tf[dk].update(TOK.findall(text.lower()))
DF: Counter = Counter()
for c in doc_tf.values():
    DF.update(c.keys())
N = len(doc_tf)


def idf(t: str) -> float:
    return math.log(N / DF[t]) if DF.get(t) else 0.0


def distinctive(tf: Counter, n: int, exclude: set[str] = frozenset()) -> list[str]:  # type: ignore[assignment]
    """The n words with the highest tf·idf, ignoring short, numeric, one-document words."""
    cands = (
        (t, c * idf(t))
        for t, c in tf.items()
        if len(t) >= 3 and not t.isdigit() and DF[t] >= 2 and t not in exclude
    )
    return [t for t, _ in sorted(cands, key=lambda x: -x[1])[:n]]


# --- 1. document cards -------------------------------------------------------------------------
def prose(md: str) -> str:
    """Body text only: drop headings, list/table/quote lines (contents lists live there) and
    markdown link targets."""
    keep = [ln for ln in md.splitlines() if ln.strip() and ln.lstrip()[0] not in "#-*|>!["]
    return re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", " ".join(keep))


def build_cards(with_plain_names: bool) -> sqlite3.Connection:
    prof = yaml.safe_load(open("registries/inventory/app-profiles.yaml"))
    purpose = {**(prof.get("fallback_profiles") or {}), **prof["profiles"]}
    labels = dict(con.execute("SELECT code, label FROM vocab WHERE kind = 'doc_type'"))
    heads: dict[str, list[str]] = defaultdict(list)
    for dk, title in con.execute(
        "SELECT doc_key, title FROM doc_sections WHERE is_latest = 1 AND level <= 2 ORDER BY seq"
    ):
        if title and title not in heads[dk]:
            heads[dk].append(title)
    intro: dict[str, str] = {}
    for dk, sid in con.execute(
        "SELECT doc_key, section_id FROM doc_sections WHERE is_latest = 1 AND "
        "(lower(title) LIKE '%introduction%' OR lower(title) LIKE '%purpose%' OR "
        "lower(title) LIKE '%overview%') ORDER BY seq"
    ):
        if dk not in intro:
            txt = "\n".join(t for (t,) in con.execute(
                "SELECT text FROM chunks WHERE section_id = ? ORDER BY part", (sid,)))  # fmt: skip
            words = prose(txt).split()
            if len(words) >= 20:  # a heading-only or contents-only section is skipped
                intro[dk] = " ".join(words[:80])
    mem = sqlite3.connect(":memory:")
    mem.execute(
        "CREATE VIRTUAL TABLE cards USING fts5("
        "doc_key UNINDEXED, title, names, purpose, headings, intro, keywords)"
    )
    meta = con.execute(
        "SELECT doc_key, title, app_code, app_name, pkg_ns, product_full, doc_type FROM documents "
        "WHERE is_latest = 1"
    ).fetchall()
    for dk, title, code, aname, ns, pfull, dtype in meta:
        names = [code or "", ns or "", P.clean(aname), P.clean(pfull)]
        if with_plain_names:
            names += P.PLAIN.get(code, [])
        names = list(dict.fromkeys(n for n in names if n))
        label = labels.get(dtype, dtype or "")
        p = purpose.get(code) or {}
        mem.execute(
            "INSERT INTO cards VALUES (?,?,?,?,?,?,?)",
            (
                dk,
                title if label.lower() in (title or "").lower() else f"{title} — {label}",
                " ; ".join(names),
                " ".join((p.get("purpose") or "").split()),
                " ; ".join(heads.get(dk, [])),
                intro.get(dk, ""),
                " ".join(distinctive(doc_tf[dk], 10)),
            ),
        )
    return mem


CARDS = build_cards(with_plain_names=True)
CARDS_NO_PLAIN = build_cards(with_plain_names=False)


def card_order(match: str, cards: sqlite3.Connection = CARDS) -> list[str]:
    if not match:
        return []
    try:
        rows = cards.execute(
            "SELECT doc_key FROM cards WHERE cards MATCH ? ORDER BY bm25(cards)", (match,)
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [r[0] for r in rows]


def rrf(*orders: list[str], restrict: set[str] | None = None) -> list[str]:
    score: dict[str, float] = defaultdict(float)
    for order in orders:
        kept = [d for d in order if restrict is None or d in restrict]
        for i, d in enumerate(kept):
            score[d] += 1 / (RRF_K + i + 1)
    return sorted(score, key=lambda d: -score[d])


# --- full-text scoring (best passage per document), with link prior ----------------------------
LINKS = Counter(
    dst for (dst,) in con.execute("SELECT dst_id FROM relations WHERE rel = 'xref'")
)  # fmt: skip
MAXLINK = max(LINKS.values())


def doc_scores(match: str) -> dict[str, float]:
    best: dict[str, float] = {}
    if not match:
        return best
    for dk, sc in con.execute(
        "SELECT doc_key, bm25(chunks_fts) FROM chunks_fts WHERE chunks_fts MATCH ?", (match,)
    ):
        if dk in P.LATEST:
            best[dk] = min(sc, best.get(dk, sc))
    return best


def prior(score: float, dk: str, lam: float) -> float:
    return score * (1 + lam * math.log1p(LINKS.get(dk, 0)) / math.log1p(MAXLINK))


def prf_terms(texts: list[str], query: str, n: int = 10) -> list[str]:
    tf: Counter = Counter()
    for t in texts:
        tf.update(TOK.findall(t.lower()))
    return distinctive(tf, n, exclude={t.lower() for t in P.ALNUM.findall(query)})


def expand(match: str, terms: list[str]) -> str:
    return f"({match}) OR " + " OR ".join(f'"{t}"' for t in terms) if terms else match


def feedback_texts_docs(match: str, top_docs: list[str], per_doc: int = 5) -> list[str]:
    rows = con.execute(
        "SELECT doc_key, chunk_id, bm25(chunks_fts) FROM chunks_fts WHERE chunks_fts MATCH ?",
        (match,),
    ).fetchall()
    keep = set(top_docs)
    by_doc: dict[str, list[tuple[float, str]]] = defaultdict(list)
    for dk, cid, sc in rows:
        if dk in keep:
            by_doc[dk].append((sc, cid))
    return [chunk_text.get(cid, "") for v in by_doc.values() for _, cid in sorted(v)[:per_doc]]


def web(q: str, variant: str, table: dict | None = R.TABLE, cards=CARDS) -> list[str]:
    """Document order for one web-console variant (all words, any-word fallback)."""
    m_all = P.reader(q, table, "AND")
    sc = doc_scores(m_all)
    fallback = not sc
    m = m_all
    if fallback:
        m = P.reader(q, table, "OR")
        sc = doc_scores(m)
    text_order = sorted(sc, key=sc.__getitem__)
    if variant == "base":
        return text_order
    if variant.startswith("links_"):
        lam = float(variant.split("_")[1])
        return sorted(sc, key=lambda d: prior(sc[d], d, lam))
    if variant.startswith("card"):
        co = card_order(m, cards)
        if variant == "card_rrf":
            return rrf(text_order, co, restrict=set(text_order))
        if variant == "card_rrf_union":
            return rrf(text_order, co)
        if variant == "card_tier":
            first = [d for d in co if d in P.LATEST]
            return first + [d for d in text_order if d not in set(first)]
    if variant.startswith("prf"):
        if not fallback:
            return text_order
        terms = prf_terms(feedback_texts_docs(m, text_order[:3]), q)
        sc2 = doc_scores(expand(m, terms))
        exp_order = sorted(sc2, key=sc2.__getitem__)
        return exp_order if variant == "prf_alone" else rrf(text_order, exp_order)
    raise ValueError(variant)


def mcp_rows(match: str, k: int = 15) -> list[dict]:
    if not match:
        return []
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(S._SELECT.format(filters=""), (match, k * 3))]
    con.row_factory = None
    return S.sp.demote_restating_parents(rows)


def mcp(q: str, variant: str, k: int = 15) -> list[str]:
    m = P.reader(q, R.TABLE, "OR")
    rows = mcp_rows(m)
    order = [r["section_id"] for r in rows]
    if variant == "base":
        return order[:k]
    if variant.startswith("links_"):
        lam = float(variant.split("_")[1])
        rows = sorted(rows, key=lambda r: prior(r["bm25"], r["doc_key"], lam))
        return [r["section_id"] for r in rows][:k]
    if variant == "card_rrf":
        crank = {d: i for i, d in enumerate(card_order(m))}
        score = {
            r["section_id"]: 1 / (RRF_K + i + 1)
            + (1 / (RRF_K + crank[r["doc_key"]] + 1) if r["doc_key"] in crank else 0)
            for i, r in enumerate(rows)
        }
        return sorted(score, key=lambda s: -score[s])[:k]
    if variant.startswith("prf"):
        texts = [" ".join(chunk_text.get(r["chunk_id"], "") for r in rows[:5])]
        rows2 = mcp_rows(expand(m, prf_terms(texts, q)))
        exp = [r["section_id"] for r in rows2]
        return (exp if variant == "prf_alone" else rrf(order, exp))[:k]
    raise ValueError(variant)


def main() -> None:
    out: dict = {"provenance": provenance(), "rrf_k": RRF_K, "latest_documents": N}
    web_v = ["base", "card_rrf", "card_rrf_union", "card_tier", "prf_alone", "prf_rrf",
             "links_0.1", "links_0.3"]  # fmt: skip
    mcp_v = ["base", "card_rrf", "prf_alone", "prf_rrf", "links_0.1", "links_0.3"]
    res: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    moved: dict[str, list[str]] = defaultdict(list)
    fired = 0
    for qid in R.JUDGED:
        rels = {r["section_id"] for r in R.G[qid]["relevant"]}
        reld = {P.SEC_DOC[s] for s in rels if s in P.SEC_DOC}
        for form, text in (("keywords", R.KW[qid]), ("sentences", R.G[qid]["query"])):
            fired += form == "sentences" and not doc_scores(P.reader(text, R.TABLE, "AND"))
            b = P.rank(web(text, "base"), reld)
            for v in web_v:
                r = P.rank(web(text, v), reld)
                res[f"web_{form}"][v].append(r)
                if r != b:
                    moved[f"web_{form}_{v}"].append(f"{qid}: {b}→{r}")
            b = P.rank(mcp(text, "base"), rels)
            for v in mcp_v:
                r = P.rank(mcp(text, v), rels)
                res[f"mcp_{form}"][v].append(r)
                if r != b:
                    moved[f"mcp_{form}_{v}"].append(f"{qid}: {b}→{r}")
    for code, name in [(c, n) for c, ns in P.PLAIN.items() for n in ns]:
        appdocs = {d for d in P.LATEST if P.DOC_APP.get(d) == code}
        for v in web_v:
            res["web_plain_names_table_off_cards_without_plain_names"][v].append(
                P.rank(web(name, v, table=None, cards=CARDS_NO_PLAIN), appdocs)
            )
    out["results"] = {s: {v: R.summ(rs) for v, rs in vs.items()} for s, vs in res.items()}
    out["web_sentence_fallback_fired"] = f"{fired}/{len(R.JUDGED)}"
    out["judged_questions_that_moved"] = moved
    # cost: one card query vs one full-text query; PRF = two full-text queries + term picking
    t0 = time.perf_counter()
    for qid in R.JUDGED:
        card_order(P.reader(R.KW[qid], R.TABLE, "AND"))
    t1 = time.perf_counter()
    for qid in R.JUDGED:
        web(R.G[qid]["query"], "prf_alone")
    t2 = time.perf_counter()
    for qid in R.JUDGED:
        web(R.G[qid]["query"], "base")
    t3 = time.perf_counter()
    out["ms_per_query"] = {
        "card_search": round((t1 - t0) * 1000 / len(R.JUDGED), 1),
        "web_sentence_base": round((t3 - t2) * 1000 / len(R.JUDGED), 1),
        "web_sentence_prf": round((t2 - t1) * 1000 / len(R.JUDGED), 1),
    }
    ex = CARDS.execute(
        "SELECT title, names, substr(purpose,1,160), substr(headings,1,200), substr(intro,1,160), "
        "keywords FROM cards WHERE doc_key = 'VBECS/vbecs_2_4_1_user_guide'"
    ).fetchone()
    out["example_card"] = dict(
        zip(["title", "names", "purpose", "headings", "intro", "keywords"], ex, strict=True)
    )
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
