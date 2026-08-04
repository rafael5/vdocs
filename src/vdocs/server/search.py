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
    after a rebuild). `index_db` is a `str` so the result is hashable/cacheable.

    **Scope, measured 2026-08-04 (SL.1).** On the production collection this map holds exactly
    **one** entry (`200 → NEW PERSON`), against 233 FileMan files that are genuinely split across a
    number and a name vocabulary. The limit is here, not in the curation queue: `skl_expansion_map`
    drops a two-digit number (`len(key) >= 3`, enforced again in `acronym_phrase_clauses`) and any
    decimal number (`.isalnum()` — and beneath that, FTS5 tokenises `50.7` into `50` and `7`, so a
    single-token key could never match one). Of 28 identifier-shaped questions that fail for
    vocabulary reasons alone, this repairs 3; the ceiling for any expansion is 23. Do not describe
    this as a collection-wide vocabulary fix — see `docs/proposals/vdocs-quality-synonym-layer/`."""
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

_SELECT_TEMPLATE = """
SELECT f.chunk_id, f.section_id, f.doc_key, f.title AS section_title,
       f.section_path, LENGTH(f.body) AS body_len,
       snippet(chunks_fts, {body}, '[', ']', ' … ', 16) AS snippet,
       {bm25} AS bm25,
       d.doc_id, d.title AS doc_title, d.app_code, d.doc_type, d.pkg_ns
FROM chunks_fts f
JOIN documents d ON d.doc_key = f.doc_key
WHERE chunks_fts MATCH ?{filters}
ORDER BY {bm25}
LIMIT ?
"""

_SELECT = _SELECT_TEMPLATE.format(body=_BODY_COL, bm25=_BM25, filters="{filters}")


# --- "an index miss is not corpus absence" — ONE rule, THREE surfaces (P6.3, audit R-11) ---------
# The MCP `search` tool, `vdocs ask`, and `ask --json` must say the same thing about a zero-hit
# search, because an agent may be reading any of them. Before P6.3 the CLI said "no matches in the
# gold corpus." — the precise phrasing the MCP surface is forbidden to emit, and the one that let
# four researchers report documented FileMan APIs as missing. It lives here, in the module all three
# already import, so a re-measure cannot update two surfaces and leave the third lying.
#
# Coverage re-measured 2026-08-02 after P6.1b: ~89% of live sections carry indexed text; the
# residual 10.5% are bare headings whose substance sits in their subsections
# (`kernel.markdown.is_searchable`).
NOT_INDEXED_RULE = (
    "An empty result is a RETRIEVAL artefact, not a documentation gap: ~89% of live sections carry "
    "indexed text, and most of the 10.5% that do not are bare headings whose substance sits in "
    "their subsections. Prose can also live in the gold body.md and its rich-tables `tables/*.csv` "
    'sidecars. Read BOTH before you ever answer "not in the vdocs gold corpus".'
)
NO_MATCH_WARNING = f"NO INDEXED MATCH — this is not evidence of absence. {NOT_INDEXED_RULE}"

# --- how many results each kind of caller gets by default (RR.1) ---------------------------------
# Two callers, opposite trade-offs, so two constants — and they live HERE, with the rule above, for
# the same reason: the MCP `search` tool and `vdocs ask --json` both import this module, so a
# re-measure moves every assistant surface at once instead of leaving one stale.
#
# MEASURED on the production collection with the post-report-card key (109 judged answers): the
# share of correct answers a caller can see is 61.5% at k=8, **77.1% at k=15**, 78.0% at 20 and
# 79.8% at 25. Fifteen is the knee — it recovers nearly all of the reachable band, and going wider
# buys under a point. The old default of 8 was hiding roughly one correct answer in six from every
# assistant, which is why this was the cheapest step in the ranking effort.
ASSISTANT_DEFAULT_K = 15
# How much wider than `k` the ranking window is fetched, so RR.3's parent/child swap has the child
# available to promote. Three is enough for every measured case (the worst observed child rank was
# 15 against a parent at 1) and costs one FTS5 scan depth, not a second query.
_OVERFETCH = 3
# A person reading a terminal is the opposite case: a longer list is reading work, not free recall.
# The human `vdocs ask` display stays where it was; `--k` overrides both.
HUMAN_DISPLAY_K = 8


def search_envelope(hits: list[dict[str, Any]]) -> dict[str, Any]:
    """The shared result envelope: ``{hits, hit_count}`` — plus ``warning`` **only** when empty.

    A warning attached to every response trains clients to skip it, so it rides exactly the case it
    is about. Shared as a *builder*, not just a string, so the three surfaces cannot drift in shape
    either: an agent parses one thing whichever front door it came through."""
    out: dict[str, Any] = {"hits": hits, "hit_count": len(hits)}
    if not hits:
        out["warning"] = NO_MATCH_WARNING
    return out


def lexical_search(
    index_db: Path,
    query: str,
    *,
    k: int = 10,
    app: list[str] | None = None,
    doc_type: list[str] | None = None,
    expansions: dict[str, str] | None = None,
    weights: dict[str, float] | None = None,
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
    retired; the SKL data is entity-resolved, not common-word acronym noise).

    `weights` overrides the per-column bm25 weights for one call (default: the shipped
    `search_pure.FTS_WEIGHTS`). It exists so a weight sweep measures **this** function rather than a
    re-implementation of its query — the same discipline the golden harness follows by importing the
    engine instead of reproducing it. Production callers leave it None."""
    if expansions is None:
        expansions = skl_expansions(str(index_db))
    match = sp.fts_match_query(query, expansions)
    if not match:
        return []
    select = (
        _SELECT
        if weights is None
        else _SELECT_TEMPLATE.format(
            body=_BODY_COL, bm25=sp.bm25_expr("chunks_fts", weights=weights), filters="{filters}"
        )
    )
    filters: str = ""
    params: list[Any] = [match]
    for col, values in (("app_code", app), ("doc_type", doc_type)):
        if values:
            filters += f" AND d.{col} IN ({', '.join('?' for _ in values)})"
            params.extend(values)
    # Over-fetch, reorder, truncate (RR.3). A restating parent can hold rank 1 while the child that
    # carries the content sits at 15 — measured — so the window has to be wide enough for the child
    # to be *in* it before the pair can be swapped. With no twins in the window this is a no-op:
    # the reorder is stable, so the first `k` rows are exactly the rows `k` alone would have given.
    params.append(k * _OVERFETCH)
    conn = db.connect(index_db, read_only=True)
    try:
        rows = conn.execute(select.format(filters=filters), params).fetchall()
    finally:
        conn.close()
    ranked = sp.demote_restating_parents([dict(r) for r in rows])[:k]
    return [_hit(r) for r in ranked]


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
