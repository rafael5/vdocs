#!/usr/bin/env python3
"""SL.1(b) — how many realistic questions does the vocabulary split cost?

`registries/golden-queries.yaml` contains exactly **one** number/name question by construction
(`fileman-file-200-new-person`), so it cannot answer this. This script builds a sample of
identifier-shaped questions from the SL.1(a) population instead, and counts the ones that fail for
vocabulary reasons *alone* — where the answering passage exists, is indexed and is latest, but is
written under the other name.

The test is mechanical, so nobody has to be trusted to judge it:

    answering set A(file) = the chunks where the file's name appears in a file-referring context
                            (`NAME … file`, `file … NAME`, `NAME (#N)`) — SL.1(a)'s anchored set,
                            restricted to documents the number form never reaches.

    vocabulary failure    = top-k("what is file <N>?")     ∩ A = ∅
                        and top-k("what is the <NAME> file?") ∩ A ≠ ∅

That second clause is what makes it a *vocabulary* failure and not an absence: the same engine, the
same index, the same k — only the word changed, and the passages appeared.

It then prices the fix. For every failing question it re-runs the number query with the expansion
the synonym layer *would* supply if that file were seeded (`<N> → <NAME>`, the exact shape
`search_pure.skl_expansion_map` emits) and reports how many failures it repairs and how many
questions it damages. That repaired count is the headroom, measured rather than asserted, and it
doubles as SL.3a's expected-gain statement.

**What this is not.** These questions have no graded relevance labels; the measure is
*reachability*, not answer quality, and its numbers are not comparable to the golden-set nDCG in
`reports/rc-final-baseline.*`. It is a count of questions, deliberately.

Usage:
    python scripts/sl1_vocab_cost.py [--data-dir DIR] [--ambiguity reports/sl1a-ambiguity.json]
                                     [--k N] [--top N] [--sample N] [--seed N]
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
from pathlib import Path
from typing import Any

from sl1_ambiguity import name_in_file_context  # noqa: E402  (sibling script, same directory)

from vdocs.server.search import lexical_search
from vdocs.server.search_pure import skl_expansion_map

DEFAULT_DATA_DIR = Path.home() / "data" / "vdocs"


def answering_sections(
    conn: sqlite3.Connection, name: str, number: str, docs: list[str]
) -> set[str]:
    """The section ids that answer *this* file's question in the other vocabulary: sections whose
    text names the file in a file-referring context, inside documents the number form never reaches.

    Section-level (not chunk-level) because citations resolve at the section — the same unit
    `baseline_golden.py` scores on."""
    if not docs:
        return set()
    placeholders = ", ".join("?" for _ in docs)
    rows = conn.execute(
        f"SELECT section_id, text FROM chunks WHERE doc_key IN ({placeholders})", docs
    ).fetchall()
    return {sid for sid, text in rows if name_in_file_context(text or "", name, number)}


def top_sections(index_db: Path, query: str, k: int, expansions: dict[str, str]) -> list[str]:
    """The ranked unique section ids the production engine returns (first appearance wins)."""
    out: list[str] = []
    seen: set[str] = set()
    for hit in lexical_search(index_db, query, k=k, expansions=expansions):
        sid = hit["section_id"]
        if sid not in seen:
            seen.add(sid)
            out.append(sid)
    return out


def build_sample(
    ambiguity: dict[str, Any], top: int, sample: int, seed: int
) -> list[dict[str, Any]]:
    """Stratified: every one of the `top` largest splits, plus a random draw of `sample` from the
    tail. A head-only sample would measure the easiest cases and flatter the result; a flat random
    sample would mostly draw files nobody asks about."""
    files = ambiguity["split_files"]
    head, tail = files[:top], files[top:]
    rng = random.Random(seed)
    drawn = rng.sample(tail, min(sample, len(tail))) if tail else []
    return [{**f, "stratum": "head"} for f in head] + [{**f, "stratum": "tail"} for f in drawn]


def run(
    data_dir: Path, ambiguity_path: Path, k: int, top: int, sample: int, seed: int
) -> dict[str, Any]:
    index_db = data_dir / "index.db"
    ambiguity = json.loads(ambiguity_path.read_text(encoding="utf-8"))
    picks = build_sample(ambiguity, top, sample, seed)

    conn = sqlite3.connect(f"file:{index_db}?mode=ro", uri=True)
    try:
        results: list[dict[str, Any]] = []
        for f in picks:
            number, name = f["number"], f["name"]
            answers = answering_sections(conn, name, number, f["context_only_docs"])
            if not answers:
                continue

            q_num = f"what is file {number}?"
            q_name = f"what is the {name} file?"
            num_hits = top_sections(index_db, q_num, k, {})
            name_hits = top_sections(index_db, q_name, k, {})

            num_ok = bool(set(num_hits) & answers)
            name_ok = bool(set(name_hits) & answers)

            # The expansion the synonym layer would supply for this file, produced by the shipped
            # projection so the test cannot drift from what the feature actually emits.
            exp = skl_expansion_map([(number, name)])
            fixed_hits = top_sections(index_db, q_num, k, exp) if exp else num_hits
            fixed_ok = bool(set(fixed_hits) & answers)

            # The CEILING: both vocabularies present in one query. No expansion map can beat this —
            # an expansion adds the name phrase to a query that already carries the number tokens,
            # which is what this is. Measured through the real engine (no re-implementation), so it
            # prices the whole direction, not just the guards that happen to be in the way today.
            oracle_ok = bool(set(top_sections(index_db, f"{q_num} {name}", k, {})) & answers)

            results.append(
                {
                    "number": number,
                    "name": name,
                    "stratum": f["stratum"],
                    "answering_sections": len(answers),
                    "number_query_reaches": num_ok,
                    "name_query_reaches": name_ok,
                    "expansion_emitted": exp,
                    "expansion_reaches": fixed_ok,
                    "oracle_reaches": oracle_ok,
                    "verdict": (
                        "reached"
                        if num_ok
                        else ("vocabulary_failure" if name_ok else "unreached_either_way")
                    ),
                }
            )
    finally:
        conn.close()

    failures = [r for r in results if r["verdict"] == "vocabulary_failure"]
    fixable = [r for r in failures if r["expansion_reaches"]]
    no_expansion = [r for r in failures if not r["expansion_emitted"]]
    damaged = [r for r in results if r["verdict"] == "reached" and not r["expansion_reaches"]]
    ceiling = [r for r in failures if r["oracle_reaches"]]

    return {
        "corpus": {"index_db": str(index_db), "k": k},
        "sample": {
            "source": str(ambiguity_path),
            "head": top,
            "tail_drawn": sample,
            "seed": seed,
            "questions_scored": len(results),
        },
        "rollup": {
            "questions_scored": len(results),
            "reached_by_the_number_query": sum(1 for r in results if r["verdict"] == "reached"),
            "vocabulary_failures": len(failures),
            "unreached_either_way": sum(
                1 for r in results if r["verdict"] == "unreached_either_way"
            ),
            "failures_repaired_by_expansion": len(fixable),
            "failures_the_layer_cannot_express": len(no_expansion),
            "questions_damaged_by_expansion": len(damaged),
            "failures_repairable_at_the_ceiling": len(ceiling),
        },
        "questions": results,
    }


def render(result: dict[str, Any]) -> str:
    r, s = result["rollup"], result["sample"]
    n = r["questions_scored"] or 1
    lines = [
        "# SL.1(b) — what the vocabulary split costs, in questions",
        "",
        f"- **index_db:** `{result['corpus']['index_db']}` · **k:** {result['corpus']['k']}",
        f"- **sample:** {s['head']} largest splits + {s['tail_drawn']} drawn from the tail "
        f"(seed {s['seed']}), from `{s['source']}`",
        "- **not** the golden set: these questions carry no relevance labels. The measure is "
        "reachability of the answering passage, and its numbers do not compare to golden nDCG.",
        "",
        "## Rollup",
        "",
        "| | |",
        "|---|---|",
        f"| identifier-shaped questions scored | {r['questions_scored']} |",
        f"| the number query already reaches the answer | {r['reached_by_the_number_query']} "
        f"({r['reached_by_the_number_query'] / n:.0%}) |",
        f"| **vocabulary failures** — the name query reaches it, the number query does not "
        f"| **{r['vocabulary_failures']}** ({r['vocabulary_failures'] / n:.0%}) |",
        f"| neither query reaches it (not a vocabulary problem) | {r['unreached_either_way']} |",
        f"| **failures the synonym layer would repair** "
        f"| **{r['failures_repaired_by_expansion']}** |",
        f"| failures the layer *cannot express* (guards drop the expansion) "
        f"| {r['failures_the_layer_cannot_express']} |",
        f"| questions the expansion would damage | {r['questions_damaged_by_expansion']} |",
        f"| **ceiling — failures repairable by *any* expansion** (both vocabularies in one query) "
        f"| **{r['failures_repairable_at_the_ceiling']}** |",
        "",
        "## Per question",
        "",
        "| file | name | stratum | verdict | expansion | repaired |",
        "|---|---|---|---|---|---|",
    ]
    for q in result["questions"]:
        exp = "—" if not q["expansion_emitted"] else f"`{q['number']} → {q['name']}`"
        rep = (
            "—"
            if q["verdict"] != "vocabulary_failure"
            else ("yes" if q["expansion_reaches"] else "no")
        )
        lines.append(
            f"| {q['number']} | {q['name']} | {q['stratum']} | {q['verdict']} | {exp} | {rep} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    ap.add_argument("--ambiguity", type=Path, default=Path("reports/sl1a-ambiguity.json"))
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--sample", type=int, default=40)
    ap.add_argument("--seed", type=int, default=20260804)
    ap.add_argument("--out", type=Path, default=Path("reports/sl1b-vocab-cost.md"))
    args = ap.parse_args()

    result = run(args.data_dir, args.ambiguity, args.k, args.top, args.sample, args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(result), encoding="utf-8")
    args.out.with_suffix(".json").write_text(
        json.dumps(result, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(result["rollup"], indent=2))
    print(f"\nwrote {args.out} and {args.out.with_suffix('.json')}")


if __name__ == "__main__":
    main()
