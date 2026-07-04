# Kickoff — Pipeline Code Review + Human-Operability Hardening (airgapped, no-AI handoff)

**For a fresh session.** This is a **review-and-harden** task, not a feature build. The goal:
**graduate the `vdocs` pipeline so a human operator with no AI assistance can configure, run, and
troubleshoot it offline / airgapped.**

> **The forcing observation.** The pipeline was just driven end-to-end (de-novo gated build →
> `GOLD LIBRARY: GREEN`, see `docs/gold-validation-report.md`) **only because an AI was supervising
> every stage** — reading `state.db`, diagnosing an OOM, killing a stage, hand-sequencing
> `--only` stages, writing ad-hoc validation scripts, and explaining cryptic counts. **The operator
> (Rafael) has stated he has zero confidence it would have completed without that supervision.** That
> is the bug. The pipeline must become legible and self-diagnosing enough that the AI is unnecessary.

> **⛔ Do NOT write code yet.** Phase 1 is a comprehensive review + a written findings/plan doc +
> the open questions below answered by the operator. Only after sign-off do you touch code. Put the
> review findings and the design in `docs/` (propose-plan-first, per the project workflow).

---

## Read first (context)
- `CLAUDE.md` (architecture rules: medallion, pure/`*_pure.py` vs I/O `stage.py`, shared `kernel/`,
  no top-level modules, **discovery-is-data** registries).
- `docs/offline-lexical-search-plan.md` (⭐ active plan — lexical-first, offline, human-consumer) and
  its implementation tracker. **The direction reset descoped semantic/vector + MCP.**
