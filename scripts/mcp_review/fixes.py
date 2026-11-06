"""Measurements behind docs/proposals/keyword-search-five-fixes.md.

Everything here is a MEASUREMENT PROTOTYPE, not production code: the query reader and the synonym
seed below exist only to size the proposal's fixes before anything is built.

1. Web ordering on keyword queries: today's title order vs relevance (bm25), weighted vs plain.
2. Web on full-sentence questions: all words (today) vs all-then-any fallback vs any word.
3. A prototype query reader (quotes = phrase; AND/OR/NOT in capitals; identifier-shaped words kept
   whole) at section level, with all-words and any-word defaults, vs today's MCP parse.
4. An application synonym seed generated from documents.app_code/pkg_ns/app_name/product_*.

The keyword forms of the 24 judged questions were written by the reviewer, who knew the answers.
"""

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
from _common import DB, FILES, provenance  # noqa: E402

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)

# The 24 judged golden questions as the keywords a person would type into a search box.
KW = {
    "kids-install-build": "KIDS install build",
    "pharmacy-api-dispense": "pharmacy API dispense",
    "fileman-add-field": "add field data dictionary",
    "rpc-broker-client-call": "RPC Broker client call",
    "mailman-decnet-transmission": "DECnet transmission script",
    "radiology-cancel-exam": "cancel radiology exam",
    "pharmacy-release-signed-order": "release digitally signed order",
    "tiu-unsigned-notes": "unsigned progress notes",
    "vpr-allergy-data": "VPR allergy",
    "lab-file60-audit": "audit laboratory test file",
    "cprs-enter-immunization": "enter immunization CPRS",
    "vbecs-accept-order": "VBECS accept order",
    "hl7-security-keys": "HL7 security keys",
    "fileman-file-200-new-person": "NEW PERSON file",
    "fileman-import-host-file": "import host file",
    "fileman-input-transform-definition": '"input transform"',
    "fileman-blddialog-icr-number": "BLD^DIALOG ICR",
    "quasar-package-wide-variables": "QUASAR package wide variables",
    "hl7-table-0136-values": "HL7 table 0136",
    "kids-backup-transport-global": 'backup "transport global"',
    "hl7-start-tcpip-link": "start TCP/IP logical link",
    "fileman-file-access-security": "file access security",
    "vista-signon-credentials": "sign on access code verify code",
    "fileman-finder-api": "FIND^DIC finder",
    "taskman-monitor": "monitor TaskMan",
}
G = {q["id"]: q for q in yaml.safe_load(open("registries/golden-queries.yaml"))["queries"]}
JUDGED = [qid for qid in G if G[qid].get("relevant")]
SEC_DOC = dict(con.execute("SELECT DISTINCT section_id, doc_key FROM chunks_fts"))
LATEST = {r[0] for r in con.execute("SELECT doc_key FROM documents WHERE is_latest=1")}
TITLE = dict(con.execute("SELECT doc_key, title FROM documents"))
DOC_APP = dict(con.execute("SELECT doc_key, app_code FROM documents"))
TEXT: dict[str, str] = defaultdict(str)
for sid, t in con.execute("SELECT section_id, text FROM chunks ORDER BY section_id, part"):
    TEXT[sid] += "\n" + t


def rel_sections(qid: str) -> set[str]:
    return {r["section_id"] for r in G[qid]["relevant"]}


def rel_docs(qid: str) -> set[str]:
    return {SEC_DOC[s] for s in rel_sections(qid) if s in SEC_DOC}


# --- the three ways of turning text into an FTS5 MATCH
def web_match(q: str) -> str:
    """vdocs-web internal/index/filter.go ftsSanitize, ported verbatim (every field must occur)."""
    return " ".join('"' + f.replace('"', '""') + '"' for f in q.split())


def any_match(q: str) -> str:
    """The same whitespace fields, any of them."""
    return " OR ".join('"' + f.replace('"', '""') + '"' for f in q.split())


WORD = re.compile(r'"[^"]*"?|\S+')
ALNUM = re.compile(r"[A-Za-z0-9]+")


def _clause(word: str, syn: dict[str, str]) -> str | None:
    toks = ALNUM.findall(word)
    if not toks:
        return None
    base = f'"{" ".join(toks)}"'  # a quoted span or an identifier-shaped word is one phrase
    alt = " ".join(ALNUM.findall(syn.get(" ".join(toks).lower(), "")))
    return f'({base} OR "{alt}")' if alt else base


