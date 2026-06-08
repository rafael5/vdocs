"""Lexical retrieval over `index.db` — the live slice of the §14 hybrid engine, surfaced as
`vdocs ask` and (later) the MCP `search()` tool.

FTS5 over `chunks_fts` (the `is_latest` search-chunk surface — prior versions and container/hollow
sections are excluded at index time, §14.6), joined back to `documents`/`doc_sections` so every hit
is **pre-cited**: the stable `section_id`/`doc_key`, the document + section titles, a snippet, a
relevance score, and the resolved gold `body_path`. Read-only (opened via `db.connect` read-only,
§14.5). Semantic fusion (RRF) lands when `embed` writes `vectors.db` (Phase 6).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from vdocs.kernel import db
from vdocs.server import ids
from vdocs.server import search_pure as sp

# Repo-relative `registries/` (same default resolution as `config.Settings.registries`, but without
# requiring a configured lake — the registry is version-controlled repo data, §9.7).
_GLOSSARY_EXPANSIONS = (
    Path(__file__).resolve().parents[3] / "registries" / "glossary" / "expansions.yaml"
)


@lru_cache(maxsize=1)
def default_expansions() -> dict[str, str]:
    """The acronym → expansion query-expansion map (L1.3), loaded once from the glossary registry;
    `{}` if absent (expansion is then a no-op). Used by `lexical_search` so the CLI and the
    measurement harness expand identically."""
    if not _GLOSSARY_EXPANSIONS.is_file():
        return {}
    data = yaml.safe_load(_GLOSSARY_EXPANSIONS.read_text(encoding="utf-8")) or {}
    return {str(k): str(v) for k, v in (data.get("expansions") or {}).items()}


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

    `expansions` (acronym → expansion) is an **opt-in** glossary query-expansion map; pass
    `default_expansions()` to enable it. It is **off by default** because measurement (L1.3, the
    19-query golden set) showed it *regresses* lexical quality on this corpus — `doc_title`
    weighting already captures the acronym signal, and expansion only dilutes it."""
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
