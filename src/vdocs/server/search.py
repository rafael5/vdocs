"""Lexical retrieval over `index.db` — the search engine behind `vdocs ask` (§14).

FTS5 over `chunks_fts` (the `is_latest` search-chunk surface — prior versions and container/hollow
sections are excluded at index time, §14.6), joined back to `documents`/`doc_sections` so every hit
is **pre-cited**: the stable `section_id`/`doc_key`, the document + section titles, a snippet, a
relevance score, and the resolved gold `body_path`. Read-only (opened via `db.connect` read-only,
§14.5). Lexical-first and offline — no semantic/vector path.
"""

from __future__ import annotations

import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Any

from vdocs.kernel import db
from vdocs.server import ids
from vdocs.server import search_pure as sp


@lru_cache(maxsize=8)
def skl_expansions(index_db: str) -> dict[str, str]:
    """The SKL-grounded query-expansion map (S3.4): a FileMan file *number* → its canonical name
    phrase, read from `index.db:entity_skl` (the `merge` projection). Replaces the hand-seeded
    `registries/glossary/expansions.yaml` (L1.3) with **entity-resolved** data — one source the CLI
    and the measurement harness expand identically. `{}` when the SKL table is absent (a pre-`merge`
    index.db) or empty, so expansion is then a no-op. Cached per index.db path (call `cache_clear()`
    after a rebuild). `index_db` is a `str` so the result is hashable/cacheable."""
    path = Path(index_db)
    if not path.exists():
        return {}
    conn = db.connect(path, read_only=True)
    try:
        rows = conn.execute("SELECT canonical, canonical_name FROM entity_skl").fetchall()
    except sqlite3.OperationalError:
        return {}  # pre-merge index.db has no entity_skl table
    finally:
        conn.close()
    return sp.skl_expansion_map([(r[0], r[1]) for r in rows])


# 0-based column index of `body` in chunks_fts (the snippet() target) — single-sourced from the
# column order in `search_pure` so it can't drift from the FTS schema.
_BODY_COL = sp.FTS_COLUMNS.index("body")

# Field-weighted bm25 (L1.1): a doc-defining token in `title`/`section_path` outranks the same token
# buried in `body`. Built once from the single-source column order/weights in `search_pure`.
_BM25 = sp.bm25_expr("chunks_fts")

_SELECT = """
SELECT f.chunk_id, f.section_id, f.doc_key, f.title AS section_title,
       snippet(chunks_fts, {body}, '[', ']', ' … ', 16) AS snippet,
       {bm25} AS bm25,
       d.doc_id, d.title AS doc_title, d.app_code, d.doc_type, d.pkg_ns
FROM chunks_fts f
JOIN documents d ON d.doc_key = f.doc_key
WHERE chunks_fts MATCH ?{filters}
ORDER BY {bm25}
LIMIT ?
""".format(body=_BODY_COL, bm25=_BM25, filters="{filters}")


def lexical_search(
    index_db: Path,
    query: str,
    *,
    k: int = 10,
    app: list[str] | None = None,
    doc_type: list[str] | None = None,
    expansions: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Rank `is_latest` chunks against `query` by BM25 and return up to `k` pre-cited hits.

    `app`/`doc_type` are optional structured pre-filters (applied as a WHERE clause *before*
    ranking, §14.2). Returns `[]` for an empty/no-usable-token query. Each hit:
    `{score, section_id, doc_key, doc_id, doc_title, section_title, app_code, doc_type, snippet,
    uri, body_path}` (`score` = −bm25, so higher is more relevant).

    `expansions` (token → name phrase) is the query-expansion map. **Default (None) → the
    SKL-grounded `skl_expansions(index_db)`** (S3.4): a number/identifier query expands to the
    entity's spelled-out name (`file #200` → `NEW PERSON`), the principled vocabulary-mismatch fix.
    Pass `{}` to disable expansion (the old hand-seeded glossary path that *regressed* — L1.3 — is
    retired; the SKL data is entity-resolved, not common-word acronym noise)."""
    if expansions is None:
        expansions = skl_expansions(str(index_db))
    match = sp.fts_match_query(query, expansions)
    if not match:
        return []
    filters: str = ""
    params: list[Any] = [match]
    for col, values in (("app_code", app), ("doc_type", doc_type)):
        if values:
            filters += f" AND d.{col} IN ({', '.join('?' for _ in values)})"
            params.extend(values)
    params.append(k)
    conn = db.connect(index_db, read_only=True)
    try:
        rows = conn.execute(_SELECT.format(filters=filters), params).fetchall()
    finally:
        conn.close()
    return [_hit(dict(r)) for r in rows]


def _hit(r: dict[str, Any]) -> dict[str, Any]:
    """Shape a result row into a pre-cited hit (stable IDs + resolved gold body path + URI)."""
    return {
        "score": round(-float(r["bm25"]), 4),
        "section_id": r["section_id"],
        "doc_key": r["doc_key"],
        "doc_id": r["doc_id"],
        "doc_title": r["doc_title"],
        "section_title": r["section_title"],
        "app_code": r["app_code"],
        "doc_type": r["doc_type"],
        "snippet": r["snippet"],
        "uri": ids.section_uri(r["section_id"]),
        "body_path": ids.gold_body_relpath(r["app_code"], r["pkg_ns"], r["doc_type"], r["doc_key"]),
    }
