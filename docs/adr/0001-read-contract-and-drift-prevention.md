# ADR 0001 — Read Contract & Drift Prevention (vdocs → consumers)

- **Status:** Accepted (2026-06-11)
- **Owner:** vdocs (the producer owns the contract)
- **Consumers in scope:** `vdocs-tui` (Go TUI), `vdocs-web` (Go server + SvelteKit, planned),
  a future MCP endpoint, and `vdocs-cli`.
- **Supersedes / relates to:** the lexical-search plans (`docs/offline-lexical-search-plan.md`),
  the vdocs-web direction (option A, server-backed). This ADR is authoritative for the
  producer→consumer data contract.

## Context

`vdocs` (the pipeline) produces `index.db` (SQLite + FTS5). Multiple independent clients read
it. Today the relationship is an **implicit, unversioned contract**, which is fragile in three
concrete, verified ways:

1. **No schema version is stamped in `index.db`.** `PRAGMA user_version = 0`; there is no `meta`
   table. The `contract_ver = 6` in the index stage is the *orchestrator's stage-rerun trigger*
   (`orchestrator/stage.py`), **not** a consumer-facing schema version. Consumers have no way to
   detect an incompatible database.
2. **Consumers bind to physical tables.** `vdocs-tui/internal/index` hardcodes `FROM documents`
   (×10), `FROM entity_mentions`, `JOIN entities`, `FROM chunks_fts`, etc., with column names in
   SQL strings. Any rename/reorder in the pipeline breaks consumers silently (wrong data) or
   loudly (scan error) with no diagnostic.
3. **A build-staging table leaks into the shipped DB.** `doc_meta_staged` is internal scratch but
   ships in `index.db`.

Crucially, the **most common** change — *fetching more docs, growing the gold library, refining
the pipeline* — is **not** primarily a schema change. It is **data** and **vocabulary** drift,
which a schema version cannot catch. Verified instance: `vdocs-tui/internal/tui/explain.go`
hardcodes `personaDef`, `sectionDef`, `domainDef` maps, while the pipeline *owns* those
vocabularies (`registries/inventory/function-domains.yaml`, personas, VDL sections). Breaking out
**Laboratory** and **Radiology** as new function domains (done 2026-06-10) silently rots those
consumer maps — a new value renders with a generic fallback, no definition.

### The three drift classes

| Class | What changes | Detected by `schema_version`? | Mechanism (this ADR) |
|---|---|---|---|
| **Structural** | columns / tables / types | ✅ yes | read-contract semver + views + codegen |
| **Data / corpus** | more docs, new rows, coverage shifts | ❌ no | `corpus_snapshot` version + coverage gates |
| **Vocabulary** | new facet *values* (domain, doc type, section) | ❌ no | vocab-as-data + producer enum-coverage gate |

## Decision

Adopt a **published read contract** with **two independent version axes**, publish **controlled
vocabularies as data**, and enforce the whole thing at **three validation points** plus a
**producer enum-coverage gate**. The producer can refactor freely behind the contract; consumers
bind only to the contract and are *warned* — at compile time, build time, and run time — whenever
drift of any class occurs.

### 1. Two version axes (stamped in `index.db` `meta` table)

- **`read_schema_version`** — **semver**, the *structural* contract.
  - MINOR bump = additive / backward-compatible (new column, new view, new capability).
  - MAJOR bump = breaking (removal, rename, type change).
- **`corpus_snapshot`** — a *data* fingerprint: build timestamp · `is_latest` doc count ·
  content hash. Changes whenever the data changes, even with identical structure. Drives staleness
  messaging, cache-keys the `vdocs-web` DB download, and is displayed by every consumer
  (`corpus: 2026-06-11 · 615 docs`).

A `meta(key, value)` table holds both, plus build git sha and per-facet coverage stats.

### 2. Views are the published interface

Consumers query **only** stable views: `v_documents`, `v_sections`, `v_entities`,
`v_entity_mentions` (and the documented `chunks_fts` virtual table — FTS5 cannot sit behind a
view, so its columns + tokenizer are a *named* part of the contract). Physical tables refactor
freely behind the views. Adding a column = additive; renaming a physical column = a view-only
change, consumers untouched. `doc_meta_staged` and other build scratch are **dropped** from the
shipped DB.

### 3. Vocabularies published as data (never hardcoded in consumers)

Emit a `vocab(kind, code, label, description)` table in `index.db`, sourced from the pipeline
`registries/`, covering: sections, function domains, personas, doc types, app names, products.
This extends the existing `Vocab()` pattern (which already loads app/doc/namespace/product from
the DB) to **all** vocabularies. Consumer payoff: `explain.go`'s `personaDef` / `sectionDef` /
`domainDef` maps are **deleted** and read from the vocab table. Growing the library then flows new
vocabulary to every consumer automatically — nothing to hand-sync.

### 4. The contract artifact (single source of truth)

`vdocs/contracts/read/v<MAJOR>.json` — a machine-readable spec declaring, per view/table:
column names, types, nullability, semantic descriptions; the FTS tokenizer; and a set of named
**capabilities** (e.g. `fts5`, `pub_year`, `entity_mentions`, `vocab_table`). Plus
`contracts/read/CHANGELOG.md`. Everything derives from this hub:

- **vdocs** generates the view DDL from it and stamps `read_schema_version`; `doctor` asserts the
  emitted DB matches it exactly (a gate — the producer cannot ship a contract violation).
- **`pkg/index`** (the shared Go core, extracted from `vdocs-tui`) vendors a copy and `go:generate`s
  typed column constants + the row struct + `RequiredSchemaVersion`.

