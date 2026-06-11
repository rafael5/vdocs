# Read Contract & Drift Prevention — Implementation Plan & Tracker

> **The *how/status* companion to [`docs/adr/0001-read-contract-and-drift-prevention.md`](adr/0001-read-contract-and-drift-prevention.md)** (the *what/why*).
> If the ADR and this tracker disagree on intent, the ADR wins; if the code and this tracker
> disagree on status, **update this tracker** (TDD → gate → update tracker → commit, per step).
> Spans three repos: **vdocs** (producer, `~/projects/vdocs`), **vdocs-tui** (consumer,
> `~/vista-cloud-dev/vdocs-tui`), and **vdocs-web** (new consumer). Cross-repo rule: **producer
> changes land before consumer changes; `pkg/index` extraction lands before vdocs-web** (leaf-first).

## Working protocol

- **TDD, hard rule.** Write the test first, confirm it fails, implement, confirm green, run the
  repo gate before commit. vdocs: `make check` (lint+mypy+coverage ≥95%). Go: `go test -race` +
  `golangci-lint` clean.
- **Per step:** TDD → gate → update this tracker's phase section (Changelog/Discoveries/Risks) →
  commit. vdocs commits docs+code directly to `master` (repo convention); vdocs-tui/vdocs-web use
  branch→PR→squash (org Increment Protocol).
- **Additive-first.** Every contract change is additive (new view/column/capability, MINOR bump)
  unless a deliberate expand/contract MAJOR migration is scheduled. Never break a consumer in the
  same step that introduces the replacement.
- **Fixtures, not the live lake.** Contract/characterization tests run against tiny fixture DBs
  built from the spec — never against `~/data/vdocs/index.db` (294 MB; and a live operator run may
  hold it — check `pgrep -af "vdocs run"` first).

## Status legend

