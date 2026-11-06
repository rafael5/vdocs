"""All words, with an any-word fallback, as the default join in every front door (D1 revised).

MEASUREMENT PROTOTYPE, not production code. Sentence search was dropped on 2026-11-06, which
removed the reason the MCP joined bare words with OR. This compares the MCP's section results under
the prototype query reader (package_names.reader, no synonym table) with bare words joined by OR,
against all words falling back to any word when no section holds them all: on the 24 judged
keyword questions, and on the patch-id and file-number identifier probes.
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
import package_names as P  # noqa: E402
from _common import FILES, provenance  # noqa: E402


def mcp(q: str, mode: str) -> list[str]:
    if mode == "any_word":
        return P.sections(P.reader(q, None, "OR"))
    return P.sections(P.reader(q, None, "AND")) or P.sections(P.reader(q, None, "OR"))


def summ(rs: list[int | None]) -> dict:
    ok = [r for r in rs if r]
    return {"n": len(rs), "top10": sum(r <= 10 for r in ok), "first": sum(r == 1 for r in ok),
            "mrr": round(sum(1 / r for r in ok) / len(rs), 3)}  # fmt: skip


def main() -> None:
    g = {q["id"]: q for q in yaml.safe_load(open("registries/golden-queries.yaml"))["queries"]}
    kw = P._keyword_forms()
    judged = [q for q in g if g[q].get("relevant")]
    text: dict[str, str] = defaultdict(str)
    for sid, t in P.con.execute("SELECT section_id, text FROM chunks ORDER BY section_id, part"):
        text[sid] += "\n" + t
    builds = [r[0] for r in P.con.execute("SELECT canonical_name FROM entities WHERE type='build'")]
    out: dict = {"provenance": provenance()}
    for mode in ("any_word", "all_words_then_any"):
        ranks = [
            P.rank(mcp(kw[q], mode), {r["section_id"] for r in g[q]["relevant"]}) for q in judged
        ]
        patch = sum(any(b in text.get(s, "") for s in mcp(b, mode)[:5]) for b in builds)
        files = 0
        for num, name in FILES.items():
            pat = re.compile(rf"(#|file\s*#?\s*){re.escape(num)}(?![\d.])", re.I)
            files += any(
                name.lower() in text.get(s, "").lower() and pat.search(text.get(s, ""))
                for s in mcp(f"file #{num}", mode)[:5]
            )
        out[mode] = {
            "mcp_keyword_questions": summ(ranks),
            "patch_id_top5": f"{patch}/{len(builds)}",
            "file_number_top5": f"{files}/{len(FILES)}",
        }
    out["fallback_fired_on_keyword_questions"] = sum(
        not P.sections(P.reader(kw[q], None, "AND")) for q in judged
    )
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
