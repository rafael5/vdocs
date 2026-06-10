# Pipeline Operability Hardening — Phase 1 Findings & Design

> **Status:** Phase 1 (review + design). **No code written yet** — this is the propose-plan-first
> deliverable for `docs/prompts/pipeline-operability-hardening-kickoff.md`. Sign off (answer the
> Open Questions at the end) before any refactor.
> **Reviewer:** Claude (Opus 4.8), 2026-06-10. Grounded in a first-hand read of the orchestrator,
> CLI, contracts, `fetch`/`manifest`/`embed` stages + two breadth code-review passes.

---

## 0. The one-paragraph problem statement

The 2026-06-10 de-novo run reached `GOLD LIBRARY: GREEN` only because an AI watched every stage:
read `state.db` by hand, spotted an OOM and killed `embed`, hand-sequenced `--only` stages to dodge
the dead semantic path, wrote throwaway B1–B5 validators, and translated cryptic counts. **None of
that is in the tool.** The pipeline is *silent for ~95 % of its runtime* (only a final
`stage: ok {counts}` line per stage), has a **dead `embed` stage that `--to manifest` silently pulls
in**, **re-downloads every document on every run**, and ships **no "is my corpus sound?" check**.
This doc inventories the gaps and proposes the design to close them so a no-AI operator can configure,
run, troubleshoot, and trust the pipeline offline.

---

## 1. Architecture review — what's sound (keep it)

The core is in good shape; this is *clean-and-harden in place*, not a rewrite.

- **DAG is genuinely data-driven.** `Orchestrator.order()` (Kahn topo-sort over
  `requires`/`produces`) — no hand-maintained stage list. The §8 contract table *is* the graph.
- **Kernel anti-duplication holds.** Breadth review found **no §9.2 copy-paste violations**:
  `cas.atomic_write`, `kernel/registry.load_mapping`, `frontmatter`, `csv`, `fingerprint`, `bundle`
  are all centralized and reused. (One soft candidate — see §2.4.)
- **Pure/I-O split is respected.** `*_pure.py` are I/O-free; `stage.py` drivers are thin.
- **Preflight/postflight live once** on the `Stage` base class; stages override only `run`
  (and `validate` overrides `deep_gate`). Good.
- **Gate config is already declarative & reversible.** `doctype-policy.yaml` / `scope-policy.yaml` /
  `noise-domains.yaml` carry inline operator rationale and are version-controlled (discovery-is-data).

**Implication:** the operability work is *additive* (a messaging/reporting layer + a `doctor` command
+ small `fetch` correctness fixes + dead-code deletion), not structural. The DAG, contracts, and
medallion layout stay.

---

## 2. Architecture review — what's broken or dead

### 2.1 The dead semantic/vector path (F1) — **delete it**
`embed` (ONNX→`vectors.db` via `fastembed`+`sqlite-vec`) is the parked, OOM-prone semantic path.
It is still in `build_stages()` and still topo-sorts **before** `manifest` (it requires `index`'s
chunks; `e` < `m` breaks the tie), so `run --to manifest` returns a contiguous slice that **includes
`embed`** — exactly the trap the run hit. `manifest` does **not** require `vectors.db`; it reads it
*optionally* and already degrades to `semantic_available=0` when absent. **Removal is clean** and
*fixes F1 outright* — nothing depends on `embed`'s output. Full file:line removal map in §3.

### 2.2 No human-facing runtime UX (F8, the heart of the task)
- The **only** stdout an operator sees is the post-hoc `f"{result.stage}: ok {result.counts}"` loop
  in `cli/app.py:78-80`. Everything else is `structlog` → stderr JSON-ish dicts.
- **Long stages emit nothing while working.** `fetch` (1040 GETs) and `convert` (1034 docs) run
  silent loops with zero heartbeat — indistinguishable from a hang.
- **No status vocabulary.** There is no `GREEN/WARN/ERROR` token, no per-stage banner, no progress
  ("stage k of N", "% done"), no end-of-run summary table.
- **WARN doesn't exist as a concept.** The decision enum is `PROCEED/SKIP/FAIL`; the run status is
  `ok/failed`. "Proceeded but with caveats" (4 persistent 500s, untyped docs admitted) has nowhere to
  live, so it's invisible.

### 2.3 `fetch` correctness defects (F2, F3, F9)
- **F2 — re-GETs everything every run.** `fetch.run()` calls `data = self._get(url)` *unconditionally*
  per target (`stage.py:81`). The `prior` lookup only carries forward `attempts`/`first_attempt_at`;
  it never short-circuits an already-fetched doc. The CAS dedupes the **write** (`store.put`), not the
  network GET. So the runbook's "re-run until `failed=0`; CAS hits are skipped" is **false** — every
  pass re-downloads all 1040.
