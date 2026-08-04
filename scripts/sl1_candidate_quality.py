#!/usr/bin/env python3
"""SL.1(c) — how sound are the waiting candidates, and what would approving them buy?

The tracker records **4,415 candidates awaiting approval**. The first thing this script establishes
is that 4,415 is a count of *mentions*: `resolve` reports `len(unresolved)` (every occurrence) while
the artifact it writes, `reports/knowledge/proposals.json`, aggregates those to one row per
`(type, surface)`. The queue a curator would face is that aggregated file.

Each proposal is then judged on two independent axes, because they can disagree and the difference
is the whole point:

* **Is it correctly recognised?** — checked against `vista-meta`'s measured model (file numbers from
  `data-model/files.tsv`, routine names from `code-model/routines.tsv`, global names from
  `code-model/routine-globals.tsv`). This scores the *extraction*.
* **Could approving it ever reach search?** — the only thing search consumes from this layer is
  `search_pure.skl_expansion_map`, which reads FileMan file **numbers** and their canonical names
  off `index.db:entity_skl`. A proposal for a routine, a global, a namespace, a build or an HL7
  segment has nowhere to land: the DD seed represents FileMan files, and the expansion map keys on
  their numbers. Those proposals are *structurally inert* — not wrong, not curatable, simply not
  connected to the surface. This scores the *projection*.

Stratified, per the plan: the easy candidates are the frequent ones and the hard candidates are the
long tail, so both are reported separately and the tail is never allowed to hide behind the head.

Usage:
    python scripts/sl1_candidate_quality.py [--data-dir DIR] [--vista-meta DIR] [--sample N]
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any

from vdocs.server.search_pure import skl_expansion_map

DEFAULT_DATA_DIR = Path.home() / "data" / "vdocs"
DEFAULT_VISTA_META = Path.home() / "projects" / "vista-meta" / "vista" / "export"

# The entity types the DD seed can represent and the expansion map can key on. Everything else is
# recognised by `index`/`resolve` but has no landing place in `registries/entities/dd-seed.*.yaml`.
PROJECTABLE_TYPES = frozenset({"fileman_file"})


def _column(path: Path, column: str) -> set[str]:
    with path.open(encoding="utf-8", newline="") as fh:
        return {(r.get(column) or "").strip().upper() for r in csv.DictReader(fh, delimiter="\t")}


def load_truth(vista_meta: Path) -> dict[str, set[str]]:
    """The measured vocabularies each proposal type is checked against."""
    files = vista_meta / "data-model" / "files.tsv"
    names: dict[str, set[str]] = {}
    with files.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    names["fileman_file"] = {(r.get("file_number") or "").strip() for r in rows}
    names["_file_name"] = {(r.get("file_name") or "").strip().upper() for r in rows}
    names["_file_by_number"] = {}  # type: ignore[assignment]
    by_number = {
        (r.get("file_number") or "").strip(): (r.get("file_name") or "").strip() for r in rows
    }
    names["routine"] = _column(vista_meta / "code-model" / "routines.tsv", "routine_name")
    names["global"] = {
        "^" + g for g in _column(vista_meta / "code-model" / "routine-globals.tsv", "global_name")
    }
    return {**names, "_by_number": by_number}  # type: ignore[dict-item]


def judge(proposal: dict[str, Any], truth: dict[str, Any]) -> dict[str, Any]:
    """One proposal's two verdicts: was it recognised correctly, and can it ever reach search."""
    etype, surface = proposal["type"], proposal["surface"]

    vocab = truth.get(etype)
    if vocab is None:
        recognised = "unchecked"  # no measured vocabulary for this type (build, hl7_segment)
    elif etype == "fileman_file":
        recognised = "valid" if surface in vocab else "not-a-file"
    else:
        recognised = "valid" if surface.upper() in vocab else "unknown-to-the-measured-model"

    if etype not in PROJECTABLE_TYPES:
        reach = "inert-no-landing-place"
    else:
        name = truth["_by_number"].get(surface, "")
        if recognised != "valid":
            reach = "inert-not-a-real-file"
        elif skl_expansion_map([(surface, name)]):
            reach = "would-expand"
        else:
            reach = "inert-guards-drop-it"

    return {
        **proposal,
        "docs": len(proposal["docs"]),
        "recognised": recognised,
        "reach": reach,
        "canonical_name": truth["_by_number"].get(surface, "") if etype == "fileman_file" else "",
    }


