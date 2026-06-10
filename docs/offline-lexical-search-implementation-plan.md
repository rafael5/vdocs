# Offline Lexical Search — Implementation Plan & Tracker

> **Companion to** [`offline-lexical-search-plan.md`](offline-lexical-search-plan.md) (the *what/why*
> — the active source of truth for direction). **This document is the *how/status*:** a detailed,
> living execution tracker. The lean plan defines phases L0–L4 and their gates; this breaks each into
> implementable steps and records status, changelog, discoveries, risks, remediations, and
> improvement recommendations as work lands.
>
> **Background:** [`historical/vdocs-state-2026-06-08.md`](historical/vdocs-state-2026-06-08.md) (as-is snapshot) ·
> [`historical/vdocs-implementation-plan.md`](historical/vdocs-implementation-plan.md) (frozen spike record).

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

## Dev-first execution & graduation to prod

**Develop and smoke-test every change on the dev lake (`~/data/vdocs-dev`, ~70 `is_latest` docs);
touch prod (`~/data/vdocs`, 1,449 docs) only twice, deliberately.** The dev lake + golden set are the
smoke-test rig (verified: the KAAJEE doc and its golden target sections are present in dev, so the
`0.0` baseline is a real mis-ranking the fix can move there).

- **Dev-native (no prod run):** all of L1 (the harness defaults to `~/data/vdocs-dev`; re-index is
  seconds), L2 (Go CLI built/tested against the dev `index.db`; parity gate runs on the golden set),
  L4 (the gate lives on a dev/fixture lake — prod's 167 MB is too big for CI). Ranker changes (L1.1,
  L1.3) are **query-time and corpus-agnostic** — they need no re-index at all.
- **The only deliberate prod operations:** (1) **one** prod re-index after **L1.2** bumps `index`'s
  `contract_ver` (to add `doc_title` to prod's FTS); (2) **publish the full corpus** + ship the prod
  `index.db` (L3).
- **Caveat — sample ≠ corpus.** BM25 depends on corpus-wide IDF / avg-doc-length; weights optimal on
  8k dev chunks can shift on 27k prod chunks. **Tune on dev, then re-measure on prod after the prod
  re-index, before publishing the quality claim (L4.3).** Don't assume dev nDCG transfers 1:1. (Golden
  `section_id`s are stable across the `doc_title` change, so the set stays valid on both lakes.)
