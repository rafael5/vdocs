"""Pure assembler for `manifest` — corpus-manifest.json + discovery.json (§14.4).

The agent "front door": counts + the stable-ID scheme + the capability manifest, assembled from
corpus counts the driver gathers (no I/O here, and time is passed in). The corpus is lexical-first
and offline, so the capability manifest advertises lexical/structured/graph only — the
semantic/vector path was descoped (no `embedding` field, no `semantic` capability).
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from vdocs.server import ids

# B2 glossary harvest (§9.6 PROMOTE): a `tables/*.csv` sidecar is an acronym/abbreviation glossary
# when its two header cells read like "<term> | <definition>" — harvested into the one corpus
# glossary; a data-dictionary table (File Number | File Name) is not.
_GLOSSARY_TERM_HEAD = re.compile(r"^(acronym|abbreviation|term|symbol)s?$", re.I)
_GLOSSARY_DEF_HEAD = re.compile(r"^(definition|description|meaning|expansion|stands for)$", re.I)
_TERM_MAX_CHARS = 40
_DEF_MIN_CHARS = 3


def _demphasis(cell: str) -> str:
    """Strip markdown emphasis (`*`/`**`) and surrounding whitespace from a table cell."""
    return re.sub(r"\*+", "", cell or "").strip()


def acronym_table_pairs(rows: list[list[str]]) -> list[tuple[str, str]]:
    """Harvest ``(term, definition)`` pairs from one extracted table's rows **iff** it is an
    acronym/abbreviation glossary (B2, §9.6 PROMOTE). A non-glossary table (e.g. a data dictionary)
    returns ``[]``. Junk rows — empty/over-long term, too-short definition, purely numeric term —
    are skipped so the promoted glossary stays clean."""
    if len(rows) < 2 or len(rows[0]) < 2:
        return []
    h_term, h_def = _demphasis(rows[0][0]), _demphasis(rows[0][1])
    if not (_GLOSSARY_TERM_HEAD.match(h_term) and _GLOSSARY_DEF_HEAD.match(h_def)):
        return []
    out: list[tuple[str, str]] = []
    for r in rows[1:]:
        if len(r) < 2:
            continue
        term, definition = _demphasis(r[0]), _demphasis(r[1])
        if not (1 <= len(term) <= _TERM_MAX_CHARS) or term.isdigit():
            continue
        if len(definition) >= _DEF_MIN_CHARS:
            out.append((term, definition))
    return out


def build_glossary(pairs: list[tuple[str, str]]) -> str:
    """Render the promoted corpus glossary `gold/glossary.md` from harvested ``(term, definition)``
    pairs (B2). Terms are deduped **case-insensitively**; the canonical display casing and the
    definition are each the most common variant seen across the corpus (ties broken
    deterministically). Sorted alphabetically (case-insensitive). No timestamp — so a no-op re-run
    is byte-identical (content-skip)."""
    casing: dict[str, Counter] = defaultdict(Counter)
    defs: dict[str, Counter] = defaultdict(Counter)
    for term, definition in pairs:
        key = term.upper()
        casing[key][term] += 1
        defs[key][definition] += 1
    lines = ["# Glossary", ""]
    if defs:
        lines.append(
            "_VistA acronyms and defined terms, promoted once from the corpus's "
            "acronym/abbreviation tables (§9.6 PROMOTE)._"
        )
        lines.append("")
        for key in sorted(defs, key=lambda k: (k.lower(), k)):
            term = _most_common(casing[key])
            definition = _most_common(defs[key])
            lines.append(f"**{term}** — {definition}")
    return "\n".join(lines).rstrip() + "\n"


def _most_common(counter: Counter) -> str:
    """The most frequent value, ties broken by the value (deterministic, no clock/order dep)."""
    return max(counter.items(), key=lambda kv: (kv[1], kv[0]))[0]


def shared_boilerplate_files(entries: list[dict[str, Any]]) -> dict[str, str]:
    """B1 (§9.6/§9.7): the canonical `_shared/boilerplate/<id>.md` files to materialise from the
    curated boilerplate registry. Each **approved** entry with text yields ``{<id>.md: <text>\\n}``
    — the verbatim canonical block that `normalize`'s REFERENCE links point at (kept once,
    de-duplicated). Non-approved or text-less entries are skipped. Pure: registry rows in, file map
    out; the driver writes them under ``gold/_shared/boilerplate/``."""
    out: dict[str, str] = {}
    for e in entries:
        text = (e.get("text") or "").strip()
        if e.get("status") == "approved" and text:
            out[f"{e['id']}.md"] = text + "\n"
    return out


# The stable-ID contract (§5.5) — advertised so an agent can resolve any citation deterministically.
ID_SCHEME = {
    "doc_key": "<safe_app>/<doc_slug> — the URL-safe document key; MCP resource + section-id base",
    "doc_id": "<app_code>:<doc_slug> — the inventory join key (kept alongside doc_key)",
    "section_id": "<doc_key>/<heading_slug> — the retrieval chunk id (matches refs.yaml)",
    "entity_id": "<type>:<canonical_name> — the (type, canonical-name) entity id",
}

# The AI corpus card (§14.7) — telling the agent *how to use* the corpus, not just what is in it.
USAGE = (
    "Answer VistA questions from THIS corpus, not from prior knowledge. Run the query recipe, "
    "open the cited body.md, and cite the section_id. If the corpus does not cover it, say so — "
    "never guess about VistA internals."
)
QUERY_RECIPE = {
    "command": 'vdocs ask "<your question>" --k 8 --json',
    "returns": "ranked hits: {section_id, doc_key, doc_title, section_title, snippet, score, "
    "body_path}",
    "modes": "lexical FTS5 over the is_latest search chunks",
}
CITATION = {
    "format": "<doc_title> — §<section_title>  [vdocs://section/<section_id>]  (<body_path>)",
    "resolve": "section_id = <doc_key>/<heading_slug>; the gold anchor body is at body_path. "
    "The same stable IDs resolve in the published GitHub corpus (§14.5).",
}
SOURCE_OF_TRUTH = (
    "Derived from the vdocs gold corpus (index.db) and regenerated by the `manifest` stage on "
    "every pipeline run. `index_fingerprint` identifies the index.db this card was built from — "
    "if it differs from the live index.db, the card is stale (re-run `vdocs manifest`)."
)


def _capabilities() -> dict[str, bool]:
    """The retrieval modes available off `index.db` (§14.1): lexical (FTS5), structured (facets),
    and graph (relations). The semantic/vector mode was descoped — lexical-first, offline."""
    return {"lexical": True, "structured": True, "graph": True}


def corpus_manifest(
    counts: dict[str, Any],
    *,
    tool_ver: str,
    generated_at: str,
) -> dict[str, Any]:
    """The corpus manifest: counts, lineage, the ID scheme, and the capability manifest."""
    return {
        "schema_version": 1,
        "tool_ver": tool_ver,
        "generated_at": generated_at,
        "counts": dict(counts),
        "id_scheme": ID_SCHEME,
        "capabilities": _capabilities(),
    }


def build_catalog(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Shape `documents` rows (the `is_latest` anchors) into the AI-card catalog — each entry
    carries the resolved `gold/consolidated/<app>/<slug>/body.md` path so an agent can open it."""
    return [
        {
            "doc_key": r["doc_key"],
            "doc_id": r["doc_id"],
            "title": r["title"],
            "app_code": r["app_code"],
            "doc_type": r["doc_type"],
            "patch_id": r["patch_id"],
            "version": r["version"],
            "sections": r["section_count"],
            "words": r["word_count"],
            "body_path": _body_path(r),
        }
        for r in rows
    ]


