# vdocs Implementation Plan & Tracker

> **Companion to** [`vdocs-remediation-plan.md`](vdocs-remediation-plan.md) (the *what/why* — the
> forward source of truth). **This document is the *how/status*:** a living tracker of execution.
> Update it as work lands. The remediation plan defines the phases (0, A–E); this tracks each phase's
> stages, status, discoveries, risks, and changelog.

## Introduction

This plan executes the greenfield closure of the vdocs pipeline toward three outcomes — **best human
search · best AI search · best signal-to-noise** (optimal chunking + denoising). Work proceeds on a
**stratified golden dev set** first (Phase 0), proving the full stack end-to-end on ~60–100
shape-varied documents in a separate dev lake (`DATA_DIR=~/data/vdocs-dev`) before expanding to the
full ~1,450-doc corpus. Corpus-frequency work (denoising registries, redundancy metrics) is mined on
the **full** corpus regardless, since it is a corpus-scale phenomenon.

**How to use this tracker**
- The **Master Tracker** is the at-a-glance status of every phase and stage.
- Each **phase section** has its own table (with gate + flag column) followed by **Discoveries**,
  **Risks**, **Changelog**, and **Notes**.
- A **discovery that warrants a change to the plan or implementation** is flagged in *two* places:
  a ⚠️ in the stage table's **Flag** column, and a dated entry under that phase's **Discoveries**
  describing the change and its impact.

**Status legend**

| Symbol | Meaning |
|--------|---------|
| ✅ | Done (gate met) |
| 🟡 | In progress |
| ⬜ | Not started |
| ⏸️ | Blocked (see Notes) |
| ⚠️ | Flag — a discovery warrants a plan/implementation change (see Discoveries) |

---

## Master Tracker

| Phase | ID | Stage / Step | Status | Flag |
|-------|----|--------------|--------|------|
| **0 — Golden dev set** | 0.1 | Mine inventory, propose ~60–100 stratified `doc_id`s | ✅ | |
| | 0.2 | Commit `registries/dev-corpus.txt` + `golden-queries.yaml` | ✅ | |
| | 0.3 | Stand up dev lake (`~/data/vdocs-dev`); run full DAG | ✅ | |
| | 0.4 | Baseline lexical nDCG@10 on golden queries | ✅ | |
| **A — Substrate / chunking** | A1 | Pick embedder (**bge-m3**, 8k) + chunk budget gate | ✅ | |
| | A2 | Context headers (active) + small-leaf merge (built, **gated off** → C) | ✅ | ⚠️ |
| | A3 | `stub` chunks → lexical-only (exclude from semantic) | ✅ | |
| **B — Denoising (full corpus)** | B1 | `discover` at scale; curate phrases + boilerplate; materialize `_shared/boilerplate/` | ✅ | ⚠️ |
| | B2 | Materialize `gold/glossary.md` (PROMOTE) | ⬜ | |
| | B3 | De-weight globals; index extracted tables as data | ⬜ | |
| **C — Semantic + hybrid** | C1 | Add embedder dep; run `embed`; `vectors.db`; manifest flips semantic on | ⬜ | |
| | C2 | ANN query + RRF fusion + full structured pre-filter | ⬜ | |
| **D — MCP endpoint** | D1 | `server/mcp.py` + `vdocs serve-mcp` (Tools/Resources/Prompts) | ⬜ | |
| | D2 | Promote machine-facing sidecars → `index.db` (contract_ver bump) | ⬜ | |
| **E — Human + quality gate** | E1 | Build `publish` + `push` (GitHub markdown tree) | ⬜ | |
| | E2 | Wire `fidelity`; §10.5 retrieval-quality gate; full `validate` gate | ⬜ | |

**Critical path:** 0 → A → C → D. **Parallel:** B and E1 once Phase 0 stands up the dev lake.

---

## Phase 0 — Stand up a stratified golden dev set

**Goal:** prove the full stack fast on ~60–100 shape-varied docs; produce the §10.5 evaluation set.

