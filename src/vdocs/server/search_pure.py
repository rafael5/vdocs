"""Pure helpers for the lexical search slice (§14.7) — no I/O, just query shaping.

The load-bearing piece is `fts_match_query`: free user text → a **safe** FTS5 MATCH expression.
Quoting every token keeps a stray term (e.g. a bare `OR`, `*`, or `:`) from being parsed as an FTS5
operator/column-filter, and OR-joining favours recall (bm25 still ranks multi-term hits highest).
"""

from __future__ import annotations

import re

_TOKEN = re.compile(r"[A-Za-z0-9_]+")


def fts_match_query(text: str) -> str:
    """A safe FTS5 MATCH string from free text: alnum tokens (length ≥ 2), each double-quoted,
    OR-joined. Returns `""` when no usable token remains (the caller treats that as no results)."""
    tokens = [t for t in _TOKEN.findall(text or "") if len(t) >= 2]
    return " OR ".join(f'"{t}"' for t in tokens)
