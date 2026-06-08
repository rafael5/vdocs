"""Pure helpers for the lexical search slice (§14.7) — no I/O, just query shaping.

The load-bearing piece is `fts_match_query`: free user text → a **safe** FTS5 MATCH expression.
Quoting every token keeps a stray term (e.g. a bare `OR`, `*`, or `:`) from being parsed as an FTS5
operator/column-filter, and OR-joining favours recall (bm25 still ranks multi-term hits highest).

`bm25_weights`/`bm25_expr` build the **field-weighted** ranking expression (L1.1): a doc-defining
token in a heading should outrank the same token buried in prose, so `title`/`section_path` carry
more weight than `body`. The column order here is the single source of truth and **must match the
`chunks_fts` schema in `stages/index/stage.py`** (a mismatch silently mis-weights columns).
"""

from __future__ import annotations

import re

_TOKEN = re.compile(r"[A-Za-z0-9_]+")

# FTS5 column order of `chunks_fts` — MUST match the schema in `stages/index/stage.py`.
# (The first three are UNINDEXED, so their weight is inert; kept for positional correctness since
# FTS5 bm25() takes one weight per column in declaration order.)
FTS_COLUMNS: tuple[str, ...] = (
    "chunk_id", "section_id", "doc_key", "title", "section_path", "body",
)  # fmt: skip

# Per-column bm25 weights (higher = more influence on rank).
# L1.1 finding (dev golden set): weighting *section* headings gives NO lift here — VistA section
# titles are generic ("Installation", "Overview") and the answer is in the body, so aggressive
# heading weights (8/4) regress and mild ones (2/1.5) are measured-neutral. Kept mild as a harmless
# prior; the real lever for the doc-defining-token case (KAAJEE) is `doc_title` (L1.2), which is not
# yet an FTS column. Re-tune once doc_title lands and the golden set grows (L4.2).
FTS_WEIGHTS: dict[str, float] = {"title": 2.0, "section_path": 1.5, "body": 1.0}


def fts_match_query(text: str) -> str:
    """A safe FTS5 MATCH string from free text: alnum tokens (length ≥ 2), each double-quoted,
    OR-joined. Returns `""` when no usable token remains (the caller treats that as no results)."""
    tokens = [t for t in _TOKEN.findall(text or "") if len(t) >= 2]
    return " OR ".join(f'"{t}"' for t in tokens)


def bm25_weights(
    columns: tuple[str, ...] = FTS_COLUMNS, weights: dict[str, float] | None = None
) -> list[float]:
    """One bm25 weight per column, in column order; columns absent from `weights` default to 1.0."""
    w = FTS_WEIGHTS if weights is None else weights
    return [float(w.get(c, 1.0)) for c in columns]


def bm25_expr(
    table: str, columns: tuple[str, ...] = FTS_COLUMNS, weights: dict[str, float] | None = None
) -> str:
    """The `bm25(<table>, w0, w1, …)` SQL expression with per-column weights (floats we control —
    no user input — so they are safe to inline as literals)."""
    args = ", ".join(repr(x) for x in bm25_weights(columns, weights))
    return f"bm25({table}, {args})"