| ID | Step | Detail | Gate | Status | Flag |
|----|------|--------|------|--------|------|
| 0.1 | Stratified selection | Mine inventory across shape axes (doc_type · era · converter · structure · version-depth · entity-density · size · answerable-Q); propose `doc_id`s + rationale | List approved by maintainer | ✅ | |
| 0.2 | Commit selection | `registries/dev-corpus.txt` (70 doc_ids) + `golden-queries.yaml` (6 starter labeled queries) | Files committed | ✅ | |
| 0.3 | Dev lake | `DATA_DIR=~/data/vdocs-dev` `fetch --select` → full DAG (convert→manifest) | DAG green on dev lake | ✅ | |
| 0.4 | Baseline | Record lexical nDCG@10 / redundancy@k on golden queries | Baseline recorded | ✅ | |

### Discoveries
- **2026-06-06 — selection mined from `index.db`, not raw inventory.** The 461 already-processed
  `is_latest` docs in `index.db` carry *observed* shape (converter, section kinds, chunk counts,
  entity-mention density, version-group depth) — far richer + safer (already proven fetchable) than
  the raw enriched catalog. Stratified the golden set over these. All 70 proposed picks exist in
  `index.db`. *No plan change.*
- **2026-06-06 — Docling routing is genuinely single-doc.** The `converter-routing` registry lists
  exactly one Docling target (`CPRS/cprsguium`); v1 noted cprsguium alone is ~65% of all bare markers
  and `constm` (the only other v1 entry) is absent from the current sample. So the *converter* axis is
  correctly represented by **one** doc (`CPRS:cprsguium`) — not under-sampling. *No plan change; noted
  so a future reviewer doesn't "fix" the 1/70 Docling ratio.*
- **2026-06-07 — select-file parser only handled *full-line* `#` comments.** `_read_select_file`
  (`cli/app.py`) split on whole-line comments only, so the per-pick `# rationale` annotations on
  `dev-corpus.txt` would have been swallowed into the `doc_id`s (70 malformed ids). Fixed to strip
  *inline* `#` comments too (doc_ids never contain `#`); added a TDD unit test. This makes the
  documented "'#' comments allowed" true for inline use and keeps the select file self-documenting.
  *Small in-scope code fix; no plan change.*
- **2026-06-07 — lexical baseline whiffs on concept-queries over terse/generically-titled sections.**
  `kaajee-install-procedure` scores **nDCG@10 = 0.0**: the labeled KAAJEE install sections are indexed
  & searchable (`kind=ok`) but never appear in the top-200 BM25 chunk hits — their bodies are terse
  and their headings generic ("VistA Installation Procedure", "WebLogic Installation"), so other docs'
  install sections outrank them, and the doc-defining token ("KAAJEE") is sparse in the relevant
  bodies. This is the canonical case for **A2 contextual chunk headers** (`«doc_title › section_path»`
  prepended to embedded text) **+ Phase C semantic/hybrid** — it is a clean "before" data point, not a
  label bug. *Validates A2/C rationale; no plan change.* (Also a candidate for golden-label refinement
  as the set matures — do not inflate labels to mask the lexical gap.)

### Risks
- **Sample not representative** → blind spots the full corpus later exposes. *Mitigation:* stratify on the eight shape axes; revisit the set after the first full-corpus run.
- **Dev/prod drift** → fixes that pass on the dev lake but assume sample-only conditions. *Mitigation:* graduation gate requires a full-corpus pass before "done."

### Changelog
- 2026-06-06 — Phase 0 added to the remediation plan; tracker created.
- 2026-06-06 — 0.1 started (🟡): mined `index.db` (461 `is_latest` docs) across the eight shape axes;
  proposed a **70-doc** stratified golden set (all picks verified present in `index.db`). Awaiting
  maintainer approval before committing the select file / fetching.