- `docs/doc-classification-filtering-summary.md` (the gate/taxonomy spec — the §3 admission funnel).
- `docs/gold-validation-report.md` (the just-completed B1–B5 validation — the flagged issues live here).
- `docs/de-novo-run.md` (the current operator runbook — **known to be partly inaccurate**, see below).
- Project memory `app-profiles-monograph.md` (the 2026-06-10 UPDATE block records the run's gotchas).

---

## Scope

### In scope
1. **Comprehensive code review** of the whole pipeline (`src/vdocs/`: the ~13-stage DAG + `kernel/`,
   `contracts/`, `cli/`, `server/`, `models/`, `registries/`) against the architecture rules — find
   **inconsistencies, redundancies (copy-paste across stages = a review failure per §9.2), and
   dead-end code.**
2. **Remove the descoped semantic/vector path** (dead end): the `embed` stage, `vectors.db`,
   `sqlite-vec`, embedding registries, the `manifest` `semantic_available` plumbing, any MCP remnants.
   (Footprint spans `stages/embed/`, `cli/app.py`, `config.py`, `contracts/registry.py`,
   `kernel/db.py`, `server/`, `pyproject.toml`, plus README/registry mentions.) See Open Q1.
3. **Transparent, operator-facing gate configuration** — two distinct, clearly-documented gates:
   - **(a) the fetch gate** — what gets *downloaded* (noise §9.5 + docx-only + app-scope G3 +
     doc-type G4, today in `scope-policy.yaml` / `doctype-policy.yaml` / `noise-domains.yaml`,
     assembled by `fetch/policy.py::load_gate_policy` into `GatePolicy`).
   - **(b) the gold gate** — what gets *promoted to the gold corpus* (today this is the same
     fetch-time admission gate; consolidation G5 is dedup, not admission). Make the human able to see
     and change *both* without reading code. See Open Q3.
4. **Human-operator runtime UX** (the heart of this task):
   - **Standardized per-stage messaging.** Every stage emits, in a uniform format: a **start banner**
     (`[k/N] STAGE — what it does`), **progress** while working (counts / % / heartbeat for long
     stages like `fetch`, `convert`), and a **stage result line** with a status token —
     **`GREEN` / `WARN` / `ERROR`** — plus headline counts and elapsed time.
   - **Diagnostics inline.** WARN/ERROR/diagnostic lines must be human-readable (what, which doc/app,
     why, what to do) — not raw structlog dicts.
   - **Pipeline progress.** The operator can always tell *which stage of how many* and overall % done.
   - **End-of-run summary table.** On completion print a table: every stage run, its status
     (GREEN/WARN/ERROR), key counts, # warnings, elapsed; then an overall verdict + next-step hint.
     Non-zero exit code on any ERROR; a documented exit-code contract.
5. **Bake the validation in.** Promote the ad-hoc B1–B5 checks (currently throwaway `/tmp` scripts)
   into a first-class **`vdocs doctor`** (or `validate`) command that emits the same human table +
   PASS/FAIL per check + a final `GOLD LIBRARY: GREEN|RED`. Must distinguish **by-design gaps** from
   **real defects** (see Open Q7). See Open Q8.
6. **Fix / trim the flagged issues from the e2e run** (list below).
7. **Rewrite `docs/de-novo-run.md`** as the single, accurate operator runbook (it currently
   misstates idempotence and stage slicing — see flagged issues).

### Out of scope (unless an Open Q answer says otherwise)
- The TUI (`tui-build-kickoff.md` is a separate phase, gated on GREEN).
- New search/ranking features. New corpus content. Re-architecting the 17-stage DAG wholesale
  (this is *clean + harden in place* — confirm appetite in Open Q11).

---

## Flagged issues from the 2026-06-10 end-to-end run (must each be addressed or consciously deferred)

| # | Issue | Why it bit a human-without-AI |
|---|---|---|
| F1 | **`embed` (ONNX→`vectors.db`) is parked/descoped but still in the DAG**; `vdocs run --to manifest --force` pulls it in and it ran to ~8 GB RSS (OOM-prone). An AI had to notice and kill it. | A human would have watched it hang/OOM with no idea it was an abandoned path. |
| F2 | **`fetch` re-GETs every target on every run** (the `state.db` `prior` lookup only counts attempts; the CAS dedupes the *write*, not the network GET). The runbook claims "CAS hits are skipped, only failures re-attempt." | The "re-run until `failed=0`" loop re-downloads 1040 docs each pass — a human would wait hours or thrash. |
| F3 | **4 fetch failures were persistent upstream VDL HTTP 500s** (verified GET+HEAD across retries); `failed=0` is unreachable. The runbook says loop "until `failed=0`." | A human follows the runbook into an infinite retry of permanently-broken URLs. |
| F4 | **Wiping `state.db` forces a re-crawl** (`catalog` preflight gates on a crawl-`ok` `stage_run`), undocumented. | A human wipes the lake, runs `catalog`, gets a cryptic preflight failure. |
| F5 | **Untyped docs admitted via fail-safe `default: keep`** (3 `SD PIMS … TM ADDENDUM` docs had empty `doc_type`→empty `anchor_key`, mis-collapsed). Fixed the regex this run, but the *class* of "couldn't classify → silently admitted" has no operator-visible surface. | A human never learns some docs entered gold unclassified. |
| F6 | **`function_category` 94.3% looks like a failure but is by-design** (fallback-profile apps have no Monograph SPM line; 0/104 main profiles affected). | A human sees "94.3%" and either panics or ignores a real gap next time. |
| F7 | **Gate counts drift silently** (1036 → 1044 after a fresh crawl found +73 docs). No message explains why the number changed. | A human can't tell benign currency drift from a gate misconfiguration. |
| F8 | **Validation was entirely ad-hoc** (`/tmp/validate_gold*.py`). No shipped way to ask "is my corpus sound?" | A human has no GREEN/RED check at all. |
| F9 | **Destructive `rm` on the shared lake + manual stage sequencing** were done by hand. No guided "build from scratch" path. | A human must know the exact wipe set and the exact `--only` sequence to dodge `embed`. |
| F10 | **One `AR/WS:p13` 3-part anchor** (bare patch-token slug, no stem) — accepted edge case, but undocumented as "known/accepted." | A future validation flags it as new corruption. |
| F11 | Stray `select-*.txt` files at the lake root; leftover `.vectors.db.tmp*` after a killed embed. | Lake clutter a human can't distinguish from real artifacts. |

---

## Acceptance criteria (definition of "graduated")

A competent operator, **offline/airgapped, with no AI**, can:
1. **Configure** what is fetched and what reaches gold by editing clearly-documented config files
   (with inline comments + a config reference doc), and *see* the effective gate before running
   (`--dry-run` style preview with human counts).
2. **Run** the whole pipeline (or any slice) with a single guided command that prints, for each
   stage: start banner → live progress → `GREEN/WARN/ERROR` result with counts + elapsed; and a
   final summary table + overall verdict + exit code.
3. **Troubleshoot** from the messages alone: every WARN/ERROR says what happened, where, why, and
   the next action — no need to read source or query `state.db` by hand.
4. **Trust** the result via `vdocs doctor` emitting `GOLD LIBRARY: GREEN|RED` with by-design gaps
   clearly separated from defects.
5. The descoped semantic/vector code is **gone** (or behind one clearly-OFF, documented flag).
6. `make check` green (≥95% cov), TDD throughout; new console/UX output is tested (snapshot or
   captured-output tests). The operator runbook (`de-novo-run.md`) matches actual behavior.

---

## Open questions — ANSWER THESE BEFORE WRITING CODE

> Bring these to the operator first; the answers shape everything. Add more as the review surfaces them.

1. **Semantic/vector path — delete or disable?** Fully remove `embed`/`vectors.db`/`sqlite-vec`/
   embedding registries/`semantic_available` (recommended, given the airgapped no-ML goal), or keep
   behind a single default-OFF feature flag for a possible future? (Affects `contracts/registry.py`,
   the DAG order, `manifest`, `pyproject.toml`.)
2. **Console UX dependency.** Is a TUI/console lib (e.g. **Rich**) acceptable for the human-facing
   output, or must runtime output be plain stdout with zero new deps (airgapped/vendoring concern)?
   Do we want **dual output** — pretty human console **and** a machine-readable JSON run-log file
   (so structlog stays for the log file, Rich/plain for the human)?
3. **Gate config model.** Consolidate the fetch gate into one operator-facing `admission.yaml`, or
   keep the three registries (`scope-policy` / `doctype-policy` / `noise-domains`) but add a config
   reference doc + a `vdocs gate --explain` preview? Is the **gold gate** ever different from the
   **fetch gate** (today they're the same), or should "what's fetched" vs "what reaches gold" be two
   independently-togglable configs?
4. **Status semantics + exit codes.** Define `GREEN/WARN/ERROR` precisely: does a WARN ever block, or
   only ERROR? Is "4 persistent upstream 500s" a WARN (proceed) or ERROR (stop)? What exit codes does
   the operator/script get (0 / WARN-but-ok / ERROR)?
5. **Failure classification in `fetch`.** Cap retries how? Classify HTTP 4xx/5xx-permanent vs
   transient, record + report permanent-missing as WARN (not a blocking loop)? Should the final table
   list every permanently-unavailable URL?
6. **Untyped/unclassified docs (F5).** When `default: keep` admits a doc the classifier couldn't
   type: (a) hard-fail, (b) admit + WARN + list for triage, or (c) quarantine out of gold until typed?
7. **By-design gaps vs defects (F6).** How should `doctor` express "expected empty" (e.g.
   `function_category` for fallback apps) vs a real gap? Encode per-field expected-coverage thresholds
   (and an allow-list of known-empty apps) in config?
8. **`vdocs doctor` shape.** Separate explicit command, and/or auto-run at the end of `run`? Does it
   read only `index.db`, or also the lake bodies? Is its `GREEN/RED` the authoritative gate, replacing
   the manual sign-off?
9. **`fetch` idempotence (F2).** Should `fetch` skip docs already present in the CAS by default (true
   resume), making "re-run to retry failures" cheap and honest? Any reason to keep re-GETting?
10. **Guided from-scratch build (F9).** Add a single `vdocs build [--fresh]` that safely sequences
    crawl→…→manifest (wipe handled, `embed` excluded, messaging on)? How should it handle the
    destructive wipe — refuse unless `--fresh --yes`, and how does it cooperate with the shared-lake
    rule (`pgrep` check)?
11. **Refactor appetite.** Is this strictly clean-in-place (preserve the DAG/contracts), or are
    structural changes (merging/splitting stages, changing `state.db`/preflight coupling F4) on the
    table? What's the size/time budget?
12. **The `fidelity` stage.** It exists on disk (`stages/fidelity/`) but was **not** in the run's DAG.
    Live, dead, or aspirational? Fold into `doctor`, keep, or remove?
13. **Airgap boundary.** Define precisely what must work with no network: is `fetch` done on a
    connected box and bronze copied to the airgapped one, or must the airgapped box fetch too? What's
    the offline-from-here line?
14. **Runbook authority.** Is `de-novo-run.md` the single operator runbook to rewrite, or do we want a
    new `OPERATING.md` / `vdocs help run` in-tool guide as the canonical reference?

---

## Process discipline (when code does start)
- **TDD hard rule** — test first, red, implement, green, `make check` before commit. UX output gets
  captured-output/snapshot tests; don't ship untested console formatting.
- **Propose-plan-first** — the review findings + the messaging/config design land in `docs/` and are
  signed off before refactoring. Update `docs/vdocs-design.md` when a stage's inputs/outputs/CLI change.
- **Incremental + committed** — land the cleanup in reviewable commits (dead-code removal; gate
  config; per-stage messaging; summary table; `doctor`; runbook), each green, not one mega-PR.
- **No regressions to GREEN** — re-run `vdocs doctor` (or the B1–B5 checks) after the refactor and
  confirm the corpus still validates GREEN.
