"""MCP protocol-level measurements: drive the real `vdocs serve-mcp` over stdio (read-only)."""

from __future__ import annotations

import json
import random
import sqlite3
import statistics
import subprocess
import time
from pathlib import Path

import yaml

LAKE = Path.home() / "data/vdocs"
DB = LAKE / "index.db"
VDOCS = "/home/rafael/projects/vdocs/.venv/bin/vdocs"


class Client:
    def __init__(self):
        self.p = subprocess.Popen([VDOCS, "serve-mcp"], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, text=True, bufsize=1)  # fmt: skip
        self.n = 0

    def call(self, method, params=None, notify=False):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        if not notify:
            self.n += 1
            msg["id"] = self.n
        t0 = time.perf_counter()
        self.p.stdin.write(json.dumps(msg) + "\n")
        self.p.stdin.flush()
        if notify:
            return None, 0.0, 0
        line = self.p.stdout.readline()
        ms = (time.perf_counter() - t0) * 1000
        return json.loads(line), ms, len(line)

    def tool(self, name, args):
        r, ms, n = self.call("tools/call", {"name": name, "arguments": args})
        res = r.get("result") or {}
        text = (res.get("content") or [{}])[0].get("text", "")
        return text, res.get("isError"), ms, r


def tok(s: str) -> int:
    return round(len(s) / 4)  # ≈ tokens (4 chars/token heuristic — no tokenizer offline)


