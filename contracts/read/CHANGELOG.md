# Read Contract — Changelog

Semver for the **read** contract (`read_schema_version`), the consumer-facing interface over
`index.db`. MINOR = additive/backward-compatible (new view/column/capability); MAJOR = breaking
(removal, rename, type change). Breaking changes follow expand/contract (parallel-change): ship the
replacement additively, keep the old as an alias for one release, then remove + MAJOR bump. See
[ADR-0001](../../docs/adr/0001-read-contract-and-drift-prevention.md).

## v1.8 — data correction, 2026-11-07 (no version change)

The `chunks_fts` `body` column now holds the **clean projection** of the chunk
(`index_pure.index_text`): the nav line, HTML tags, link targets and `<img>` asset hashes are gone,
inner text, alt text, link labels and keystroke notation (`<Enter>`) stay. `chunks_fts.title` and
`v_doc_sections.title` / `section_path` carry the heading's link label instead of a legacy TOC
entry (`[Preface [ii](#preface)](#preface)` → `Preface`; 320 live titles, 10 documents). `v_chunks.text`
is unchanged markdown. No view, column or meaning changed — `body` was always "the text of the
chunk" and `title` "the heading text" — so the version stays 1.8; `index` `contract_ver` 18→19
rebuilds it. End-to-end search review A1, decision D1 (`docs/proposals/end-to-end-search-architecture-review.md`).

## v1.8 — 2026-11-06

Additive (backward-compatible) — the search synonym table (keyword-search proposal, fix 3,
`docs/proposals/keyword-search-five-fixes.md`):

- **`v_search_synonyms`** — term → alternatives, in table order (`seq`), that every search front
  door ORs into an unquoted word or phrase that is a term: "blood bank" → ("blood bank" OR "VistA
  Blood Establishment Computer Software" OR "VBECS"). `match_case` 1 marks a term that matches
  only as written (application codes and namespaces, many of which are also ordinary words); 0
  matches in any case. `source` says where the row came from: the plain-English package names,
  Kernel parts and judged terms of `registries/search-synonyms.yaml`, the documents' application
  codes and namespaces (each → the application's name), or the SKL's file names (file 200 → NEW
  PERSON, which the MCP used to read from `v_entity_skl`). The reader rules and their cases
  are `contracts/query/v1.json` (`synonyms`).
- **capability `search_synonyms`.**

`index` owns the empty shell and `merge` fills it, like the other SKL tables. (`index`
`contract_ver` 17→18, `merge` 1→2.)

## v1.7 — 2026-11-05

Additive (backward-compatible) — the whole VDL inventory in `index.db` (inventory browser step 1,
`docs/proposals/inventory-browser-proposal.md`):

- **`v_inventory`** — one row per listing in the gold inventory (`inventory.json`, 9,080 on
  2026-11-05): a `row_key` of its own (neither `doc_id` nor the VDL URL is unique), `doc_id`, the
  listing's application, section, doc type, title, file, format, patch id, lifecycle label, system
  type and URLs, the four profile tags, the namespace, and the completeness `disposition` with its
  `reason` string, `reason_kind` and `reason_value`. Gold status is not stored: join `doc_id` to
  `v_documents`. `refiled_from` labels the 14 ISS guides VA re-filed from ADT to SD with the id
  gold still holds them under — a stopgap that `vdocs doctor` reds on once a listed id joins
  without it (identity continuity).
- **`v_documents.last_updated`** / **`last_updated_source`** — the document's own last update
  (`YYYY-MM`): its newest Revision History date, else its title-page date (`history.yaml`
  `official_date`), and which of the two it was. Never the VDL posting date.
- **`v_vocab`** gained the kinds `disposition`, `reason_kind` (one sentence per kind),
  `doc_type_family` (one row per member type; a type in none is Other) and `namespace` (the
  inventory's namespaces, PACKAGE file #9.4 name first, read by the Inventory mode only).
- **`meta`** gained `inventory_record_count` and `inventory_content_hash` (order-independent,
  over the enriched records); `vdocs doctor` compares the hash with the current `inventory.json`.
- **capabilities `inventory`, `last_updated`.**

(`index` `contract_ver` 16→17; `index` now requires the gold inventory.)

## v1.6 — 2026-08-03

Additive (backward-compatible) — VA lifecycle labels on the document (vdocs-quality-crawl-integrity
CI.3, the visibility half of the CI.2 master-set retention rule: a relabel is a badge, never a
removal):

- **`v_documents.app_status`** — VA's lifecycle label for the owning application
  (`active` | `archive` | `decommissioned`) as of the last inventory.
- **`v_documents.decommission_date`** — VA-supplied decommission date (empty when none).
- **`v_documents.cots_dependent`** — 1 when VA flags the application as replaced by / dependent on
  a commercial product.
- **`v_documents.out_of_scope_reason`** — provenance-only: the disqualifying source-format label,
  empty for the admitted DOCX representation.
- **capability `lifecycle_labels`** — advertises the four columns are populated.

The same labels are baked into the gold body frontmatter by `enrich` (`app_status` always;
`decommission_date` / `cots_dependent` / `out_of_scope_reason` only when VA supplies them), so the
human reading surface carries the fact too. (`enrich` `contract_ver` 1→2, `index` 15→16.)

## v1.5 — 2026-06-17

Additive (backward-compatible) — SKL entity-keying (skl-implementation-plan S3.3). `merge` folds the
Semantic Knowledge Layer (`knowledge.db`) into the shipped `index.db`; `index` owns the (empty) table
shells + these views so the version is consistent even before `merge` runs:

- **`v_entity_skl`** — the reconciliation map between the two entity-id schemes: index `entity_id`
  (`type:canonical`) ↔ SKL `node_id` (`type/canonical`), with the SKL canonical identity. Present
  only where the SKL resolved the entity (DI today); empty elsewhere — non-SKL coverage is unchanged.
- **`v_entity_synonyms`** — every surface (canonical name + synonyms) of each resolved entity.
- **`v_chunk_entities`** — chunk→entity tags (entity-keyed retrieval).
- **capability `skl_entity_keying`** — advertises the three views are populated.

(`index` `contract_ver` 11→12; the new tables are populated by the `merge` stage.)

## v1.4 — 2026-06-16

Additive (backward-compatible) — gold bundle path (rich-reading groundwork):

- **`v_documents.bundle_path`** — the de-versioned gold anchor relpath a doc resolves to, so a
  consumer can locate the doc's gold sidecars (e.g. the rich-reading `tables/*.csv`) without
  reverse-engineering `doc_key`. (`index` `contract_ver` 10→11.)

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