### 5. Capabilities, not just columns (scales to N consumers)

The published `manifest.json` declares the DB's `capabilities`. Each consumer declares the
capabilities it *requires*; the union is what the producer must satisfy. A consumer needing a
capability the DB lacks gets a clear message, not a crash. This is how the MCP endpoint, the TUI,
and the web client — with different and *evolving* demands — share one producer.

### 6. The four guardrails (where drift is caught)

1. **Producer publish-time gate (`doctor`):** emitted DB == contract spec; views present;
   `read_schema_version` stamped; **enum-coverage** — every distinct value in
   `function_category` / `doc_type` / `section` has a `vocab` entry (so a newly fetched doc
   introducing an undefined domain *fails the producer gate* until the registry is updated); no
   orphan staging tables; per-facet coverage above thresholds.
2. **Consumer build/dev-time:**
   - **Compile-time** — code referencing a column not declared in the contract fails to compile
     (generated constants). *"You want a field the contract doesn't have — extend it upstream."*
   - **Drift check** (`make contract-check`, in CI + locally) — diffs the vendored contract
     against the canonical one in the local `~/projects/vdocs/contracts/read/` sibling. *"vdocs is
     at v2.1; you vendor v2.0 — run `make contract-sync` and regenerate."*
   - **Contract test** — a tiny fixture DB built from the spec; the core's queries run against it.
3. **Consumer load-time (runtime `Open()`):** read `meta.read_schema_version`; MAJOR mismatch →
   actionable error (*"index.db is schema v3.0; this build needs v2.x — update the app or fetch a
   matching DB."*). Snapshot `PRAGMA table_info` and degrade gracefully — a facet whose optional
   column is absent simply isn't built (extends the existing empty-axis suppression).
4. **Corpus characterization (approval) test** in vdocs: snapshot distinct-values + counts per
   facet column; diff on every build. Catches data-shape surprises (a value vanishing, a column's
   population collapsing) that no version number reflects.

### 7. Distribution / coupling model

Canonical contract lives in **vdocs** (the producer owns its schema). The Go core **vendors** a
copy + records the upstream version it tracks; `make contract-check` diffs against the local vdocs
sibling. Chosen over a `go.work`/submodule binding (tighter coupling) or having the core carry the
contract (the producer should own its own schema) because all repos are local siblings and the
target is airgapped/offline.

### 8. Migration discipline

- **Semver bump-type is enforced** (`contract-lint`): a removed/renamed/retyped column without a
  MAJOR bump fails. No accidental mis-versioning.
- **Expand/contract (parallel-change)** for breaking changes: ship *expand* (add new, keep old as
  a view alias, MINOR) → one release window → *contract* (drop old, MAJOR). Consumers migrate on
  their own schedule — never a big-bang.
- Every bump is recorded in `contracts/read/CHANGELOG.md` (and the decision in `CHANGES.md`).
- Optional: `make check-consumers` in vdocs runs each sibling consumer's contract test against a
  candidate new contract → a compatibility matrix *before* publishing (know the blast radius).

## Consequences

**Positive**
- Growing the gold library is **drift-proof by construction**: new vocabulary flows via the vocab
  table; a new undefined value fails the producer gate, not the consumer silently.
- Each drift class has a dedicated alarm at the moment it originates (compile / build / run /
  publish).
- The pipeline refactors physical schema freely behind views; breaking changes become deliberate,
  gated, semver events.
- Consumer demand routes through explicit capability requirements + contract bumps — N consumers
  with diverging needs share one producer with least pain.
- `explain.go` loses three hand-maintained maps (first concrete consumer payoff).

**Costs / tradeoffs**
- A ~100-line Go generator + a JSON contract spec + view DDL to maintain (justified by
  compiler-enforced contracts; revisited last turn — codegen *is* warranted given the "warn me"
  requirement).
- One more artifact (`manifest.json` capabilities) and a `meta` table in the DB.
- Discipline required: schema changes must go through the contract, not ad-hoc DDL.

**Out of scope / deferred**
- Python-side codegen of the DDL *from* the JSON (start by validating the hand-written DDL against
  the spec; generate later if hand-sync hurts).
- A networked contract registry — unnecessary for local-sibling, airgapped repos.

## Build sequence (incremental, each step shippable)

1. **vdocs (tiny):** add `meta` table with `read_schema_version` + `corpus_snapshot`; drop
   `doc_meta_staged`. Immediate fragility reduction.
2. **vdocs:** author `contracts/read/v2.json` describing *today's* schema (no behavior change) +
   CHANGELOG; add `v_*` views generated from it; extend `doctor` to validate emitted DB == spec.
3. **vdocs:** publish the `vocab` table from `registries/`; add the `doctor` enum-coverage gate +
   coverage stats in `manifest.json`; add the corpus characterization test.
4. **`pkg/index`:** extract from `vdocs-tui/internal/index`; add codegen + `RequiredSchemaVersion`
   runtime check + `make contract-check` drift check + contract test against the fixture.
5. **vdocs-tui:** switch to the imported core + views; **delete** the `explain.go` vocab maps,
   read from the `vocab` table.
6. **vdocs-web:** born consuming the contract correctly — capabilities declared, version checked,
   DB download validated against the manifest.

## References

- Topology and rationale: this session's design discussion (2026-06-11).
- Architecture tenet #13 "discovery is data, not code" (`docs/historical/vdocs-design.md`) — this
  ADR extends it across the producer/consumer boundary.
- vdocs-web direction: option A (local Go server + SvelteKit + auto-download DB), facets + fuzzy +
  FTS5.