| Symbol | Meaning |
|---|---|
| ✅ | Done (gate met) |
| 🟡 | In progress |
| ⬜ | Not started |
| ⏸️ | Blocked (see Notes) |
| ⛔ | Parked / out of scope |
| ⚠️ | Flag — a discovery warrants a plan/impl change (see that phase's Discoveries) |

## Master tracker

| Phase | ID | Step | Status | Note |
|-------|----|------|--------|------|
| **P0 — Contract baseline** (vdocs) | P0.1 | `meta(key,value)` table in `index.db` | ✅ | index stage; contract_ver 6→7 |
| | P0.2 | Stamp `read_schema_version` (`1.0`) | ✅ | `index_pure.READ_SCHEMA_VERSION` |
| | P0.3 | Stamp `corpus_content_hash` + `corpus_doc_count` | ✅ | deterministic; build ts deferred to manifest (D8) |
| | P0.4 | ~~Drop `doc_meta_staged`~~ → exclude from consumer surface | ⚠️ | **revised (D7):** real `enrich→index` contract, kept; views exclude it (P1), strip at publish |
| **P1 — Read contract + views** (vdocs) | P1.1 | `contracts/read/v1.json` spec describing *today's* schema | ✅ | SSOT; `cfg.read_contract_dir` |
| | P1.2 | `contracts/read/CHANGELOG.md` (+ ~~meta-schema~~ deferred) | ✅ | meta-schema low-value; spec shape covered by tests |
| | P1.3 | `v_documents`/`v_sections`/`v_chunks`/`v_entities`/`v_entity_mentions` views | ✅ | **generated** from spec (`kernel.read_contract.view_ddl`) |
| | P1.4 | Document `chunks_fts` (cols + tokenizer) as named contract | ✅ | `fts` block in v1.json (D-fts) |
| | P1.5 | `doctor`: assert emitted DB == spec (views, cols, version) | ✅ | `contract_check`; FAIL⇒RED; wired in `_emit_doctor` |
| | P1.6 | `contract-lint`: enforce semver bump-type vs prior spec | ✅ | `lint_bump` + `make contract-lint` (no-op at v1) |
| **P2 — Vocab-as-data + drift gates** (vdocs) | P2.1 | `vocab(kind,code,label,description)` table from `registries/` | ✅ | `kernel/vocab.py`; v_vocab (contract→1.1); domains/doc_type/section/persona |
| | P2.2 | `doctor` enum-coverage gate (every distinct facet value ∈ vocab) | ✅ | `enum_coverage_check`; undefined value ⇒ RED |
| | P2.3 | Coverage stats (% populated, distinct counts, rows) in `manifest.json` | ✅ | `_gather_coverage` (defensive over columns) → `coverage` block |
| | P2.4 | `capabilities` (read-contract) in `manifest.json` | ✅ | `read_contract`{version,capabilities} block from spec |
| | P2.5 | Corpus characterization snapshot in `manifest.json` | ✅ | `facet_distribution` → `characterization` block (diffable per build) |
| **P3 — Shared Go core** (vdocs-tui) | P3.1 | Extract `internal/index` → importable `pkg/index` | ✅ | mechanical PR #23 (`5d2f880`); API-stable |
| | P3.2 | Vendor `contracts/read/v1.json` + bind (`go:embed`+parse, not codegen) | ✅ | PR #24; `RequiredSchemaVersion`/`Capabilities`/`ContractViewColumns` |
| | P3.3 | `Open()` runtime version check (MAJOR mismatch → clear error) | ✅ | unstamped DB degrades, doesn't block |
| | P3.4 | `make contract-check` drift check (vendored vs local vdocs sibling) | ✅ | the "warn me" alarm; in `make check`, self-skips in CI |
| | P3.5 | Contract test (accessors + accept/refuse/degrade) | ✅ | `pkg/index/contract_test.go` |
| **P4 — vdocs-tui consumes contract** | P4.1 | Query `v_*` views, not physical tables | ✅ | PR #25 (`91860a4`); chunks_fts stays |
| | P4.2 | Pre-contract DB degrades (`HasContractViews` → skip/degrade) | ✅ | real-corpus tests skip; `Vocab()` best-effort |
| | P4.3 | Read persona/section/domain vocab from `v_vocab` | ✅ | `Vocab.Persona/Section/Domain` |
| | P4.4 | **Deleted** `explain.go` `personaDef`/`sectionDef`/`domainDef` | ✅ | explainer fully data-driven (the payoff) |
| **P5 — vdocs-web** (new repo) | P5.1 | Scaffold: Go module, SvelteKit, Makefile, CI | ⬜ | |
| | P5.2 | Spine: `/api/facets` + `/api/candidates` over `pkg/index` + minimal Svelte page | ⬜ | prove the seam |
| | P5.3 | Preview / TOC / fuzzy / **FTS5** endpoints + panes | ⬜ | |
| | P5.4 | DB auto-download on first run + manifest validation (sha256, schema_version) | ⬜ | zstd, resumable |
| | P5.5 | Declare required `capabilities`; `go:embed` built front-end | ⬜ | self-contained binary |
| | P5.6 | Cross-compile matrix (linux/mac/win) | ⬜ | |
| **P6 — Multi-consumer hardening** (future) | P6.1 | MCP endpoint consuming `pkg/index` + capabilities | ⛔ | when MCP is revived |
| | P6.2 | `make check-consumers` compatibility matrix in vdocs | ⬜ | blast-radius before a bump |

---

## Pre-implementation discoveries (grounded 2026-06-11)

These are the verified findings that motivate the plan and seed the per-phase risks.

- **D1 — No schema version exists.** `PRAGMA user_version = 0`; no `meta` table. The index stage's
  `contract_ver = 6` is the *orchestrator stage-rerun trigger* (`orchestrator/stage.py`), **not** a
  DB schema version. Consumers cannot currently detect an incompatible DB. → P0.
- **D2 — Consumers bind to physical tables.** `vdocs-tui/internal/index` hardcodes `FROM documents`
  (×10), `FROM entity_mentions`, `JOIN entities`, `FROM chunks_fts`, `FROM doc_sections`,
  `FROM chunks`; no view indirection, no `Open()` version check. → P1, P3, P4.
- **D3 — Build-scratch leaks.** `doc_meta_staged` ships in `index.db`. → P0.4.
- **D4 — Mixed vocab sourcing.** `explain.go` hardcodes `personaDef`/`sectionDef`/`domainDef`, but
  `AppName`/`DocType`/`Namespace`/`Product` already load from the DB via `Vocab()`. Breaking out
  Laboratory/Radiology domains (2026-06-10) silently rots the hardcoded maps. → P2, P4.
- **D5 — 294 MB DB.** Rules out client-side WASM; vdocs-web is server-backed and the DB is a
  *distributed artifact* needing versioned, checksummed delivery. → P5.4.
- **D-fts — FTS5 can't be a view.** `MATCH` requires querying the virtual table directly, so
  `chunks_fts` is a *named* part of the contract rather than wrapped. → P1.4.
- **D6 — Go `internal/` is module-private.** The query core must move to `pkg/` before vdocs-web
  (a separate module) can import it. → P3.1.

---

## Phase P0 — Contract baseline (vdocs)

**Goal:** stamp the two version axes and stop leaking build scratch — no behavior change, immediate
fragility reduction. Smallest shippable increment.

**Steps:** P0.1 `meta(key,value)` table created + populated in the index stage; P0.2 write
`read_schema_version="1.0"`; P0.3 write `corpus_snapshot` (build timestamp, `is_latest` doc count,
content hash over the documents+sections payload); P0.4 `DROP TABLE doc_meta_staged` (or build it in
an attached temp DB) before finalizing. Tests first: assert the published DB has a `meta` table with
both keys and no `doc_meta_staged`.

### Changelog
- **2026-06-11** — ✅ landed. `index_pure.corpus_content_hash()` + `meta_rows()` (pure,
  unit-tested: deterministic + order-independent + changes on any row change); `meta(key,value)`
  table added to `_SCHEMA`; `build()` inserts `read_schema_version=1.0`, `corpus_content_hash`,
  `corpus_doc_count`. Stage `contract_ver` 6→7 (produces[] shape change → re-run rebuilds). 2 unit
  + 2 integration tests (incl. rebuild-determinism). `make check` green: 886 passed, 98.18%.

### Discoveries
- **D7 ⚠️ (revises P0.4):** `doc_meta_staged` is **not** build scratch — it's a real cross-stage
  contract (`ArtifactContract DOC_META_STAGED`): `enrich` produces it, `index` `requires`+consumes
  it, and `index.db` is *both* the pipeline working store and the read artifact, so the build
  **deliberately carries it forward** (`_carry_staged`; tests
  `test_index_preserves_staged_across_forced_rebuild`). It cannot be dropped in the index stage
  without breaking re-runnability. **Resolution:** keep it; exclude it from the *consumer* surface
  via the `v_*` views (P1, consumers never query it); strip it from the *distributed* artifact at
  publish time (deferred to P5.4 / a publish stage), not here.
- **D8:** baking a wall-clock build timestamp into `index.db` would make it non-reproducible.
  Decision: `corpus_content_hash` is timestamp-free (sorted content only) so identical data
  rebuilds to the same fingerprint; the human-facing **build timestamp lives in the publish
  `manifest.json`** (P2.3), not in `index.db`.

### Risks & mitigations
- **Risk:** `corpus_content_hash` couples to the exact `documents` row representation, so a benign
  refactor of column order/format churns the fingerprint. **Mitigation (accepted):** that *is* a
  consumer-visible change (display columns are part of what consumers read); a structural change
  also bumps `read_schema_version`. Revisit only if churn proves noisy.
- ~~Risk: dropping `doc_meta_staged` breaks a later stage~~ — resolved by D7 (not dropped here).

### Lessons learned
- Reading the producing stage + its `ArtifactContract` *before* acting caught D7 — the "leaked
  staging table" framing in the ADR was wrong; it's a real contract edge. Grounding before code
  paid for itself. The ADR's build-sequence step 1 is corrected accordingly.

---

## Phase P1 — Read contract + views (vdocs)

**Goal:** publish an explicit, versioned read interface that consumers bind to instead of physical
tables; make the producer unable to ship a contract violation.

**Steps:** P1.1 author `contracts/read/v1.json` (per view/table: columns, types, nullability,
semantic descriptions; FTS tokenizer; capabilities) describing today's schema verbatim; P1.2 add
CHANGELOG + a meta-schema to validate the spec's own shape; P1.3 emit `v_*` views from the spec in
the index/publish stage; P1.4 document `chunks_fts`; P1.5 extend `doctor` to assert emitted DB ==
spec (gate); P1.6 `contract-lint` comparing spec vN vs vN-1 to enforce bump-type. Tests first for
each (doctor assertion test with a deliberately-mutated fixture that must fail).

### Changelog
- **2026-06-11** — ✅ landed (`make check` green: 903 passed, 98.04%).
  - `contracts/read/v1.json` — the SSOT spec (5 views over their source tables + the `chunks_fts`
    named surface + `capabilities`), `contracts/read/CHANGELOG.md`, `Settings.read_contract_dir`.
  - `kernel/read_contract.py` (pure, unit-tested): `load`/`view_columns`/`view_ddl` (generates the
    `CREATE VIEW`s — views ARE the spec), `version`/`capabilities`, `lint_bump`/`lint_latest`.
  - Index stage loads the spec, **generates** the `v_*` views from it, and stamps
    `meta.read_schema_version` from `version(spec)` (single source).
  - `doctor.contract_check` (pure) + `diagnose(read_spec=…)` — emitted DB must expose every view
    with the spec's columns + matching version; FAIL ⇒ RED. Wired into `_emit_doctor` (doctor+build).
  - `make contract-lint` (semver bump-type guard; no-op until a v2 exists).

### Discoveries
- **D9:** the live `~/data/vdocs/index.db` predates P0/P1 (no `meta`/views), so `vdocs doctor` now
  reports **RED** against it (missing `meta` version → contract mismatch) until an `index` re-run.
  Expected — `contract_ver` 6→7 forces the rebuild; not run here (294 MB; shared-lake guard).
- **D10:** `doctor.diagnose` had a parameter-shadowing footgun — `for fld, spec in
  policy.coverage.items()` clobbered a `spec` param, so the contract block ran against a
  `CoverageSpec`. Renamed the param to `read_spec`. Watch loop-var/param collisions in long fns.

### Risks & mitigations
- **Risk:** views drift from physical tables silently. **Mitigation (shipped):** views are
  *generated* from the spec, and `doctor` asserts the emitted view columns == spec — a new physical
  column is invisible to consumers until deliberately added to the spec (MINOR bump).
- **Risk:** view indirection costs query performance. **Mitigation:** SQLite views are query-rewrite
  (no materialization); facet-column indices unchanged. Revisit with `EXPLAIN QUERY PLAN` if a
  consumer reports slowness.
- **Note:** the operator must re-run `index` (or `build`) on the real lake to gain the views+meta;
  until then `doctor` is RED on the pre-P1 DB (D9).

### Lessons learned
- Generating the views from the spec (vs hand-writing DDL + a drift check) removed an entire class
  of drift — there is genuinely one source. Worth the small build-time spec load.
- Reading `diagnose` before extending it would have caught D10 sooner; the integration suite did.

---

## Phase P2 — Vocab-as-data + drift gates (vdocs)

**Goal:** make *data/corpus* and *vocabulary* drift (the common "grow the library" case) safe by
construction — new vocabulary flows to consumers as data; an undefined value fails the producer.

**Steps:** P2.1 build a `vocab(kind,code,label,description)` table from `registries/` (sections,
function domains, personas, doc types, app names, products); P2.2 `doctor` enum-coverage gate —
every distinct value in `function_category`/`doc_type`/`section` must have a vocab row; P2.3 coverage
stats into `manifest.json`; P2.4 `capabilities` list into `manifest.json`; P2.5 corpus
characterization (approval) test. Tests first: a fixture introducing an undefined domain must fail
the enum gate; a vocab-table read returns expected labels.

### Changelog
- **2026-06-11** — ✅ landed (`make check` green: 916 passed, 98.02%).
  - **P2.1** `registries/inventory/personas.yaml` (NEW) + `section-codes.yaml` `descriptions:`
    block; `kernel/vocab.py` (`vocab_rows`, pure, unit-tested); `vocab` table + `v_vocab` view;
    read contract → **v1.1** (additive: `v_vocab` + `vocab_table` capability); stage `contract_ver`
    7→8. Commit `26cb923`.
  - **P2.2** `doctor.enum_coverage_check` + `diagnose`: undefined `function_category`/`doc_type`/
    `section`/`app_user`/`doc_user` value ⇒ FAIL ⇒ RED (runs only when `vocab` populated). `26cb923`.
  - **P2.3** `_gather_coverage` → manifest `coverage` block (populated/total/pct/distinct per facet).
  - **P2.4** manifest `read_contract`{version, capabilities} block (consumer negotiation).
  - **P2.5** `manifest_pure.facet_distribution` (pure) → manifest `characterization` block
    (distinct-value→count per vocab-gated facet) — a diffable per-build data-shape snapshot.

### Discoveries
- **D11:** persona descriptions had **no registry** (lived only in `vdocs-tui/explain.go`). Created
  `personas.yaml` as the authoritative source — so P4 can delete the Go `personaDef` map. Section
  descriptions similarly only in Go → added a `descriptions:` block to `section-codes.yaml`.
  (Function-domain definitions + doc-labels already existed in registries.)
- **D12:** the manifest integration fixture uses a *minimal* `documents` schema (no
  `function_category`/`section`/`app_user`/`doc_user`). Made `_gather_coverage`/
  `_gather_characterization` **defensive** (cover only columns that exist) rather than assume the
  full schema — good behavior generally, not just for the test.
- **process:** backticks inside a double-quoted `git commit -m` trigger shell command substitution
  and silently drop the backticked word (mangled `26cb923` message). Use single quotes / a message
  file for commit bodies.

### Risks & mitigations
- **Risk:** registries and DB values keyed differently (case/whitespace) → false enum-gate
  failures. **Mitigation (verified):** the facet values in `documents` are sourced from the *same*
  registries the vocab is built from (function_category from function-domains, etc.), so keys align;
  the integration tests confirm a real seeded value (`registration`, `UM`, `CLI`, personas) gates
  correctly.
- **Risk:** enum gate too strict — blocks a rebuild on a genuinely-new value. **Mitigation:** that
  *is* the intended behavior; the failure names the offending values (`{n} undefined … value(s)` +
  offender sample) so the fix is a 1-line registry add.

### Lessons learned
- The vocab table makes the enum gate and the consumer explainer share one source — adding a domain
  is now a registry edit that both the producer gate and (after P4) every consumer pick up.
- Defensive column handling (D12) is worth doing in producer-side gather code too, not just
  consumers — fixtures and partial DBs are real.

---

## Phase P3 — Shared Go core `pkg/index` (vdocs-tui)

**Goal:** one importable, contract-aware query core that both vdocs-tui and vdocs-web consume, with
the build-time drift alarm and runtime version check.

**Steps:** P3.1 mechanical move `internal/index` → `pkg/index` (API unchanged; all tests green —
this is the leaf for vdocs-web); P3.2 vendor `v1.json` + `go:generate` codegen of column
constants/row struct/`RequiredSchemaVersion`; P3.3 `Open()` reads `meta.read_schema_version` and
errors clearly on MAJOR mismatch; P3.4 `make contract-check` diffs vendored vs
`~/projects/vdocs/contracts/read/`; P3.5 contract test against a fixture DB built from the spec.
TDD throughout; one PR for P3.1 (isolated mechanical move), then feature PRs.

### Changelog
- **2026-06-11** — ✅ landed (vdocs-tui, two PRs; build + tests + lint + contract-check green).
  - **P3.1** PR #23 (`5d2f880`): `git mv internal/index pkg/index` + import rewrites; API-unchanged.
  - **P3.2–P3.5** PR #24 (`12baa2f`): vendored `pkg/index/contract/v1.json` (`go:embed`),
    `contract.go` (`RequiredSchemaVersion`/`Capabilities`/`ContractViewColumns`), `Open()`
    MAJOR-compat check (unstamped DB degrades), `make contract-check` (in `make check`),
    `contract_test.go`.

### Discoveries
- **D13 (deviation from plan):** chose **`go:embed` + parse** over a `go:generate` code generator
  for the Go contract binding — same runtime/drift/contract guarantees with far less machinery (no
  generator to maintain, no generated-file-diff CI dance). **Tradeoff:** the kickoff's scenario-1
  guarantee ("*compile* error when you read a field the contract lacks") softens to a **test/runtime**
  failure, because the SQL still uses string column names rather than generated constants. Wiring
  generated column constants into every query (true compile-time enforcement) is a larger query
  rewrite — deferred; the drift check + contract test + producer-side doctor gate cover the gap.
- **D14:** `Open()`'s version check must be **lenient on a missing stamp** — pre-contract/foreign
  DBs and the existing Go test fixtures have no `meta` table, so absent → proceed; only a
  *present-but-incompatible* MAJOR is fatal. (Also why the live pre-P1 lake DB still opens in the
  TUI — it just doesn't get the compatibility guarantee until rebuilt.)
- **process:** `git mv internal/index pkg/index` failed until `pkg/` existed (`mkdir -p pkg` first).

### Risks & mitigations
- **Risk:** `make contract-check` needs the vdocs sibling present. **Mitigation (shipped):** the
  drift check self-skips ("drift unknown") when `$(VDOCS_CONTRACT)` is absent, so CI/airgapped
  builds don't break; the vendored copy is authoritative for the build either way.
- **Risk:** vendored contract silently rots behind upstream. **Mitigation (shipped):**
  `make contract-check` is in `make check`, so a local dev build flags drift the moment the sibling
  advances.

### Lessons learned
- `go:embed`+parse is the pragmatic equal of codegen when the generated artifact is just *data the
  code reads* (versions, capability/column sets) rather than *symbols the code references*. Reach
  for codegen only when you want the compiler to enforce references.

---

## Phase P4 — vdocs-tui consumes the contract

**Goal:** flip vdocs-tui onto the contract surface and realize the first concrete payoff (delete the
hardcoded vocab maps).

**Steps:** P4.1 switch queries to `v_*` views; P4.2 snapshot `PRAGMA table_info` and skip facets
whose optional column is absent (extends existing empty-axis suppression); P4.3 read all vocab from
the `vocab` table; P4.4 delete `personaDef`/`sectionDef`/`domainDef` from `explain.go`. Tests first:
explainer returns registry-sourced definitions; a fixture missing an optional column renders without
that facet and without crashing.

### Changelog
- **2026-06-11** — ✅ landed (vdocs-tui PR #25 `91860a4`; build + tests + lint + contract-check green).
  Queries switched to `v_*` views (chunks_fts kept); `DocTOC`/`Preview` order by `v_sections.seq`;
  `Vocab()` loads `Persona`/`Section`/`Domain` from `v_vocab`; `explain.go`'s three hardcoded maps
  **deleted**; `HasContractViews()` skip/degrade for pre-contract DBs; fixtures rebuilt
  contract-faithfully (`ViewDDL` + stamped meta).
- **2026-06-11** — producer round-trip (vdocs `8c3dee8`): added `doc_sections.seq` + read contract
  **v1.2** to satisfy the consumer's ordering need (see D15).

### Discoveries
- **D15 (the canonical round-trip):** switching `DocTOC`/`Preview` to `v_sections` broke ordering —
  **SQLite views have no `rowid`**, and there was no explicit order column. The fix flowed *upstream*
  exactly as designed: add `doc_sections.seq` (document-order ordinal) to the producer → additive
  contract bump **v1.1→v1.2** → re-vendor in vdocs-tui → `ORDER BY seq`. A clean demonstration of
  "consumer demand → versioned, additive producer change → consumer adopts."
- **D16:** the live pre-P1 lake DB has no `v_*` views, so real-corpus integration tests must *skip*
  (via `HasContractViews()`), not fail. Same reason the TUI degrades rather than hard-blocks on it.
  A friendly "rebuild your index" guard in `cmd/vdocs-tui` is a nice follow-up (not yet done).
- **process:** `git add -A` swept two pre-existing untracked `docs/*.draft.yaml` into a commit
  (`8c3dee8`); un-tracked them in `30ec765`. Stage explicit paths only.

### Risks & mitigations
- **Risk:** vocab maps deleted before the producer ships vocab → blank defs. **Mitigation (held):**
  P2.1 shipped `v_vocab` before P4.4 deleted the maps; `orFallback` degrades a missing def to the
  raw code, never a crash.
- **Risk:** a v1.0/v1.1-built DB lacks `seq`/`v_vocab` but passes the MAJOR check. **Mitigation:**
  `Vocab()` v_vocab reads are best-effort (degrade); `ORDER BY seq` with NULLs is harmless ordering,
  not an error. A full rebuild at v1.2 is the clean state.

### Lessons learned
- The whole investment paid off here: a consumer-side need (section order) became a small, additive,
  *versioned* producer change with a re-vendor step — no big-bang, no guesswork about compatibility.
- Deleting the `explain.go` maps is the concrete proof the contract works: vocabulary is now data,
  edited once in `registries/` and consumed everywhere.

---

## Phase P5 — vdocs-web (new repo)

**Goal:** the server-backed web consumer, born contract-correct (option A: local Go server +
SvelteKit, auto-download DB, facets + fuzzy + FTS5).

**Steps:** P5.1 scaffold; P5.2 spine (`/api/facets` + `/api/candidates` over `pkg/index`, proven by
a handler test + a minimal Svelte page rendering live facets) — *nothing downstream until the spine
is green*; P5.3 preview/TOC/fuzzy/FTS endpoints + panes; P5.4 first-run DB auto-download +
`manifest.json` validation (sha256 + `read_schema_version` compatibility, zstd, resumable); P5.5
declare required capabilities + `go:embed` the built front-end; P5.6 cross-compile matrix.

### Changelog
_(none yet)_

### Discoveries
_(to fill)_ — seeded by D5.

### Risks & mitigations
- **Risk:** 294 MB download UX (slow, interrupted, no host). **Mitigation:** zstd-compress (mostly
  text — large ratio), resumable ranged download, sha256 verify, cache under `$XDG_CACHE_HOME`;
  also honor `--db`/`$VDOCS_DB`/`$DATA_DIR` for a locally-present DB (no download).
- **Risk:** schema/DB mismatch after a contract bump — user has an old cached DB. **Mitigation:**
  manifest carries `read_schema_version`; the binary refuses an incompatible cached DB *at fetch/load
  time* with the actionable message, and offers to re-download.
- **Risk:** serving the read-only DB to a browser exposes more than intended. **Mitigation:** bind
  `127.0.0.1` only; DB opened `mode=ro`+`query_only`; JSON API exposes only contract views.
- **Risk:** front-end build toolchain bloats the airgapped binary / breaks offline builds.
  **Mitigation:** SvelteKit static adapter → plain assets embedded via `go:embed`; pin deps; vendor
  the npm cache for offline builds (mirror the Go `GOPROXY=file://` pattern).

### Lessons learned
_(none yet)_

---

## Phase P6 — Multi-consumer hardening (future)

**Goal:** prove the contract scales to N diverging consumers; revived when the MCP endpoint returns.

**Steps:** P6.1 MCP endpoint over `pkg/index` declaring its own required capabilities; P6.2
`make check-consumers` in vdocs runs each sibling consumer's contract test against a *candidate* new
contract → compatibility matrix before publishing a bump.

### Changelog
_(none yet)_

### Discoveries
_(to fill)_

### Risks & mitigations
- **Risk:** consumers diverge in required capabilities; a producer change satisfies one and breaks
  another. **Mitigation:** the union of declared capabilities is the producer's obligation;
  `check-consumers` surfaces the blast radius before the bump lands.

### Lessons learned
_(none yet)_

---

## Cross-phase risk register (summary)

| ID | Risk | Phase | Mitigation |
|----|------|-------|-----------|
| RR1 | Silent structural drift (consumer binds physical tables) | P1/P3/P4 | views + codegen + runtime version check |
| RR2 | Silent vocabulary drift (corpus growth adds undefined values) | P2 | vocab-as-data + doctor enum gate |
| RR3 | Silent data drift (distribution/coverage shifts) | P2 | corpus_snapshot + coverage stats + characterization test |
| RR4 | Mis-versioned contract (breaking change as MINOR) | P1 | contract-lint bump-type enforcement |
| RR5 | Big-bang breaking migration | all | expand/contract (parallel-change) + check-consumers |
| RR6 | 294 MB DB distribution failure / mismatch | P5 | compressed+resumable+sha256+schema_version in manifest |
| RR7 | `internal/`→`pkg/` extraction destabilizes vdocs-tui | P3 | isolated mechanical PR, API-stable, gate green |
| RR8 | DDL/spec/codegen divergence | P1/P3 | doctor validates emitted DB == spec; `go generate` no-diff CI |
