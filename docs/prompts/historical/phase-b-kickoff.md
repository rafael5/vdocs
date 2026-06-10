Start Phase B of the vdocs remediation plan (drive signal-to-noise to target — the denoising loop).
This runs IN PARALLEL with a separate session doing Phase A/C; read the COORDINATION section first.

CONTEXT — read these first, in order:
1. docs/vdocs-remediation-plan.md — the FORWARD source of truth. Read §8 (Signal-to-Noise
   Optimization), §10 (Structured-Data / Sidecar Assessment), and §12 "The Closure Plan" → Phase B.
2. docs/vdocs-implementation-plan.md — the execution tracker. Phase B has its own table + the master
   tracker. You will UPDATE this file as you work (statuses ⬜→🟡→✅, Discoveries, Risks, Changelog,
   ⚠️ flags for plan-impacting findings).
3. docs/historical/ — prior design/spec docs are REFERENCE ONLY, NOT to be implemented. Do NOT treat
   docs/historical/vdocs-design.md as authoritative.

WHAT PHASE B IS:
Saturate the built discover → curate → apply denoising loop so the corpus carries minimal
redundancy/boilerplate. The mechanism exists; the curated registries are thin. Phase B is
**corpus-frequency work and MUST run on the FULL corpus** (~1,450 docs at ~/data/vdocs), NOT the
golden dev set — boilerplate/phrase/glossary are corpus-scale phenomena (≥3-doc thresholds) a sample
cannot reveal. Goal (the three outcomes): best signal-to-noise → sharper embeddings, redundancy@k→~0.

COORDINATION (a parallel Phase A/C session is live — avoid stepping on it):
- **Git:** master tip is `b1c3b6f` (Phase A complete). **Work on a branch** `feat/phase-b-denoising`
  off current master and open a PR; the other session pushes to master, so rebase before merging.
  Stage only files you touch (never `git add -A`); commit/push your own work as you go.
- **Lakes:** Phase B uses the **FULL prod lake `~/data/vdocs`** (DATA_DIR). The A/C session owns
  **`~/data/vdocs-dev`** — DO NOT touch it. Before any `vdocs run`/`discover` on the prod lake, check
  `pgrep -af "vdocs (run|discover|embed)"` — two orchestrators race state.db/index.db/CAS
  (see memory `feedback_shared_lake_concurrent_runs.md`). Run only the stages you need.
- **Code overlap:** B3 (tables-as-data, entity de-weighting) touches `index`/`manifest`/`relate`/
  `server/search`. The A/C session is editing `index_pure`/`index/stage` (chunking) and
  `embed`/`server`. Coordinate edits to `stages/index/*` to avoid merge pain; prefer additive changes.

KEY FACTS (don't re-discover):
- Full lake: ~/data/vdocs (DATA_DIR). ~1,450 docs in index.db; entities 4,792 (globals 2,355 — the
  dominant, low-signal type), relations 110k.
- Curated registries are version-controlled IN THE REPO at `registries/` (NOT the lake): phrases 7,
  boilerplate 37, glossary 0, structures 7, templates 129, entities 10. `gold/_shared/boilerplate/`
  and `gold/glossary.md` are NOT materialized. These thin counts are the gap Phase B closes.
- `discover` mines pattern CANDIDATES into `reports/patterns` (its candidate counts are large — e.g.
  thousands of phrase/boilerplate/glossary candidates — these are NOT registry entries; curation
  promotes a chosen subset into `registries/`). `normalize` consumes the curated registries:
  boilerplate→REFERENCE (single-source), phrases→DELETE (dead furniture), glossary→PROMOTE,
  templates→STRIP+retain-schema, structures→CANONICALIZE. Capture-before-strip is enforced
  (typed `capture.yaml`), so denoising is reversible and audited.
- Project rules: uv + ruff + mypy + pytest, TDD (test first), `.venv/bin/` prefixes, `make check`
  (≥95% cov) before any commit. Pure functions in `*_pure.py`, thin I/O `stage.py`. structlog, no print.

TASKS:
- B1  Run `discover` at full-corpus scale; curate the **phrases** + **boilerplate** registries
      aggressively (phrases: 7 → the long tail of paper-era furniture — "This page intentionally left
      blank", "Continued on next page", revision-table filler; boilerplate: 37 → the real legal/
      header/footer blocks). **Materialize `gold/_shared/boilerplate/`** and have `normalize` replace
      duplicated blocks with references (the biggest redundancy@k win). Curate by reviewing graded
      candidates; keep the canonical copy + reference, never delete boilerplate.
- B2  Materialize **`gold/glossary.md`** (glossary 0 → PROMOTE acronyms once; drop per-doc copies).
- B3  De-weight ubiquitous low-signal entities (globals dominate — keep queryable but not
      ranking-dominant; already excluded from `xref` edges — also drop from semantic boost + the
      entity-index headline). Index extracted `tables/*.csv` as data (§8.4): re-introduce them as a
      distinct structured chunk (caption + headers + rows) so data-dictionary lookups work, otherwise
      table recall is lost when tables are lifted out of prose.

TRACKING (every step):
- Update docs/vdocs-implementation-plan.md: Phase B row statuses (⬜→🟡→✅) in the master tracker AND
  the Phase B table; add dated Changelog entries; record Discoveries/Risks. Plan-impacting findings
  get ⚠️ in the Flag column + a dated Discoveries entry.

GATE for "Phase B done": redundancy@k → ~0 on the golden set, and an ablation (with/without
condensation) shows the denoising lift.
- The ablation is measured on the golden queries via `scripts/baseline_golden.py` (current lexical
  baseline: nDCG@10 0.3947 / MRR 0.5167 / recall@10 0.50 / redundancy@10 0.017). Measuring it means
  re-running normalize→consolidate→index with the enriched registries and re-baselining.
  **Do NOT mutate `~/data/vdocs-dev`** (the C session owns it) — stand up your own throwaway dev lake
  from `registries/dev-corpus.txt` (the Phase-0 standup recipe is in the implementation plan's Phase 0
  Notes: copy prod inventory mtime-preserved + seed the 3 inventory `state.db` rows, then
  `fetch --select` → run the DAG), or coordinate a shared measurement window with the C session.

Begin with B1: check for a live orchestrator, then run `discover` on the full lake and survey the
graded candidates before curating.
