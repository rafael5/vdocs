"""Pure assembler for `manifest` — corpus-manifest.json + discovery.json (§14.4, D3).

The agent "front door": counts + the stable-ID scheme + the MCP capability manifest, assembled from
corpus counts the driver gathers (no I/O here, and time is passed in). The load-bearing rule is the
**optional `vectors.db`** (D3): with no embedding info the semantic capability is *off* and the
embedding fields are omitted; once `embed` (Phase 6) writes `vectors.db`, a re-run passes the model
info and flips semantic on — the same "optional produces don't gate" rule as `convert`'s `assets`.
"""

from __future__ import annotations

from typing import Any

# The stable-ID contract (§5.5) — advertised so an agent can resolve any citation deterministically.
ID_SCHEME = {
    "doc_key": "<safe_app>/<doc_slug> — the URL-safe document key; MCP resource + section-id base",
    "doc_id": "<app_code>:<doc_slug> — the inventory join key (kept alongside doc_key)",
    "section_id": "<doc_key>/<heading_slug> — the retrieval chunk id (matches refs.yaml)",
    "entity_id": "<type>:<canonical_name> — the (type, canonical-name) entity id",
}


def _capabilities(*, vectors: bool) -> dict[str, bool]:
    """The four MCP retrieval modes (§14.1). Lexical/structured/graph are always available off
    `index.db`; semantic depends on `vectors.db` (absent in Phase 4 ⇒ off, D3)."""
    return {"lexical": True, "structured": True, "graph": True, "semantic": vectors}


def corpus_manifest(
    counts: dict[str, Any],
    *,
    tool_ver: str,
    generated_at: str,
    embedding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The corpus manifest: counts, lineage, the ID scheme, and the capability manifest.
    ``embedding`` is the model id+version when `vectors.db` exists, else ``None`` (semantic off)."""
    return {
        "schema_version": 1,
        "tool_ver": tool_ver,
        "generated_at": generated_at,
        "counts": dict(counts),
        "id_scheme": ID_SCHEME,
        "embedding": embedding,
        "capabilities": _capabilities(vectors=embedding is not None),
    }


def discovery_descriptor(
    counts: dict[str, Any], *, tool_ver: str, embedding: dict[str, Any] | None = None
) -> dict[str, Any]:
    """The machine discovery descriptor (`discovery.json`): corpus schema + entity-type vocabulary +
    the ID scheme + MCP capabilities — what an agent reads to understand the corpus without crawling
    it (§14.4)."""
    return {
        "schema_version": 1,
        "tool_ver": tool_ver,
        "id_scheme": ID_SCHEME,
        "entity_types": sorted((counts.get("entities_by_type") or {}).keys()),
        "counts": {
            "documents": counts.get("documents", 0),
            "version_groups": counts.get("version_groups", 0),
            "searchable_sections": counts.get("sections_searchable", 0),
            "entities": counts.get("entities", 0),
        },
        "embedding": embedding,
        "capabilities": _capabilities(vectors=embedding is not None),
    }
