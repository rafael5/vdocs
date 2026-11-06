"""Consistency + coverage measurements for the vdocs MCP design review (read-only).

1. Re-derive every number the MCP strings hard-code (live sections, chunkless share, tables).
2. Citation resolvability: does every latest doc's body_path / tables_dir exist on disk?
3. Index coverage of the gold body: share of body.md word tokens that the index also holds.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

from vdocs.server import ids

sys.path.insert(0, str(Path(__file__).parent))
from _common import provenance  # noqa: E402

LAKE = Path.home() / "data/vdocs"
con = sqlite3.connect(f"file:{LAKE / 'index.db'}?mode=ro", uri=True)
con.row_factory = sqlite3.Row
out: dict = {"provenance": provenance()}

# --- 1. hard-coded numbers ---------------------------------------------------------------------
live = con.execute(
    "SELECT COUNT(*) FROM doc_sections s JOIN documents d USING(doc_key) WHERE d.is_latest=1"
).fetchone()[0]
# chunks has NO index on section_id (measured: EXPLAIN = SCAN chunks), so a correlated NOT EXISTS
# is quadratic — collect the chunked section ids once instead.
chunked = {r[0] for r in con.execute("SELECT DISTINCT section_id FROM chunks")}
kinds: Counter = Counter()
nochunk: Counter = Counter()
for sid, kind in con.execute(
    "SELECT s.section_id, s.kind FROM doc_sections s JOIN documents d USING(doc_key) "
    "WHERE d.is_latest=1"
):
    kinds[kind] += 1
    if sid not in chunked:
        nochunk[kind] += 1
chunkless = sum(nochunk.values())
by_kind = [{"kind": k, "n": n, "nochunk": nochunk[k]} for k, n in kinds.most_common()]
tables = sum(1 for _ in (LAKE / "rich-tables").rglob("*.csv"))
table_chunks = con.execute(
    "SELECT COUNT(*) FROM chunks WHERE chunk_id LIKE '%#table-%'"
).fetchone()[0]
out["hardcoded"] = {
    "live_sections": live,
    "chunkless": chunkless,
    "chunkless_pct": round(100 * chunkless / live, 2),
    "by_kind": by_kind,
    "table_csvs": tables,
    "table_chunks_in_index": table_chunks,
}

# --- 2. citation resolvability -----------------------------------------------------------------
docs = con.execute(
    "SELECT doc_key, app_code, pkg_ns, doc_type, bundle_path, is_latest FROM documents"
).fetchall()
res = Counter()
bad = []
for d in docs:
    body = ids.gold_body_relpath(d["app_code"], d["pkg_ns"], d["doc_type"], d["doc_key"])
    tdir = ids.gold_tables_reldir(d["app_code"], d["pkg_ns"], d["doc_type"], d["doc_key"])
    tag = "latest" if d["is_latest"] else "prior"
    ok = (LAKE / body).exists()
    res[f"{tag}_body_{'ok' if ok else 'missing'}"] += 1
    res[f"{tag}_tables_{'ok' if (LAKE / tdir).exists() else 'none'}"] += 1
    if d["is_latest"] and d["bundle_path"]:
        same = body == f"documents/gold/consolidated/{d['bundle_path']}/body.md"
        res[f"latest_bundle_path_{'agrees' if same else 'DISAGREES'}"] += 1
    if d["is_latest"] and not ok:
        bad.append(body)
out["resolvability"] = dict(res)
out["resolvability_bad_sample"] = bad[:5]

# --- 3. index coverage of the gold body --------------------------------------------------------
TOK = re.compile(r"[A-Za-z0-9_]{2,}")
CHROME = re.compile(r"\[↑ Back to Contents\]\([^)]*\)")
tot_body = tot_cov = 0
types_body = types_missing = 0
per_doc = []
missing_terms = Counter()
# one pass over chunks + section headings, grouped by doc_key (chunks_fts.doc_key is UNINDEXED,
# so a per-doc WHERE on the FTS table full-scans it 615 times)
idx_by_doc: dict[str, Counter] = {}
for dk, txt in con.execute("SELECT doc_key, text FROM chunks"):
    idx_by_doc.setdefault(dk, Counter()).update(
        t.lower() for t in TOK.findall(CHROME.sub("", txt or ""))
    )
for dk, title in con.execute("SELECT doc_key, title FROM doc_sections WHERE is_latest=1"):
    idx_by_doc.setdefault(dk, Counter()).update(t.lower() for t in TOK.findall(title or ""))
for d in docs:
    if not d["is_latest"]:
        continue
    body_p = LAKE / ids.gold_body_relpath(d["app_code"], d["pkg_ns"], d["doc_type"], d["doc_key"])
    if not body_p.exists():
        continue
    raw = body_p.read_text(errors="ignore")
    raw = re.sub(
        r"\A---\n.*?\n---\n", "", raw, flags=re.S
    )  # YAML frontmatter is metadata, not content
    body = Counter(t.lower() for t in TOK.findall(CHROME.sub("", raw)))
    idx = idx_by_doc.get(d["doc_key"], Counter())
    b = sum(body.values())
    c = sum(min(n, idx[t]) for t, n in body.items())
    miss = [t for t in body if t not in idx]
    tot_body += b
    tot_cov += c
    types_body += len(body)
    types_missing += len(miss)
    missing_terms.update(miss)
    per_doc.append((d["doc_key"], b, round(c / b, 4) if b else 1.0, len(miss)))
per_doc.sort(key=lambda r: r[2])
out["coverage"] = {
    "docs": len(per_doc),
    "body_tokens": tot_body,
    "token_coverage_pct": round(100 * tot_cov / tot_body, 3),
    "distinct_terms_in_body_absent_from_doc_index": types_missing,
    "distinct_terms_total": types_body,
    "docs_below_99pct": sum(1 for r in per_doc if r[2] < 0.99),
    "docs_below_95pct": sum(1 for r in per_doc if r[2] < 0.95),
    "worst_docs": per_doc[:8],
    "most_common_missing_terms": missing_terms.most_common(25),
}
print(json.dumps(out, indent=1))
