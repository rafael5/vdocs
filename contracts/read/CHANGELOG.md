# Read Contract — Changelog

Semver for the **read** contract (`read_schema_version`), the consumer-facing interface over
`index.db`. MINOR = additive/backward-compatible (new view/column/capability); MAJOR = breaking
(removal, rename, type change). Breaking changes follow expand/contract (parallel-change): ship the
replacement additively, keep the old as an alias for one release, then remove + MAJOR bump. See
[ADR-0001](../../docs/adr/0001-read-contract-and-drift-prevention.md).

## v1.0 — 2026-06-11

Initial published contract. Describes the existing `index.db` schema verbatim (no behavior change):

- **Views** (generated from `v1.json`, the SSOT): `v_documents`, `v_sections`, `v_chunks`,
  `v_entities`, `v_entity_mentions`.
- **FTS surface:** `chunks_fts` (named contract; queried via `MATCH` directly — FTS5 can't be a
  view).
- **Capabilities:** `fts5`, `pub_year`, `entity_mentions`, `persona_facets`, `product_facets`.
- **Version axes** stamped in `index.db` `meta` (P0): `read_schema_version=1.0` +
  `corpus_content_hash`.

`doc_meta_staged` is a pipeline-internal `enrich→index` table and is **deliberately excluded** from
this contract (consumers must not read it; it is stripped from the distributed artifact at publish).
