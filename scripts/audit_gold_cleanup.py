#!/usr/bin/env python3
"""Regression oracle for the gold title-page / revision-history / legacy-TOC cleanup.

Audits every ``$DATA_DIR/documents/gold/consolidated/*/*/body.md`` for the three legacy
artifacts the pipeline is supposed to shed (P1 title page, P2 revision history, P3 legacy TOC)
and the TOC-integrity gap (missing modern ``## Contents``). It is deliberately **independent of
the vdocs code under test** — all detection is inlined here — so it can serve as an honest
before/after regression gate (the kickoff's acceptance check). Run it before remediation to fix
the baseline and after to prove the counts fall to ~0.

Usage:
    python scripts/audit_gold_cleanup.py [--data-dir DIR] [--out REPORT.md]

Writes a markdown report (corpus rollup + per-document table) and prints the rollup to stdout.
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

# --- detection vocab (inlined; not imported from vdocs — this is an independent oracle) ----------
_MONTH = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|"
    r"Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
_MONTH_YEAR_RE = re.compile(rf"\b{_MONTH}\.?,?\s+(\d{{4}})\b", re.IGNORECASE)
_FM_RE = re.compile(r"^---\n(.*?)\n---\n(?:\n)?(.*)$", re.DOTALL)
_ATX_RE = re.compile(r"^(#+)\s+(.*?)\s*$")

# A revision-history section header in any corpus form: ATX (#…), bold (**…**), blockquote (> …),
# or a bare plain line — case-insensitive — for one of the curated revision-heading texts.
_REV_TEXTS = {
    "revision history",
    "revisions",
    "documentation revisions",
    "documentation revision history",
    "template revision history",
}
_DEAD_TEXT_RE = re.compile(r"^[>#*\s]+|[*\s:]+$")

# A legacy page-numbered TOC entry: ``[Title [12](#anchor)](#anchor)`` — the inner page number is a
# plain integer, a roman numeral (front matter), or a chapter-dash form (``7-9``).
_LEGACY_TOC_ENTRY_RE = re.compile(r"(?i)\[.*\[[0-9ivxlcdm\-]+\]\(#[^)]*\)\]\(#[^)]*\)")
# Only the *legacy* contents header counts here — the modern derived ``## Contents`` (which
# normalizes to bare "contents") must NOT be flagged as a legacy TOC.
_TOC_TEXTS = {"table of contents"}
# The descriptive revision boilerplate ("the following table displays the revision history…").
# Precise on purpose — it must mention the *revision history*, so a plain table caption
# ("Table 2: … Display Description") is not mistaken for it.
_REV_BOILERPLATE_RE = re.compile(
    r"(?i)displays the revision history|lists the history for each revision"
)
_HTML_TABLE_HDR_RE = re.compile(r"(?is)<t[hd]>\s*(?:<[^>]+>\s*)*date")


def _norm_heading(text: str) -> str:
    return _DEAD_TEXT_RE.sub("", text.strip()).strip().lower()


def _is_rev_heading_line(line: str) -> bool:
    return _norm_heading(line) in _REV_TEXTS


def _is_toc_heading_line(line: str) -> bool:
    return _norm_heading(line) in _TOC_TEXTS


def _split_body(text: str) -> str:
    m = _FM_RE.match(text)
    return m.group(2) if m else text


def _first_real_heading_idx(lines: list[str]) -> int:
    """Index of the first real section heading (where the document proper begins) — the cover /
    revision / TOC furniture sits above it. ``len(lines)`` if there is no such heading."""
    skip = _REV_TEXTS | _TOC_TEXTS | {"contents"}
    for i, ln in enumerate(lines):
        m = _ATX_RE.match(ln)
        if m and m.group(2).strip().lower() not in skip:
            return i
    return len(lines)


_TAG_RE = re.compile(r"<[^>]+>")
# The cover sits at the very top; bound the title-page region so a deep section heading can't drag
# unrelated content (a revision-table date cell, an in-prose date example) into the P1 check.
_COVER_WINDOW = 60


def _visible(line: str) -> str:
    """The line's visible text — HTML tags removed — so a ``Department of Veterans Affairs`` that is
    only an ``<img alt=…>`` attribute or a ``<td>`` date cell is not mistaken for furniture."""
    return _TAG_RE.sub("", line)


def _is_dva_imprint(line: str) -> bool:
    """A VA-imprint *cover* line — the visible text (list/blockquote markers stripped) **begins
    with** the department name — as opposed to a prose mention (``…pursuant to Department of
    Veterans Affairs…``) or a contributor entry, which are not legacy title-page furniture."""
    v = re.sub(r"^[\s>#*•.\-\[\]]+", "", _visible(line)).strip().lower()
    return v.startswith("department of veterans affairs") or v.startswith(
        "u.s. department of veterans affairs"
    )


def audit_body(text: str) -> dict:
    body = _split_body(text)
    lines = body.split("\n")
    region = lines[: min(_first_real_heading_idx(lines), _COVER_WINDOW)]

    # --- P1: legacy title page in the (bounded) cover region — visible text only --------------
    dva = any(_is_dva_imprint(ln) for ln in region)
    blank_page = sum("intentionally left blank" in _visible(ln).lower() for ln in lines)
    # a cover date is a short standalone Month-YYYY line, not a date inside an HTML table cell/tag
    cover_date = any("<" not in ln and _MONTH_YEAR_RE.search(ln) and len(ln) < 80 for ln in region)
    p1 = dva or cover_date or blank_page > 0

    # --- P2: revision history in any form ----------------------------------------------------
    rev_headers = [ln for ln in lines if _is_rev_heading_line(ln)]
    html_rev_table = False
    for i, ln in enumerate(lines):
        if _is_rev_heading_line(ln):
            window = "\n".join(lines[i : i + 25])
            if "<table" in window.lower() and _HTML_TABLE_HDR_RE.search(window):
                html_rev_table = True
                break
    rev_boiler = any(_REV_BOILERPLATE_RE.search(ln) for ln in lines)
    p2 = bool(rev_headers) or html_rev_table or rev_boiler

    # --- P3: legacy text TOC -----------------------------------------------------------------
    legacy_toc_lines = sum(bool(_LEGACY_TOC_ENTRY_RE.search(ln)) for ln in lines)
    toc_header = any(_is_toc_heading_line(ln) for ln in lines)
    p3 = legacy_toc_lines > 0 or toc_header

    has_contents = any(ln.strip().lower() == "## contents" for ln in lines)

    return {
        "p1": p1,
        "p1_dva": dva,
        "p1_date": cover_date,
        "p1_blank": blank_page,
        "p2": p2,
        "p2_header": bool(rev_headers),
        "p2_html_table": html_rev_table,
        "p2_boiler": rev_boiler,
        "rev_headers": [_norm_heading(h) for h in rev_headers],
        "p3": p3,
        "p3_toc_lines": legacy_toc_lines,
        "p3_toc_header": toc_header,
        "missing_contents": not has_contents,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    default_data = os.environ.get("DATA_DIR", str(Path.home() / "data" / "vdocs"))
    ap.add_argument("--data-dir", default=default_data)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    root = Path(args.data_dir) / "documents" / "gold" / "consolidated"
    bodies = sorted(root.rglob("body.md"))
    rows = []
    for bp in bodies:
        rel = bp.parent.relative_to(root).as_posix()
        rows.append((rel, audit_body(bp.read_text(encoding="utf-8"))))

    n = len(rows)
    p1 = sum(r["p1"] for _, r in rows)
    p1_blank = sum(r["p1_blank"] > 0 for _, r in rows)
    p2 = sum(r["p2"] for _, r in rows)
    p2_hdr = sum(r["p2_header"] for _, r in rows)
    p2_html = sum(r["p2_html_table"] for _, r in rows)
    p2_boiler = sum(r["p2_boiler"] for _, r in rows)
    p3 = sum(r["p3"] for _, r in rows)
    p3_hdr = sum(r["p3_toc_header"] for _, r in rows)
    missing = sum(r["missing_contents"] for _, r in rows)
    clean = sum(not (r["p1"] or r["p2"] or r["p3"]) for _, r in rows)
    total_toc_lines = sum(r["p3_toc_lines"] for _, r in rows)

    def pct(x: int) -> str:
        return f"{round(100 * x / n)}%" if n else "0%"

    out = []
    out.append("# Gold Consolidated — Title-Page/Revision/TOC Cleanup Audit\n")
    out.append(f"_Audit of `{root}/*/*/body.md` — {n} documents._\n")
    out.append("## Corpus rollup\n")
    out.append("| Check | Affected docs | % |")
    out.append("|---|---:|---:|")
    out.append(f"| **P1 — Legacy title page** | {p1} | {pct(p1)} |")
    out.append(f"|   ↳ 'intentionally left blank' lines | {p1_blank} | {pct(p1_blank)} |")
    out.append(f"| **P2 — Revision history present** (any form) | {p2} | {pct(p2)} |")
    out.append(f"|   ↳ revision-history section header | {p2_hdr} | {pct(p2_hdr)} |")
    out.append(f"|   ↳ HTML revision table | {p2_html} | {pct(p2_html)} |")
    out.append(f"|   ↳ descriptive boilerplate | {p2_boiler} | {pct(p2_boiler)} |")
    out.append(f"| **P3 — Legacy text TOC present** (any form) | {p3} | {pct(p3)} |")
    p3_entry_docs = sum(r["p3_toc_lines"] > 0 for _, r in rows)
    out.append(f"|   ↳ page-numbered double-bracket TOC lines (docs) | {p3_entry_docs} | |")
    out.append(f"|   ↳ 'Table of Contents' header | {p3_hdr} | {pct(p3_hdr)} |")
    out.append(f"| **Missing modern `## Contents`** | {missing} | {pct(missing)} |")
    out.append(f"| **Clean on all 3 problems** | {clean} | {pct(clean)} |\n")
    out.append(f"Total legacy TOC lines across corpus: **{total_toc_lines}**.\n")

    out.append("## Per-document findings (docs needing work)\n")
    out.append(
        "Legend: **T**=title page · **R**=revision history · **L**=legacy TOC · "
        "**noTOC**=missing modern Contents"
    )
    out.append("| Doc | T | R | L | legacy-TOC lines | rev header(s) |")
    out.append("|---|:--:|:--:|:--:|---:|---|")
    for rel, r in sorted(rows, key=lambda kv: -kv[1]["p3_toc_lines"]):
        if not (r["p1"] or r["p2"] or r["p3"]):
            continue
        t = "✓" if r["p1"] else ""
        rr = "✓" if r["p2"] else ""
        ll = "✓" if r["p3"] else ""
        notoc = " **noTOC**" if r["missing_contents"] else ""
        hdrs = "; ".join(dict.fromkeys(r["rev_headers"]))
        out.append(f"| {rel} | {t} | {rr} | {ll} | {r['p3_toc_lines']} | {hdrs}{notoc} |")

    report = "\n".join(out) + "\n"
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
    # rollup to stdout (the regression numbers)
    print(
        f"docs={n} P1={p1} P2={p2}(hdr={p2_hdr},html={p2_html},boiler={p2_boiler}) "
        f"P3={p3}(lines={total_toc_lines}) missing_contents={missing} clean={clean}"
    )


if __name__ == "__main__":
    main()
