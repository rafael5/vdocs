# vdocs Implementation Plan & Tracker

> **Companion to** [`vdocs-remediation-plan.md`](vdocs-remediation-plan.md) (the *what/why* — the
> forward source of truth). **This document is the *how/status*:** a living tracker of execution.
> Update it as work lands. The remediation plan defines the phases (0, A–E); this tracks each phase's
> stages, status, discoveries, risks, and changelog.

## 🏁 Closure — spike succeeded, plan frozen (2026-06-08)

> **This plan is CLOSED and frozen as a record.** It is no longer executed to its original C→D
> finish. Go-forward work lives in **[`offline-lexical-search-plan.md`](offline-lexical-search-plan.md)**.

The remediation effort this plan tracked was, in effect, a **spike** — and a spike's deliverable is a
*decision*, not a feature set. It delivered: it subset the full VDL into a stratified gold dev corpus,
stood up the entire 14-stage DAG end-to-end on it, recorded a lexical baseline (nDCG@10 = **0.395**),
drove denoising to prod, and then produced the **decisive architectural finding** that closes it:

> **Key discovery (full detail in Phase C Discoveries, 2026-06-08): the all-or-nothing
> embedding/vector path is not worth its cost on this corpus.** It OOM-killed the machine via ONNX
> process fan-out (~19 workers × ~1.78 GB ≈ 24.6 GB on a 16-core/27 GiB box), and — more
> structurally — it has **no incrementality**: any upstream doc add or silver-doc change forces a
> full ~26k-chunk re-embed + `vectors.db` rebuild, on a corpus we do **not** control upstream.

That finding, set against the **reframed goal** — *high-quality offline, human, no-AI search,
distributed to developers who have no agent to plug in* — flips the architecture decision:

| | **Lexical (FTS5 + BM25)** | **Vector (embed → vectors.db)** |
|---|---|---|
| Footprint | SQLite built-in; no model/GPU | ~500 MB model + fastembed + onnxruntime + sqlite-vec |
| Rebuild on corpus change | seconds–minutes, no inference | full re-embed of all chunks; OOM-prone |
| Incrementality | cheap; trivially incremental | none — one new doc ⇒ whole-corpus rebuild |
| Iteration | field weights / query shaping are *query-time* | every chunking tweak invalidates the index |
| **Portability** | **one `index.db`, opened anywhere with stock `sqlite3`, zero ML deps** | recipient needs the full ML stack to query at all |

For this corpus + goal, lexical is the better engineering trade and its residual quality gap is
closable cheaply (field-weighted BM25 + doc-title/breadcrumb in FTS + glossary expansion) — and
**portability is the headline**: "distribute to developers with no agent" *is* a portability
requirement that a self-contained SQLite file satisfies and a 500 MB-model surface does not.

**Disposition of the phases** (the Master Tracker rows are annotated to match):
- **Kept / done & still load-bearing:** Phase 0 (golden set → now the lexical quality harness),
  Phase B (denoising — helps lexical *and* human readability; applied to prod).
- **Done but embed-motivated, now inert for lexical-only:** A1 (chunk-sizing to the embedder token
  budget) and A2a (contextual headers — already noted to have *zero* lexical effect). Retained, not
  load-bearing for the go-forward goal.
- **⛔ Parked:** Phase C (semantic + hybrid) — see the 2026-06-08 Discovery.
- **⛔ Descoped:** Phase D (MCP endpoint) — that is the *AI-agent* deliverable; out of scope for the
  no-agent goal. Revisit only if an agent consumer ever materializes.
- **➡️ Promoted to primary go-forward work** (tracked in the new plan): Phase E (human deliverable —
  `publish`/`push` + the lexical quality gate) **plus** the lexical-quality thread and a
  zero-dependency **distributable offline search tool** over `index.db`.

Everything below this section is the **frozen execution record** of the spike — accurate as of
2026-06-08, not maintained further.

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
| ⛔ | Parked / descoped at closure (see the 🏁 Closure section) |
| ⚠️ | Flag — a discovery warrants a plan/implementation change (see Discoveries) |

---

## Master Tracker