def run(data_dir: Path, vista_meta: Path, sample: int, seed: int) -> dict[str, Any]:
    proposals_path = data_dir / "reports" / "knowledge" / "proposals.json"
    proposals = json.loads(proposals_path.read_text(encoding="utf-8"))["proposals"]
    truth = load_truth(vista_meta)
    judged = [judge(p, truth) for p in proposals]

    mentions = sum(p["occurrences"] for p in proposals)
    # Strata: "head" = seen more than once (the easy, frequent candidates); "tail" = a single
    # occurrence. Judged separately so the tail cannot hide behind the head.
    head = [j for j in judged if j["occurrences"] > 1]
    tail = [j for j in judged if j["occurrences"] == 1]
    rng = random.Random(seed)
    tail_sample = rng.sample(tail, min(sample, len(tail)))

    def tally(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
        return dict(sorted(Counter(r[key] for r in rows).items(), key=lambda kv: -kv[1]))

    return {
        "source": {"proposals": str(proposals_path), "vista_meta": str(vista_meta)},
        "queue_shape": {
            "mentions_reported_by_resolve": mentions,
            "distinct_candidates_a_curator_would_review": len(judged),
            "by_type": dict(
                sorted(Counter(p["type"] for p in proposals).items(), key=lambda kv: -kv[1])
            ),  # fmt: skip
        },
        "rollup": {
            "projectable_candidates": sum(1 for j in judged if j["type"] in PROJECTABLE_TYPES),
            "structurally_inert_candidates": sum(
                1 for j in judged if j["reach"] == "inert-no-landing-place"
            ),
            "would_reach_search_if_approved": sum(
                1 for j in judged if j["reach"] == "would-expand"
            ),
            "recognised": tally(judged, "recognised"),
            "reach": tally(judged, "reach"),
        },
        "strata": {
            "head_occurrences_gt_1": {
                "n": len(head),
                "recognised": tally(head, "recognised"),
                "reach": tally(head, "reach"),
            },
            "tail_occurrences_eq_1": {
                "n": len(tail),
                "sampled": len(tail_sample),
                "recognised_in_sample": tally(tail_sample, "recognised"),
                "reach_in_sample": tally(tail_sample, "reach"),
            },
        },
        "fileman_file_candidates": sorted(
            [j for j in judged if j["type"] == "fileman_file"], key=lambda j: -j["occurrences"]
        ),
        "tail_sample": sorted(tail_sample, key=lambda j: (j["type"], j["surface"])),
    }


def render(result: dict[str, Any]) -> str:
    q, r = result["queue_shape"], result["rollup"]
    head = result["strata"]["head_occurrences_gt_1"]
    tail = result["strata"]["tail_occurrences_eq_1"]
    lines = [
        "# SL.1(c) — how sound are the waiting candidates?",
        "",
        f"- **queue:** `{result['source']['proposals']}`",
        f"- **ground truth:** `{result['source']['vista_meta']}` (vista-meta measured model)",
        "",
        "## The queue is smaller than reported, and differently shaped",
        "",
        "| | |",
        "|---|---|",
        f"| mentions (`resolve`'s `proposals` count — what the tracker records) "
        f"| {q['mentions_reported_by_resolve']} |",
        f"| **distinct candidates a curator would actually review** "
        f"| **{q['distinct_candidates_a_curator_would_review']}** |",
        "",
        "By type: " + ", ".join(f"`{t}` {n}" for t, n in q["by_type"].items()) + ".",
        "",
        "## What approving them would buy",
        "",
        "| | |",
        "|---|---|",
        f"| candidates of a type the seed can represent (`fileman_file`) "
        f"| {r['projectable_candidates']} |",
        f"| **structurally inert** — recognised, but no landing place in the seed and nothing the "
        f"expansion map keys on | **{r['structurally_inert_candidates']}** |",
        f"| **would reach search if approved** | **{r['would_reach_search_if_approved']}** |",
        "",
        "Recognition quality (is the surface a real thing in the measured VistA?): "
        + ", ".join(f"{k} {v}" for k, v in r["recognised"].items())
        + ".",
        "",
        "## Strata",
        "",
        f"- **head** (seen more than once): {head['n']} candidates — recognised "
        + ", ".join(f"{k} {v}" for k, v in head["recognised"].items())
        + ".",
        f"- **tail** (seen exactly once): {tail['n']} candidates, {tail['sampled']} sampled — "
        "recognised "
        + ", ".join(f"{k} {v}" for k, v in tail["recognised_in_sample"].items())
        + ".",
        "",
        "## Every `fileman_file` candidate — the only type that could reach search",
        "",
        "| surface | occurrences | docs | real file? | canonical name | reach |",
        "|---|---|---|---|---|---|",
    ]
    for j in result["fileman_file_candidates"]:
        lines.append(
            f"| {j['surface']} | {j['occurrences']} | {j['docs']} | {j['recognised']} "
            f"| {j['canonical_name'] or '—'} | {j['reach']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    ap.add_argument("--vista-meta", type=Path, default=DEFAULT_VISTA_META)
    ap.add_argument("--sample", type=int, default=40)
    ap.add_argument("--seed", type=int, default=20260804)
    ap.add_argument("--out", type=Path, default=Path("reports/sl1c-candidate-quality.md"))
    args = ap.parse_args()

    result = run(args.data_dir, args.vista_meta, args.sample, args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(result), encoding="utf-8")
    args.out.with_suffix(".json").write_text(
        json.dumps(result, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({**result["queue_shape"], **result["rollup"]}, indent=2))
    print(f"\nwrote {args.out} and {args.out.with_suffix('.json')}")


if __name__ == "__main__":
    main()