- 2026-06-07 — 0.1 approved + 0.2 done (✅): committed `registries/dev-corpus.txt` (70 annotated
  doc_ids, parses to 70 bare ids) and `registries/golden-queries.yaml` (6 starter labeled queries:
  kids-install ×2, hwsc-rest ×2, kaajee-auth ×1, + a redundancy@k probe). Fixed inline-comment
  handling in `_read_select_file` (TDD); `make check` green (726 passed, 98.5% cov). Next: 0.3 stand
  up `~/data/vdocs-dev` and run the DAG.
- 2026-06-07 — 0.3 done (✅): dev lake `~/data/vdocs-dev` stood up (prod untouched). **Fetch**:
  70 picks → 455 lineage docs, **453 fetched / 2 failed** (both failures = non-selected NUMI
  prior-versions, "docx unavailable"; all 70 picks fetched). **Full DAG `convert→manifest` ran green**
  in ~3 min: convert 451 (docling=1 → cprsguium ✓, 0 errors), consolidate 451→**69 version groups**,
  index **33,407 sections / 7,189 chunks / 1,824 entities / 22,342 mentions**, validate **0 blocking**,
  **embed SKIPPED** (no fastembed ✓), relate 34,476 edges, manifest `semantic_available=0`. Dev index:
  69 latest anchors, 6,308 searchable sections. All 17 golden-query `section_id` labels resolve in the
  dev index (slugs deterministic across lakes). Next: 0.4 baseline metrics.
- 2026-06-07 — 0.4 done (✅) → **Phase 0 COMPLETE.** Recorded the lexical (FTS5+BM25) baseline on the
  golden queries via `scripts/baseline_golden.py` (report: `reports/baseline-phase0.{md,json}`):
  **mean nDCG@10 = 0.3947 · MRR = 0.5167 · recall@10 = 0.50 · redundancy@10 = 0.017** (5 labeled
  queries + 1 redundancy probe). Per-query nDCG@10 ranges 0.0 (kaajee — see Discoveries) → 0.98
  (hwsc-install-privileges). Redundancy is already near-zero (consolidate collapsed version groups).
  Metric oracle inlined; retrieval path imported (measures the real engine). `make check` green.
  **This is the number every later phase (A2 headers, C semantic/hybrid RRF) must beat.**

### Baseline (Phase 0.4 — lexical FTS5+BM25, dev lake, 2026-06-07)

| metric | value | notes |
|---|---|---|
| mean nDCG@10 | **0.3947** | 5 labeled queries |
| mean MRR | **0.5167** | |
| mean recall@10 | **0.50** | |
| mean redundancy@10 | **0.0167** | near-dup content (Jaccard ≥ 0.85), all 6 queries |

Per-query nDCG@10: kids-install-build 0.267 · kids-delphi-components-install 0.354 ·
hwsc-rest-from-vista-m 0.373 · hwsc-install-privileges 0.979 · kaajee-install-procedure **0.000**.
Reproduce: `DATA_DIR=~/data/vdocs-dev .venv/bin/python scripts/baseline_golden.py`.

### Notes
- `consolidate`/`index`/`relate`/`manifest` are **corpus-global** (rebuild over whatever is in the
  lake), so a *separate dev lake* is the clean way to scope — not per-doc flags on the prod lake.
- The prod lake `~/data/vdocs` (~1,450 docs) stays intact; switch scopes by `DATA_DIR` env var.
- **Dev-lake standup recipe (0.3).** The inventory medallion is the control plane and identical
  across lakes, so we **reuse prod's** rather than re-crawling the live VDL site (avoids drift):
  (1) copy `~/data/vdocs/inventory/` → dev, **preserving mtimes** (`os.utime` from prod) so the cheap
  `size:mtime_ns` fingerprints still match; (2) seed dev `state.db` with the three inventory
  `stage_runs` rows (`crawl`/`catalog`/`serve-inventory` = ok) copied from prod — required because
  `fetch`'s preflight checks upstream completion in `state.db`, not just file presence; (3)
  `fetch --select registries/dev-corpus.txt`; (4) `run --from convert --to manifest`. No doc-side
  acquisitions are copied, so the DOC DAG builds fresh.
