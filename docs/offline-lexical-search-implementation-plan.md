# Offline Lexical Search — Implementation Plan & Tracker

> **Companion to** [`offline-lexical-search-plan.md`](offline-lexical-search-plan.md) (the *what/why*
> — the active source of truth for direction). **This document is the *how/status*:** a detailed,
> living execution tracker. The lean plan defines phases L0–L4 and their gates; this breaks each into
> implementable steps and records status, changelog, discoveries, risks, remediations, and
> improvement recommendations as work lands.
>
> **Background:** [`vdocs-state-2026-06-08.md`](vdocs-state-2026-06-08.md) (as-is snapshot) ·
> [`vdocs-implementation-plan.md`](vdocs-implementation-plan.md) (frozen spike record).

## Working protocol

1. **TDD — hard rule.** Write the `*_pure.py` unit test (or Go `_test.go`) first, confirm it fails,
   implement, confirm green. `make check` (ruff line 100 · mypy · pytest random-order · coverage ≥95%)
   before any commit.
2. **Per-step cadence:** implement → `make check` green → **update this tracker's Status + abbreviated
   note** → append a phase **Changelog** entry → **commit** (and push). One step ≈ one commit where
   practical.
3. **Flags:** a discovery that changes the plan/implementation gets a ⚠️ in the tracker **and** a dated
   entry under that phase's **Discoveries**, with the fix recorded under **Remediations**.
4. **Measurement discipline:** every L1 change is measured against the golden set
   (`scripts/baseline_golden.py`) and the before/after recorded — never assert a lift, show the number.

## Status legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Done (gate met, `make check` green) |
| 🟡 | In progress |
| ⬜ | Not started |
| ⏸️ | Blocked (see Notes) |
| ⛔ | Parked / out of scope |
| ⚠️ | Flag — a discovery warrants a plan/impl change (see Discoveries) |

## Table of contents