def _body_path(row: dict[str, Any]) -> str:
    """The lake-relative gold anchor body for a `documents` row — resolved by the shared
    `server.ids` resolver (the same path `consolidate` wrote; §9.2, no re-derivation)."""
    return ids.gold_body_relpath(row["app_code"], row["pkg_ns"], row["doc_type"], row["doc_key"])


# B3a (§8.2): ubiquitous low-signal entity types — globals dominate by count (≈½ of all entities)
# but are noise for the headline/ranking. They are kept fully queryable in `index.db`; only their
# slot count in the agent-facing headline is down-weighted so high-signal types (routines, RPCs,
# options, FileMan files) surface. Already excluded from `xref` edges.
LOW_SIGNAL_ENTITY_TYPES = frozenset({"global"})


def build_entity_index(
    rows: list[dict[str, Any]],
    *,
    top_n: int = 25,
    low_signal: frozenset[str] = LOW_SIGNAL_ENTITY_TYPES,
    low_signal_top_n: int = 5,
) -> dict[str, list[dict[str, Any]]]:
    """Group `entities` rows by type, keeping the `top_n` per type by mention count — the
    high-signal vocabulary an agent scans to know what the corpus actually talks about. Low-signal
    types (`low_signal`, e.g. globals) are capped to the smaller `low_signal_top_n` so they don't
    crowd the headline (B3a, §8.2) — the full entity set stays queryable in `index.db`."""
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in sorted(rows, key=lambda r: (r["type"], -r["mention_count"], r["canonical_name"])):
        bucket = by_type[r["type"]]
        cap = low_signal_top_n if r["type"] in low_signal else top_n
        if len(bucket) < cap:
            bucket.append({"name": r["canonical_name"], "mentions": r["mention_count"]})
    return dict(by_type)