- **70 selected ids → 455 fetched docs** (×6.5): `fetch` always acquires a selected doc's **full
  version lineage** (§5.6 invariant 2). Intended — the deep-version-group picks exist to exercise
  `consolidate` (455 physical docs collapse to ~70 latest anchors in the searchable corpus).

---

## Phase A — Substrate / chunking

**Goal:** make chunks optimal *units of knowledge* and safe for the chosen embedder, before any embed.

| ID | Step | Detail | Gate | Status | Flag |
|----|------|--------|------|--------|------|
| A1 | Embedder + chunk sizing | **bge-m3 chosen** (1024-d, 8192-tok); chunk constants verified within budget; `embed` asserts no-truncation per chunk (`embed_pure.assert_within_budget`) | No chunk exceeds model token limit | ✅ | |
| A2 | Context headers + merge | Prepend `«doc_title › section_path»` to embedded text (**active**); merge tiny adjacent leaves under same parent up to TARGET (**built + tested, gated off** `MERGE_SMALL_LEAVES=False`) | Mean chunk substance ↑ (+53% w/ merge); hollow stays 0 | ✅ | ⚠️ |
| A3 | Stub handling | `stub` chunks (referent-only) lexical-only, excluded from semantic | Stubs absent from `vectors.db` | ✅ | |

