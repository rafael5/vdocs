# Pipeline audit remediation plan — findings 1–5

**Status: ACCEPTED · in progress** · Tracker:
[`pipeline-audit-remediation-tracker.md`](pipeline-audit-remediation-tracker.md) · Source:
[`../reference/pipeline-adversarial-audit.md`](../reference/pipeline-adversarial-audit.md)
(2026-08-01, live lake `corpus_content_hash 3ce0872e…`).

Fixes the audit's five significant findings, in enforcement-first order:

| Finding | Audit refs | Phase |
|---|---|---|
| 1. Sha-keyed `raw/index.json` collapsed 6 doc_ids; no gate joins the acquisition chain | R‑2, R‑3, [S4], [S12] | P1 |
| 4. Doctor (the only index.db gate) is advisory — `vdocs run` never executes it | R‑6, [S18] | P2 |
| 3. Retention verdicts don't gate; `blocks_publish()` is dead code | R‑5, [S8] | P3 |
| 5a. Cheap SQLite fingerprint = row count → content-only changes skip consumers | R‑1, §2 | P4 |
| 5b. `history.yaml` append-only merge keeps stale member facts | R‑9, [S9] | P5 |
| 2. Container lead-in prose never chunked (27.2% of live sections unsearchable) | R‑7, [S10] | P6 |

Ordering rationale: P1 first because it is the one **measured live data defect**; P2 second so
every later phase lands under an enforced (not advisory) index.db gate; the substrate fixes
(P4/P5) before P6 because P6 is the largest behavioral change and should re-run under sound
skip/lineage semantics; P7 closes out (re-measure, update the published constants, strike the
register rows).

House rules apply to every step: **TDD** (failing test first), `make check` green before
commit, `contract_ver` bump on any produced-shape change, pure logic in `*_pure.py`,
update `vdocs-design.md` in the same commit when a stage's inputs/outputs change, and tick the
tracker per landed step.

---

## P1 — Acquisition-chain integrity (finding 1)

**Problem (measured).** `raw/index.json` is keyed by content sha: 1,040 `fetched` acquisitions
→ 1,034 index entries; 6 doc_ids (`CPRS:cprsguitm_0_636`, `PSJ:psj_5_nurse_um`,
`PSJ:psj_5_supr_um`, `PSJ:psj_5_tm`, `PSN:psn_4_um`, `PSN:psn_4_tm`) collapsed
(last-writer-wins), got no bundle, yet report `fetched`. The merge is also add-only (stale
entries never leave), the winner of a doubled bundle is dict-insertion order, and **no gate
anywhere joins the chain** — which is why a silent loss class, not just this bug, exists.
Bonus defect found during the audit: a re-run cannot self-heal a lost entry, because
`SKIP_PRESENT` short-circuits before the index write.