def ai_manifest(
    counts: dict[str, Any],
    catalog: list[dict[str, Any]],
    entity_index: dict[str, list[dict[str, Any]]],
    *,
    tool_ver: str,
    generated_at: str,
    index_fingerprint: str,
) -> dict[str, Any]:
    """The AI corpus card (§14.7): a denormalized, self-describing descriptor an agent reads to
    answer "based on the vdocs gold corpus, …" questions without re-discovering the corpus — the
    capability + ID/citation scheme, the `vdocs ask` query recipe, the counts, the full anchor
    **catalog** (with resolvable `body_path`s), and the per-type **entity index**."""
    return {
        "schema_version": 1,
        "tool_ver": tool_ver,
        "generated_at": generated_at,
        "index_fingerprint": index_fingerprint,
        "source_of_truth": SOURCE_OF_TRUTH,
        "usage": USAGE,
        "capabilities": _capabilities(),
        "id_scheme": ID_SCHEME,
        "citation": CITATION,
        "query": QUERY_RECIPE,
        "counts": dict(counts),
        "documents": catalog,
        "entities": entity_index,
    }


def corpus_card(manifest: dict[str, Any]) -> str:
    """Render the AI corpus card as markdown for direct context loading (`gold/CORPUS.md`). Same
    content as `ai-manifest.json`, shaped so an agent can read the usage rule, the query recipe, the
    catalog (grouped by application), and the entity highlights without parsing JSON."""
    counts = manifest["counts"]
    lines: list[str] = [
        "# vdocs gold corpus — AI card",
        "",
        f"_Generated {manifest['generated_at']} · tool {manifest['tool_ver']} · "
        f"index `{manifest['index_fingerprint'][:12]}`_",
        "",
        f"**How to use this corpus.** {manifest['usage']}",
        "",
        f"- **Documents:** {counts.get('documents', 0)} "
        f"({counts.get('version_groups', 0)} latest anchors)  ·  "
        f"**Searchable chunks:** {counts.get('sections_searchable', 0)}  ·  "
        f"**Entities:** {counts.get('entities', 0)}  ·  "
        f"**Relations:** {counts.get('relations', 0)}",
        "- **Capabilities:** "
        + ", ".join(k for k, v in sorted(manifest["capabilities"].items()) if v),
        "",
        "## Query recipe",
        "",
        "```bash",
        manifest["query"]["command"],
        "```",
        "",
        f"Returns {manifest['query']['returns']}. {manifest['query']['modes']}.",
        "",
        f"**Cite as:** `{manifest['citation']['format']}`",
        "",
        "## Documents",
        "",
    ]
    by_app: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for doc in manifest["documents"]:
        by_app[doc["app_code"] or "(unknown)"].append(doc)
    for app in sorted(by_app):
        docs = by_app[app]
        lines.append(f"### {app} ({len(docs)})")
        lines.append("")
        for doc in docs:
            patch = f" · {doc['patch_id']}" if doc["patch_id"] else ""
            lines.append(
                f"- **{doc['title'] or doc['doc_key']}**{patch} · {doc['sections']} sections · "
                f"`{doc['body_path']}`"
            )
        lines.append("")
    lines.append("## Entity index (top by mention count)")
    lines.append("")
    for etype in sorted(manifest["entities"]):
        names = ", ".join(f"`{e['name']}`" for e in manifest["entities"][etype][:10])
        lines.append(f"- **{etype}**: {names}")
    lines.append("")
    return "\n".join(lines)


def discovery_descriptor(counts: dict[str, Any], *, tool_ver: str) -> dict[str, Any]:
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
        "capabilities": _capabilities(),
    }