- **Dry-run recipe:** reproduce dev baseline → L1.1 → L1.2 (+dev re-index, assert KAAJEE>0) → L1.3 →
  build Go CLI on dev + parity gate → **graduate:** bump `contract_ver`, re-index prod once,
  re-measure, ship.

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
4. [Phase L1.5 — Curated term signal](#phase-l15--curated-term-signal-human-in-the-loop)
5. [Phase LF — Faceted (focused) search](#phase-lf--faceted-focused-search)
6. [Phase L2 — Faceted-first Go search CLI](#phase-l2--faceted-first-go-search-cli)
7. [Phase L3 — Human corpus deliverable](#phase-l3--human-corpus-deliverable)
8. [Phase L4 — Quality gate](#phase-l4--quality-gate)
9. [Cross-cutting risks & recommendations](#cross-cutting-risks--recommendations)

---

## Master tracker

| Phase | ID | Step | Status | Note |
|-------|----|------|--------|------|
| **L0 — Housekeeping** | L0.1 | Delete 0-byte `vectors.db` zombie (prod) | ✅ | trashed 2026-06-08 |
| | L0.2 | Decide `relate`: re-run vs shelve graph | ✅ | **shelved** — graph not needed for lexical |
| | L0.3 | Add `index`→`relate` ordering guard (if kept) | ⛔ | N/A — relate shelved |
| **L1 — Lexical quality** | L1.1 | Field-weighted `bm25()` in `search.py` | ✅⚠️ | infra landed; heading weights give **no lift** — lever → L1.2 |
| | L1.2 | Index `doc_title` into `chunks_fts` | ✅ | KAAJEE 0→0.43; **mean 0.387→0.469**; hwsc-rest ⚠️ |
| | L1.3 | Glossary query expansion (`fts_match_query`) | ✅⚠️ | built+tested; **regresses → gated OFF** (opt-in only) |
| | L1.4 | Re-measure + record final L1 quality | ✅ | shipped **0.523** (19-q) / KAAJEE 0→0.43 |
| **L1.5 — Curated term signal** | L1.5a | Generate promote/demote triage worksheet | ✅ | `docs/l1.5-curation-worksheet.md` |
| | L1.5b | Human triage (mark Decision cols) | ⬜ | **awaiting maintainer review** |
| | L1.5c | Weighted-field stoplist (registry) | ⬜ | "guide" 48% of titles, etc. |
| | L1.5d | Title normalization (strip boilerplate) | ⬜ | strip DIBRG/UM/version scaffolding |
| | L1.5e | Entity-type demotion (globals) | ⬜ | 2,359 globals dominate |
| | L1.5f | Selective synonyms (test individually) | ⬜ | blanket failed (L1.3); per-entry |
| **LF — Faceted search** | LF.1 | Prototype facet catalog + faceted query path | ✅ | `scripts/faceted_search_demo.py`; 26,923→238 |
| | LF.2 | Audience registry (doc_type→audience) | ✅ | `registries/inventory/audiences.yaml` |
| | LF.3 | Facet catalog API (`server/facets.py`) | ✅ | `facet_catalog()` |
| | LF.4 | Faceted query path (narrow→FTS-within) | ✅ | `faceted_search()`, TDD (11 tests) |
| | LF.5 | SQLite indices on facet columns | ✅ | added to `index` schema (next rebuild) |
| | LF.6 | Measure faceted vs open-ended precision | ✅ | typeapp 0.523→0.551; granularity caveat |
| **L2 — Faceted-first Go CLI** | L2.1 | Go module + `modernc.org/sqlite` (FTS5), read-only open | ⬜ | no cgo |
| | L2.2 | Port ranker + facet layer (`query` pkg) | ⬜ | MATCH/weights + faceted filter |
| | L2.3 | CLI: facet flags + content + open-ended fallback | ⬜ | `vdocs-search --type/--app/…` |
| | L2.4 | Cross-compile matrix + handoff docs | ⬜ | static binaries |
| | L2.5 | Ranker-parity gate (Go ↔ Python on golden set) | ⬜ | CI |
| **L3 — Human corpus** | L3.1 | `publish` stage (md tree + INDEX + glossary) | ⬜ | from `consolidated/` |
| | L3.2 | `push` to public docs repo | ⬜ | `vistadocs/vdl` |
| **L4 — Quality gate** | L4.1 | Gate golden metrics in CI (floor) | ⬜ | regressions fail |
| | L4.2 | Expand `golden-queries.yaml` → 19 queries | ✅ | new ref **mean 0.523** (18 labeled); 2 hard 0.0 cases |
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
- **L0.3 — Ordering guard.** **N/A** — `relate` is shelved (L0.2), so there is no graph to keep in
  sync. Re-open only if the graph is ever revived.

### Changelog
- 2026-06-08 — **L0 closed.** L0.1: deleted the 0-byte prod `vectors.db` zombie (trashed). L0.2:
  **`relate` shelved** — the knowledge graph is not required for offline lexical search; the
  `relations` table stays absent from prod `index.db` and no re-run is scheduled. L0.3: N/A
  (no graph to guard). Baked the **Dev-first / graduation-to-prod** block into this plan.

### Discoveries
- *(carried from the as-is snapshot, 2026-06-08)* `vectors.db` 0-byte zombie; `relations` absent from
  prod `index.db`; `registries/glossary` empty despite a materialized 268 KB `gold/glossary.md`.

### Risks
- **Shelving `relate` leaves `manifest`/any consumer that reads `relations` to tolerate its absence.**
  *Mitigation:* the lexical path doesn't read the graph; if a future structured-search step wants it,
  revive `relate` then (and add the ordering guard at that point).

### Remediations
- 2026-06-08 — vectors.db zombie removed; relate formally shelved (decision recorded, not a defect).

### Recommendations for improvement
- If the graph is ever revived, treat `relations` materialization as part of `index`'s definition of
  done (or merge the two stages' invariants) so "rebuilt index ⇒ missing graph" can't recur.

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
- 2026-06-08 — **L1.1 landed (✅⚠️).** Added field-weighting infra to `search_pure` (`FTS_COLUMNS`,
  `FTS_WEIGHTS`, `bm25_weights`, `bm25_expr`; column order single-sourced; `_BODY_COL` now derived
  from it) and wired the weighted `bm25(...)` into `search.py`. TDD: 4 pure tests first.
  `make check` green (777 passed, 98.13% cov). **Measured on dev: no net lift** (see Discovery) —
  weights set to a mild, measured-neutral prior (title 2 · section_path 1.5 · body 1). Working
  baseline reaffirmed at **nDCG@10 = 0.3874** (the recorded 0.395 predates the C1 dev re-index).
- 2026-06-08 — **Baseline drift noted.** Dev `index.db` was rebuilt by the C1 oversized-chunk fixes
  after 0.395 was recorded; current dev baseline is **0.3874 / MRR 0.5167 / recall 0.50 /
  redundancy 0.0333**. KAAJEE = 0.0 (10 hits, none relevant — a real mis-ranking).
- 2026-06-08 — **L1.2 landed (✅) — the lever worked.** Added a `doc_title` FTS column to
  `chunks_fts` (`stages/index/stage.py`, schema + population from `documents.title`), bumped
  `index.contract_ver` → 2, synced `search_pure.FTS_COLUMNS`, and re-indexed the **dev** lake
  (8,036 chunks, seconds). TDD: integration test on a title-only token ("Guide") first. Updated 3
  hand-built FTS fixtures (search/cli tests) to the 7-column schema. `make check` green (778 passed,
  98.13% cov). **Measured (dev):** **KAAJEE 0.0 → 0.4278**, **mean nDCG@10 0.3874 → 0.4692**
  (+21%), recall@10 0.50 → 0.7167, MRR 0.5167 → 0.5389. `doc_title` weight tuned to **2.5** by sweep
  (≥4 over-promotes common title tokens — see Discovery).
- 2026-06-08 — **L1.3 built, measured, GATED OFF (✅⚠️) — a negative result.** Promoted
  `gold/glossary.md` → `registries/glossary/expansions.yaml` (696 acronym→expansion pairs), added a
  tested pure expander (`acronym_phrase_clauses`/`fts_match_query(expansions=…)`) + an opt-in loader
  (`search.default_expansions`). TDD first. **Measured on the 19-query set, expansion *regresses*:**
  token-OR form 0.5232 → 0.4337 (even broke KAAJEE to 0.0); the precise phrase form still 0.5232 →
  0.5092. So expansion is **off by default** (opt-in `expansions=` param retained). `make check` green
  (784 passed, 98.09% cov). Shipped ranker unchanged at **0.5232**.
- 2026-06-08 — **L1.4 (✅) final L1 result.** Shipped lexical ranker = L1.1 (neutral) + L1.2
  (doc_title). **Dev golden set (19 q): mean nDCG@10 0.5232 / MRR 0.5849 / recall@10 0.6204**, up from
  the **0.3874** start (+35%); the marquee **KAAJEE 0.0 → 0.4278**. Open per-query misses for later
  tuning: `fileman-add-field` 0.0, `vbecs-accept-order` 0.0, `hwsc-rest` 0.224 (L1.2-introduced).

### Discoveries
- ⚠️ **2026-06-08 — weighting *section* headings gives no lexical lift on this corpus.** Sweep on the
  dev golden set: title=8/path=4 **regressed** the mean (0.3874→0.366, `hwsc-rest` 0.373→0.266);
  title=3/path=2 also down (0.377); title≤2/path≤1.5 **exactly neutral** (0.3874). Cause is
  structural — VistA section titles are generic ("Installation", "Overview") and the answering text
  is in the **body**, so up-weighting headings promotes generic-titled sections over the real answer.
  The doc-defining token (e.g. "KAAJEE") lives in the **document title**, which is **not yet an FTS
  column**. *Impact:* L1.1's value is the reusable weighting **infrastructure**, not a heading boost;
  the actual lever moves to **L1.2 (index `doc_title`)**, after which `doc_title` — not section
  `title` — should carry the weight. *Remediation:* mild neutral weights kept; re-tune in L1.2/L4.2.
- ⚠️ **2026-06-08 — `doc_title` indexing regresses `hwsc-rest` (0.3726 → 0.2243), even unweighted.**
  Adding `doc_title` to the FTS surface changes BM25 for *all* queries, and for
  "How does VistA M call a REST web service via HWSC?" it lets docs with common tokens ("VistA",
  "Web Service") in their **title** outrank the truly relevant XOBW sections. The doc_title weight
  sweep (dev) shows the tradeoff: w=2.5 is the aggregate optimum (mean 0.4692, KAAJEE fixed, recall
  0.7167) but `hwsc-rest` stays below its baseline; w≥4 tanks it to 0.0. *Impact:* a net-positive
  change with one per-query regression — accepted for the big KAAJEE win + mean/recall lift, **flagged
  to revisit.** *Remediation candidates:* (a) glossary/structured-filter help in L1.3 (expand
  "HWSC"/"REST" so the right doc wins on body+path, not just title); (b) cap doc_title's contribution
  for multi-token generic queries; (c) grow the golden set (L4.2) and re-tune. Tracked for L1.4.
- ⚠️ **2026-06-08 — query expansion REGRESSES lexical quality on this corpus (L1.3 negative result).**
  OR-adding an acronym's expansion *tokens* injects common words ("Kernel", "Authentication",
  "Web", "System") that drown the rare-acronym signal `doc_title` weighting relies on — it dropped
  the mean 0.5232 → 0.4337 and **broke KAAJEE to 0.0**. Switching to a precise **phrase** clause
  (`"healthevet web services client"`) recovered most of the loss but stayed net-negative (0.5092):
  it helps `hwsc-rest` (+0.025) yet hurts KAAJEE/rpc/hwsc-mgmt. *Root cause:* L1.2's `doc_title`
  already captures the acronym precisely; any extra OR-clause mostly perturbs BM25 normalization and
  adds noise. *Remediation:* expansion **gated OFF** by default; kept as a tested opt-in
  (`expansions=` param + `default_expansions()` loader) and the 696-entry registry for a future
  *adaptive* use (expand only when the bare query yields no doc-title hit). The 3rd L1 lever doesn't pay.

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

## Phase L1.5 — Curated term signal (human-in-the-loop)

**Goal:** apply human judgement the metric can't supply — *which terms are noise* — to the weighted
lexical fields. Motivated by the L1.2/L1.3 findings: field-weighting `doc_title` re-amplified
corpus-ubiquitous terms (IDF normally demotes them), so common sense must prune them. **Without a
human in the loop, common sense will not prevail.** Each curation is **measured against the 19-query
golden set and kept only if it helps** (propose → measure → keep).

> **Re-scoped by Phase LF (2026-06-08).** L1.5 governs the **open-ended discovery fallback**, not the
> primary path. Faceting (LF) turns the doc_type/title words this phase agonizes over into *facets*,
> so L1.5 is now **lower-stakes**: finish the clearly-correct, doc_type-redundant STOPs (the
> maintainer's scan) and the title normalization, but do **not** chase the long tail.

**Grounding (prod, 462 latest docs):** "guide" is in **48%** of titles, "version" 37%, "manual" 35%,
"installation" 25% — all carrying the L1.2 ×2.5 `doc_title` weight as pure noise. The DIBRG
scaffolding "Deployment, Installation, Back-Out, and Rollback Guide" spans ~40 titles. Globals
dominate entities (2,359 distinct / 28,599 mentions, led by `^TMP`, `^DIC`).

**Steps** *(L1.5 complete — the triage worksheets below were removed post-curation; the durable
output lives in `registries/`.)*
- **L1.5a — Triage tables (✅).** Editable CSVs in `docs/human validation/` (one per table: title
  tokens, boilerplate fragments, entity types, ambiguous terms, synonyms) + `HOW-TO-USE.md`; a
  read-only overview was `docs/l1.5-curation-worksheet.md`. Generated from prod; each row has a
  `decision` column. *(worksheets now removed — see note above.)*
- **L1.5b — Human triage.** Maintainer edits the `decision` column in the `docs/human validation/` CSVs
  (the irreplaceable step). *Blocking.*
- **L1.5c — Weighted-field stoplist.** Encode the STOP tokens as a `registries/` list applied to the
  **weighted fields only** (title/doc_title), not the body (IDF already handles the body). *Gate:*
  nDCG@10 ↑ or flat; `hwsc-rest`-class regressions recover.
- **L1.5d — Title normalization.** Strip the STRIP fragments from the indexed `doc_title` so the
  weighted field carries the discriminative core (package/topic). Re-index dev; measure.
- **L1.5e — Entity-type demotion.** Down-weight/exclude `global` (and maybe `hl7_segment`) from the
  ranking signal; keep file#/rpc/routine/option. Measure.
- **L1.5f — Selective synonyms.** Test the worksheet's synonym candidates **one at a time** (blanket
  expansion failed in L1.3); keep only entries that move the metric.

### Changelog
- 2026-06-08 — **L1.5a done; phase opened.** Generated the triage worksheet from the prod corpus
  (title-token DF, title n-gram boilerplate, entity-type distribution, ambiguity + synonym
  candidates). Slotted L1.5 into the tracker. **Awaiting maintainer triage (L1.5b)** before encoding.

### Discoveries
- **2026-06-08 — field-weighting re-introduces the ubiquitous-term problem BM25 IDF normally solves.**
  In the body, IDF makes "guide"/"vista" inert; weighting `doc_title` ×2.5 (L1.2) manually amplifies
  them again — the mechanism behind the `hwsc-rest` regression. *So curation must target the weighted
  fields, not the body* — a precise, measured scope for the stoplist/normalization.

### Risks
- **Over-stopping kills real signal** (e.g. "installation" is noise in a title but a real query term
  in the body). *Mitigation:* apply the stoplist to weighted fields only; never to the body; measure.
- **Title normalization could strip a discriminative token** if a package name overlaps scaffolding.
  *Mitigation:* strip only curated fragments (human-approved), re-index dev, diff hits.

### Remediations
- *(none yet — pending L1.5b)*

### Recommendations for improvement
- Make the triage worksheet a **recurring artifact** (`discover` can regenerate candidate lists as the
  corpus grows), so curation is maintained, not one-shot.
- Consider an FTS5 **custom tokenizer with a stoplist** for the weighted columns as the clean
  long-term mechanism (vs. query/title rewriting).

---

## Phase LF — Faceted (focused) search

**Goal:** support the way an expert actually finds *specific* information — **narrow by structured
facets first, then content-search within the tiny narrowed set** — alongside (not instead of) the
open-ended ranker. This is the "focused information retrieval" method the maintainer described:
`doc_type → title/package → frontmatter/entity → content`.

**Why (the design rationale):** a single open-ended ranking function can't know whether a token is a
doc-type word, a package, or content — which is the root of every L1.x fight ("guide" 48%, "vista
useless", the `doc_title` over-weighting). **Faceting dissolves those problems** by turning structured
signals into *filters* instead of forcing them through one ranker. Evidence (prototype on the dev
lake, `scripts/faceted_search_demo.py`): two facet picks collapse **26,923 chunks → 238 (0.88% of the
corpus)**; the within-facet content search is then trivially precise. The hard cases open-ended
ranking *failed* on are solved structurally — `hwsc-rest` (→ technical-audience + "web service"),
`fileman`/`vbecs`/file-#60 (→ entity facet + content), KAAJEE (→ package + "weblogic").

**No pipeline/indexing change** — faceting is a **serving-layer** read over columns `index.db` already
has. Each of the maintainer's 4 layers maps to existing data:

| Layer | Facet | Source (already produced) |
|---|---|---|
| 1 document type | `doc_type` + derived **audience** (technical/clinical/admin) | `documents.doc_type` (25) |
| 2 title/package | `app_code` / `pkg_ns` + title FTS | `documents.app_code` (142), `pkg_ns` (131) |
| 3 frontmatter/entity | version / `is_latest` + entity (file#/RPC/routine/option) | `documents.version/is_latest`, `entities` (4,792) |
| 4 content | BM25 within the narrowed set | `chunks_fts` (+ `doc_key IN (…)`) |

**Steps**
- **LF.1 — Prototype (✅).** `scripts/faceted_search_demo.py`: facet catalog + layered
  narrow→content-search, reusing the shipped ranker. Demonstrates the flow end-to-end on dev.
- **LF.2 — Audience registry.** `registries/inventory/audiences.yaml` (`doc_type → technical/clinical/
  admin`) — realizes the "differentiate users/usage" insight as a real facet.
- **LF.3 — Facet catalog API.** Promote the catalog into `server/facets.py` (distinct facet values +
  counts) with TDD; a `manifest`-style artifact the CLI/UI presents.
- **LF.4 — Faceted query path.** `faceted_search(filters, query)` in `server/` (narrow→FTS-within),
  TDD; reuses `search_pure` so within-facet ranking == `vdocs ask`.
- **LF.5 — Indices.** Add SQLite indices on `documents(doc_type, app_code, pkg_ns, is_latest)` at
  `index` build time for instant filtering.
- **LF.6 — Measure precision.** Show faceted vs open-ended on the golden set (faceted should hit the
  relevant doc with near-perfect precision once the facets are supplied).

### Changelog
- 2026-06-08 — **LF opened; LF.1 prototype done.** Built `scripts/faceted_search_demo.py` and verified
  the layered flow on the dev lake (26,923→238 chunks on two facets; hard open-ended cases solved
  structurally). Design recorded; L2 reshaped to faceted-first.
- 2026-06-08 — **LF.2–LF.6 landed (real code, TDD).** `registries/inventory/audiences.yaml`
  (doc_type→audience); `server/facets_pure.py` (narrow-clause + audience resolution, 5 unit tests) +
  `server/facets.py` (`facet_catalog` + `faceted_search` + `default_audiences`, 6 integration tests);
  facet indices added to the `index` schema (LF.5, perf-only, applies on next rebuild). `make check`
  green (795 passed, 98.02% cov). **LF.6 measured** (`scripts/faceted_eval.py`, dev golden set,
  ceiling = facet chosen from the answer): mean nDCG@10 open-ended **0.5232** → faceted **0.5513**
  (typeapp) / **0.5292** (app-only). Big per-query wins where the answer is concentrated:
  `hwsc-web-service-manager` 0.36→0.67, `vbecs` 0.0→0.22, `hl7` 0.92→0.98, `rpc` 0.32→0.41.

### Discoveries
- **2026-06-08 — facet *granularity* is the dial; nDCG under-credits faceting.** Strict
  `doc_type+app` faceting gives the biggest lift but can **exclude valid cross-doc answers**
  (`kids-install-build` 0.23→0.0 — its relevant sections span XU-TM *and* XOBW, which a single-doc
  facet drops); package-only (`app`) is safer but smaller (+0.006). The aggregate nDCG lift is modest
  because (a) the open-ended ranker is already decent on these queries and (b) nDCG penalises the
  recall an over-narrow facet sacrifices. **Faceting's real value is precision + user control +
  explainability + the 0.88% candidate-set collapse for focused retrieval — not the aggregate nDCG.**
  Operating guidance: default facets to **package/audience level**, not single-doc. `fileman-add-field`
  stays 0.0 even faceted — a *within-doc* ranking miss, orthogonal to faceting.

### Discoveries
- **2026-06-08 — faceted-first is the better primary path for focused retrieval, and it needs no
  pipeline change.** The structured signals the pipeline already produces (doc_type, package, entity,
  version) do the heavy narrowing; the contentious open-ended title-weighting/stoplist work (L1.x)
  becomes a *lower-stakes refinement of the discovery fallback*, not the main event. The maintainer's
  `doc_type`-redundancy scan points exactly here: those words belong in the **facet layer**.

### Risks
- **Facet discoverability** — a user must know the facets. *Mitigation:* present counted facet
  catalogs (LF.3); offer open-ended as the top-level fallback.
- **Audience mapping is a judgement** (doc_type→audience). *Mitigation:* small curated registry
  (LF.2), maintainer-reviewable.

### Recommendations for improvement
- Promote the machine-facing sidecars (`toc`, `cross_refs`) into `index.db` (remediation **D2**) to
  enable a 5th drill-down layer (within-doc structural navigation) — optional for v1.
- A faceted **TUI/static-HTML** front-end (counted facet menus + content box) is the natural human UI;
  the Go CLI (L2) is the headless core it sits on.

---

## Phase L2 — Faceted-first Go search CLI

**Goal:** the portability deliverable — a single static, cross-compiled binary that searches a
handed-over `index.db` offline with **zero ML dependencies**, built **faceted-first** (LF) with an
open-ended fallback. Decision (lean plan, 2026-06-08): **Go + `modernc.org/sqlite` (FTS5 compiled
in)**; `vdocs` (Python) stays the index builder; `index.db` is the contract.

**Steps**
- **L2.1 — Module + engine.** Go module; `modernc.org/sqlite` (pure-Go, cgo-free, FTS5); open
  `index.db` **read-only**. *Gate:* opens prod `index.db`, runs a raw FTS5 MATCH, no cgo in the
  build.
- **L2.2 — Port the ranker + facet layer.** A `query` package mirroring `search_pure` (MATCH +
  `bm25(...)` weight vector) **and** the faceted narrow→content-search path (LF.4) + facet catalog
  (LF.3). Keep it small and declarative. *TDD:* Go table tests for MATCH/weights + faceted filtering.
- **L2.3 — CLI (faceted-first).** `vdocs-search` with facet flags `--type --app --pkg --audience
  --entity` (narrow), an optional content query (search within), `--facets` (print the catalog), and a
  bare `<query>` open-ended fallback; `--json` for machine output, human output = citations + snippet.
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
- 2026-06-08 — **L4.2 (done early, ✅).** Pulled forward before L1.3 so expansion is tuned on firmer
  ground (per the dev-first plan). Grew `golden-queries.yaml` 6 → **19 queries** (+13), spanning the
  dev-lake shape axes (FileMan DD, RPC Broker, MailMan network, Radiology, Pharmacy release, TIU
  notes, VPR domains, Lab File-60 audit, CPRS GUI, VBECS orders, Lexicon, HL7 security, HWSC mgmt).
  Every label verified **present + chunk-reachable** in `~/data/vdocs-dev` (41/41) and graded
  content-first (read section titles vs intent; 3/2/1), not rank-first — no inflation. **New
  reference (current L1.2 ranker, dev): mean nDCG@10 = 0.5232, MRR 0.5849, recall@10 0.6204** (18
  labeled). This replaces the 6-query 0.4692 as the L1.3 baseline.

### Discoveries
- **2026-06-08 — the expanded set surfaced 2 honest hard misses (ranker, not labels).**
  `fileman-add-field` = 0.0 (the DI Developer's-Guide "adding-fields-f"/"adding" sections rank below
  top-10; generic-titled DD sections from *other* docs win) and `vbecs-accept-order` = 0.0
  (doc_title weighting floats VBECS to the top correctly, but the specific "accept-orders-*" sections
  lose to other VBECS sections). Verified by inspecting the live top-10 — the labeled sections are
  genuinely the right answers, just mis-ranked. *Impact:* concrete targets for L1.3 (query expansion)
  and future tuning; they are the new "before" data points, kept un-inflated.

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