def main() -> None:
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    from _common import provenance

    out: dict = {"provenance": provenance()}
    c = Client()
    hello = {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "probe", "version": "0"},
    }
    init, ms, n = c.call("initialize", hello)
    c.call("notifications/initialized", notify=True)
    r = init["result"]
    out["negotiation"] = {
        "requested": "2025-06-18",
        "returned": r["protocolVersion"],
        "capabilities": r["capabilities"],
        "instructions_tokens": tok(r.get("instructions", "")),
    }
    tl, _, n = c.call("tools/list")
    tools = tl["result"]["tools"]
    out["tools_list"] = {
        "tokens": tok(json.dumps(tools)),
        "tools": [t["name"] for t in tools],
        "have_annotations": [t["name"] for t in tools if "annotations" in t],
        "have_outputSchema": [t["name"] for t in tools if "outputSchema" in t],
        "have_title": [t["name"] for t in tools if "title" in t],
        "params_without_description": [
            f"{t['name']}.{p}"
            for t in tools
            for p, s in t["inputSchema"].get("properties", {}).items()
            if "description" not in s
        ],
    }
    o, _, ms, _ = c.tool("orientation", {})
    out["orientation"] = {"tokens": tok(o), "ms": round(ms, 1)}
    for m in ("resources/list", "resources/templates/list", "prompts/list"):
        rr, _, _ = c.call(m)
        out.setdefault("unsupported_methods", {})[m] = rr.get("error", {}).get("code")

    # --- search over the golden queries at the default k --------------------------------------
    Q = [q for q in yaml.safe_load(open("registries/golden-queries.yaml"))["queries"]]
    lat, toks, snip_share, chrome, per_hit, snippet_chars, dup_body = [], [], [], 0, [], [], []
    nhits = 0
    first_hits = []
    for q in Q:
        text, err, ms, _ = c.tool("search", {"query": q["query"]})
        lat.append(ms)
        toks.append(tok(text))
        env = json.loads(text)
        hits = env["hits"]
        nhits += len(hits)
        if hits:
            first_hits.append(hits[0]["section_id"])
            sn = sum(len(h["snippet"]) for h in hits)
            snip_share.append(sn / len(text))
            per_hit.append(len(text) / len(hits))
            for h in hits:
                snippet_chars.append(len(h["snippet"]))
                chrome += "Back to Contents" in h["snippet"]
                # bytes spent on fields derivable from others (uri from section_id, doc_id from
                # doc_key, body_path repeated per doc)
            derivable = sum(len(h["uri"]) + len(h["doc_id"]) for h in hits)
            dup_body.append(derivable / len(text))
    out["search"] = {
        "queries": len(Q),
        "latency_ms_p50": round(statistics.median(lat), 1),
        "latency_ms_p95": round(sorted(lat)[int(0.95 * (len(lat) - 1))], 1),
        "response_tokens_mean": round(statistics.fmean(toks)),
        "response_tokens_max": max(toks),
        "tokens_per_hit": round(statistics.fmean(per_hit) / 4),
        "snippet_share_of_response_bytes": round(statistics.fmean(snip_share), 3),
        "snippet_chars_median": statistics.median(snippet_chars),
        "snippets_with_nav_chrome": f"{chrome}/{nhits}",
        "derivable_field_share_of_bytes(uri+doc_id)": round(statistics.fmean(dup_body), 3),
    }

    # --- lookup: section (chunked + chunkless), doc, entity; latency of the chunk probe ------
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rnd = random.Random(11)
    sids = [r[0] for r in con.execute(
        "SELECT section_id FROM doc_sections s JOIN documents d USING(doc_key) WHERE d.is_latest=1"
    )]  # fmt: skip
    sample = rnd.sample(sids, 30)
    lk = []
    has_text_field_text = 0
    for sid in sample:
        text, err, ms, _ = c.tool("lookup", {"kind": "section", "key": sid})
        lk.append(ms)
        d = json.loads(text)
        row = d["rows"][0]
        has_text_field_text += int(any(k in row for k in ("text", "body")))
    out["lookup_section"] = {
        "latency_ms_p50": round(statistics.median(lk), 1),
        "latency_ms_p95": round(sorted(lk)[int(0.95 * 29)], 1),
        "returns_section_text": has_text_field_text,
        "sampled": len(sample),
    }
    # to read a hit's text an agent must hand-write SQL against `chunks` (no fetch tool)
    t, err, ms, _ = c.tool(
        "query",
        {"sql": f"SELECT text FROM chunks WHERE section_id='{first_hits[0]}' ORDER BY part"},
    )  # noqa: E501
    out["read_text_via_query"] = {"ms": round(ms, 1), "is_error": err, "tokens": tok(t)}

    # --- keys an agent would naturally guess --------------------------------------------------
    guesses = {
        "doc": ["DI/fm22_2dg", "CPRS/or_um", "FileMan Developer Guide", "di/fm22_2dg"],
        "entity": ["fileman_file:200", "fileman_file:NEW PERSON", "file:200", "rpc:ORWDX SAVE",
                   "routine:XUP", "global:^DPT", "global:^VA(200"],
    }  # fmt: skip
    gres = {}
    for kind, keys in guesses.items():
        for k in keys:
            text, err, ms, _ = c.tool("lookup", {"kind": kind, "key": k})
            gres[f"{kind}:{k}"] = "MISS" if text.startswith("NOT FOUND") else "hit"
    out["lookup_guesses"] = gres

    # --- filters: invalid codes are indistinguishable from "not indexed" ----------------------
    fres = {}
    for args in (
        {"query": "FIND^DIC finder", "app": ["DI"]},
        {"query": "FIND^DIC finder", "app": ["di"]},
        {"query": "FIND^DIC finder", "app": ["FileMan"]},
        {"query": "FIND^DIC finder", "doc_type": ["Developer Guide"]},
        {"query": "FIND^DIC finder", "doc_type": ["DG"]},
    ):
        text, err, ms, _ = c.tool("search", args)
        env = json.loads(text)
        fres[json.dumps(args)] = {
            "hits": env["hit_count"],
            "warning_says_retrieval_artefact": "RETRIEVAL artefact" in env.get("warning", ""),
        }
    out["filters"] = fres

    # --- zero-hit honesty: identical warning whether or not the lake holds the term -----------
    absent = ["zzqxvwk", "flurbometer", "QWERTYUIOPZX"]
    warns = set()
    for a in absent:
        text, *_ = c.tool("search", {"query": a})
        warns.add(json.loads(text).get("warning"))
    out["zero_hit_warning_distinct_texts_for_absent_terms"] = len(warns)

    # --- schema edge cases ---------------------------------------------------------------------
    edge = {}
    for args in ({"query": "kids", "k": 51}, {"query": "kids", "k": "15"}, {"query": ""},
                 {"query": "!!! ??? ^^^"}, {"query": "a I"}):  # fmt: skip
        text, err, ms, _ = c.tool("search", args)
        edge[json.dumps(args)] = {"isError": err, "text": text[:90]}
    out["edge_cases"] = edge
    c.p.stdin.close()
    c.p.wait(timeout=10)

    # --- `query` has no time budget: a runaway SELECT blocks the single-threaded server -------
    c2 = Client()
    c2.call("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                           "clientInfo": {"name": "probe", "version": "0"}})  # fmt: skip
    heavy = ("WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i+1 FROM n WHERE i < 300000000) "
             "SELECT COUNT(*) FROM n")  # fmt: skip
    msg = {"jsonrpc": "2.0", "id": 99, "method": "tools/call",
           "params": {"name": "query", "arguments": {"sql": heavy}}}  # fmt: skip
    c2.p.stdin.write(json.dumps(msg) + "\n")
    c2.p.stdin.flush()
    t0 = time.perf_counter()
    import select

    ready, _, _ = select.select([c2.p.stdout], [], [], 20)
    out["runaway_query"] = {
        "answered_within_20s": bool(ready),
        "waited_s": round(time.perf_counter() - t0, 1),
    }
    c2.p.kill()
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