1. [Master tracker](#master-tracker)
2. [Phase L0 — Transition housekeeping](#phase-l0--transition-housekeeping)
3. [Phase L1 — Lexical quality](#phase-l1--lexical-quality)
4. [Phase L2 — Distributable Go search CLI](#phase-l2--distributable-go-search-cli)
5. [Phase L3 — Human corpus deliverable](#phase-l3--human-corpus-deliverable)
6. [Phase L4 — Quality gate](#phase-l4--quality-gate)
7. [Cross-cutting risks & recommendations](#cross-cutting-risks--recommendations)

---

## Master tracker

| Phase | ID | Step | Status | Note |
|-------|----|------|--------|------|
| **L0 — Housekeeping** | L0.1 | Delete 0-byte `vectors.db` zombie (prod) | ⬜ | from killed embed run |
| | L0.2 | Decide `relate`: re-run vs shelve graph | ⬜ | absent from prod `index.db` |
| | L0.3 | Add `index`→`relate` ordering guard (if kept) | ⬜ | wipe-on-rebuild sharp edge |
| **L1 — Lexical quality** | L1.1 | Field-weighted `bm25()` in `search.py` | ⬜ | query-time; zero rebuild |
| | L1.2 | Index `doc_title` into `chunks_fts` | ⬜ | build-time; `contract_ver` bump |
| | L1.3 | Glossary query expansion (`fts_match_query`) | ⬜ | needs registry term map (L1.3a) |
| | L1.4 | Re-measure + record final L1 quality | ⬜ | vs nDCG@10 0.395 / KAAJEE 0.0 |
| **L2 — Go CLI** | L2.1 | Go module + `modernc.org/sqlite` (FTS5), read-only open | ⬜ | no cgo |
| | L2.2 | Port ranker (`query` pkg mirrors `search_pure`) | ⬜ | MATCH + weights |
| | L2.3 | CLI (flags, human + `--json`, citations) | ⬜ | `vdocs-search` |
| | L2.4 | Cross-compile matrix + handoff docs | ⬜ | static binaries |
| | L2.5 | Ranker-parity gate (Go ↔ Python on golden set) | ⬜ | CI |
| **L3 — Human corpus** | L3.1 | `publish` stage (md tree + INDEX + glossary) | ⬜ | from `consolidated/` |
| | L3.2 | `push` to public docs repo | ⬜ | `vistadocs/vdl` |
| **L4 — Quality gate** | L4.1 | Gate golden metrics in CI (floor) | ⬜ | regressions fail |
| | L4.2 | Expand `golden-queries.yaml` → ~20–30 | ⬜ | trust weight-tuning |
| | L4.3 | Publish the quality claim | ⬜ | reproducible |

**Suggested order:** L0 (quick) → L1 (defines the quality ceiling, mostly query-time) → L2 (the
headline portability deliverable) → L3/L4 parallelizable. **Critical path to a shippable tool:**
L1 → L2.

---

## Phase L0 — Transition housekeeping

**Goal:** clear the loose ends the as-is snapshot flagged so development starts from a clean,
truthful lake. Small, fast, no new abstractions.

**Steps**
- **L0.1 — Delete the 0-byte `vectors.db`.** `~/data/vdocs/vectors.db` is a 0-byte file left by the
  OOM-killed run; remove it so nothing mistakes it for a built index. (Data-only; no code.)
- **L0.2 — `relate` decision.** The `relations` graph is absent from the current prod `index.db`
  (wiped by this week's `index` rebuilds). For the lexical-only goal the graph is not required;
  decide explicitly to **(a) re-run `relate`** to restore it, or **(b) formally shelve** it and note
  that `manifest`/any consumer must tolerate its absence. Record the decision here.
- **L0.3 — Ordering guard (only if L0.2 = keep).** `index` rebuilds `index.db` wholesale, wiping
  `relations`; `relate` must run after. Add a guard/preflight so a lone `index` run flags that
  `relate` is now stale, preventing silent graph loss.

### Changelog
- *(none yet)*

### Discoveries
- *(carried from the as-is snapshot, 2026-06-08)* `vectors.db` 0-byte zombie; `relations` absent from
  prod `index.db`; `registries/glossary` empty despite a materialized 268 KB `gold/glossary.md`.

### Risks
- Re-running `relate` on prod touches the live `index.db`; do it when no other run is active.

### Remediations
- *(none yet)*

### Recommendations for improvement
- Treat `relations` materialization as part of `index`'s definition of done, or merge the two stages'
  invariants, so "rebuilt index ⇒ missing graph" can't recur.

---

## Phase L1 — Lexical quality

**Goal:** close the lexical quality gap — beat the **nDCG@10 = 0.395** baseline and fix the
`kaajee-install-procedure` **0.0** vocabulary-mismatch case — using cheap levers, two of which are
query-time (zero rebuild). Measure each lever independently.

**As-is facts this phase acts on** (from the audit):
- `server/search.py` ranks with `bm25(chunks_fts)` — **unweighted** (all columns weight 1).
- `chunks_fts(chunk_id⌀, section_id⌀, doc_key⌀, title, section_path, body)` — `section_path`
  (breadcrumb) **is** indexed; the **document title is not** (joined only at query time). `⌀` = UNINDEXED.
- `search_pure.fts_match_query` builds a plain OR-of-quoted-tokens MATCH string.
- `registries/glossary` holds only a README; `gold/glossary.md` (268 KB) is materialized.

**Steps**
- **L1.1 — Field-weighted BM25.** Pass per-column weights to `bm25(chunks_fts, w…)` in
  `server/search.py`, weighting `title`/`section_path` (and `doc_title` once L1.2 lands) above `body`.
  Keep weights as named constants. *TDD:* a pure helper builds the weight vector in column order
  (unit-tested); integration test asserts ordering on a seeded DB. *Gate:* nDCG@10 ↑ vs 0.395, no
  per-query regression among the labeled set.
- **L1.2 — Index `doc_title` into `chunks_fts`.** Add a `doc_title` column to the FTS schema in
  `stages/index/stage.py` and populate it from `documents.title` per chunk. **Implementation notes:**
  (1) column placement shifts the `body` index — update `_BODY_COL` (the `snippet()` target) in
  `search.py` and the bm25 weight-vector order to match; (2) this is a schema change → **bump
  `index`'s `contract_ver`** so consumers re-derive; (3) re-index the **dev** lake and verify the
  KAAJEE sections now surface. *Gate:* `kaajee-install-procedure` nDCG@10 > 0; dev re-index stays
  seconds.
- **L1.3 — Glossary query expansion.**
  - **L1.3a — term map.** Promote `gold/glossary.md` (and/or `discover`'s glossary candidates) into a
    structured `registries/glossary` YAML (term → synonyms/expansions, e.g. `KAAJEE` ↔ its expansion).
    Data-driven; no terms hard-coded in code.
  - **L1.3b — expansion fn.** In `search_pure`, expand query tokens via the term map before building
    the MATCH string. *TDD:* pure-function tests (expansion + safe MATCH construction) first.
  - **L1.3c — wire + measure.** Wire into `fts_match_query`; measure lift where applicable.
- **L1.4 — Re-measure + record.** Run the full golden set; record final L1 nDCG@10 / MRR /
  recall@10 / redundancy@10 and the per-lever deltas in this phase's Changelog.

### Changelog
- *(none yet)*

### Discoveries
- *(none yet)*

### Risks
- **Weights overfit the 6-query golden set.** *Mitigation:* prefer changes that help the *class*
  (title-bearing tokens), not individual labels; grow the set (L4.2) before trusting fine tuning.
- **`contract_ver` bump (L1.2) forces a full re-derive** of `index.db`. Cheap (no model) but not free
  on prod. *Mitigation:* iterate on the dev lake; re-index prod once, deliberately.
- **Expansion over-broadens recall** (synonyms pull in noise), depressing precision. *Mitigation:*
  expand conservatively; measure precision/redundancy alongside recall.
- **Column-order/weight-vector drift** between the FTS schema and `bm25()`/`_BODY_COL`. *Mitigation:*
  single source the column order; integration test that pins it.

### Remediations
- *(none yet)*

### Recommendations for improvement
- Add **prefix (`tok*`) and proximity/`NEAR`** options to `fts_match_query` for morphology and
  locality once the basics land.
- Consider a **blended AND/OR pass** (require some tokens, OR the rest) to lift precision on
  multi-term queries without losing recall.
- Treat the glossary term map as a **maintained asset** fed by `discover`; it benefits both expansion
  and the human glossary deliverable (L3).

---

## Phase L2 — Distributable Go search CLI

**Goal:** the portability deliverable — a single static, cross-compiled binary that searches a
handed-over `index.db` offline with **zero ML dependencies**. Decision recorded in the lean plan
(2026-06-08): **Go + `modernc.org/sqlite` (FTS5 compiled in)**; `vdocs` (Python) stays the index
builder; `index.db` is the contract.

**Steps**
- **L2.1 — Module + engine.** Go module; `modernc.org/sqlite` (pure-Go, cgo-free, FTS5); open
  `index.db` **read-only**. *Gate:* opens prod `index.db`, runs a raw FTS5 MATCH, no cgo in the
  build.
- **L2.2 — Port the ranker.** A `query` package mirroring `search_pure`: build the MATCH string
  (with L1.3 expansion) + the `bm25(...)` weight vector (L1.1) + the structured WHERE. Keep it small
  and declarative. *TDD:* Go table tests for MATCH construction + weights.
- **L2.3 — CLI.** `vdocs-search <query>` with `--db --k --app --doc-type --json`; human output =
  table with snippet + citation (`section_id`/URI/`body_path`), `--json` = machine-readable. Glossary
  term map embedded via `go:embed`.
- **L2.4 — Cross-compile + handoff.** `GOOS`/`GOARCH` matrix (linux/darwin/windows × amd64/arm64);
  document the "give a developer the corpus" path (`index.db` + binary, no rebuild). Decide: ship full
  prod `index.db` (167 MB) or a curated subset. *Gate:* a clean machine with no Python/ML searches via
  documented steps.
- **L2.5 — Ranker-parity gate.** Run the Go binary against `golden-queries.yaml` in CI; assert it
  reproduces the Python ranker's top-k/nDCG within tolerance. *Gate:* divergence fails CI.

### Changelog
- *(none yet)*

### Discoveries
- *(none yet)*

### Risks
- **Two-language drift** (Go ranker vs Python `search_pure`). *Mitigation:* L2.5 parity gate is the
  contract; keep the ranker surface tiny and declarative.
- **`modernc.org/sqlite` vs cgo `mattn`**: pure-Go is slightly slower but trivially cross-compiles and
  has no C toolchain. *Mitigation:* speed is a non-issue at local FTS5 scale; if ever needed, the cgo
  build with `-tags sqlite_fts5` is a drop-in.
- **FTS5 tokenizer mismatch** between the build-time index and the Go query path (e.g. unicode
  folding). *Mitigation:* the query only constructs MATCH text; tokenization lives in the DB — verify
  identical results via L2.5.
- **`index.db` size (167 MB) is heavy for handoff.** *Mitigation:* offer a curated subset; document
  both.

### Remediations
- *(none yet)*

### Recommendations for improvement
- A `--interactive`/REPL mode for human browsing (read-eval loop over the same engine).
- Optional **SQLite-WASM + static HTML** companion for a browser-zero-install experience on the
  dev-lake-size corpus (prod 167 MB is heavy for a browser tab) — only if an audience asks.
- Ship a tiny `make dist` that builds the matrix + bundles `index.db` + a README into per-platform
  archives.

---

## Phase L3 — Human corpus deliverable

**Goal:** ship the human-browsable markdown corpus so search hits resolve to readable docs — the
human half of the original master plan, now the headline deliverable.

**Steps**
- **L3.1 — `publish` stage.** Build a markdown-only tree from `consolidated/` + an `INDEX` + the
  materialized glossary. *Gate:* tree builds; internal links/anchors resolve.
- **L3.2 — `push`.** Commit the published tree to the public docs repo (`vistadocs/vdl`). *Gate:*
  corpus live and browsable.

### Changelog
- *(none yet)*

### Discoveries
- *(none yet)*

### Risks
- **Anchor/slug drift** between `index.db` `section_id`s and the published tree breaks
  search→doc resolution. *Mitigation:* reuse the same slug logic (`server/ids.py`); test resolution.
- **Repo size / binary assets** (images) on push. *Mitigation:* CAS assets already deduped; decide
  what ships.

### Remediations
- *(none yet)*

### Recommendations for improvement
- Make `publish` output the **same `section_id` URIs** the search tool emits, so a hit can deep-link
  straight to the published doc.
- Generate a static search page alongside the tree (ties into L2's WASM option).

---

## Phase L4 — Quality gate

**Goal:** make retrieval quality measured and non-regressing, and publish a reproducible claim.

**Steps**
- **L4.1 — Gate in CI.** Run `scripts/baseline_golden.py` against a committed floor; regressions fail.
- **L4.2 — Expand the golden set.** Grow `golden-queries.yaml` toward ~20–30 queries across the shape
  axes so weight-tuning (L1) is trustworthy.
- **L4.3 — Publish the claim.** Record the final lexical nDCG@10 / redundancy@k as the documented,
  reproducible quality statement.

### Changelog
- *(none yet)*

### Discoveries
- *(none yet)*

### Risks
- **A small/biased golden set makes the gate meaningless or brittle.** *Mitigation:* L4.2 first;
  grade honestly (don't inflate labels to mask gaps — see the spike's KAAJEE note).
- **CI without a lake** — the harness needs an `index.db`. *Mitigation:* gate against the committed
  dev-lake fixture or a small built-in fixture, not the 167 MB prod DB.

### Remediations
- *(none yet)*

### Recommendations for improvement
- Track **per-axis** nDCG (kids-install, hwsc-rest, kaajee-auth, …) not just the mean, so a class
  regression is visible.
- Add **redundancy@k** and **version-correctness** to the gate, not just nDCG.

---

## Cross-cutting risks & recommendations

**Risks**
- **Index rebuild is still whole-DB, not incremental.** Cheap today (seconds–minutes, no model) but a
  large corpus change re-derives everything. *Mitigation:* acceptable for now; revisit per-doc
  incremental indexing only if rebuild time becomes a real iteration drag.
- **Two delivery artifacts (binary + `index.db`) can drift in version.** *Mitigation:* stamp the
  binary with the `index.db` `contract_ver`/fingerprint it was tested against (manifest already
  carries one); refuse mismatched stores.

**Recommendations**
- Keep `embed`/A1/`b1c5c2c` in-tree (parked, not deleted). Un-park prerequisites remain: (a) a
  worker/thread cap to kill the fan-out OOM, **and** (b) content-hash delta-embedding so an upstream
  change doesn't rebuild the whole `vectors.db`.
- If semantic ever returns, prefer a **lightweight static-embedding** surface (`model2vec` — tens of
  MB, CPU-instant, no process fan-out) fused via RRF — never the heavyweight fastembed/nomic path on
  this corpus.

### Changelog (plan-level)
- 2026-06-08 — **Implementation plan opened.** Detailed L0–L4 breakdown + tracker created as the
  how/status companion to `offline-lexical-search-plan.md`. All steps ⬜; working protocol = TDD →
  `make check` → update tracker → commit, per step.
