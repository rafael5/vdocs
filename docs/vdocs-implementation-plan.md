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
| | 0.3 | Stand up dev lake (`~/data/vdocs-dev`); run full DAG | ⬜ | |
| | 0.4 | Baseline lexical nDCG@10 on golden queries | ⬜ | |
| **A — Substrate / chunking** | A1 | Pick embedder + right-size chunking (token-budget aligned) | ⬜ | ⚠️ |
| | A2 | Contextual chunk headers + small-leaf merge | ⬜ | |
| | A3 | `stub` chunks → lexical-only (exclude from semantic) | ⬜ | |
| **B — Denoising (full corpus)** | B1 | `discover` at scale; curate phrases + boilerplate; materialize `_shared/boilerplate/` | ⬜ | |
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
| 0.3 | Dev lake | `DATA_DIR=~/data/vdocs-dev` `fetch --select` → full DAG (convert→manifest) | DAG green on dev lake | ⬜ | |
| 0.4 | Baseline | Record lexical nDCG@10 / redundancy@k on golden queries | Baseline recorded | ⬜ | |

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

### Notes
- `consolidate`/`index`/`relate`/`manifest` are **corpus-global** (rebuild over whatever is in the
  lake), so a *separate dev lake* is the clean way to scope — not per-doc flags on the prod lake.
- The prod lake `~/data/vdocs` (~1,450 docs) stays intact; switch scopes by `DATA_DIR` env var.

---

## Phase A — Substrate / chunking

**Goal:** make chunks optimal *units of knowledge* and safe for the chosen embedder, before any embed.

| ID | Step | Detail | Gate | Status | Flag |
|----|------|--------|------|--------|------|
| A1 | Embedder + chunk sizing | Choose model (recommend **bge-m3**, 8k ctx); set `CHUNK_TARGET/HARD` to its token budget; assert no truncation at embed time | No chunk exceeds model token limit | ⬜ | ⚠️ |
| A2 | Context headers + merge | Prepend `«doc_title › section_path»` to embedded text; merge tiny adjacent leaves under same parent up to TARGET | Mean chunk substance ↑; hollow stays 0 | ⬜ | |
| A3 | Stub handling | `stub` chunks (referent-only) lexical-only, excluded from semantic | Stubs absent from `vectors.db` | ⬜ | |

### Discoveries
- ⚠️ **2026-06-06 — chunk/embedder truncation (plan-impacting).** Current `CHUNK_TARGET_CHARS=4000` /
  `OVERSIZED_CHUNK_CHARS=8000` exceed the **512-token (~2,000 char) limit of the originally-planned
  `bge-small-en-v1.5`** → the back half of large chunks would be silently dropped at embed time.
  **Plan change:** A1 now includes an explicit embedder decision; recommendation is to switch to a
  long-context embedder (**bge-m3 / nomic-embed / jina-v3, 8k**) and align chunk constants to its
  budget. *Do A1 before any `embed` run (Phase C).*

### Risks
- **Wrong embedder → costly re-embed.** *Mitigation:* decide in A1 with a small eval on the golden set; record the choice + dim in `embedding_model`.
- **Over-merging crosses semantic boundaries.** *Mitigation:* merge only within the same parent heading; never merge across H2 boundaries.

### Changelog
- *(none yet)*

### Notes
- Constants live in `src/vdocs/stages/index/index_pure.py` (`CHUNK_TARGET_CHARS`,
  `OVERSIZED_CHUNK_CHARS`) and `kernel/markdown.py` (`MIN_SUBSTANTIVE_TOKENS=8`). A1 changes these +
  adds a context-header field to the embedded text (not the displayed/cited body).

---

## Phase B — Denoising (full corpus)

**Goal:** drive signal-to-noise to target by saturating the discover→curate→apply loop.

| ID | Step | Detail | Gate | Status | Flag |
|----|------|--------|------|--------|------|
| B1 | Phrases + boilerplate | Run `discover` on full corpus; curate `phrases`/`boilerplate` registries; materialize `gold/_shared/boilerplate/`; `normalize` references | Boilerplate single-sourced; dead phrases removed | ⬜ | |
| B2 | Glossary | Materialize `gold/glossary.md` (PROMOTE); drop per-doc copies | Glossary exists; per-doc dupes gone | ⬜ | |
| B3 | Entity weighting + tables | De-weight globals in ranking; index extracted `tables/*.csv` as searchable structured chunks | Globals not ranking-dominant; tables findable | ⬜ | |

### Discoveries
- *(none yet)*

### Risks
- **Over-aggressive deletion → silent content loss.** *Mitigation:* capture-before-strip is already enforced (`capture.yaml` typed outcomes) + the §10.5/fidelity gate; curate by PR, reversible.
- **Boilerplate near-dup threshold (0.8 Jaccard) mis-clusters.** *Mitigation:* review graded candidates; keep canonical copy + reference, never delete boilerplate.

### Changelog
- *(none yet)*

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
