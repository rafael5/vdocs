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
| **P0 — Contract baseline** (vdocs) | P0.1 | `meta(key,value)` table in `index.db` | ⬜ | written by index stage |
| | P0.2 | Stamp `read_schema_version` (start `1.0`) | ⬜ | semver string |
| | P0.3 | Stamp `corpus_snapshot` (build ts · doc count · content hash) | ⬜ | data fingerprint |
| | P0.4 | Drop `doc_meta_staged` from shipped DB | ⬜ | build-scratch leak (D3) |
| **P1 — Read contract + views** (vdocs) | P1.1 | `contracts/read/v1.json` spec describing *today's* schema | ⬜ | SSOT; no behavior change |
| | P1.2 | `contracts/read/CHANGELOG.md` + `read-contract.schema.json` meta-schema | ⬜ | |
| | P1.3 | `v_documents` / `v_sections` / `v_entities` / `v_entity_mentions` views | ⬜ | from spec |
| | P1.4 | Document `chunks_fts` (cols + tokenizer) as named contract | ⬜ | FTS can't be a view (D-fts) |
| | P1.5 | `doctor`: assert emitted DB == spec (views, cols, types, version) | ⬜ | producer gate |
| | P1.6 | `contract-lint`: enforce semver bump-type vs prior spec | ⬜ | breaking change w/o MAJOR fails |
| **P2 — Vocab-as-data + drift gates** (vdocs) | P2.1 | `vocab(kind,code,label,description)` table from `registries/` | ⬜ | sections, domains, personas, doc types, apps, products |
| | P2.2 | `doctor` enum-coverage gate (every distinct facet value ∈ vocab) | ⬜ | growth introducing undefined value fails producer |
| | P2.3 | Coverage stats (% populated, distinct counts, rows) in `manifest.json` | ⬜ | |
| | P2.4 | `capabilities` list in `manifest.json` | ⬜ | `fts5`,`pub_year`,`vocab_table`,… |
| | P2.5 | Corpus characterization (approval) test | ⬜ | distinct-values/counts diff per build |
| **P3 — Shared Go core** (vdocs-tui) | P3.1 | Extract `internal/index` → importable `pkg/index` | ⬜ | API-stable; tests green |
| | P3.2 | Vendor `contracts/read/v1.json` + `go:generate` → col constants/struct/`RequiredSchemaVersion` | ⬜ | codegen |
| | P3.3 | `Open()` runtime version check (MAJOR mismatch → clear error) | ⬜ | |
| | P3.4 | `make contract-check` drift check (vendored vs local vdocs sibling) | ⬜ | the "warn me" alarm |
| | P3.5 | Contract test against fixture DB built from spec | ⬜ | CI |
| **P4 — vdocs-tui consumes contract** | P4.1 | Query `v_*` views, not physical tables | ⬜ | |
| | P4.2 | Defensive optional columns → absent column = absent facet | ⬜ | graceful degradation |
| | P4.3 | Read all vocab from `vocab` table | ⬜ | |
| | P4.4 | **Delete** `explain.go` `personaDef`/`sectionDef`/`domainDef` | ⬜ | first consumer payoff (D4) |
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
_(none yet)_

### Discoveries
_(to fill as work lands)_ — seeded by D1, D3.

### Risks & mitigations
- **Risk:** `corpus_snapshot` hash unstable across rebuilds of identical data (ordering, timestamps
  baked in) → false "data changed" signals, needless vdocs-web re-downloads. **Mitigation:** hash a
  canonical, sorted projection of content columns only (exclude build timestamps from the hash;
  keep the timestamp as a separate display field).
- **Risk:** dropping `doc_meta_staged` mid-build breaks a later stage that reads it. **Mitigation:**
  confirm it's consumed only within the index stage (grep) before dropping; drop at the very end.

### Lessons learned
_(none yet)_

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
_(none yet)_

### Discoveries
_(to fill)_ — seeded by D2, D-fts.

### Risks & mitigations
- **Risk:** views drift from physical tables silently (a column added to `documents` but not to
  `v_documents`). **Mitigation:** P1.5 `doctor` asserts the view's columns == spec; a new physical
  column is invisible to consumers until *deliberately* added to the view + spec (MINOR bump).
- **Risk:** view indirection costs query performance on large joins. **Mitigation:** SQLite views
  are query-rewrite (no materialization); verify with `EXPLAIN QUERY PLAN` parity on the candidate
  query; keep facet-column indices.
- **Risk:** hand-written DDL diverges from `v1.json`. **Mitigation:** generate the view DDL from the
  spec (or, minimally, P1.5 fails if they disagree) — single SSOT.

### Lessons learned
_(none yet)_

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
_(none yet)_

### Discoveries
_(to fill)_ — seeded by D4.

### Risks & mitigations
- **Risk:** registries and DB values are keyed differently (case, whitespace, abbreviation vs full)
  → false enum-gate failures. **Mitigation:** normalize keys in one place (the vocab builder);
  characterization test surfaces mismatches early.
- **Risk:** enum gate too strict — blocks a legitimate corpus rebuild because a new doc type is
  genuinely new. **Mitigation:** the gate *should* block; the fix is a 1-line registry add, which is
  the intended workflow. Provide a clear failure message naming the missing code + registry file.
- **Risk:** characterization-test snapshot churns on every legitimate corpus growth → noisy diffs.
  **Mitigation:** snapshot *structure of the distribution* (distinct value set + presence), not raw
  counts, for the gate; keep counts as informational.

### Lessons learned
_(none yet)_

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
_(none yet)_

### Discoveries
_(to fill)_ — seeded by D2, D6.

### Risks & mitigations
- **Risk:** `internal/`→`pkg/` move breaks the `vdocs-tui` build / import paths broadly.
  **Mitigation:** mechanical move + global import rewrite in a single isolated PR; gate green before
  any feature work; keep the package API identical.
- **Risk:** `make contract-check` needs the vdocs sibling present — fails on a machine without it.
  **Mitigation:** drift check is *advisory + CI-only against a checked-in upstream snapshot*; the
  vendored copy is authoritative for builds, so a missing sibling degrades to "drift unknown," not a
  broken build.
- **Risk:** codegen output committed vs generated-on-build divergence. **Mitigation:** commit the
  generated file + a CI check that `go generate ./...` produces no diff (the standard Go pattern).

### Lessons learned
_(none yet)_

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
_(none yet)_

### Discoveries
_(to fill)_ — seeded by D4.

### Risks & mitigations
- **Risk:** vocab table ships *after* the maps are deleted → blank definitions in the interim.
  **Mitigation:** sequence P2.1 (producer ships vocab) **before** P4.4 (consumer deletes maps); keep
  `orFallback` so a missing definition degrades to the raw code, never a crash.
- **Risk:** a consumer expects a vocab kind the producer doesn't emit yet. **Mitigation:** capability
  declaration (`vocab_table`) + load-time check; missing kind → fallback, logged.

### Lessons learned
_(none yet)_

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