| Phase | ID | Stage / Step | Status | Flag |
|-------|----|--------------|--------|------|
| **0 — Golden dev set** | 0.1 | Mine inventory, propose ~60–100 stratified `doc_id`s | ✅ | |
| | 0.2 | Commit `registries/dev-corpus.txt` + `golden-queries.yaml` | ✅ | |
| | 0.3 | Stand up dev lake (`~/data/vdocs-dev`); run full DAG | ✅ | |
| | 0.4 | Baseline lexical nDCG@10 on golden queries | ✅ | |
| **A — Substrate / chunking** | A1 | Pick embedder (**nomic-embed-text-v1.5**, 8k; A1 chose bge-m3 — see ⚠️) + chunk budget gate | ✅ | ⚠️ |
| | A2 | Context headers (active) + small-leaf merge (built, **gated off** → C) | ✅ | ⚠️ |
| | A3 | `stub` chunks → lexical-only (exclude from semantic) | ✅ | |
| **B — Denoising (full corpus)** | B1 | `discover` at scale; curate phrases + boilerplate; materialize `_shared/boilerplate/` | ✅ | ⚠️ |
| | B2 | Materialize `gold/glossary.md` (PROMOTE) | ✅ | |
| | B3 | De-weight globals; index extracted tables as data | ✅ | |
| **C — Semantic + hybrid** | C1 | Add embedder dep; run `embed`; `vectors.db`; manifest flips semantic on | ⛔ | ⚠️ |
| | C2 | ANN query + RRF fusion + full structured pre-filter | ⛔ | |
| **D — MCP endpoint** | D1 | `server/mcp.py` + `vdocs serve-mcp` (Tools/Resources/Prompts) | ⛔ | |
| | D2 | Promote machine-facing sidecars → `index.db` (contract_ver bump) | ⛔ | |
| **E — Human + quality gate** | E1 | Build `publish` + `push` (GitHub markdown tree) | ➡️ moved | |
| | E2 | Wire `fidelity`; §10.5 retrieval-quality gate; full `validate` gate | ➡️ moved | |

**Critical path (original):** 0 → A → C → D. **Superseded at closure (2026-06-08):** C/D parked·
descoped; E + lexical-quality work moved to
[`offline-lexical-search-plan.md`](offline-lexical-search-plan.md). See the 🏁 Closure section.

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
| A1 | Embedder + chunk sizing | A1 chose **bge-m3** (1024-d); **C1 switched to `nomic-embed-text-v1.5`** (768-d, 8192-tok) — fastembed's dense API doesn't serve bge-m3 (⚠️ Discoveries). Chunk constants verified within the 8k budget; `embed` asserts no-truncation per chunk (`embed_pure.assert_within_budget`) | No chunk exceeds model token limit | ✅ | ⚠️ |
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
- ⚠️ **2026-06-07 — embedder switched bge-m3 → `nomic-ai/nomic-embed-text-v1.5` at C1 (plan-impacting).**
  A1 decided **bge-m3** (1024-d) and only *gated* chunk size — it did not install fastembed or run
  `embed`. At C1 (commit `41514dd`) we found **fastembed's dense `TextEmbedding` API does not serve
  bge-m3** (only via sentence-transformers/FlagEmbedding), so to keep the planned `uv add fastembed`
  toolchain the default `_default_embedder` switched to **`nomic-ai/nomic-embed-text-v1.5`** — the
  fastembed-native long-context (8192-tok) embedder. Consequences: **`vectors.db` is dim 768, not
  1024** (still ~2× the old 384); the model needs a **task prefix** on every input — the corpus side
  uses `search_document:` (C1), the query side uses `search_query:` (C2); same no-truncation property
  (largest golden chunk ~5.7k tok « 8192). The `embedding_model` row carries
  `nomic-ai/nomic-embed-text-v1.5 : 1.5 : 768`. See `stages/embed/stage.py:_default_embedder`. *Flag
  on A1 + C1 rows; the original bge-m3 1024-d expectation is superseded.*
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
| B2 | Glossary | Materialize `gold/glossary.md` (PROMOTE) by harvesting the corpus's acronym tables; *(per-doc dupe-drop deferred)* | Glossary exists (2,287 terms) | ✅ | |
| B3 | Entity weighting + tables | De-weight globals in the entity-index headline (5 vs 25); index extracted `tables/*.csv` as searchable chunks | Globals not headline-dominant; tables findable | ✅ | |

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
- 2026-06-07 — **B2 done** (`9d57208`). `manifest` harvests the corpus's own acronym/abbreviation
  tables (silver `tables/*.csv` whose header reads `<term>|<definition>`) and PROMOTEs them into one
  `gold/glossary.md` — new pure `acronym_table_pairs` + `build_glossary` (case-insensitive dedupe,
  most-common casing/def, content-skippable). Full corpus ≈ **2,287 terms** from 287 acronym tables
  (988 on the golden lake), real definitions (VA/CPRS/KIDS/FileMan…). The discover glossary
  *candidates* were useless (bare uppercase tokens, no defs) — harvesting tables is the right source.
  Per-doc dupe-drop deferred (needs capture-gated normalize stripping). TDD 6 pure; `make check` 756.