- **F3 — no failure classification / retry cap.** The injected `ByteFetcher` returns `None` on any
  failure; `fetch` records `status="failed", error="docx unavailable"` with no 4xx/5xx distinction
  and no cap. The 4 persistent VDL 500s make `failed=0` **unreachable**, yet the runbook loops "until
  `failed=0`" — a human follows it into an infinite retry of permanently-broken URLs.

### 2.4 Soft duplication — the per-document error-isolation loop
`convert`, `normalize`, `consolidate` each hand-roll the same `try/except → log.warning → errors++ →
doc_error_gate` shape. It's *intentional* (R6) and currently correct, but it's the one place a small
shared helper (`kernel/docloop.py` or a `Stage` mixin) would both remove repetition **and** become the
natural choke point to emit the standardized per-doc WARN messaging (§4). Recommend folding the two
together rather than touching it twice.

### 2.5 Preflight coupling surprises (F4)
`catalog`'s preflight (step 2, `stage.py:114-127`) requires `crawl`'s `state.db` run to be `ok`.
Wiping `state.db` (the runbook's step 1 keeps it, but a human who wipes the lake wholesale loses it)
makes `catalog` fail with `upstream crawl has not completed ok` — cryptic, undocumented. **Decided
(Open Q11): fix it** — gate `catalog` on `catalog.raw.json` presence/fingerprint rather than `crawl`'s
`state.db` run-record, so a `state.db` wipe no longer forces a re-crawl. Plus a clear remediation
message either way.

### 2.6 `PostflightError` escapes the CLI (exit-code defect)
`engine.run()` raises `PostflightError` on a deep-gate failure (e.g. `validate` finds a severed ref).
`_drive` catches only `StageFailed` → **`PostflightError` propagates as an uncaught traceback**, not a
clean `ERROR` line + exit code. Any real `validate` failure today dumps a Python stack at the operator.

### 2.7 Orphaned / ambiguous code (F12)
- **`stages/fidelity/`** (`compliance_pure.py`, `overstrip_pure.py`) — pure kernels with **no
  `stage.py`**, not in `build_stages()`, imported only by their own tests. Documented as "Phase-5
  `validate` hard-gate, driver lands later." It's *aspirational*, not wired. Decision needed (Open Q12):
  fold into `doctor`/`validate`, keep as future work, or remove.
- **`scripts/`** — `baseline_golden.py` + `audit_gold_cleanup.py` are documented CI gates (keep);
  `faceted_search_demo.py`, `faceted_eval.py`, `preview.py`, `proto_latest_only.py` look like spikes
  (candidates to retire, low priority).

### 2.8 Lake clutter (F11) & untyped admission (F5) & by-design gaps (F6/F7)
- **F5** confirmed: `GatePolicy.doctype_kept()` is an *omit blocklist* — an empty/unclassified
  `doc_code` is **kept** (`default: keep` fail-safe). Correct policy, but there is **no operator-visible
  surface** listing what got admitted untyped. (That's how the 3 SD "TM ADDENDUM" docs slipped in.)
- **F6/F7** are *by-design gaps and benign currency drift* presented with no framing, so a human can't
  tell them from defects. The fix is **`doctor`-level expected-coverage thresholds** (§5), not code in
  the stages.
- **F11** stray `select-*.txt` / `.vectors.db.tmp*` — handled by removing `embed` (no more tmp) + a
  `doctor` "lake hygiene" check + the guided-build wipe set.

---

## 3. F1 removal map (semantic/vector path) — exhaustive

**Delete entirely:** `src/vdocs/stages/embed/` (whole dir) · `tests/integration/stages/test_embed_stage.py`
· `tests/unit/stages/test_embed_pure.py`.

**Edit:**
- `pyproject.toml` — drop `fastembed>=0.8.0` (L11) and `sqlite-vec>=0.1.9` (L17); `uv lock`. (Confirmed
  these two deps are imported **only** by `embed/stage.py`.)
- `cli/app.py` — drop the `EmbedStage` import (L21) and its entry in `build_stages()` (L50).
- `contracts/registry.py` — delete the `VECTORS_DB` contract (L259-269) and its line in
  `default_registry()` (L313).
- `tests/integration/stages/test_manifest_stage.py` — delete the two "vectors present → semantic on"
  tests (L152-177); keep "semantic off".
- `tests/unit/stages/test_manifest_pure.py` — delete the embedding-present tests (L118-122, L137-139).
- `tests/unit/test_config.py` — drop the `vectors_db` path assertion (L40).
- `README.md` L5 — "hybrid semantic + lexical…" → "lexical + structured + graph".

**Decision (Open Q1) — keep or drop the harmless remnants:**
- `config.vectors_db` property and `manifest`'s optional `_read_embedding` / `semantic_available=0`
  plumbing **can stay untouched** (they already no-op to "unavailable"). *Recommended:* delete them too
  for a clean airgapped surface — leaving `semantic_available` in the manifest invites "where's
  semantic?" questions. One small extra edit to `manifest_pure` drops the `embedding`/`semantic`
  capability keys entirely.

**DAG impact:** none — 14→13 stages, topo-sort still valid, no stage consumes `embed`'s output.

---

## 4. Design — the human-operator runtime UX

The core deliverable. A thin **reporter** layer the orchestrator drives; stages stay pure-ish and just
emit structured events.

### 4.1 A run reporter, not scattered `echo`s
Introduce one `RunReporter` (in `orchestrator/` or a new `cli/report.py`) the `Orchestrator` calls at
defined hooks. Stages don't print; they yield/return structured progress the reporter renders. This
keeps the "no second execution route" rule and makes the output **testable** (capture the reporter's
event stream; snapshot the rendered table).

### 4.2 The per-stage contract (every stage, uniform)
```
[ 4/13] fetch — download selected documents into the bronze CAS
        1040 targets · 1036 in CAS (skip) · 4 to fetch …
        ▸ fetching 4/4 … (heartbeat every N or every ~2s)
        WARN  2 docs permanently unavailable (HTTP 500): DGBT:dgbt_1_40_um, ROEB:hreg_bcrv2…
   ── fetch: WARN  fetched=2 skipped=1036 failed=2(permanent)  3.1s
```
- **Start banner:** `[k/N] stage — description`.
- **Progress:** counts up front; a heartbeat for `fetch`/`convert`/`index` (every N items or ~2 s),
  TTY-aware (plain incremental lines when not a TTY, so logs stay clean).
- **Result line:** `stage: GREEN|WARN|ERROR  key=count …  elapsed`.
- **Diagnostics inline & human:** WARN/ERROR say *what, which doc/app, why, next action* — never a raw
  `structlog` dict. `structlog` keeps going to the JSON run-log file (§4.4), not the human console.

### 4.3 Status model & exit codes (resolves the F2.6 / Open Q4 gap)
Add `WARN` as a first-class outcome alongside the existing `ok`/`failed`.

| Token | Meaning | Blocks? | In summary |
|---|---|---|---|
| `GREEN` | stage did its work, no caveats | no | ✅ |
| `WARN`  | completed, but operator should know (e.g. N permanent-missing fetches; M untyped docs admitted; benign count drift) | **no** | ⚠️ + reason |
| `ERROR` | preflight FAIL or postflight/deep-gate FAIL (severed ref, systemic doc-error-rate, invalid output) | **yes, stops** | ❌ + remediation |

**Exit-code contract (documented):** `0` = all GREEN · `0` (default) or `10` (opt-in `--strict`) =
some WARN, no ERROR · `1` = at least one ERROR. `PostflightError`/`StageFailed` both render as a clean
`ERROR` result line + summary, **never a traceback** (fixes §2.6).

### 4.4 Dual output (Open Q2)
- **Human console:** the banners/heartbeat/table above.
- **Machine run-log:** a `reports/run-YYYYMMDD-HHMMSS.json` (the reporter's event stream + final
  table) so a run is auditable and `doctor`/CI can read it. `structlog` continues to the log file.
- **Console lib:** *recommended* allow **Rich** (single pure-Python wheel, vendoring-friendly,
  TTY-aware, degrades to plain) — but gate all UI through the reporter so swapping to zero-dep plain
  `print` is a one-file change if you'd rather not add the dep. **Confirm in Open Q2.**

### 4.5 End-of-run summary table
```
═══ vdocs run summary ═══════════════════════════════════════════════
  #  stage         status  headline counts                  warn  elapsed
  1  crawl         GREEN   8907 docs / 396 apps                0    42.1s
  …
  4  fetch         WARN    fetched 1040, 2 permanent-missing   2     6m
  …
 12  manifest      GREEN   615 gold docs, semantic off         0     3.2s
 13  validate      GREEN   0 severed, 0 reconcile findings     0     1.1s
─────────────────────────────────────────────────────────────────────
  VERDICT: WARN (12 GREEN, 1 WARN, 0 ERROR) — corpus built; 2 upstream
  docs permanently unavailable (not a pipeline defect). Next: vdocs doctor
═════════════════════════════════════════════════════════════════════
exit 0
```

---

## 5. Design — `vdocs doctor` (bakes in B1–B5; F8)

Promote the throwaway `/tmp/validate_gold*.py` into a first-class command.

- **Shape (Open Q8):** a standalone `vdocs doctor` **and** an opt-in `run --doctor` tail. Reads
  `index.db` (+ registries) primarily; opts into lake-body checks with `--deep`.
- **Reuses the existing `validate` stage** for the structural floor (severed refs, count reconciliation,
  bundle integrity — already implemented) and adds the **corpus-soundness** B1–B5 checks (anchor/
  is_latest one-per-anchor, facet totals == gold count, persona coverage, gate fidelity = zero
  forbidden tiers, entity sanity).
- **By-design vs defect (F6/F7, Open Q7):** a `doctor-policy.yaml` registry encodes **expected-coverage
  thresholds** per field + an **allow-list of known-empty apps** (the 12 fallback profiles) and known
  accepted edge cases (the 1 `AR/WS:p13` anchor). `doctor` then renders three buckets: **PASS**,
  **BY-DESIGN** (expected-empty, explained), **FAIL** (real defect). Only FAIL flips the verdict.
- **Output:** the same human table + `GOLD LIBRARY: GREEN|RED` as the authoritative gate (Open Q8 —
  replaces the manual sign-off), and a JSON report for CI.
- **Untyped-doc surface (F5, Open Q6):** `doctor` lists every gold doc with empty `doc_type`/`anchor_key`
  as a **WARN bucket** ("admitted untyped — triage"), so the class is never invisible again.

---

## 6. Design — gate legibility & guided build

### 6.1 Gate config (Open Q3)
The YAMLs are already well-commented; the missing piece is **preview + reference**, not consolidation.
- Add **`vdocs gate --explain`** (or `fetch --dry-run --explain`): prints the *effective* assembled
  `GatePolicy` in human terms — "app scope: system-type prefixes [...]; denied statuses [...]; doc-types
  kept (14): UM, UG, … ; omitted (N): … ; default-untyped → KEEP" — plus the resulting admitted count
  with a per-dimension breakdown. This is the "see the gate before running" acceptance criterion.
- Add a **`docs/gate-reference.md`** that documents the three registries + the assembly in one place.
- **Recommend keeping the three registries** (each is a coherent concern with rationale comments);
  consolidating into one `admission.yaml` loses the per-concern clarity for little gain.
- **Fetch gate vs gold gate:** today they're the same admission gate (consolidate G5 is dedup, not
  admission). Recommend **documenting them as one gate with two checkpoints** rather than inventing a
  second independent config nobody asked for — unless you foresee fetching broadly but promoting
  narrowly (Open Q3).

### 6.2 `fetch` idempotence (F2/F9, Open Q9) — **make resume cheap & honest**
Default `fetch` to **skip any `doc_id` already `fetched` in `state.db`/present in CAS**; only
`failed`/never-attempted targets hit the network. Add `--refetch` to force re-GET. This makes "re-run
to retry failures" *actually* mean that. Pair with **F3**: classify failures (transient vs permanent
4xx/410/persistent-5xx), cap retries (e.g. 3), and record `status="permanent_missing"` so the summary
WARNs with the URL list instead of looping forever.

