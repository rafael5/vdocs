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
    "chunk_id", "section_id", "doc_key", "title", "doc_title", "section_path", "body",
)  # fmt: skip

# Per-column bm25 weights (higher = more influence on rank).
# L1.1 finding: weighting *section* headings (`title`/`section_path`) gives no lift here — VistA
# section titles are generic and the answer is in the body — so those stay a mild neutral prior.
# L1.2 adds `doc_title` (the document title), which carries the doc-defining token (e.g. "KAAJEE").
# Sweep on the dev golden set picked doc_title=2.5: KAAJEE 0.0→0.43, mean nDCG@10 0.387→0.469;
# heavier (≥4) over-promotes common title tokens ("VistA") and tanks `hwsc-rest`. Re-tune at L4.2.
FTS_WEIGHTS: dict[str, float] = {
    "doc_title": 2.5, "title": 2.0, "section_path": 1.5, "body": 1.0,
}  # fmt: skip


def acronym_phrase_clauses(tokens: list[str], expansions: dict[str, str]) -> list[str]:
    """For any token whose upper-case form is a known acronym (≥3 chars, L1.3), the expansion as a
    single **quoted phrase** FTS5 clause (e.g. `"healthevet web services client"`). A *phrase* —
    not loose OR-tokens — is the load-bearing choice: it matches only the exact spelled-out
    sequence, adding precise signal without injecting common words ("Kernel", "System", "Web") that
    dilute the rare-acronym match and drown a `doc_title` win. De-duped, order-preserving."""
    clauses: list[str] = []
    seen: set[str] = set()
    for t in tokens:
        if len(t) < 3:
            continue
        exp = expansions.get(t.upper())
        if not exp:
            continue
        words = _TOKEN.findall(exp)
        phrase = " ".join(words).lower()  # FTS5 is case-insensitive; lower-case is deterministic
        if len(words) >= 2 and phrase not in seen:
            clauses.append(f'"{phrase}"')
            seen.add(phrase)
    return clauses


def fts_match_query(text: str, expansions: dict[str, str] | None = None) -> str:
    """A safe FTS5 MATCH string from free text: alnum tokens (length ≥ 2), each double-quoted,
    OR-joined. Returns `""` when no usable token remains (the caller treats that as no results).

    When `expansions` is given (acronym → expansion), each query acronym also contributes the
    spelled-out form as one **precise phrase clause** (L1.3); omitting it preserves the
    bare-tokenisation contract."""
    tokens = [t for t in _TOKEN.findall(text or "") if len(t) >= 2]
    clauses = [f'"{t}"' for t in tokens]
    if expansions:
        clauses += acronym_phrase_clauses(tokens, expansions)
    return " OR ".join(clauses)


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
