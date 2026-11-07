"""Fix 5 as built: the web console's search-box suggestions, measured through the running vdocs-web.

MEASUREMENT, not production code. Everything goes through the shipped `/api/suggest` and
`/api/candidates` of a running vdocs-web (default http://127.0.0.1:8765; pass another base URL as
the first argument) over the lake's index.db.

Checks, against the proposal's §3 fix 5 and §4 target:
- time per keystroke: every prefix (from two characters) of the probe searches, timed at the client
  over loopback, so it includes the HTTP round trip (target: under 50 ms);
- every package name, code and plain-English name is offered once typed in full, and how many are
  offered once only their first word is typed (at most 3 packages are shown);
- choosing a heading searches for it as a quoted phrase and finds its documents;
- the proposal's examples.
"""

from __future__ import annotations

import json
import sqlite3
import statistics
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

from vdocs.stages.merge.merge_pure import clean_app_name

sys.path.insert(0, str(Path(__file__).parent))
from _common import DB, provenance  # noqa: E402

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
REG = yaml.safe_load(open("registries/search-synonyms.yaml"))
PROBES = ["blood bank", "email", "warfarin", "cancel order", "taskman", "new person",
          "input template", "allergies", "progress notes", "set up printer", "background jobs",
          "change password", "create user account", "outpatient pharmacy"]  # fmt: skip
EXAMPLES = ["blood b", "email", "taskm", "cancel ord"]


def get(path: str) -> object:
    with urllib.request.urlopen(BASE + path) as r:
        return json.load(r)


def suggest(typed: str) -> list[dict]:
    return get("/api/suggest?q=" + urllib.parse.quote(typed))  # type: ignore[return-value]


def offered(name: str, typed: str) -> bool:
    return any(
        s["Kind"] == "package" and s["Search"].lower() == name.lower() for s in suggest(typed)
    )


def main() -> None:
    out: dict = {"provenance": {**provenance(), "web": BASE}}

    times = []
    for probe in PROBES:
        for n in range(2, len(probe) + 1):
            t0 = time.perf_counter()
            suggest(probe[:n])
            times.append((time.perf_counter() - t0) * 1000)
    out["ms_per_keystroke_at_the_client"] = {
        "keystrokes": len(times),
        "median": round(statistics.median(times), 1),
        "p95": round(sorted(times)[int(len(times) * 0.95)], 1),
        "max": round(max(times), 1),
    }

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    apps = con.execute(
        "SELECT DISTINCT app_code, app_name FROM documents WHERE is_latest = 1 ORDER BY 1"
    ).fetchall()
    names = {
        "application names": [clean_app_name(n) or c for c, n in apps],
        "application codes": [c for c, _ in apps],
        "plain-English package names": [n for ns in REG["packages"].values() for n in ns],
        "Kernel parts": [n for p in REG["kernel_parts"] for n in p["names"]],
    }
    coverage = {}
    for group, ns in names.items():
        full = [n for n in ns if not offered(n, n)]
        first = [n for n in ns if not offered(n, n.split()[0])]
        coverage[group] = {
            "names": len(ns),
            "offered_typed_in_full": len(ns) - len(full),
            "offered_after_the_first_word": len(ns) - len(first),
            "not_offered_typed_in_full": full,
            "not_offered_after_the_first_word_sample": first[:15],
        }
    out["package_names"] = coverage

    heads = [s for p in PROBES for s in suggest(p) if s["Kind"] == "heading"]
    found = sum(
        bool(get("/api/candidates?q=" + urllib.parse.quote(h["Search"]))["Docs"])  # type: ignore[index]
        for h in heads
    )
    out["chosen_headings_that_find_documents"] = f"{found}/{len(heads)}"
    out["examples"] = {e: [s["Label"] for s in suggest(e)] for e in EXAMPLES}
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
