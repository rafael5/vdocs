Resume vdocs at **Phase C1 — Semantic + hybrid**: actually build `vectors.db` on the full corpus
(the embed run that kept OOM-killing the box), then flip semantic search on. The OOM has been fixed
on a branch; this session merges it, runs `embed` for real, and updates the tracker.

CONTEXT — read these first, in order:
1. docs/vdocs-implementation-plan.md — the execution tracker (source of truth for status). Read the
   master tracker (Phase C rows), Phase A's A1 row + its ⚠️ note on the embedder, and the Phase 0
   baseline (the nDCG@10 number every later phase must beat). You will UPDATE this file as you work.
2. docs/vdocs-remediation-plan.md — the FORWARD plan; §"Closure Plan" → Phase C (semantic + hybrid).
3. docs/historical/ — REFERENCE ONLY, do NOT implement. `docs/historical/vdocs-design.md` is NOT
   authoritative (the CLAUDE.md still points at a `docs/vdocs-design.md` that no longer exists —
   treat the implementation + remediation plans as truth, and fix that stale CLAUDE.md pointer if you
   touch it).

WHERE THINGS STAND (don't re-discover):
- **The embed stage was OOM-killing the machine.** Root cause: a fixed `batch_size=256`; fastembed/
  ONNX pads each batch to its longest member, so memory scaled with `items × longest_seq` — one
  ~2.5k-token chunk dragged all 256 up and allocated ~20-25 GB. It killed the process (and the
  VSCode terminal's cgroup) twice on 2026-06-07; `vectors.db` was never produced.
- **Fix is committed + pushed but NOT merged.** Branch `fix/embed-oom-batching` (tip `b1c5c2c`) off
  master `d91e34d`. It replaces fixed-count batching with `embed_pure.token_batched` (bounds the
  *padded* footprint `items × longest ≤ max_batch_tokens`, default 8192; `max_batch_items` 64) and
  streams vectors into `vectors.db` batch-by-batch instead of accumulating them all in memory. Full
  gate green (773 tests, 98.13% cov). **First task: open/merge the PR (or rebase onto current master)
  before running anything.**
- **Embedder changed and the plan is stale on it.** A1 records **bge-m3 (1024-dim)**, but C1
  (commit 41514dd) switched the default to **`nomic-ai/nomic-embed-text-v1.5` (768-dim, 8192-tok)** —
  fastembed's dense `TextEmbedding` API doesn't serve bge-m3 (see the docstring in
  `stages/embed/stage.py:_default_embedder`). So `vectors.db` will be **dim 768**, not 1024, and the
  corpus side prefixes every input with `search_document:` (query side uses `search_query:`, C2).
  **Reconcile the tracker:** update the A1/C1 notes + clear/restate the bge-m3 ⚠️ flag to reflect the
  nomic switch (plan-impacting → dated Discoveries entry).
- **Corpus:** full prod lake `~/data/vdocs` (DATA_DIR). `index.db` has **26,923 chunks** (max ~2,500
  tokens, avg ~500). `vectors.db` does **not** exist yet. `fastembed 0.8.0` IS installed in `.venv`;
  the first `embed` run downloads the nomic model (~hundreds of MB) before embedding — normal.

OPERATIONAL GUARDRAILS:
- **Run `embed` from a plain tmux/ssh shell, NOT the VSCode integrated terminal** — so even if memory
  gets tight the editor's cgroup isn't the thing that dies. Watch it: `watch -n5 free -h` or
  `pgrep -af vdocs` in another pane. With the fix, peak should be ~1-2 GB, nowhere near the 27 GB box.
- **Shared lake:** before any `vdocs run`/`embed` on `~/data/vdocs`, check `pgrep -af "vdocs (run|
  embed|discover)"` + `reports/*.log` for a live operator run — two orchestrators race
  state.db/index.db/CAS. Run only the stage you need (see memory `feedback_shared_lake_concurrent_runs`).
- Project rules: uv + ruff + mypy + pytest, **TDD (test first, confirm red, implement, green)**,
  `.venv/bin/` prefixes, `make check` (≥95% cov) before any commit. Pure fns in `*_pure.py`, thin I/O
  in `stage.py`, structlog (no print). Stage only files you touch (never `git add -A`); the
  `docs/prompts/ → historical/` moves were already in the working tree from a prior session — leave
  them or commit them deliberately, don't sweep them into an unrelated commit.

TASKS (Phase C):
- **C1** Land the OOM fix (merge `fix/embed-oom-batching`), then run `embed` on the full lake →
  build `vectors.db` (dim 768, model row `nomic-ai/nomic-embed-text-v1.5`). Then run `manifest` and
  confirm it flips `semantic_available=1` (D3). Verify: `vec_chunks` row count ≈ chunks minus stubs;
  spot-check a `vec0` ANN query returns sane neighbours. Mark C1 ✅ + reconcile the embedder notes.
- **C2** ANN query + **RRF fusion** of semantic + lexical (FTS) + structured pre-filter in
  `server/search`. Query side uses the `search_query:` prefix. Add tests first.
- **GATE for Phase C done:** re-baseline the golden queries (`scripts/baseline_golden.py`) and show
  hybrid **beats the lexical baseline** — mean **nDCG@10 0.3947 / MRR 0.5167 / recall@10 0.50**
  (redundancy@10 0.017). The kaajee-install query (nDCG@10 = 0.0 lexically) is the canonical case
  semantic+headers should rescue — check it specifically.

TRACKING (every step): update docs/vdocs-implementation-plan.md — Phase C row statuses (⬜→🟡→✅) in
the master tracker, dated Changelog entries, Discoveries/Risks; plan-impacting findings get ⚠️ +
a dated Discoveries entry (the embedder bge-m3→nomic switch is one).

Begin by checking out master, pulling, and landing the `fix/embed-oom-batching` PR; then (from a
tmux shell, after the live-orchestrator check) run `embed` on `~/data/vdocs` and watch memory.