### Discoveries
- ⚠️→✅ **2026-06-06 — chunk/embedder truncation (plan-impacting; RESOLVED 2026-06-07 in A1).** Current
  `CHUNK_TARGET_CHARS=4000` / `OVERSIZED_CHUNK_CHARS=8000` exceed the **512-token (~2,000 char) limit
  of the originally-planned `bge-small-en-v1.5`** → the back half of large chunks would be silently
  dropped at embed time. **Resolution (A1):** switched the embedder to **bge-m3 (8192-token context,
  1024-d)**; at that budget the existing chunk constants are safe (worst golden-set chunk ~5.7k tok
  worst-case / 4.5k conservative = **54% of budget**, 0 of 7,189 chunks over), so the char constants
  were **kept** (they're B3 calibration targets, not truncation knobs). `embed` now enforces it per
  chunk via `embed_pure.assert_within_budget` (fails the build rather than truncating). Flag cleared.
- **2026-06-07 — bge-m3 dep + dim must be verified at C1.** A1 only *decides* the model + gates chunk
  size; it does **not** install `fastembed` or run `embed`. C1 must confirm fastembed actually serves
  `BAAI/bge-m3` (model id, lazy load) and that `vectors.db` is built at **dim 1024** (up from the old
  384 — ~2.7× vector storage; `embedding_model` row carries model/version/dim). The default
  `Embedder` advertises `BAAI/bge-m3 : 1.0`, `max_tokens=8192`.
- ⚠️ **2026-06-07 — A2b small-leaf merge regresses the *lexical* baseline → GATED OFF pending C.**
  Measured on the dev lake (merge ON): mean chunk substance **+53%** (1769→2703 chars), redundancy@10
  **0.017→0.0**, chunks 7,189→4,708 — but lexical **nDCG@10 0.395→0.223** / recall@10 0.50→0.367.
  Root cause (verified, not a findability loss): merge cites folded content under the **first leaf's**
  anchor, so 5/17 fine-grained golden labels resolve to a merge-anchor *sibling* — a
  **citation-granularity** effect. Merge's real payoff (coherent embedding units) only shows for
  *semantic* retrieval, which isn't live until C. **Decision (maintainer-approved):** keep the merge
  code (tested), gate it off via `index_pure.MERGE_SMALL_LEAVES=False` (current default = pre-A2b
  per-leaf chunking), and **re-enable + measure merge ON vs OFF under hybrid retrieval in Phase C.**
  A2a context headers stay active (embed-only → zero lexical effect; baseline unchanged).

### Risks
- **Wrong embedder → costly re-embed.** *Mitigation:* decide in A1 with a small eval on the golden set; record the choice + dim in `embedding_model`.
- **Over-merging crosses semantic boundaries.** *Mitigation:* merge only within the same parent heading; never merge across H2 boundaries.

### Changelog
- 2026-06-07 — A1 done (✅). Embedder decision: **`BAAI/bge-m3`** (8192-token context, 1024-d) — user-
  approved over nomic-8k / right-sized-bge-small. `_default_embedder` switched from bge-small;
  `Embedder` gained `max_tokens` (default 8192); `embed.run` now calls the new pure gate
  `embed_pure.assert_within_budget` (conservative token estimate, runs before the model loads). Chunk
  constants **unchanged** (proven safe: 0/7,189 golden chunks exceed budget, worst 54%). Also
  committed the pre-existing graceful-skip WIP separately (`1d9c108`). TDD: 6 pure + 1 integration
  test added; `make check` green (733 passed, 98.5% cov). A1 gate verified on the dev lake.
  *Deferred to A2:* contextual chunk headers (`«doc_title › section_path»`) on the embedded text +
  small-leaf merge — A1 covered only the embedder/budget half.
- 2026-06-07 — A2 done (✅). **A2a (active):** `embed_pure.contextual_embed_text` prepends
  `«doc_title › section_path»` to the *embedded* text only (chunks.text/FTS stay clean); `embed.run`
  resolves it via a chunks→doc_sections→documents join. Verified on the dev lake — the KAAJEE install
  section (baseline 0.0) now embeds with its product-name breadcrumb (the intended Phase-C lift). No
  lexical effect (embed not yet run): baseline unchanged. **A2b (built + gated off):**
  `index_pure.chunk_units`/`chunks_for_unit` + `ChunkUnit` merge adjacent small same-parent leaves;
  `index.stage` now builds chunks per-document via `chunk_units`. Measured the ON/OFF tradeoff (see
  Discoveries ⚠️) and **gated off** by maintainer decision. TDD: A2a 4 pure +1 integration; A2b 8
  pure +1 gate-off. `make check` green (747 passed, 98.5% cov). A2a committed in `cbeb7e3`; A2b
  (gated) committed alongside this tracker update.
- 2026-06-07 — A3 done (✅) → **Phase A COMPLETE.** `embed._read_chunks` now filters
  `WHERE s.kind != 'stub'`: a pointer-only `stub` section ("[see boilerplate]") embeds to nothing
  useful, so it stays lexically findable in FTS but is excluded from the semantic surface
  (`vectors.db` holds fewer chunks than `index.db:chunks` by the stub count). Verified on the dev
  lake: 7,189 chunks → **7,141 embed-eligible** (48 stubs excluded, **0 leak**); FTS still holds all
  7,189 (lexical unchanged → baseline unaffected, no re-index needed). TDD: 1 integration test (seed
  reshaped to carry `kind`). `make check` green (748 passed). *Phase-C note:* with A2b merge OFF a
  chunk maps 1:1 to a section so the kind filter is exact; when merge is re-enabled in C, a merged
  unit cites its first leaf — exclude only if that representative is a stub (revisit then).

### Notes
- Constants live in `src/vdocs/stages/index/index_pure.py` (`CHUNK_TARGET_CHARS`,
  `OVERSIZED_CHUNK_CHARS`) and `kernel/markdown.py` (`MIN_SUBSTANTIVE_TOKENS=8`). A1 kept the char
  constants and added the embed-time budget gate; **A2** still adds the context-header field to the
  embedded text (not the displayed/cited body) + the small-leaf merge pass.

---

## Phase B — Denoising (full corpus)

**Goal:** drive signal-to-noise to target by saturating the discover→curate→apply loop.

| ID | Step | Detail | Gate | Status | Flag |
|----|------|--------|------|--------|------|
| B1 | Phrases + boilerplate | Run `discover` on full corpus; curate `phrases`/`boilerplate` registries; materialize `gold/_shared/boilerplate/`; `normalize` references | Boilerplate single-sourced; dead phrases removed | ✅ | ⚠️ |
| B2 | Glossary | Materialize `gold/glossary.md` (PROMOTE); drop per-doc copies | Glossary exists; per-doc dupes gone | ⬜ | |
| B3 | Entity weighting + tables | De-weight globals in ranking; index extracted `tables/*.csv` as searchable structured chunks | Globals not ranking-dominant; tables findable | ⬜ | |

### Discoveries
- ⚠️ **2026-06-07 — the golden-set lexical ablation does NOT capture boilerplate-denoising lift.**
  Applied B1 on a measurement lake (`~/data/vdocs-bmeas`, a copy of the dev golden set): boilerplate
  references **158 → 684**, **89 canonical copies materialized**, phrases 7 → 13 — all working. Yet the
  golden-set baseline was **unchanged** (nDCG@10 0.3947, redundancy@10 0.017, identical to pre-B1).
  Root cause: the golden set's redundancy was *already* ~0 (consolidate collapses version groups), and
  boilerplate blocks are never the *hits* for the curated content queries — so the lexical metric is
  blind to single-sourcing. **Implication for the gate:** "redundancy@k → ~0 on the golden set" is
  trivially already-met and is the **wrong instrument** for boilerplate denoising. The real, measured
  lift is **corpus-scale single-sourcing** (the 158→684 reference count) + cleaner published markdown +
  (Phase C) sharper embeddings / lower *semantic* redundancy. *Plan change:* measure B-denoising by
  corpus single-sourcing counts and a Phase-C semantic-redundancy ablation, not golden lexical nDCG.
- **2026-06-07 — boilerplate candidate `doc_count` is inflated by version-group members.** A deep
  version group (e.g. SD VS-GUI TM, 66 versions) makes one logical document's prose look like it
  recurs in 60+ "docs". Curating it as boilerplate would REFERENCE-strip real content. *Mitigation
  applied (B1b):* require **≥2 distinct apps** in the candidate's sample before promoting — plus an
  explicit exclude of shared package-content (CPRS+PSJ order-checks, GMRA+PSJ allergy) and
  patch-specific text. Kept the 89-entry registry safe/cross-corpus.
- **2026-06-07 — phrase artifacts flatten to an empty furniture-core (DELETE footgun).** `#`, `...`,
  `---`, `**  **` all normalize to `""` via `_furniture_core`, so adding any one as a `phrases` entry
  would blanket-DELETE *every* punctuation-only block corpus-wide (incl. `<hr>`/table separators).
  Deliberately avoided; B1c added only ≥4-word furniture (the "two-sided copying"/"blank page" family).

### Risks
- **Over-aggressive deletion → silent content loss.** *Mitigation:* capture-before-strip is already enforced (`capture.yaml` typed outcomes) + the §10.5/fidelity gate; curate by PR, reversible.
- **Boilerplate near-dup threshold (0.8 Jaccard) mis-clusters.** *Mitigation:* review graded candidates; keep canonical copy + reference, never delete boilerplate.
- **Prod apply needs explicit authorization.** An in-place `--force` rebuild of `~/data/vdocs` was
  auto-denied (correct). Phase B's corpus-wide apply (re-run prod with the enriched registries) is a
  separate maintainer-approved step; the ablation was measured on a throwaway copy instead.

### Changelog
- 2026-06-07 — **B1 complete** (commits `799414b` materialize, `f953e5b` registries). **B1a:**
  `manifest_pure.shared_boilerplate_files` + manifest writes `gold/_shared/boilerplate/<id>.md`
  (REGISTRIES added to `manifest.requires`) — the dangling REFERENCE links now resolve. **B1b:**
  boilerplate registry **21 → 89** (multi-app-safe curation from the full-corpus `patterns.json`).
  **B1c:** phrases **+6** (blank-page furniture family). Ablation on `~/data/vdocs-bmeas`: refs
  158→684, 89 materialized, golden lexical flat (see ⚠️ Discovery). `make check` green (750).

### Notes
- **Must run on the FULL corpus, not the golden set** — boilerplate/phrase/glossary are
  corpus-frequency phenomena (≥3-doc thresholds). Registries are version-controlled in
  `registries/`; current counts are thin (phrases 7, boilerplate 37, glossary 0).

---

## Phase C — Semantic + hybrid retrieval

**Goal:** turn on semantic search and fuse it with lexical/structured via RRF.

| ID | Step | Detail | Gate | Status | Flag |
|----|------|--------|------|--------|------|
| C1 | Embed | `uv add` the chosen model; run `embed`; populate `vectors.db`; `manifest` flips `capabilities.semantic` on | `vectors.db` built; semantic=true | ⬜ | |
| C2 | Hybrid retrieval | Vector ANN over `vec_chunks` + **RRF fusion** with lexical; structured pre-filter as WHERE | hybrid nDCG@10 ≥ lexical baseline | ⬜ | |

### Discoveries
- *(none yet)*

### Risks
- **RRF weighting/`k` tuning** under-/over-weights a mode. *Mitigation:* tune against the golden query set; report per-mode + fused nDCG.
- **Embedding throughput** on the full corpus (24k+ chunks) with an 8k model. *Mitigation:* batch; run on dev lake first; cache.

### Changelog
- *(none yet)*

### Notes
- `embed` already skips gracefully without `fastembed` (preflight SKIP). C1 is gated by A1 (chunk
  sizing) — do not run embed until A1 lands.

---

## Phase D — MCP endpoint

**Goal:** expose the corpus to agents over MCP with the full Tool/Resource/Prompt surface.

| ID | Step | Detail | Gate | Status | Flag |
|----|------|--------|------|--------|------|
| D1 | MCP server | `src/vdocs/server/mcp.py` + `vdocs serve-mcp`: `search`/`get_section`/`get_document`/`find_entity`/`cross_references`/`list_versions`/`get_lineage` + `vdocs://` resources | Agent queries corpus via MCP, semantically, with citations | ⬜ | |
| D2 | Sidecars → index.db | Promote `revisions`/`toc`/`cross_refs`/`doc_tables` into `index.db` (bump `index` `contract_ver`) | `list_versions`/`cross_references`/table lookups DB-served | ⬜ | |

### Discoveries
- *(none yet)*

### Risks
- **MCP transport/auth & read-only safety.** *Mitigation:* open derived stores read-only; refuse incompatible `contract_ver`.
- **Schema additions (D2) invalidate downstream.** *Mitigation:* `contract_ver` bump already forces re-derive via inputs_fp.

### Changelog
- *(none yet)*

### Notes
- Reuses `server/search.py` (now hybrid) and `server/ids.py`. The `vdocs-corpus` skill + `ai-manifest`
  already orient agents; MCP is the richer protocol front door.

---

## Phase E — Human deliverable + quality gate

**Goal:** ship the human GitHub corpus and stand up the measured quality gate.

| ID | Step | Detail | Gate | Status | Flag |
|----|------|--------|------|--------|------|
| E1 | Publish + push | `publish` (markdown-only tree + INDEX + glossary, gitignored images) → `push` to `vistadocs/vdl` | Human corpus live on GitHub | ⬜ | |
| E2 | Fidelity + gates | Wire `fidelity` into DAG; §10.5 retrieval-quality gate; finish full `validate` (schema + per-doc verdict) | PASS/REVIEW/QUARANTINE verdicts + published quality claim | ⬜ | |

### Discoveries
- *(none yet)*

### Risks
- **`publish`/`push` are unbuilt from scratch** (no stage dirs). *Mitigation:* smallest viable tree first; commit-replay stays deferred (opt-in).
- **Fidelity gate too strict → blocks release.** *Mitigation:* REVIEW band with sign-off; QUARANTINE only on floor breach.

### Changelog
- *(none yet)*

### Notes
- `fidelity/` dir exists but is **not wired** into `build_stages`. `publish`/`push`/`analyze` dirs do
  not exist yet.
