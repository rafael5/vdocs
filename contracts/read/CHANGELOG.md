# Read Contract — Changelog

Semver for the **read** contract (`read_schema_version`), the consumer-facing interface over
`index.db`. MINOR = additive/backward-compatible (new view/column/capability); MAJOR = breaking
(removal, rename, type change). Breaking changes follow expand/contract (parallel-change): ship the
replacement additively, keep the old as an alias for one release, then remove + MAJOR bump. See
[ADR-0001](../../docs/adr/0001-read-contract-and-drift-prevention.md).

## v1.3 — 2026-06-15

Additive (backward-compatible) — per-doc figure stats (rich-publication groundwork):

- **`v_documents.image_count`** — distinct figures the doc references that resolve in the asset
  store.
- **`v_documents.image_bytes`** — total bytes of those referenced figures (a per-doc upper bound;
  a published image bundle dedups assets shared across docs). Precomputed at `index` time so
  consumers and publish-size planning never recount on the fly. (`index` `contract_ver` 9→10.)

## v1.2 — 2026-06-11

Additive (backward-compatible) — ADR-0001 P4:

- **`v_sections.seq`** — the document-order ordinal of each section. Consumers `ORDER BY seq` for
  TOC/preview order; SQLite views have no `rowid`, so an explicit ordering column is required once
  consumers read through `v_sections` instead of the physical table. (Driven by the vdocs-tui
  consumer need — the canonical "consumer demand → additive producer change" round-trip.)

## v1.1 — 2026-06-11

Additive (backward-compatible) — ADR-0001 P2:

- **New view** `v_vocab` over the new `vocab` table: the controlled facet vocabularies (function
  domains, doc types, VDL sections, personas) published as data, sourced from `registries/`
  (`function-domains.yaml`, `doc-labels.yaml`, `section-codes.yaml`, the new `personas.yaml`).
  Consumers read definitions from here instead of hardcoding them.
- **New capability** `vocab_table`.

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