def reader(q: str, syn: dict[str, str] | None = None, default: str = "AND") -> str:
    """PROTOTYPE query reader: quoted text is a phrase, AND/OR/NOT in capitals are operators, and
    any other word becomes one phrase of its alphanumeric runs (so DG*5.3*1029 → "dg 5 3 1029").
    Words with no operator between them are joined by `default`. A synonym key adds its
    alternative as an OR'd phrase; multi-word keys are matched outside existing quotes first."""
    syn = syn or {}
    for key in sorted((k for k in syn if " " in k), key=len, reverse=True):
        parts = re.split(r'("[^"]*")', q)
        q = "".join(
            p if i % 2 else re.sub(rf"(?<!\w){re.escape(key)}(?!\w)", f'"{key}"', p, flags=re.I)
            for i, p in enumerate(parts)
        )
    out: list[str] = []
    pending = default
    for w in WORD.findall(q):
        if w in ("AND", "OR", "NOT"):
            pending = w
            continue
        c = _clause(w, syn)
        if c is None:
            continue
        if not out and pending == "NOT":
            pending = default  # a leading NOT has nothing to subtract from
            continue
        if out:
            out.append(pending)
        out.append(c)
        pending = default
    return " ".join(out)


# --- running a MATCH
PLAIN_BM25 = "bm25(chunks_fts)"


def docs(match: str, expr: str = S._BM25) -> list[str]:
    """Latest documents matching, ordered by their best passage's score (or by title)."""
    if not match:
        return []
    sql = f"SELECT doc_key, {PLAIN_BM25 if expr == 'title' else expr} FROM chunks_fts "
    best: dict[str, float] = {}
    for dk, sc in con.execute(sql + "WHERE chunks_fts MATCH ?", (match,)):
        if dk in LATEST:
            best[dk] = min(sc, best.get(dk, sc))
    if expr == "title":
        return sorted(best, key=lambda d: (TITLE.get(d) or "").lower())
    return sorted(best, key=best.__getitem__)


def sections(match: str, k: int = 15) -> list[str]:
    """Section-level, the MCP's own SELECT + twin demotion, for a given MATCH."""
    if not match:
        return []
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(S._SELECT.format(filters=""), (match, k * 3))]
    con.row_factory = None
    return [r["section_id"] for r in S.sp.demote_restating_parents(rows)[:k]]


def mcp(q: str, k: int = 15) -> list[str]:
    return [h["section_id"] for h in S.lexical_search(DB, q, k=k)]


def rank(lst: list[str], rel: set[str]) -> int | None:
    return next((i + 1 for i, d in enumerate(lst) if d in rel), None)


def summ(rs: list[int | None], zero: int | None = None) -> dict:
    ok = [r for r in rs if r]
    d: dict = {
        "n": len(rs),
        "top10": sum(r <= 10 for r in ok),
        "first": sum(r == 1 for r in ok),
        "mrr": round(sum(1 / r for r in ok) / len(rs), 3),
    }
    if zero is not None:
        d["zero_results"] = zero
    return d


out: dict = {"provenance": provenance(), "judged_questions": len(JUDGED)}

# --- 1. web ordering, keyword queries (document level)
w = defaultdict(list)
best_is_judged = []
for qid in JUDGED:
    q = KW[qid]
    w["title_order"].append(rank(docs(web_match(q), "title"), rel_docs(qid)))
    w["relevance_weighted"].append(rank(docs(web_match(q)), rel_docs(qid)))
    w["relevance_plain_bm25"].append(rank(docs(web_match(q), PLAIN_BM25), rel_docs(qid)))
    w["relevance_with_reader"].append(rank(docs(reader(q)), rel_docs(qid)))
    best: dict[str, tuple[float, str]] = {}
    sql = f"SELECT doc_key, section_id, {S._BM25} FROM chunks_fts WHERE chunks_fts MATCH ?"
    for dk, sid, sc in con.execute(sql, (web_match(q),)):
        if dk in LATEST and (dk not in best or sc < best[dk][0]):
            best[dk] = (sc, sid)
    first = next((d for d in sorted(best, key=lambda d: best[d][0]) if d in rel_docs(qid)), None)
    if first:
        best_is_judged.append(best[first][1] in rel_sections(qid))
out["web_keyword_queries"] = {k: summ(v) for k, v in w.items()}
out["web_best_passage_is_a_judged_section"] = f"{sum(best_is_judged)}/{len(best_is_judged)}"
out["web_keyword_median_documents_matched"] = {
    "all_words": statistics.median(len(docs(web_match(KW[q]))) for q in JUDGED),
    "any_word": statistics.median(len(docs(any_match(KW[q]))) for q in JUDGED),
    "latest_documents": len(LATEST),
}

