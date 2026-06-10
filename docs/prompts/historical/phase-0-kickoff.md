# Phase 0 Kickoff Prompt — Golden Dev Set

> Paste the block below into a **fresh session** to start Phase 0 of the vdocs remediation plan. It is
> self-contained (re-states all load-bearing facts) so a session with no prior context can't drift.
> Plan: [`../vdocs-remediation-plan.md`](../vdocs-remediation-plan.md) §12 ·
> Tracker: [`../vdocs-implementation-plan.md`](../vdocs-implementation-plan.md) Phase 0.

---

```
Start Phase 0 of the vdocs remediation plan (stand up the stratified golden dev set).

CONTEXT — read these first, in order:
1. docs/vdocs-remediation-plan.md — the FORWARD source of truth (greenfield reset, 2026-06-06).
   Read §12 "The Closure Plan" → Phase 0, and §2/§8/§9 for the goal and chunking/denoising rationale.
2. docs/vdocs-implementation-plan.md — the execution tracker. Phase 0 has its own table + the
   master tracker. You will UPDATE this file as you work.
3. docs/historical/ — all prior design/spec docs live here and are REFERENCE ONLY, NOT to be
   implemented. Do NOT treat docs/historical/vdocs-design.md as authoritative.

WHAT PHASE 0 IS:
Prove the full pipeline end-to-end on a small, shape-stratified "golden set" (~60–100 docs) in a
SEPARATE dev lake before touching the full corpus. The same set doubles as the retrieval-quality
evaluation set. Denoising/pattern work (Phase B) is mined on the FULL corpus later — not in scope here.

KEY FACTS (don't re-discover):
- Full lake: ~/data/vdocs (DATA_DIR). Full enriched inventory: ~/data/vdocs/inventory/silver/
  catalog.enriched.json (~8,834 records). Genuine-doc gold inventory: ~/data/vdocs/inventory/gold/
  inventory.json. index.db already holds ~1,448 processed docs.
- doc_id = "<app_name_abbrev>:<doc_slug>" (vdocs.kernel.ids.doc_id). Select-file format: one doc_id
  per line, '#' comments allowed; consumed by `.venv/bin/vdocs fetch --select <file>`.
- consolidate/index/relate/manifest are CORPUS-GLOBAL (rebuild over the whole lake) → use a separate
  dev lake, do not scope the prod lake. embed will gracefully SKIP without fastembed (expected; Phase 0
  does not embed).
- Project rules: uv + ruff + mypy + pytest, TDD (test first), `.venv/bin/` prefixes, `make check`
  (≥95% cov) before any commit. Commit/push ONLY when I ask.

TASKS (do 0.1 and STOP for my approval before fetching):
- 0.1  Mine the inventory and propose ~60–100 doc_ids stratified across these eight SHAPE axes, with a
       one-line rationale per pick and a coverage summary showing each axis is represented:
         (a) doc_type: UM, TM, IG, DG, SMG, RN, DIBR/DIBRG, security-config, quick-ref
         (b) era: old-gen (flattened / bookmark-span headings / legacy TOC) AND modern (clean)
         (c) converter: Pandoc-clean AND Docling-required (bare-marker exploders, e.g. cprsguium)
         (d) structure: has revision-table / legacy-TOC / heavy _Toc·_Ref xrefs / big data tables /
             boilerplate-heavy / title seal-or-banner images
         (e) version-group depth: standalone (1 member) AND deep groups (e.g. PXRM ~10, ADT ~15)
         (f) entity density: KIDS/Kernel (XU), HTTP/HWSC (XOBW), FileMan-heavy, routine/RPC-heavy
         (g) size: tiny RN, medium guide, huge (Monograph / a big TM)
         (h) answerable-Q coverage: include docs with known ground-truth questions (KIDS install,
             KAAJEE auth, HWSC REST) so the golden query set has labels
       Present the list for my approval. Do NOT fetch yet.
- 0.2  On approval: commit registries/dev-corpus.txt (the doc_ids) + a starter golden-queries.yaml
       (query → expected section_ids), version-controlled.
- 0.3  Stand up the dev lake: DATA_DIR=~/data/vdocs-dev; fetch --select the set, then run the DAG
       (convert → … → manifest). Keep ~/data/vdocs untouched.
- 0.4  Record a baseline (lexical nDCG@10 / redundancy@k on the golden queries) to measure later
       phases against.

TRACKING (every step):
- Update docs/vdocs-implementation-plan.md: set Phase 0 row statuses (⬜→🟡→✅) in the master tracker
  and the Phase 0 table; add a dated Changelog entry; record any Discovery/Risk. If a discovery
  warrants a plan/implementation change, flag it BOTH with ⚠️ in the table's Flag column AND a dated
  entry under Phase 0 Discoveries.
- Gate for "Phase 0 done": full DAG runs green on the dev lake + baseline recorded.

Begin with 0.1: explore the inventory and propose the stratified selection for my approval.
```