**P1.1 — derive `raw/index.json` from acquisitions ⋈ inventory (re-key by `doc_id`).**
`fetch` stops merging a mutable file and instead *derives* the index each run: for every
acquisition with `status='fetched'` whose `doc_id` is a current gate-admitted target, emit
`doc_id → {sha256, app_code, doc_slug, title, source_url, ext}` (identity fields joined from
the gold inventory). Format marker `{"format": 2, "docs": {…}}`; a v1 (sha-keyed) file is
ignored as a source (the derivation replaces it — nothing in v1 is authoritative that
acquisitions ⋈ inventory doesn't hold). Effects, all intended: the 6 lost doc_ids reappear
(CAS hit, no network); duplicate-content docs each keep their own entry (CAS still stores one
blob); withdrawn/renamed docs drop out of the index the next run (un-strands R‑10 and makes
convert's `prune_bundles` actually able to fire); insertion-order winner-picking disappears
(one entry per doc_id by construction).
*Code:* `stages/fetch/fetch_pure.py` (new pure `build_raw_index(acquisitions, records,
targets)`), `stages/fetch/stage.py` (drop the merge; write the derivation), **fetch
`contract_ver = 2`** (RAW_INDEX shape change → convert/normalize re-run via `#contract_ver`).
*Consumers to adapt:* `convert/stage.py` (iterate `docs`; `raw.get(entry["sha256"], ext=…)`),
`normalize/stage.py:_sha_by_bundle_path` (read `sha256` field).
*Tests first:* pure derivation (incl. duplicate-sha pair → two entries; withdrawn doc_id →
absent; format marker), consumer readers on a v2 fixture, migration behavior on a v1 file.

**P1.2 — chain-reconciliation gate in `validate` (Step 5).** New pure
`stages/validate/chain_pure.py::reconcile_chain(admitted, acquisitions, raw_index_ids,
converted_bundles, normalized_bundles)` enforcing, as blocking findings:
`fetched ⊆ admitted` *(a fetched doc the gate no longer admits = stale corpus)*,
`raw_index_ids == fetched` *(the P1.1 derivation, verified independently from disk)*, and
`converted == normalized == bundles(raw_index_ids)` *(no doc lost between CAS and silver)*.
Set differences are reported by doc_id in `verification.json` (a computable finding list, not
just counts). `validate` gains `requires` on `GOLD_INVENTORY` + `RAW_INDEX` + `TEXT_CONVERTED`
(real edges, per the contract discipline) and reads acquisitions via `ctx.state`.
*Tests first:* each seam broken in a fixture lake → its finding fires; healthy fixture → none.

**P1.3 — content admission check at the CAS door (R‑8, same seam, 10 lines).** Before
`store.put`, verify DOCX magic (`PK\x03\x04`); a non-DOCX 2xx body records a typed
`bad_content` acquisition status (never enters the write-once CAS). `Acquisition.status`
literal extended; `inventory --status` surfaces it.

**Measure of done (P1):** on the live lake, one `vdocs fetch --all` + `run --from convert`:
`fetched == raw-index entries == converted bundles == normalized bundles == 1,040`; the six
doc_ids present in `doc_meta_staged`; `validate` green **and demonstrably red** when any seam
is hand-broken on a scratch lake; consolidate re-groups the six as version-group members (5 of
6 share a stem with their twin — group counts shift from 615, doctor re-baselines).

## P2 — Doctor into the DAG (finding 4)

**Problem.** The strongest independent gate (19 checks, read-contract verbatim, quarantine
residue) runs only under `build` or by hand; `vdocs run` can finish green over a RED corpus.

**P2.1 — new terminal stage `doctor`.** Thin `stages/doctor/stage.py` wrapping the existing
`server/doctor.py:diagnose` (no logic fork): `requires` = INDEX_DOCUMENTS + RELATIONS +
CONTRACT_MANIFEST (sorts it after `manifest`), `produces` = `reports/doctor/doctor.json` — the
report as a **computable artifact** (verdict, per-check health/detail), closing the audit's
"gate that works ≠ gate that's enforced" placement gap and giving the §5 ledger a 17th node.
`ALWAYS_RERUN`; `deep_gate` fails on RED (`PostflightError` → non-zero exit, stop-on-first-
error). Knowledge.db/entity-quality inputs stay optional exactly as the CLI treats them.
*CLI:* `vdocs doctor` becomes a thin alias that renders the stage's report (one diagnosis
path); `build` drops its manual doctor tail (the DAG now ends with it).
*Tests first:* orchestrator order (doctor last), RED-fixture → `StageFailed`/exit ≠ 0,
report JSON golden.

**Measure of done (P2):** `vdocs run` on the live lake ends `… manifest → doctor` GREEN with
`reports/doctor/doctor.json` written; the same run on a lake with an induced defect (e.g. a
quarantined entity type re-enabled) exits non-zero at `doctor`.

## P3 — Retention gates (finding 3)

**Problem.** `score_retention` fires (7 live low-retention docs) but only lands in
`flags.yaml`; `blocks_publish()` is called by nothing but its own unit test; QUARANTINE docs
ship. Also the score is unfairly harsh: relocated table words aren't credited.

**P3.1 — credit relocated words.** `normalize/stage.py` passes
`relocated_words = Σ word_count(tab.csv_text)` into `score_retention` (the parameter already
exists). Re-score expectation: some of the 7 flip to PASS.

**P3.2 — record retention in `capture.yaml`.** Add a `retention` block
(`{retention, verdict, enriched_words, kept_words}`) to the per-bundle manifest
(`capture_pure.build_manifest`) so the verdict is a **typed, dense record**, not a sparse
flag. **normalize `contract_ver = 2`** (sidecar shape change).

**P3.3 — gate in `validate` (Step 6).** Using the existing `blocks_publish` rule (it finally
goes live): any bundle whose `capture.yaml` verdict is QUARANTINE → blocking finding; REVIEW
blocks unless its `doc_id` is signed off in a new curated
`registries/retention-signoff.yaml` (`signoffs: [{doc_id, reason, date}]` — the human
in-the-loop is a registry entry, per tenet #13, and the registry is already a fingerprinted
validate input via REGISTRIES… note: validate does not currently require REGISTRIES — add it).
*Tests first:* QUARANTINE fixture blocks; REVIEW blocks; REVIEW + signoff passes; PASS never
blocks.

**Measure of done (P3):** live run green with every remaining low-retention doc either PASS
(after P3.1), signed off with a reason, or genuinely blocked; a synthetic over-strip (drop 60%
of a fixture body) reds `validate`.

## P4 — Sound SQLite fingerprints (finding 5a)

**Problem.** Cheap SQLite fingerprint is `rows:<count>`; content-only changes with a stable
row count (e.g. a registry label fix flowing into `doc_meta_staged`'s 1,034 rows) let
consumers skip stale. Files/trees are fine (atomic-write content-skip preserves mtime
honestly); only the SQLite path lies.

**P4.1 — content-hash SQLite fingerprints unconditionally.** `kernel/fingerprint.py:
sqlite_fingerprint` drops the row-count path: always the canonical content hash (the existing
strong path: typed-cell encoding, NULL ≠ `''`, sorted rows — already order-independent).
Measured cost is bounded (largest contracted table: `chunks`, 48.7k rows — a sub-second hash
on this box; if preflight latency ever matters, memoize per `(path, mtime_ns)` within a run).
The `--verify` flag keeps its meaning for files/trees.

**P4.2 — migration.** Old recorded `outputs_fp` (`rows:N`) mismatch the new format, which the
consumer preflight reads as upstream drift → FAIL. Handle it cleanly, not by operator lore:
treat a recorded fingerprint matching `^rows:\d+$` as *format-migrated* (log + accept once,
re-record on this run's postflight). One-line predicate + test; removed after one release.

**Measure of done (P4):** regression test — mutate one cell of `doc_meta_staged` without
changing the row count → `index` preflight re-runs (today's behavior: skips); full live
`vdocs run` completes with no spurious drift FAILs.

## P5 — History lineage truth (finding 5b)

**Problem.** `merge_history` appends only unseen `doc_id`s; a re-processed member's fresh
facts (`body_sha256`, `revisions`, `official_date`) are silently discarded, so `history.yaml`
— the designated replay source — can misdescribe the current bundle. Undetectable today:
`bundle.yaml` is recomputed from parts, so validate passes.

**P5.1 — supersedes entries.** `consolidate_pure.merge_history`: when a fresh member shares a
`doc_id` with a captured entry but differs in `body_sha256`, adopt the fresh facts and push
the prior fact-dict onto the entry's `superseded: […]` list (append-only *preserved* — no
recorded fact is ever deleted, it is demoted with its capture intact; prior bodies remain in
the `_shared/history` CAS by construction). Unchanged members untouched; identical re-runs
stay no-ops. **consolidate `contract_ver = 4`.**

**P5.2 — validate check (Step 4 extension).** For every gold bundle: the history member with
`is_latest: true` must satisfy `body_sha256 == sha256(bundle body.md bytes)` — the check that
makes lineage staleness impossible to ship. Blocking finding kind `stale-lineage`.
*Tests first:* changed-member fixture → superseded list populated + validate green; hand-stale
history → `stale-lineage` fires.

**Measure of done (P5):** re-normalize one live doc with a forced content change → its
history entry updates with a `superseded` record; validate green; the audit's [S9] scenario
(stale sha) reds.

## P6 — Container lead-in chunking (finding 2)

**Problem (mechanism confirmed in code).** `shred_sections` marks a section `container`
purely structurally (next heading is deeper) and `searchable` is `kind ∈ {ok, stub}` — so a
container's own lead-in prose (in reference manuals: the Format / Input Parameters / flag-table
contract text) never reaches `chunks`/FTS. Live: 11,526 containers + 2,627 hollow = 27.2% of
52,048 latest sections yield no searchable text. This is the single highest-leverage
search-quality fix in the audit.

**P6.1 — searchable containers.** `kernel/markdown.classify_section` /
`index_pure.shred_sections`: a container whose **own body** (heading → first child) passes the
existing substantive-token floor becomes `searchable=True` (kind stays `container` — the
nav-map semantics and `section_path` derivation are untouched; hollow stays unsearchable —
there is nothing to index). `chunk_units` then emits its lead-in chunk with no further change.
**index `contract_ver = 15`**; no read-contract shape change (column semantics only —
confirm `contracts/read/v1.json` documents `searchable` loosely enough, else MINOR bump).
*Tests first:* container-with-substantive-lead-in fixture → chunked; bare container (heading
only) → not; golden-set nDCG@10 re-run **must not regress** (the merge-small-leaves experiment
showed structural chunking changes can tank precision — this change only *adds* chunks under
their own anchors, but prove it, don't assume it).

**P6.2 — re-measure and republish the numbers.** The 26.7% / 13,899 / 52,048 / "~73%" figures
are hardcoded in five places that must move together: `server/mcp.py`
(`NOT_INDEXED_RULE`, `TOOL_RULE`, orientation, initialize instructions), the `_has_chunks`
docstring, and the operator-facing docs. Re-measure post-P6.1 (expected residual: true bare
containers + hollow only), update the constants, and record the before/after in the tracker.
The residual disclosure stays — the rule is right even when the number shrinks.

**P6.3 — warning parity on the CLI (audit R‑11, same seam).** The `ask` CLI's empty result
and `--json` output emit the same not-indexed warning object as the MCP search tool — one
shared constant in `server/search.py`, three surfaces.

**Measure of done (P6):** chunk-less share of live latest sections drops from 27.2% to the
measured residual (target < 8%; report actual); golden nDCG@10 ≥ baseline; a known
container-lead-in query (the FileMan API "Input Parameters" class the audit cites) returns the
section from `search` where it previously required the body.md fallback; all five constant
sites agree with the new measurement.

## P7 — Close-out

1. Re-run the full pipeline end-to-end (`vdocs run --force`, then doctor via the P2 stage) —
   all green on the re-keyed, re-gated, re-chunked lake.
2. Update `../reference/pipeline-adversarial-audit.md`: strike register rows R‑1, R‑2, R‑3,
   R‑5, R‑6, R‑7, R‑8 (P1.3), R‑9, R‑11, R‑13-adjacent numbers, each with its landing commit
   hash, per the audit's own correction rule; refresh the master-table Status/Credibility
   cells the fixes change.
3. Update the external surfaces that quote the 27% rule: the `vdocs-corpus` skill and the
   mounted vdocs MCP server instructions (out-of-repo — flag to the operator; do not edit
   silently).
4. Archive this plan + tracker to `docs/historical/` per the docs lifecycle when every phase
   is ticked.

## Out of scope (tracked in the audit register, not this plan)

R‑4 (crawl completeness floor), R‑12 (SKL curation loop), R‑13 (WAL checkpoint before
AI-card fingerprint — one-liner, may ride along with P2), R‑14 (`--fresh` spares
`reports/validation/`), R‑15/R‑16 (error-budget tightening, classification golden sets).
Anything here that turns out to be a 5-line rider on a phase already touching the file may
land with that phase, noted in the tracker.
