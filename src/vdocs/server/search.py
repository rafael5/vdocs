"""Lexical retrieval over `index.db` — the live slice of the §14 hybrid engine, surfaced as
`vdocs ask` and (later) the MCP `search()` tool.

FTS5 over `chunks_fts` (the `is_latest` search-chunk surface — prior versions and container/hollow
sections are excluded at index time, §14.6), joined back to `documents`/`doc_sections` so every hit
is **pre-cited**: the stable `section_id`/`doc_key`, the document + section titles, a snippet, a
relevance score, and the resolved gold `body_path`. Read-only (opened via `db.connect` read-only,
§14.5). Semantic fusion (RRF) lands when `embed` writes `vectors.db` (Phase 6).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vdocs.kernel import db
from vdocs.server import ids
from vdocs.server import search_pure as sp

# 0-based column index of `body` in the chunks_fts virtual table — the snippet() target column.
_BODY_COL = 5

_SELECT = """
SELECT f.chunk_id, f.section_id, f.doc_key, f.title AS section_title,
       snippet(chunks_fts, {body}, '[', ']', ' … ', 16) AS snippet,
       bm25(chunks_fts) AS bm25,
       d.doc_id, d.title AS doc_title, d.app_code, d.doc_type, d.pkg_ns
FROM chunks_fts f
JOIN documents d ON d.doc_key = f.doc_key
WHERE chunks_fts MATCH ?{filters}
ORDER BY bm25(chunks_fts)
LIMIT ?
""".format(body=_BODY_COL, filters="{filters}")


def lexical_search(
    index_db: Path,
    query: str,
    *,
    k: int = 10,
    app: list[str] | None = None,
    doc_type: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Rank `is_latest` chunks against `query` by BM25 and return up to `k` pre-cited hits.

    `app`/`doc_type` are optional structured pre-filters (applied as a WHERE clause *before*
    ranking, §14.2). Returns `[]` for an empty/no-usable-token query. Each hit:
    `{score, section_id, doc_key, doc_id, doc_title, section_title, app_code, doc_type, snippet,
    uri, body_path}` (`score` = −bm25, so higher is more relevant)."""
    match = sp.fts_match_query(query)
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