- 2026-06-07 — **B3 done** (`9bce0e7`) → **Phase B COMPLETE.** **B3b (§8.4) tables-as-data:** `index`
  re-introduces each extracted `tables/*.csv` as a searchable chunk (`find_table_refs` +
  `table_chunk_text`; chunk id `<section_id>#table-NN.csv` cites the referencing section) → **+563
  table chunks** on the golden lake (7,189→7,752); a data-dictionary query now returns the FileMan
  routines table (was invisible). **B3a (§8.2) de-weight globals:** `build_entity_index` caps
  low-signal types (globals) to **5** headline slots vs 25, full set stays queryable (974 globals in
  `index.db`). Semantic-boost de-weight is Phase C. TDD 5; `make check` 761.
- 2026-06-07 — **Phase B APPLIED TO PROD** (maintainer-authorized). `DATA_DIR=~/data/vdocs run
  --from normalize --to manifest --force` over all 1,449 docs, **0 errors**: boilerplate refs
  649→**2,437**, `_shared/boilerplate/` **89** copies, `gold/glossary.md` **2,081** terms, **1,996**
  table chunks (total 24,338→26,334), globals 25→**5** in the headline. Verified on disk. (In-place
  prod rebuild required explicit auth — auto-denied on the first attempt.)

### Phase B summary (2026-06-07)

| deliverable | result |
|---|---|
| boilerplate registry | 21 → **89** (multi-app-safe) |
| boilerplate refs single-sourced | 158 → **684** |
| `_shared/boilerplate/` materialized | **89** canonical copies (was dangling) |
| phrases | 7 → **13** (blank-page family) |
| `gold/glossary.md` | **2,287 terms** (harvested acronym tables) |
| extracted tables searchable | **+table chunks** (was invisible) |
| globals in entity headline | 25 → **5** (still fully queryable) |

**APPLIED TO PROD** (`~/data/vdocs`, 2026-06-07, maintainer-authorized): re-ran prod
`normalize→manifest --force` with the enriched registries + current code across all **1,449 docs,
0 errors**. Corpus-wide before→after: boilerplate refs **649 → 2,437** (3.8×); `_shared/boilerplate/`
**0 → 89** materialized; `gold/glossary.md` **0 → 2,081** terms; searchable **table chunks 0 → 1,996**
(total chunks 24,338 → 26,334); global entity headline **25 → 5** slots. consolidate 462 groups /
relate 110,387 edges unchanged-shape. (This also brought prod to current code — A2b merge stays OFF
so chunk structure is unchanged apart from the new table chunks; A2a/A3 are embed-only.) Throwaway
`~/data/vdocs-bmeas` is now redundant (safe to delete). **Gate reframed** (see ⚠️ Discovery): the
golden-set lexical metric is blind to denoising; the lift is corpus single-sourcing + Phase-C
semantic.

### Notes
- **Must run on the FULL corpus, not the golden set** — boilerplate/phrase/glossary are
  corpus-frequency phenomena (≥3-doc thresholds). Registries are version-controlled in
  `registries/`; current counts are thin (phrases 7, boilerplate 37, glossary 0).

