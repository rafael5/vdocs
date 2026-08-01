# Kickoff — P2: doctor into the DAG (the only index.db gate stops being advisory)

**Repo: `vdocs`.** Fresh session, `cd ~/projects/vdocs`. Read `CLAUDE.md`, then
`docs/proposals/pipeline-audit-remediation-implementation-plan.md` **§P2**, and audit footnote
[S18] + register row R‑6 in `docs/reference/pipeline-adversarial-audit.md`. Tick
`docs/proposals/pipeline-audit-remediation-tracker.md` per landed step. **Shared-lake rule:**
`pgrep -af "vdocs run"` before any command touching `~/data/vdocs`.

## Where we are

**P1 is complete** (`6ba05eb`, `38190e9`, `fa66309`): `raw/index.json` is derived and
`doc_id`-keyed, `validate` Step 5 joins the acquisition chain, and non-DOCX payloads are refused
at the CAS door. The live lake was re-derived and re-run end-to-end — the six previously-lost
documents are back with zero downloads, and the corpus is now **1,040 documents**
(*fill in the final consolidate group count + doctor verdict from the P1-close tracker row*).

P1 proved the value of a gate that *runs*. P2 fixes the inverse problem: the strongest gate in
the system **does not run**.

`server/doctor.py` is 19 checks — coverage floors, anchor integrity + coverage, entity
quarantine cascade, SKL projection wipe detection, gate fidelity, latest-only FTS, vocab
closure, and read-contract **verbatim view verification** — and every one passed on the live
lake. But it is invoked only by `vdocs build` and by hand. **A pipeline driven with `vdocs run`
can finish green over a RED-able `index.db` and nobody asks.** Same finding class as the org's
CI-audit F‑27: *a gate that works is not a gate that is enforced*. Note the specific danger
doctor already guards and `run` currently misses: `index --force` after `merge` silently
recreates merge's empty shells (the "SKL projections" check exists precisely because that
happened).

## Goal — one landed step, commit subject `P2.1:`

A terminal **`doctor` stage** in the DAG that fails the run on RED and writes its report as a
**computable artifact** (the §5 ledger gains a 17th node; today the verdict exists only as
stdout a human read).

### The stage

`src/vdocs/stages/doctor/stage.py` — a *thin* driver wrapping the existing
`server/doctor.py:diagnose`. **Do not fork the check logic**: one diagnosis path, as
`_emit_doctor` in `cli/app.py` already demonstrates. Extract what that CLI helper does
(load kept doctypes, doctor policy, read contract, excluded entity types, optional
`knowledge.db` entity count) into a shared function both the stage and the CLI call, rather
than writing it twice.

- `name = "doctor"`, `requires = [INDEX_DOCUMENTS, RELATIONS, CONTRACT_MANIFEST]` — the
  CONTRACT_MANIFEST edge is what sorts it after `manifest`, making it terminal. Verify that in
  a test against `Orchestrator.order()` rather than assuming.
- `produces = [DOCTOR_REPORT]` — a new contract for `reports/doctor/doctor.json`:
  `{verdict, gold_count, checks: [{name, health, detail}], generated_at}`. Deterministic
  ordering; the timestamp is the one non-reproducible field (mirror how `manifest` handles it).
- `idempotency = ALWAYS_RERUN` (a gate re-checks every time, like `validate`).
- `deep_gate` fails when the verdict is RED → `PostflightError` → non-zero exit through the
  existing stop-on-first-error contract. **WARN and BY-DESIGN must not fail** — F6 in
  `doctor.py:verdict()` is deliberate; preserve it.
- `knowledge.db`/entity-quality inputs stay **optional** exactly as the CLI treats them (a lake
  with no SKL must not fail doctor).

### CLI

`vdocs doctor` becomes a thin alias that runs the stage (or renders its report) — one
diagnosis path, no second route (§7.1). `build` drops its manual doctor tail now that the DAG
ends with it. Check `build`'s `--to manifest` bound: it must extend to `doctor` or the guided
build silently stops short of the gate.

### Tests (write first)

1. `Orchestrator(build_stages()).order()` ends with `doctor` — the placement *is* the fix.
2. A RED fixture index.db (easiest: a document row with an empty policy-floor field, or a
   quarantined entity type present) → `StageFailed`/`PostflightError`, non-zero exit.
3. A GREEN fixture → stage ok + `doctor.json` written with the expected shape.
4. WARN-only fixture → **passes** (F6 preserved).
5. `vdocs run` (no `--only`) reaches doctor — the regression test for R‑6 itself.

## Acceptance — the P2 ✓ row

- `make check` green.
- Live lake: `vdocs run --to doctor` (or plain `vdocs run`) ends **GREEN** with
  `reports/doctor/doctor.json` present and its `verdict` matching what `vdocs doctor` prints.
- **Red-path demo on a scratch lake** (`DATA_DIR` override — never the live one): induce a
  defect doctor catches (e.g. re-enable a quarantined entity type in
  `registries/entity-quality.yaml` and rebuild the index) and show `vdocs run` exiting non-zero
  *at the doctor stage*, not silently green.
- Tick P2.1 + P2 ✓, then **write `P3-retention-gates-kickoff.md`** (plan §P3 — it will need
  P3's live inputs: the current low-retention count, which was **7** at audit time and may have
  changed with the 6 restored documents; re-measure it and put the number in that prompt),
  update the prompts README, retire this prompt to `docs/prompts/historical/`.

## Riders worth taking (both one-liners, same files)

- **R‑13**: `manifest._index_fingerprint` streams `index.db` while the lake runs WAL, so the
  AI-card staleness stamp can hash a stale view. `PRAGMA wal_checkpoint(TRUNCATE)` (or
  `VACUUM INTO`) before hashing.
- **R‑14**: `_wipe_lake` deletes `reports/`, destroying validate's cross-run drop-detection
  baseline exactly on `--fresh` builds. Exempt `reports/validation/` — it is *evidence*, not
  derived state (the same argument that already spares `catalog.raw.json`).

Log either in the tracker's "Riders landed" line if taken.

## Increment protocol

Commit + push per step with the trailer; update `docs/vdocs-design.md` in the same commit (the
§8 stage table gains a `doctor` row; the §5.3 lake layout gains `reports/doctor/`). If the code
contradicts this prompt, **the plan is the bug report** — reconcile the plan first.
