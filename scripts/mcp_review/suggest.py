"""Sizing the web console's search-box suggestions (keyword-search proposal, fix 5).

MEASUREMENT PROTOTYPE, not production code. Builds the suggestion list the proposal describes, from
what index.db already holds (the documents' application names, codes and products; the
v_sections headings of latest documents) plus the reviewer-drafted plain-English names in
package_names.py, and shows what a few typed prefixes would offer.

Rules: every typed word must be the start of a word in the suggestion (case ignored), from two
characters; packages first (at most 3), then headings ordered by how many documents use them; at
most 8 in all. Headings are cleaned of leading numbering and kept only if 3–80 characters long with
a letter in them.
"""

from __future__ import annotations

import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import package_names as P  # noqa: E402
from _common import provenance  # noqa: E402

con = P.con
WORD = re.compile(r"[a-z0-9]+")


def build() -> tuple[list[tuple[str, str, int]], dict]:
    """(display text, kind, weight) entries."""
    pkgs: dict[str, list[str]] = defaultdict(list)  # text (any case) → what it stands for
    shown_pkg: dict[str, str] = {}

    def add(text: str, what: str) -> None:
        shown_pkg.setdefault(text.lower(), text)
        if what not in pkgs[text.lower()]:
            pkgs[text.lower()].append(what)

    for code, aname, pabbr, pfull in con.execute(
        "SELECT DISTINCT app_code, app_name, product_abbr, product_full FROM documents "
        "WHERE is_latest = 1"
    ):
        name = P.clean(aname)
        for text in (name, code, P.clean(pfull), pabbr, *P.PLAIN.get(code, [])):
            if text and text != "OR":
                add(text, f"{name} ({code})")
    for _code, names, tg in P.PARTS:
        for n in [*names, *tg]:
            add(n, f"{tg[1] if len(tg) > 1 else tg[0]} (Kernel)")
    heads: dict[str, set[str]] = defaultdict(set)
    shown: dict[str, str] = {}
    for dk, title in con.execute("SELECT doc_key, title FROM v_sections WHERE is_latest = 1"):
        t = re.sub(r"[*_\\]", "", title or "")  # markdown emphasis and escapes
        t = re.sub(r"^\s*(\d+(\.\d+)*\.?|[A-Z]\.\d+(\.\d+)*)\s+", "", t).strip()
        if 3 <= len(t) <= 80 and re.search(r"[A-Za-z]", t):
            heads[t.lower()].add(dk)
            shown.setdefault(t.lower(), t)
    entries = []
    for key, whats in pkgs.items():
        text = shown_pkg[key]
        if len(whats) == 1 and text == whats[0].split(" (")[0]:
            entries.append((whats[0], "package", 10**6))  # the package's own name
        else:
            entries.append((f"{text} → {'; '.join(whats)}", "package", 10**6))
    entries += [(shown[k], "heading", len(v)) for k, v in heads.items()]
    stats = {
        "package_entries": len(pkgs),
        "heading_entries": len(heads),
        "headings_in_2_or_more_documents": sum(len(v) >= 2 for v in heads.values()),
    }
    return entries, stats


def suggest(typed: str, index: list[tuple[list[str], str, str, int]], n: int = 8) -> list[str]:
    words = WORD.findall(typed.lower())
    if not words or len(typed.strip()) < 2:
        return []
    starts = typed.strip().lower()
    hits = [
        (kind, not text.lower().startswith(starts), -w, text)
        for toks, text, kind, w in index
        if all(any(t.startswith(x) for t in toks) for x in words)
    ]
    pk = sorted(h for h in hits if h[0] == "package")[:3]
    hd = sorted(h for h in hits if h[0] == "heading")[: n - len(pk)]
    return [h[3] for h in pk + hd]


def main() -> None:
    entries, stats = build()
    index = [(WORD.findall(text.lower()), text, kind, w) for text, kind, w in entries]
    probes = ["bl", "blood b", "email", "warf", "cancel ord", "taskm", "new pers", "input tr",
              "allerg", "progress no"]  # fmt: skip
    t0 = time.perf_counter()
    shown = {p: suggest(p, index) for p in probes}
    ms = (time.perf_counter() - t0) * 1000 / len(probes)
    out = {
        "provenance": provenance(),
        "entries": stats,
        "ms_per_keystroke_python_linear_scan": round(ms, 1),
        "examples": shown,
    }
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