### 6.3 Guided from-scratch build (F9, Open Q10)
Add **`vdocs build [--fresh] [--yes]`** that sequences crawl→…→manifest→doctor with messaging on and
**`embed` gone** (so the F1 trap can't recur). `--fresh` does the documented wipe set; the destructive
wipe **refuses without `--yes`** and runs the shared-lake `pgrep`/`reports/*.log` precheck first
(honoring the vdocs-shared-lake rule).

### 6.4 Runbook (F2/F3/F4, Open Q14)
Rewrite `docs/de-novo-run.md` (currently in `docs/historical/`) to match real behavior: idempotent
resume, the 4 permanent 500s as an *expected* WARN (not an infinite loop), the `state.db`/crawl
coupling, and `vdocs build` as the one-command path. Decide (Open Q14) whether the canonical reference
is the runbook or an in-tool `vdocs help run` / `OPERATING.md`.

---

## 7. Proposed work breakdown (reviewable commits, each green, TDD)

1. **Delete the semantic path** (§3) — pure subtraction; `make check` green at 13 stages.
2. **Status model + reporter scaffold** — add `WARN`; `RunReporter`; route `StageFailed`/`PostflightError`
   to clean `ERROR` + exit codes; **fix F4** (decouple `catalog` preflight from `crawl`'s `state.db`
   run-record); capture-output tests. (No visual polish yet.)
3. **Per-stage banners + summary table** (§4.2/4.5) + the shared doc-loop helper (§2.4) carrying per-doc
   WARN messaging; snapshot tests.
4. **`fetch` idempotence + failure classification** (§6.2); `convert`/`fetch` heartbeats.
5. **`vdocs gate --explain`** + `docs/gate-reference.md` (§6.1).
6. **`vdocs doctor`** + `doctor-policy.yaml` + B1–B5 checks + `GOLD LIBRARY: GREEN|RED` (§5).
7. **`vdocs build --fresh --yes`** guided path (§6.3).
8. **Rewrite `de-novo-run.md`** (§6.4); update `vdocs-design.md` for any CLI/contract changes.
9. **Re-run `vdocs doctor` on the live lake** → confirm still GREEN (no regression).

Each lands TDD-first with captured-output/snapshot tests for the new console surface; `make check`
(≥95 %) before every commit.

---

## 8. Open Questions — decisions

**Operator sign-off 2026-06-10.** The four starred (★) were answered directly; the rest proceed on the
defaults below. **DECIDED** marks a locked answer.

1. ★ **Semantic path — delete or disable?** → **DECIDED: Delete outright** (§3). Cleanest airgapped
   surface; fixes F1 by construction. Also delete the `config.vectors_db` property + the `manifest`
   `semantic_available`/`embedding` capability keys (the §3 "Open Q1" extra edit) — no semantic surface
   remains in the manifest.
2. ★ **Console UX dep + dual output?** → **DECIDED: Rich + JSON run-log.** All UI gated through one
   `RunReporter`; `structlog` → the JSON run-log; Rich for the human console (degrades to plain on
   non-TTY). Swapping to zero-dep plain stays a one-file change.
3. ★ **Gate config model?** → **Keep 3 registries + `gate --explain` + `docs/gate-reference.md`; one
   gate, two checkpoints** (no fetch-gate/gold-gate split unless narrow-promote is wanted later).
4. **Status semantics + exit codes?** → **WARN never blocks, only ERROR; the 4 persistent 500s = WARN;
   exit 0 / `--strict`→10 on WARN, 1 on ERROR** (§4.3).
5. **Fetch failure classification?** → **Cap retries (3); classify transient vs permanent; record
   `permanent_missing`; list every permanently-unavailable URL in the summary.**
6. **Untyped docs (F5)?** → **(b) admit + WARN + list for triage** (preserves the fail-safe; makes the
   class visible).
7. **By-design gaps vs defects (F6)?** → **`doctor-policy.yaml` with per-field expected-coverage +
   known-empty allow-list; render BY-DESIGN as its own bucket.**
8. **`doctor` shape?** → **Standalone command + opt-in `run --doctor`; reads `index.db` (+`--deep` for
   bodies); its `GREEN|RED` is the authoritative gate.**
9. **`fetch` idempotence?** → **Skip CAS-present by default; `--refetch` to force.**
10. **Guided build (F9)?** → **`vdocs build --fresh --yes` with `pgrep` precheck; refuse wipe without
    `--yes`.**
11. ★ **Refactor appetite & budget?** → **DECIDED: Open to structural changes.** Broader than the
    clean-in-place default — so **F4 is in scope to FIX** (decouple `catalog` preflight from `crawl`'s
    `state.db` run-record; gate on `catalog.raw.json` presence instead), and structural reshaping of the
    `state.db`/preflight model is permitted where it clearly improves operability. Still preserve the
    medallion layout, the contract registry, and the data-driven DAG as the spine — structural latitude
    is for the *coupling/UX seams*, not a wholesale DAG rewrite. Budget: all 9 commits, sequenced; each
    green; consolidate+validate per the operating-preferences cadence.
12. **`fidelity` stage (F12)?** → **Fold `compliance_pure`/`overstrip_pure` into `doctor` as soundness
    checks; don't ship a separate `fidelity` stage.**
13. ★ **Airgap boundary?** → **DECIDED: Fetch on a connected box, copy the bronze CAS to the airgapped
    box.** `crawl`+`fetch` need the network; everything after `fetch` (convert→…→manifest→doctor) runs
    fully offline. The runbook documents the bronze-CAS hand-off as the airgap line; no internal-mirror
    fetch path required.
14. **Runbook authority?** → **Rewrite `de-novo-run.md` as the canonical runbook; add a short in-tool
    `vdocs help run` pointer.**