---

## Phase C — Semantic + hybrid retrieval

**Goal:** turn on semantic search and fuse it with lexical/structured via RRF.

> ⛔ **PARKED (2026-06-08) — plan-changing.** On this corpus the embed/vector path costs more
> than it returns for the *actual* near-term goal (high-quality **offline, human, no-AI** search,
> distributed to developers with no agent to plug in). Two compounding findings drove the call:
> a **process-fan-out OOM that killed the whole machine overnight**, and **no incrementality —
> every upstream doc add/change forces a full ~26k-chunk re-embed + `vectors.db` rebuild** on a
> corpus we do **not** control upstream. See the 2026-06-08 Discovery. **Pivot: lexical-first**
> (field-weighted BM25 + doc-title/breadcrumb in FTS + glossary query expansion). Revisit a
> *lightweight static-embedding* surface only if a measured golden-query gap demands it.

| ID | Step | Detail | Gate | Status | Flag |
|----|------|--------|------|--------|------|
| C1 | Embed | `uv add fastembed`; run `embed`; populate `vectors.db` (dim 768); `manifest` flips `capabilities.semantic` on | `vectors.db` built; semantic=true | ⛔ PARKED | ⚠️ |
| C2 | Hybrid retrieval | Vector ANN over `vec_chunks` + **RRF fusion** with lexical; structured pre-filter as WHERE | hybrid nDCG@10 ≥ lexical baseline | ⛔ PARKED | |

