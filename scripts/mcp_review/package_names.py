"""Plain-English package names → VistA package name and namespace (keyword-search proposal, fix 3).

MEASUREMENT PROTOTYPE, not production code. The plain-English names below are REVIEWER DRAFTS for
the operator to edit (proposal Appendix B). For each application in the latest corpus they list
what a non-technical searcher might type; each name expands to that application's package name,
code and namespaces, which the producer already holds (documents.app_name / app_code / pkg_ns and
registries/inventory/package-master.yaml). Two Kernel parts that people name on their own
(TaskMan, KIDS) get rows of their own with explicit targets.

Measured, per plain-English name (all 109 applications):
- web console today (all words, title order), with relevance order (fix 1), and with relevance
  order plus the plain-name expansion: is a document of that application on page 1 (top 10)?
- MCP today and with expansion: is a section of that application in the top 10?
- how many documents the web would match without and with expansion (the facet counts).
Regression with the whole table switched on: the 24 judged keyword and sentence questions, and the
patch-id / file-number probes, against the same reader with no table.

Rule kept from the proposal: text the user puts in double quotes is exact and never expanded.

Dropped from the first draft after measuring: "security keys", "sign on", "menus" (Kernel) and
"data dictionary" (FileMan). Every package's manuals use those words, so they name a concept, not
a package. With "security keys" in, the HL7 security-keys question fell from first to tenth on the
web and out of the MCP top 15; with all four out, the judged questions are unchanged.
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

# --- reviewer drafts: application code → plain-English names (operator edits these)
PLAIN: dict[str, list[str]] = {
    "ACKQ": ["audiology", "speech pathology"],
    "ACR": ["outpatient encounter reporting"],
    "ADT": ["admissions", "discharges", "bed control"],
    "AMT": ["blood thinners", "warfarin", "anticoagulation clinic"],
    "ANRV": ["blind rehabilitation", "low vision"],
    "AR/WS": ["ward stock", "restocking"],
    "ASCD": ["service connection", "disability rating"],
    "ASU": ["signing permissions", "cosignature"],
    "CPRS": ["electronic health record", "patient chart", "medical record"],
    "CRHD": ["shift change", "handoff"],
    "DGBT": ["travel pay", "mileage reimbursement"],
    "DGJ": ["incomplete records", "chart deficiencies"],
    "DI": ["database"],
    "DVBA": ["disability exams", "compensation and pension"],
    "EC": ["workload capture", "procedure counts"],
    "ECME": ["pharmacy claims", "prescription insurance claims"],
    "ECX": ["cost accounting", "managerial cost accounting"],
    "EDIS": ["emergency department", "emergency room", "tracking board"],
    "EFR": ["embedded fragments", "shrapnel"],
    "EN": ["equipment maintenance", "work orders", "biomedical engineering"],
    "EPI": ["infectious disease reporting", "disease surveillance"],
    "FB": ["community care payments", "non-VA care", "fee for service"],
    "FFP": ["fugitive felons", "outstanding warrants"],
    "FH": ["dietetics", "diet orders", "meals"],
    "FIM": ["rehabilitation assessment", "functional status"],
    "GEN": ["code sheets"],
    "GMPL": ["patient problems", "diagnosis list"],
    "GMR": ["fluid intake", "fluid balance"],
    "GMRA": ["allergies", "drug allergies", "adverse drug reactions"],
    "GMRC": ["consults", "referrals"],
    "GMRV": ["vital signs", "blood pressure", "pulse"],
    "GMTS": ["patient summary report"],
    "HBPC": ["home care", "home health"],
    "HL7": ["interfaces", "interface messages"],
    "IB": ["billing", "insurance billing", "copayments"],
    "IBD": ["encounter forms", "scannable forms"],
    "IVMB": ["means test", "income verification"],
    "KMPD": ["capacity planning"],
    "KMPR": ["resource usage"],
    "KMPS": ["database growth", "global growth"],
    "KMPV": ["system monitoring", "performance metrics"],
    "LA": ["lab instruments", "instrument interface"],
    "LEDI": ["reference lab", "send-out lab tests"],
    "LR": ["lab", "lab tests", "lab results"],
    "MAG": ["medical images", "scanned documents", "image capture"],
    "MC": ["cardiology", "EKG", "endoscopy"],
    "MD": ["medical devices", "device interface", "dialysis"],
    "MMRS": ["staph infection", "infection control"],
    "MPIF": ["duplicate patients", "patient identity", "ICN"],
    "NCR": ["clozapine monitoring"],
    "NUPA": ["nursing assessments", "nursing documentation"],
    "NUR": ["nurses", "nursing staff"],
    "ONC": ["cancer registry", "tumor registry"],
    "OOPS": ["employee injuries", "workplace accidents"],
    "OR": ["orders", "ordering"],
    "PAIT": ["appointment extract"],
    "PCMM": ["primary care teams", "PACT", "patient panels"],
    "POC": ["point of care testing", "bedside testing", "glucose meters"],
    "PRC": ["purchasing", "procurement", "purchase orders"],
    "PRCA": ["patient debts", "collections", "patient bills"],
    "PRCN": ["equipment requests", "equipment turn-in"],
    "PREA": ["pharmacist medication profile", "medication review"],
    "PRF": ["behavioral flags", "flagged patients"],
    "PRPF": ["patient trust accounts", "personal funds"],
    "PRS": ["payroll", "timekeeping", "time and attendance"],
    "PSA": ["drug inventory", "pharmacy inventory"],
    "PSB": ["bar code scanning", "medication administration", "barcode"],
    "PSD": ["narcotics", "controlled drugs"],
    "PSJ": ["inpatient pharmacy", "unit dose", "IV medications"],
    "PSN": ["drug file", "drug database", "drug classes"],
    "PSO": ["prescriptions", "refills"],
    "PSS": ["pharmacy setup", "drug setup"],
    "PSU": ["drug usage reports", "pharmacy benefits"],
    "PSX": ["mail order pharmacy", "mailed prescriptions"],
    "PX": ["encounters", "visits", "workload"],
    "PXRM": ["reminders", "preventive care reminders"],
    "QAC": ["patient complaints", "compliments"],
    "QAM": ["quality monitoring"],
    "QAO": ["adverse event screening", "quality review"],
    "QAP": ["surveys", "questionnaires"],
    "QMIM": ["credentialing", "incident reporting"],
    "RA": ["x-ray", "imaging exams", "radiology exams"],
    "RMDS": ["nursing home assessment", "long-term care assessment", "minimum data set"],
    "RMPR": ["artificial limbs", "wheelchairs", "home oxygen"],
    "ROEV": ["eye injuries", "vision injuries"],
    "ROR": ["HIV registry", "hepatitis C registry", "case registry"],
    "RT": ["paper records", "chart tracking", "record room"],
    "SD": ["appointments", "clinic schedules"],
    "SPN": ["spinal cord injury"],
    "SQLI": ["SQL", "ODBC"],
    "SR": ["operating room", "surgical cases", "anesthesia"],
    "SRA": ["surgical outcomes", "surgical quality"],
    "TBI": ["brain injury", "concussion"],
    "TIU": ["progress notes", "clinical notes", "discharge summaries"],
    "VALM": ["list screens"],
    "VAQ": ["patient record exchange", "other facility records"],
    "VBECS": ["blood bank", "blood transfusion", "blood products"],
    "VDEF": ["HL7 message extraction"],
    "VPR": ["patient data extract"],
    "WII": ["wounded warriors", "injured service members"],
    "WV": ["mammogram", "pap smear", "maternity"],
    "XM": ["email", "mail messages", "mail groups"],
    "XOBV": ["Java connector", "J2EE"],
    "XQOR": ["protocol menus", "protocols"],
    "XT": ["developer utilities", "routine tools"],
    "XU": ["user accounts"],
    "XWB": ["remote procedure calls", "client server"],
    "YS": ["psychological tests", "mental health assessments", "crisis line"],
    "ZSLOT": ["quick login"],
}
# Kernel parts people name on their own: (application checked, plain names, explicit targets)
PARTS = [
    ("XU", ["background jobs", "scheduled tasks"], ["TaskMan"]),
    ("XU", ["patches", "software installation"],
     ["KIDS", "Kernel Installation and Distribution System", "XPD"]),
]  # fmt: skip

ALNUM = re.compile(r"[A-Za-z0-9]+")
STOP_TARGETS = {"or", "and", "not"}  # never OR an operator word in as a target


def norm(s: str) -> str:
    return " ".join(ALNUM.findall(s)).lower()


def clean(name: str | None) -> str:
    name = re.sub(r"\s*\([^)]*\)", "", name or "")
    return re.sub(r"^[^:]{1,20}:\s*", "", name).strip()


def build_table() -> dict[str, list[str]]:
    """plain name → targets (package name, code, namespaces), from data the producer holds."""
    pm = yaml.safe_load(open("registries/inventory/package-master.yaml"))["packages"]
    rows = con.execute(
        "SELECT app_code, app_name, group_concat(DISTINCT pkg_ns) FROM documents "
        "WHERE is_latest=1 GROUP BY app_code"
    ).fetchall()
    targets: dict[str, list[str]] = {}
    for code, aname, nss in rows:
        t = [clean(aname), code, *(nss or "").split(","), (pm.get(code) or {}).get("pkg_ns") or ""]
        targets[code] = list(dict.fromkeys(x for x in t if norm(x) and norm(x) not in STOP_TARGETS))
    table: dict[str, list[str]] = defaultdict(list)
    for code, names in PLAIN.items():
        for n in names:
            table[norm(n)] += [t for t in targets[code] if t not in table[norm(n)]]
    for _code, names, tg in PARTS:
        for n in names:
            table[norm(n)] += tg
    return dict(table)


# --- prototype reader: quotes exact; capital AND/OR/NOT operators; synonyms on unquoted words
def units(q: str, keys: set[str]) -> list[tuple[str, str]]:
    """Split into ('exact', text) for user-quoted spans, ('op', X), and ('word', text); a run of
    unquoted words that equals a multi-word key becomes one ('word', run)."""
    maxn = max((k.count(" ") + 1 for k in keys), default=1)
    out: list[tuple[str, str]] = []
    for i, part in enumerate(re.split(r'("[^"]*"?)', q)):
        if i % 2:
            out.append(("exact", part))
            continue
        words = part.split()
        j = 0
        while j < len(words):
            if words[j] in ("AND", "OR", "NOT"):
                out.append(("op", words[j]))
                j += 1
                continue
            for n in range(min(maxn, len(words) - j), 0, -1):
                run = words[j : j + n]
                if n == 1 or (norm(" ".join(run)) in keys and not {"AND", "OR", "NOT"} & set(run)):
                    out.append(("word", " ".join(run)))
                    j += n
                    break
    return out


def reader(q: str, table: dict[str, list[str]] | None = None, default: str = "AND") -> str:
    table = table or {}
    out: list[str] = []
    pending = default
    for kind, text in units(q, set(table) if table else set()):
        if kind == "op":
            pending = text
            continue
        toks = ALNUM.findall(text)
        if not toks or (kind == "word" and len(toks) == 1 and len(toks[0]) == 1):
            continue
        clause = f'"{" ".join(toks)}"'
        alts = table.get(norm(text), []) if kind == "word" else []
        alts = [norm(a) for a in alts if norm(a) and norm(a) != norm(text)]
        if alts:
            clause = "(" + " OR ".join([clause, *(f'"{a}"' for a in dict.fromkeys(alts))]) + ")"
        if not out and pending == "NOT":
            pending = default
            continue
        if out:
            out.append(pending)
        out.append(clause)
        pending = default
    return " ".join(out)


# --- running a MATCH (same queries as scripts/mcp_review/fixes.py)
LATEST = {r[0] for r in con.execute("SELECT doc_key FROM documents WHERE is_latest=1")}
TITLE = dict(con.execute("SELECT doc_key, title FROM documents"))
DOC_APP = dict(con.execute("SELECT doc_key, app_code FROM documents"))
SEC_DOC = dict(con.execute("SELECT DISTINCT section_id, doc_key FROM chunks_fts"))


def web_match(q: str) -> str:
    """vdocs-web ftsSanitize, ported verbatim (every whitespace field must occur)."""
    return " ".join('"' + f.replace('"', '""') + '"' for f in q.split())


def docs(match: str, order: str = "relevance") -> list[str]:
    if not match:
        return []
    best: dict[str, float] = {}
    sql = "SELECT doc_key, bm25(chunks_fts) FROM chunks_fts WHERE chunks_fts MATCH ?"
    for dk, sc in con.execute(sql, (match,)):
        if dk in LATEST:
            best[dk] = min(sc, best.get(dk, sc))
    if order == "title":
        return sorted(best, key=lambda d: (TITLE.get(d) or "").lower())
    return sorted(best, key=best.__getitem__)


def sections(match: str, k: int = 15) -> list[str]:
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


def summ(rs: list[int | None]) -> dict:
    ok = [r for r in rs if r]
    return {"n": len(rs), "top10": sum(r <= 10 for r in ok), "first": sum(r == 1 for r in ok),
            "mrr": round(sum(1 / r for r in ok) / len(rs), 3)}  # fmt: skip


def main() -> None:
    table = build_table()
    out: dict = {"provenance": provenance(), "draft": "reviewer drafts, operator to edit"}
    apps_in_corpus = {r[0] for r in con.execute("SELECT app_code FROM documents WHERE is_latest=1")}
    pairs = [(c, n) for c, ns in PLAIN.items() for n in ns] + [
        (c, n) for c, ns, _ in PARTS for n in ns
    ]
    out["coverage"] = {
        "applications_in_latest_corpus": len(apps_in_corpus),
        "applications_with_plain_names": len(set(PLAIN) & apps_in_corpus),
        "missing": sorted(apps_in_corpus - set(PLAIN)),
        "plain_names": len(pairs),
        "table_keys": len(table),
    }

    # 1. each plain-English name: does its application show up?
    hit = defaultdict(list)
    matched = defaultdict(list)
    misses: dict[str, list[str]] = defaultdict(list)
    for code, name in pairs:
        appdocs = {d for d in LATEST if DOC_APP.get(d) == code}
        res = {
            "web_today_title_order": docs(web_match(name), "title")[:10],
            "web_relevance_no_synonyms": docs(web_match(name))[:10],
            "web_relevance_with_synonyms": docs(reader(name, table))[:10],
        }
        for k, top in res.items():
            ok = bool(appdocs & set(top))
            hit[k].append(ok)
            if not ok and k != "web_today_title_order":
                misses[k].append(f"{code}: {name}")
        for k, hits in (
            ("mcp_today", mcp(name, k=10)),
            ("mcp_with_synonyms", sections(reader(name, table, default="OR"), k=10)),
        ):
            ok = any(SEC_DOC.get(s) in appdocs for s in hits)
            hit[k].append(ok)
            if not ok:
                misses[k].append(f"{code}: {name}")
        matched["no_synonyms"].append(len(docs(web_match(name))))
        matched["with_synonyms"].append(len(docs(reader(name, table))))
    out["plain_name_finds_its_application_top10"] = {
        k: f"{sum(v)}/{len(v)}" for k, v in hit.items()
    }
    out["web_documents_matched_median"] = {k: statistics.median(v) for k, v in matched.items()}
    out["web_documents_matched_max"] = {k: max(v) for k, v in matched.items()}
    out["misses"] = misses

    # 2. regression: the whole table on vs off, same reader
    g = {q["id"]: q for q in yaml.safe_load(open("registries/golden-queries.yaml"))["queries"]}
    sys.path.insert(0, str(Path(__file__).parent))
    kw = _keyword_forms()
    judged = [q for q in g if g[q].get("relevant")]
    reg = defaultdict(list)
    changed: list[str] = []
    for qid in judged:
        rels = {r["section_id"] for r in g[qid]["relevant"]}
        reld = {SEC_DOC[s] for s in rels if s in SEC_DOC}
        for form, text in (("keywords", kw[qid]), ("sentence", g[qid]["query"])):
            for tag, tb in (("off", None), ("on", table)):
                reg[f"web_{form}_{tag}"].append(rank(docs(reader(text, tb)), reld))
                reg[f"mcp_{form}_{tag}"].append(rank(sections(reader(text, tb, "OR")), rels))
            if reader(text, table) != reader(text):
                changed.append(f"{qid} ({form})")
    out["regression_judged_questions"] = {k: summ(v) for k, v in reg.items()}
    out["judged_queries_the_table_touches"] = changed

    text: dict[str, str] = defaultdict(str)
    for sid, t in con.execute("SELECT section_id, text FROM chunks ORDER BY section_id, part"):
        text[sid] += "\n" + t
    idp = defaultdict(list)
    for build in (
        r[0] for r in con.execute("SELECT canonical_name FROM entities WHERE type='build'")
    ):
        for tag, tb in (("off", None), ("on", table)):
            top = sections(reader(build, tb, "OR"))[:5]
            idp[f"patch_id_{tag}"].append(any(build in text.get(s, "") for s in top))
    for num, name in FILES.items():
        pat = re.compile(rf"(#|file\s*#?\s*){re.escape(num)}(?![\d.])", re.I)
        for tag, tb in (("off", None), ("on", table)):
            top = sections(reader(f"file #{num}", tb, "OR"))[:5]
            idp[f"file_number_{tag}"].append(
                any(
                    name.lower() in text.get(s, "").lower() and pat.search(text.get(s, ""))
                    for s in top
                )
            )
    out["identifiers_found_in_top5"] = {k: f"{sum(v)}/{len(v)}" for k, v in idp.items()}
    examples = ("blood bank", "blood bank ISBT", '"blood bank"', "background jobs", "email")
    out["examples"] = {q: reader(q, table) for q in examples}
    print(json.dumps(out, indent=1))


def _keyword_forms() -> dict[str, str]:
    """The 24 keyword forms, read from fixes.py's KW literal without running that script."""
    import ast

    src = (Path(__file__).parent / "fixes.py").read_text()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "KW":
            return ast.literal_eval(node.value)
    raise SystemExit("KW not found in fixes.py")


if __name__ == "__main__":
    main()
