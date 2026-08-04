#!/usr/bin/env python3
"""SL.1(a) — how common is the number/name vocabulary split in this collection?

The synonym layer's whole thesis is that VistA documentation names one thing several ways (*file
200* / *NEW PERSON* / `^VA(200,`) and that a keyword index therefore hides the manuals written in
the other vocabulary. This script measures how large that population actually is, on the production
index, against an **independent** ground truth.

Ground truth is `vista-meta`'s measured data model (`export/data-model/files.tsv`: file number ↔
file name ↔ global root, read from a live VistA). Deliberately *not* the pilot's 21-file
`registries/entities/dd-seed.di.yaml` — that seed is the thing under evaluation, and measuring the
feature against its own input would only tell us the input is self-consistent.

Three surface forms per file, each read the way search would see it:

* **number form** — `index.db:entity_mentions` for `fileman_file:<n>`; that is the production
  recognizer's *"file #N"*-contexted match, i.e. exactly the mentions the shipped index knows about.
* **name form** — an FTS5 phrase query for the file name against `chunks_fts`. This is the literal
  "would a search for this name find these chunks" question, asked of the real index.
* **global form** — `index.db:entity_mentions` for `global:<root>`. The recognizer clips a global at
  `(`, so `^VA(200,` is indexed as `^VA`; a root is counted as *identifying* only when exactly one
  file in the ground truth reduces to it (otherwise the form names a family, not a file).

A name is only counted when it is **distinctive**: a single-word name that collides with ordinary
English ("FILE", "PATIENT", "STATUS") would match half the corpus and flatter every number here.
The English-collision test is the shipped one (`kernel.casing_pure`), and the discarded population
is reported so the guard's cost is visible rather than assumed.

Usage:
    python scripts/sl1_ambiguity.py [--data-dir DIR] [--files-tsv PATH] [--out REPORT.md]

Writes a markdown report and a sibling JSON, and prints the rollup to stdout.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from vdocs.kernel import casing_pure, termbase

DEFAULT_DATA_DIR = Path.home() / "data" / "vdocs"
DEFAULT_FILES_TSV = (
    Path.home() / "projects" / "vista-meta" / "vista" / "export" / "data-model" / "files.tsv"
)
DEFAULT_REGISTRIES = Path(__file__).resolve().parent.parent / "registries"


def global_root_key(global_root: str) -> str:
    """The recognizer's view of a global root: everything up to the first subscript.

    `^VA(200,` → `^VA`, `^DD("IX",` → `^DD`, `^DPT(` → `^DPT`. This mirrors the `global` rule in
    `registries/entities/entities.yaml` (`\\^%?[A-Z][A-Z0-9]+\\b`), which stops at the paren — so it
    is what `index.db` actually holds, not what the manual wrote."""
    m = re.match(r"\^%?[A-Za-z][A-Za-z0-9]*", global_root.strip())
    return m.group(0).upper() if m else ""


def is_distinctive_name(name: str, english: frozenset[str]) -> bool:
    """A file name specific enough to be evidence of the file. Multi-word names are always kept; a
    single word is kept only when it is not ordinary English (so "NEW PERSON" and "AUDIT LOG" count,
    "FILE" and "PATIENT" do not)."""
    words = name.split()
    if len(words) >= 2:
        return True
    if not words:
        return False
    return not casing_pure.collides_with_english(words[0], english)


def fts_phrase(name: str) -> str:
    """`name` as one FTS5 phrase clause. Punctuation is dropped (FTS5 tokenises on it anyway) so the
    clause can never be mistaken for query syntax; returns "" when no token survives."""
    tokens = re.findall(r"[A-Za-z0-9]+", name)
    return '"' + " ".join(tokens) + '"' if tokens else ""


def load_ground_truth(path: Path) -> list[dict[str, str]]:
    """The vista-meta data-model rows with a usable number + name."""
    out: list[dict[str, str]] = []
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            number = (row.get("file_number") or "").strip()
            name = (row.get("file_name") or "").strip()
            if not number or not name:
                continue
            out.append(
                {"number": number, "name": name, "global": (row.get("global_root") or "").strip()}
            )
    return out


def mention_docs(conn: sqlite3.Connection, etype: str) -> dict[str, set[str]]:
    """canonical → the doc_keys the production recognizer saw it in, for one entity type."""
    rows = conn.execute(
        "SELECT e.entity_id, m.doc_key FROM entities e "
        "JOIN entity_mentions m ON m.entity_id = e.entity_id WHERE e.type = ?",
        (etype,),
    ).fetchall()
    out: dict[str, set[str]] = defaultdict(set)
    for entity_id, doc_key in rows:
        out[entity_id.split(":", 1)[1]].add(doc_key)
    return out


def phrase_docs(conn: sqlite3.Connection, phrase: str) -> tuple[set[str], int, int, list[str]]:
    """(doc_keys, chunk hits, body characters, bodies) for one FTS phrase — what a search for this
    name would reach, plus the matched text so the context test below can re-read it."""
    rows = conn.execute(
        "SELECT doc_key, body FROM chunks_fts WHERE chunks_fts MATCH ?", (phrase,)
    ).fetchall()
    return (
        {r[0] for r in rows},
        len(rows),
        sum(len(r[1] or "") for r in rows),
        [(r[0], r[1] or "") for r in rows],  # type: ignore[list-item]
    )


# The number form is anchored ("file #N" — the recognizer refuses a bare number). The name form must
# be anchored the same way or the two sides are not comparable: "PARAMETERS" matches ordinary prose
# 7,397 times, and counting that as evidence of file 8989.5 would flatter every number in this
# report. So a name only counts as *file-referring* when the manual marks it as one — the name
# beside the word "file", or beside its own file number in the `NAME (#8989.5)` convention.
_CONTEXT_WINDOW = 24


def name_in_file_context(body: str, name: str, number: str) -> bool:
    """True when `name` occurs in `body` marked as a file reference: within a short window of the
    word "file", or immediately followed by `(#<number>)`. Case-insensitive."""
    pat = re.escape(name)
    num = re.escape(number)
    near = rf"(?:file\w*\W{{0,{_CONTEXT_WINDOW}}}{pat}|{pat}\W{{0,{_CONTEXT_WINDOW}}}file\w*)"
    numbered = rf"{pat}\s*\(?\s*#\s*{num}"
    return re.search(f"{near}|{numbered}", body, re.IGNORECASE) is not None


def corpus_stamp(conn: sqlite3.Connection, index_db: Path) -> dict[str, Any]:
    """The provenance every report in this repo carries — which corpus was measured
    (see `reports/README.md`)."""
    docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    keys = conn.execute("SELECT doc_key FROM documents ORDER BY doc_key").fetchall()
    digest = hashlib.sha256("\n".join(k[0] for k in keys).encode("utf-8")).hexdigest()
    return {
        "index_db": str(index_db),
        "documents": docs,
        "chunks": chunks,
        "corpus_doc_key_hash": digest[:16],
    }


def measure(data_dir: Path, files_tsv: Path, registries: Path) -> dict[str, Any]:
    index_db = data_dir / "index.db"
    conn = sqlite3.connect(f"file:{index_db}?mode=ro", uri=True)
    try:
        stamp = corpus_stamp(conn, index_db)
        english = termbase.load_english_words(registries)
        truth = load_ground_truth(files_tsv)

        number_docs = mention_docs(conn, "fileman_file")
        global_docs = mention_docs(conn, "global")

        # A global root is identifying only when one ground-truth file reduces to it.
        root_owners: dict[str, set[str]] = defaultdict(set)
        for f in truth:
            root = global_root_key(f["global"])
            if root:
                root_owners[root].add(f["number"])

        per_file: list[dict[str, Any]] = []
        suppressed: list[dict[str, Any]] = []
        for f in truth:
            num_docs = number_docs.get(f["number"], set())
            root = global_root_key(f["global"])
            identifying_root = bool(root) and len(root_owners.get(root, ())) == 1
            glob_docs = global_docs.get(root, set()) if identifying_root else set()

            if not is_distinctive_name(f["name"], english):
                if num_docs:
                    suppressed.append(
                        {"number": f["number"], "name": f["name"], "number_docs": len(num_docs)}
                    )
                continue
            phrase = fts_phrase(f["name"])
            if not phrase:
                continue
            nm_docs, nm_chunks, nm_chars, bodies = phrase_docs(conn, phrase)
            if not (num_docs or nm_docs or glob_docs):
                continue  # the collection never mentions this file at all

            ctx_docs: set[str] = set()
            ctx_chunks = 0
            for doc_key, body in bodies:
                if name_in_file_context(body, f["name"], f["number"]):
                    ctx_docs.add(doc_key)
                    ctx_chunks += 1

            forms = sum(bool(s) for s in (num_docs, nm_docs, glob_docs))
            per_file.append(
                {
                    "number": f["number"],
                    "name": f["name"],
                    "global": f["global"],
                    "global_root": root if identifying_root else "",
                    "forms": forms,
                    "number_docs": sorted(num_docs),
                    "name_docs": sorted(nm_docs),
                    "global_docs": sorted(glob_docs),
                    "name_only_docs": sorted(nm_docs - num_docs),
                    "number_only_docs": sorted(num_docs - nm_docs),
                    "name_chunks": nm_chunks,
                    "name_chars": nm_chars,
                    "context_docs": sorted(ctx_docs),
                    "context_only_docs": sorted(ctx_docs - num_docs),
                    "context_chunks": ctx_chunks,
                }
            )
    finally:
        conn.close()

    mentioned = per_file
    multi = [f for f in mentioned if f["forms"] >= 2]
    split = [f for f in multi if f["name_only_docs"] and f["number_docs"]]
    hidden = [f for f in mentioned if f["number_docs"] and not f["name_docs"]]
    name_only_files = [f for f in mentioned if f["name_docs"] and not f["number_docs"]]
    # The defensible population: both sides anchored the same way (see `name_in_file_context`).
    anchored = [f for f in mentioned if f["context_only_docs"] and f["number_docs"]]

    return {
        "corpus": stamp,
        "ground_truth": {"path": str(files_tsv), "files": len(truth)},
        "rollup": {
            "files_mentioned_at_all": len(mentioned),
            "files_under_two_or_more_forms": len(multi),
            "files_with_a_true_split_raw": len(split),
            "files_with_a_true_split_anchored": len(anchored),
            "files_number_form_only": len(hidden),
            "files_name_form_only": len(name_only_files),
            "name_only_doc_pairs_raw": sum(len(f["name_only_docs"]) for f in split),
            "name_only_doc_pairs_anchored": sum(len(f["context_only_docs"]) for f in anchored),
            "anchored_chunks_behind_split": sum(f["context_chunks"] for f in anchored),
            "names_suppressed_as_english": len(suppressed),
        },
        "split_files": sorted(anchored, key=lambda f: -len(f["context_only_docs"])),
        "split_files_raw_only": sorted(
            [f for f in split if not f["context_only_docs"]],
            key=lambda f: -len(f["name_only_docs"]),
        )[:20],
        "suppressed_english_names": sorted(suppressed, key=lambda s: -s["number_docs"])[:40],
    }


def render(result: dict[str, Any]) -> str:
    c, r = result["corpus"], result["rollup"]
    lines = [
        "# SL.1(a) — how common is the number/name vocabulary split?",
        "",
        f"- **index_db:** `{c['index_db']}` · **documents:** {c['documents']} · "
        f"**chunks:** {c['chunks']} · **doc_key hash:** `{c['corpus_doc_key_hash']}`",
        f"- **ground truth:** `{result['ground_truth']['path']}` "
        f"({result['ground_truth']['files']} FileMan files, measured from a live VistA)",
        "",
        "## Rollup",
        "",
        "| | |",
        "|---|---|",
        f"| FileMan files this collection mentions at all (distinctive names only) "
        f"| {r['files_mentioned_at_all']} |",
        f"| …of those, mentioned under **two or more** surface forms "
        f"| {r['files_under_two_or_more_forms']} |",
        f"| …with a split on a **bare** name match (upper bound, over-counts prose) "
        f"| {r['files_with_a_true_split_raw']} |",
        f"| **…with a split on a *file-referring* name match (the defensible number)** "
        f"| **{r['files_with_a_true_split_anchored']}** |",
        f"| documents reachable by the anchored name but not by the number (file×doc pairs) "
        f"| **{r['name_only_doc_pairs_anchored']}** |",
        f"| chunks behind those anchored name matches | {r['anchored_chunks_behind_split']} |",
        f"| (same, unanchored) | {r['name_only_doc_pairs_raw']} |",
        f"| files the collection names **only** by number | {r['files_number_form_only']} |",
        f"| files the collection names **only** by name (bare match; mostly prose noise) "
        f"| {r['files_name_form_only']} |",
        f"| file names suppressed as ordinary English (guard) "
        f"| {r['names_suppressed_as_english']} |",
        "",
        "## The anchored split, largest first",
        "",
        "| file | name | docs by number | docs by anchored name "
        "| anchored name-only docs | chunks |",
        "|---|---|---|---|---|---|",
    ]
    for f in result["split_files"][:40]:
        lines.append(
            f"| {f['number']} | {f['name']} | {len(f['number_docs'])} | {len(f['context_docs'])} "
            f"| {len(f['context_only_docs'])} | {f['context_chunks']} |"
        )
    lines += [
        "",
        "## Dropped by the anchor — a bare name match with no file-referring occurrence",
        "",
        "| file | name | bare name-only docs | bare chunks |",
        "|---|---|---|---|",
    ]
    for f in result["split_files_raw_only"]:
        lines.append(
            f"| {f['number']} | {f['name']} | {len(f['name_only_docs'])} | {f['name_chunks']} |"
        )
    lines += [
        "",
        "## Names the English guard suppressed (largest number-form presence first)",
        "",
        "These files *are* referenced by number in the collection, but their names are ordinary",
        "English words, so no name-form measurement is trustworthy for them.",
        "",
        "| file | name | docs by number |",
        "|---|---|---|",
    ]
    for s in result["suppressed_english_names"][:20]:
        lines.append(f"| {s['number']} | {s['name']} | {s['number_docs']} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    ap.add_argument("--files-tsv", type=Path, default=DEFAULT_FILES_TSV)
    ap.add_argument("--registries", type=Path, default=DEFAULT_REGISTRIES)
    ap.add_argument("--out", type=Path, default=Path("reports/sl1a-ambiguity.md"))
    args = ap.parse_args()

    result = measure(args.data_dir, args.files_tsv, args.registries)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(result), encoding="utf-8")
    args.out.with_suffix(".json").write_text(
        json.dumps(result, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({**result["corpus"], **result["rollup"]}, indent=2))
    print(f"\nwrote {args.out} and {args.out.with_suffix('.json')}")


if __name__ == "__main__":
    main()