### Discoveries
- ⚠️⚠️ **2026-06-08 — PLAN-CHANGING: the heavyweight embed/vector path is not worth its cost on
  this corpus; Phase C semantic+hybrid is PARKED, pivot to lexical-first.** Two compounding findings
  from the live prod embed run:

  **(1) A process-fan-out OOM killed the entire machine overnight — distinct from the b1c5c2c
  per-batch fix.** The Jun-8 live run (`vdocs run --only embed` on `~/data/vdocs`, ~26,179 chunks)
  kept climbing past the "fixed" ~5.3 GB single-worker peak and at **01:44:31** the kernel
  OOM-killer fired. Root cause is **not** per-batch padding (that *is* fixed) but **fastembed /
  ONNX-Runtime process fan-out**: a single OOM dump shows **19 `python` worker processes** (≈ one
  per core on the **16-core** box), **each independently resident at ~1.78 GB RSS** (model weights +
  ONNX runtime loaded per process), summing to **~24.6 GB of `python`** against **27 GiB RAM + ~2 GiB
  swap**. The kernel fired the OOM-killer **9 times** and SIGKILLed **14 processes** — the cascade
  went *beyond* embed into the user session itself (`systemd`/`sd-pam`/VS Code/`codex`), so the whole
  `claude` task died and **`vectors.db` was never materialized**. The b1c5c2c fix bounds *one*
  worker's padded batch; it does nothing about *N* workers each loading the full model. A safe
  unattended run would need an explicit cap (ONNX `intra_op` / `OMP_NUM_THREADS` + fastembed
  `parallel=1` / single-process) — **but see (2) before investing.**

  **(2) `embed` has no incrementality — every corpus change forces a FULL re-embed + `vectors.db`
  rebuild.** `EmbedStage.run` reads *all* latest non-stub chunks, re-embeds the **entire** corpus,
  and atomically rebuilds `vectors.db` from scratch (temp + `os.replace`); there is no per-chunk
  delta. Its SKIP/run decision is the cheap input fingerprint of `index.db:chunks`, which is **just
  the row count** (`rows:{N}`, `kernel/fingerprint.py`). Consequences:
  - **Fetch one new VDL doc — or any silver normalize/chunking change that adds/removes/splits
    chunks — re-embeds all ~26,179 chunks** (the heavy, OOM-prone, multi-GB, tens-of-minutes job
    above). One document ⇒ the whole corpus.
  - **Same-count text edits silently skip** (the cheap fingerprint is blind to content) → stale
    vectors unless `--force` / `--verify` (a correctness footgun in its own right).
  - The VDL is a **large upstream corpus we do NOT control** — docs are added/revised on the VA's
    cadence, so this full-rebuild cost is **recurring, not one-time**.
  - It also **throttles iteration on the cheaper, higher-leverage lexical/structural/chunking work**:
    every chunking tweak invalidates the *entire* `vectors.db`, so the full embed cost is re-paid on
    each experiment — directly opposing rapid lexical optimization.

  **Decision (plan change).** The actual near-term goal is **high-quality offline, human, no-AI
  search distributed to developers who have no agent to plug in** — not agent/semantic retrieval.
  For *that* goal the embed/vector cost (CPU fan-out OOM risk + full-corpus rebuild on every upstream
  change + iteration drag) is **not justified**. **Park C1/C2.** Pivot to **lexical-first**:
  field-weighted BM25 + doc-title/breadcrumb indexed in `chunks_fts` + glossary query expansion —
  all rebuild in **seconds**, cannot OOM, and are well-matched to expert humans searching technical
  VistA docs (exact-token strength; the human reformulates, the agent can't). Revisit a *lightweight
  static-embedding* surface (e.g. `model2vec` — tens of MB, CPU-instant, no process fan-out, no
  transformer inference) **only if** a measured golden-query gap proves lexical insufficient — never
  the heavyweight fastembed/nomic path on this corpus. *Supersedes the Phase C goal; C1/C2 parked.*
- ⚠️ **2026-06-07 — embedder is `nomic-ai/nomic-embed-text-v1.5` (768-d), not bge-m3 (1024-d).**
  fastembed's dense `TextEmbedding` API doesn't serve bge-m3, so C1 (commit `41514dd`) switched the
  default backend to fastembed-native nomic-embed-text-v1.5 (8192-tok context). `vectors.db` is built
  at **dim 768**; every input is task-prefixed (`search_document:` corpus side / `search_query:` query
  side, C2). Full detail + rationale in Phase A Discoveries (the A1 entry). *Tracker reconciled:
  A1/C1 rows + details updated.*
- **2026-06-07 — embed OOM fixed before the first real run.** The fixed `batch_size=256` made
  fastembed/ONNX pad every batch to its longest member, so transient memory scaled with
  `items × longest_seq` — one ~2.5k-token chunk dragged all 256 up and allocated ~20-25 GB, OOM-killing
  the box (and the VSCode terminal cgroup) twice with no `vectors.db` produced. Fix (`b1c5c2c`, landed
  on master): `embed_pure.token_batched` bounds the *padded* footprint (`items × longest ≤
  max_batch_tokens=8192`, `max_batch_items=64`) and `_build_vectors_db` streams vectors batch-by-batch
  instead of accumulating them. Measured peak on the full-corpus run: **~5.3 GB RSS** (model + ONNX
  runtime), far under the 27 GB box. *No plan change; unblocks C1.*
- **2026-06-08 — the A1 budget gate worked: it caught two oversized-chunk classes before `vectors.db`
  was written, forcing index-side fixes.** Running `embed` on prod, `assert_within_budget` (the A1
  no-truncation gate) failed the build *correctly* rather than silently truncating — twice, on chunks
  the chunker had emitted whole because they had no splittable boundaries: (1) a **21,518-token B3b
  glossary table chunk** (a single big extracted table emitted as one chunk) → fixed by `table_chunk_texts`
  windowing a table by rows, caption repeated per `#pN` window, no row lost (`d5a6169`); (2) a **~35k-char
  (~11k-token) section with an *unextracted* inline HTML `<table>`** — one block, no blank-line
  boundaries, so paragraph windowing left it whole → fixed by a final `_split_long` guarantee pass
  (line-split, then char-split a single enormous line) so no window exceeds `hard` (`d91e34d`). Also
  tightened the embed query to `AND d.is_latest = 1` so the semantic surface mirrors the latest-only
  lexical corpus instead of leaning on the upstream `index` invariant (`2a994c7`, no-op on current prod
  — all 26,179 non-stub chunks are already `is_latest=1`). *Validates the A1 gate design; no plan change.*

### Risks
- 🔴 **REALIZED (2026-06-08) — embed process-fan-out OOM.** ~19 ONNX/fastembed workers × ~1.78 GB
  each ≈ 24.6 GB on a 27 GiB box → OOM-killer took down the whole session. *Mitigation if ever
  un-parked:* cap workers/threads (`parallel=1`, `OMP_NUM_THREADS`), run single-process, watch RSS.
  See the 2026-06-08 Discovery.
- 🔴 **REALIZED (2026-06-08) — full-corpus re-embed on every upstream change.** No incrementality;
  fingerprint is chunk row count. One new/changed doc ⇒ rebuild all of `vectors.db`. *Mitigation:*
  parked — lexical-first needs no rebuild. A delta-embed keyed on per-chunk content hash would be a
  prerequisite to ever un-parking.
- **RRF weighting/`k` tuning** under-/over-weights a mode. *Mitigation:* tune against the golden query set; report per-mode + fused nDCG.

### Changelog
- 2026-06-07 — **C1 started (🟡).** Landed the embed OOM fix (`b1c5c2c`) on master, then ran
  `vdocs run --only embed` on the full prod lake (`~/data/vdocs`, 26,923 chunks / 744 stubs →
  ~26,179 embed-eligible). First run downloads `nomic-ai/nomic-embed-text-v1.5` (~hundreds of MB) then
  embeds; peak ~5.3 GB RSS (OOM fix holds). Reconciled the embedder notes (bge-m3 → nomic, dim 768).
  `vectors.db` build + `manifest` semantic flip + verification pending. *(updated to ✅ on verify.)*
- 2026-06-08 — **C1 oversized-chunk fixes + live embed run.** The A1 budget gate fired on prod and
  caught two unsplittable oversized chunks before any vectors were written (see Discoveries
  2026-06-08): fixed B3b table-chunk row-windowing (`d5a6169`) and a final `_split_long` guarantee pass
  for blank-line-less blocks / giant inline HTML tables (`d91e34d`), and tightened the embed query to
  latest-only (`2a994c7`). `make check` green across all three (765 passed). With chunks now provably
  ≤ budget, **`vdocs run --only embed` is running live on `~/data/vdocs`** (as of this update ~38 min
  in, ~10 GB RSS, `vectors.db` not yet materialized — fastembed streams and renames on completion).
  Still 🟡: flips to ✅ once `vectors.db` is built, `manifest` reports `semantic_available=1`, and the
  vector count is verified against the 26,179 embed-eligible chunks.
- 2026-06-08 — **C1/C2 PARKED (⛔) — plan change.** The live prod embed run never finished: at
  **01:44:31** the kernel OOM-killer fired (process fan-out — ~19 workers × ~1.78 GB ≈ 24.6 GB on a
  16-core / 27 GiB box), SIGKILLing 14 processes and cascading into the user session; `vectors.db`
  was never written. Combined with the structural finding that `embed` re-embeds the **entire**
  ~26k-chunk corpus + rebuilds `vectors.db` on **any** upstream doc/chunk change (no incrementality,
  row-count fingerprint), the embed/vector path is judged **not worth its cost** for the offline,
  human, no-AI search goal. Phase C semantic+hybrid is **parked**; work pivots to **lexical-first**
  (field-weighted BM25 + doc-title/breadcrumb FTS + glossary query expansion). Full rationale +
  numbers in the 2026-06-08 Discovery. *No `vectors.db` shipped; `manifest` semantic stays off.*

### Notes
- `embed` already skips gracefully without `fastembed` (preflight SKIP). C1 is gated by A1 (chunk
  sizing) — do not run embed until A1 lands.
- **⛔ C1/C2 parked as of 2026-06-08** (see Discoveries/Changelog). The embed code, the A1 budget
  gate, and the b1c5c2c per-batch fix all stay in-tree and correct — parking is a *cost/sequencing*
  decision for this corpus + goal, not a defect. Un-parking prerequisites: (1) worker/thread cap to
  kill the fan-out OOM, **and** (2) incremental delta-embed keyed on per-chunk content hash so an
  upstream change doesn't rebuild the whole `vectors.db`.

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