# --- 2. web, full-sentence questions
s = defaultdict(list)
fired = {"sentences": 0, "keywords": 0}
for qid in JUDGED:
    a, o = docs(web_match(G[qid]["query"])), docs(any_match(G[qid]["query"]))
    s["all_words"].append(rank(a, rel_docs(qid)))
    s["all_then_any_if_empty"].append(rank(a or o, rel_docs(qid)))
    s["any_word"].append(rank(o, rel_docs(qid)))
    fired["sentences"] += not a
    fired["keywords"] += not docs(web_match(KW[qid]))
out["web_sentence_questions"] = {k: summ(v) for k, v in s.items()}
out["web_fallback_would_fire"] = fired

# --- 3. prototype reader vs today's MCP parse (section level)
b = defaultdict(list)
zero: dict[str, int] = defaultdict(int)
for qid in JUDGED:
    for form, text in (("keywords", KW[qid]), ("sentence", G[qid]["query"])):
        for eng, hits in (
            ("today", mcp(text)),
            ("reader_all_words", sections(reader(text))),
            ("reader_any_word", sections(reader(text, default="OR"))),
        ):
            b[f"{form}_{eng}"].append(rank(hits, rel_sections(qid)))
            zero[f"{form}_{eng}"] += not hits
out["section_level"] = {k: summ(v, zero[k]) for k, v in b.items()}

idp = defaultdict(list)
for build in (r[0] for r in con.execute("SELECT canonical_name FROM entities WHERE type='build'")):

    def has(sid: str, lit: str = build) -> bool:
        return lit in TEXT.get(sid, "")

    idp["patch_id_today"].append(any(has(x) for x in mcp(build)[:5]))
    idp["patch_id_reader"].append(any(has(x) for x in sections(reader(build, default="OR"))[:5]))
for num, name in FILES.items():
    pat = re.compile(rf"(#|file\s*#?\s*){re.escape(num)}(?![\d.])", re.I)

    def about(sid: str, n: str = name, p: re.Pattern[str] = pat) -> bool:
        t = TEXT.get(sid, "")
        return n.lower() in t.lower() and bool(p.search(t))

    for q in (f"file #{num}", f"FileMan file #{num}"):
        tag = "file_number_short" if q.startswith("file") else "file_number_long"
        idp[f"{tag}_today"].append(any(about(x) for x in mcp(q)[:5]))
        idp[f"{tag}_reader"].append(any(about(x) for x in sections(reader(q, default="OR"))[:5]))
out["identifiers_found_in_top5"] = {k: f"{sum(v)}/{len(v)}" for k, v in idp.items()}


# --- 4. application synonym seed
def clean(name: str | None) -> str:
    name = re.sub(r"\s*\([^)]*\)", "", name or "")
    return re.sub(r"^[^:]{1,20}:\s*", "", name).strip()


rows = con.execute(
    "SELECT DISTINCT app_code, pkg_ns, app_name, product_abbr, product_full FROM documents "
    "WHERE is_latest=1"
).fetchall()
syn: dict[str, str] = {}
apps: dict[str, str] = {}
for code, ns, aname, pabbr, pfull in rows:
    nm = clean(aname)
    if nm and code:
        apps.setdefault(code, nm)
        for c in {code, ns} - {None, ""}:
            if c.lower() != nm.lower():
                syn.setdefault(c.lower(), nm.lower())
                syn.setdefault(nm.lower(), c.lower())
    if pabbr and clean(pfull) and pabbr.lower() != clean(pfull).lower():
        syn.setdefault(pabbr.lower(), clean(pfull).lower())
        syn.setdefault(clean(pfull).lower(), pabbr.lower())
c = defaultdict(list)
for code, nm in sorted(apps.items()):
    for form, q in (("by_code", code), ("by_name", nm)):
        for eng, m in (("today", web_match(q)), ("with_seed", reader(q, syn))):
            top = docs(m)[:10]
            c[f"{form}_{eng}"].append(any(DOC_APP.get(d) == code for d in top))
out["application_synonym_seed"] = {
    "applications": len(apps),
    "generated_pairs": len(syn),
    "application_found_in_top10": {k: f"{sum(v)}/{len(v)}" for k, v in c.items()},
}
print(json.dumps(out, indent=1))
