"""Faceted (focused) search over `index.db` (LF) — narrow by structured facets, then content-search
within the narrowed set.

The "focused information retrieval" path: declare facets (doc_type / audience / package / entity)
that collapse the corpus to a tiny homogeneous set, then run BM25 over the restricted `chunks_fts`.
A serving-layer read over columns the pipeline already produces — no pipeline/indexing change. The
within-facet ranking reuses `search_pure`, so it matches `vdocs ask`. Read-only.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from vdocs.kernel import db
from vdocs.server import facets_pure as fp
from vdocs.server import ids
from vdocs.server import search_pure as sp

_AUDIENCES_YAML = (
    Path(__file__).resolve().parents[3] / "registries" / "inventory" / "audiences.yaml"
)
_BM25 = sp.bm25_expr("chunks_fts")
_BODY_COL = sp.FTS_COLUMNS.index("body")


@lru_cache(maxsize=1)
def default_audiences() -> dict[str, str]:
    """The `doc_type → audience` map (LF.2), loaded once from the registry; `{}` if absent."""
    if not _AUDIENCES_YAML.is_file():
        return {}
    data = yaml.safe_load(_AUDIENCES_YAML.read_text(encoding="utf-8")) or {}
    return {str(k): str(v) for k, v in (data.get("audiences") or {}).items()}


def facet_catalog(index_db: Path) -> dict[str, list[tuple[str, int]]]:
    """The navigable facets (value → #latest-docs) the UI/CLI presents so a user picks, not guesses:
    `doc_type`, `app_code`, `pkg_ns`, derived `audience`, `entity_type`. One GROUP BY per facet."""
    conn = db.connect(index_db, read_only=True)
    try:
        out: dict[str, list[tuple[str, int]]] = {}
        for col in ("doc_type", "app_code", "pkg_ns"):
            out[col] = [
                (r[0], r[1])
                for r in conn.execute(
                    f"SELECT {col}, COUNT(*) c FROM documents "
                    f"WHERE is_latest = 1 AND {col} <> '' GROUP BY {col} ORDER BY c DESC, {col}"
                )
            ]
        aud_map = default_audiences()
        aud: dict[str, int] = {}
        for dt, c in conn.execute(
            "SELECT doc_type, COUNT(*) FROM documents WHERE is_latest = 1 GROUP BY doc_type"
        ):
            key = aud_map.get(dt, "any")
            aud[key] = aud.get(key, 0) + c
        out["audience"] = sorted(aud.items(), key=lambda x: (-x[1], x[0]))
        out["entity_type"] = [
            (r[0], r[1])
            for r in conn.execute(
                "SELECT type, COUNT(*) FROM entities GROUP BY type ORDER BY 2 DESC, type"
            )
        ]
        return out
    finally:
        conn.close()


def faceted_search(
    index_db: Path,
    *,
    doc_type: list[str] | None = None,
    app: list[str] | None = None,
    pkg_ns: list[str] | None = None,
    audience: str | None = None,
    entity: str | None = None,
    query: str | None = None,
    k: int = 10,
    audiences: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Narrow by facets (layers 1–3) then content-search (layer 4). Returns
    `{candidate_docs, hits}` — `hits` are ranked, pre-cited chunk hits when `query` is given, else
    the narrowed doc list. `audience` resolves to `doc_type` codes via the audience map."""
    aud_map = default_audiences() if audiences is None else audiences
    eff_doc_type = fp.resolve_doc_types(doc_type, audience, aud_map)
    where, params = fp.narrow_clause(doc_type=eff_doc_type or None, app=app, pkg_ns=pkg_ns)
    conn = db.connect(index_db, read_only=True)
    try:
        doc_keys = [
            r[0] for r in conn.execute(f"SELECT doc_key FROM documents WHERE {where}", params)
        ]
        if entity:  # layer 3: restrict to docs that mention the entity
            mentioned = {
                r[0]
                for r in conn.execute(
                    "SELECT DISTINCT doc_key FROM entity_mentions WHERE entity_id = ?", (entity,)
                )
            }
            doc_keys = [d for d in doc_keys if d in mentioned]
        if not doc_keys:
            return {"candidate_docs": 0, "hits": []}
        ph = ", ".join("?" for _ in doc_keys)
        if query:
            match = sp.fts_match_query(query)
            if not match:
                return {"candidate_docs": len(doc_keys), "hits": []}
            rows = conn.execute(
                f"SELECT f.section_id, f.doc_key, d.title AS doc_title, "
                f"snippet(chunks_fts, {_BODY_COL}, '[', ']', ' … ', 12) AS snippet, "
                f"{_BM25} AS bm25 FROM chunks_fts f JOIN documents d ON d.doc_key = f.doc_key "
                f"WHERE chunks_fts MATCH ? AND f.doc_key IN ({ph}) ORDER BY {_BM25} LIMIT ?",
                [match, *doc_keys, k],
            ).fetchall()
            hits = [
                {
                    "section_id": r["section_id"],
                    "doc_key": r["doc_key"],
                    "doc_title": r["doc_title"],
                    "snippet": r["snippet"],
                    "score": round(-float(r["bm25"]), 4),
                    "uri": ids.section_uri(r["section_id"]),
                }
                for r in rows
            ]
        else:  # pure browse: the narrowed docs
            rows = conn.execute(
                f"SELECT doc_key, title AS doc_title FROM documents "
                f"WHERE doc_key IN ({ph}) ORDER BY doc_key LIMIT ?",
                [*doc_keys, k],
            ).fetchall()
            hits = [{"doc_key": r["doc_key"], "doc_title": r["doc_title"]} for r in rows]
        return {"candidate_docs": len(doc_keys), "hits": hits}
    finally:
        conn.close()
