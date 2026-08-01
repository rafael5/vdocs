# Pipeline audit remediation — tracker

Plan:
[`pipeline-audit-remediation-implementation-plan.md`](pipeline-audit-remediation-implementation-plan.md)
· Kickoff prompts: [`../prompts/pipeline-audit-remediation/`](../prompts/pipeline-audit-remediation/)
· Audit: [`../reference/pipeline-adversarial-audit.md`](../reference/pipeline-adversarial-audit.md).
Update this table **per landed step** (TDD → `make check` → commit → tick). A step is DONE
only when its plan-stated measure is demonstrated (green *and*, where specified, red on the
broken fixture). Record the commit hash and any measured number in Notes. A `P<n> ✓` row
additionally requires the **next** phase's kickoff prompt written (execution protocol in the
plan).

Baseline (2026-08-01, `corpus_content_hash 3ce0872e…`): 1,040 fetched / 1,034 indexed (6
doc_ids collapsed); doctor advisory-only; 7 low-retention docs in gold; SQLite fp = row
count; 27.2% of 52,048 latest sections chunk-less; golden nDCG@10 = 0.469 (L1.2 sweep).

| Step | What lands | Status | Commit / notes |
|------|-----------|--------|----------------|
| **P1 — acquisition-chain integrity** | | | |
| P1.1 | `raw/index.json` v2: derived from acquisitions ⋈ inventory, keyed by `doc_id`; fetch `contract_ver=2`; convert/normalize readers adapted | ☑ | `make check` green (1,118 tests, 96.22%). Design §5.5 already *specified* "derived projection of acquisitions" — the sha-keyed merge was the deviation, now corrected. v1 files refused with a remediation (`parse_raw_index`). Obsolete merge test replaced by two behavior tests (narrow re-fetch keeps every fetched doc; a no-longer-admitted doc leaves). New count `indexed`. |
| P1.2 | `validate` Step 5 chain reconciliation (fetched ⊆ admitted; raw-index == fetched; converted == normalized == indexed-raw), findings by doc_id | ☑ | `chain_pure.py` 100% cov; 6 finding kinds; validate gains 4 contract edges (GOLD_INVENTORY/RAW_INDEX/TEXT_CONVERTED/REGISTRIES). 4 red-path integration tests incl. the measured six-doc scenario. Fixture note: seed a broken chain **before** blessing — mutating a tree after trips the drift preflight (a different, coarser guard) instead of the gate under test. |
| P1.3 | DOCX magic check before CAS put; `bad_content` acquisition status | ☑ | `is_docx_payload` (ZIP magic `PK\x03\x04`); refused bytes never enter the write-once CAS, WARN names the URL, retried like a transient miss (a WAF hiccup must not blacklist a real doc). `Acquisition.status` literal + `_STATUS_ORDER` extended. |
| P1.4 | **NEW** — `build_atomic` sweeps the TARGET's stale `-wal`/`-shm` after the replace | ☑ | `6668a26`. Found BY the acceptance run, not the audit: rebuilding index.db over a live-WAL database corrupted it (`database disk image is malformed`; integrity_check showed real btree damage). R7 hardened the temp side only. Shared primitive — serve-inventory/index/relate all rebuild through it. |
| P1 ✓ | Live: 1,040 == 1,040 == 1,040 == 1,040; six doc_ids in `doc_meta_staged`; gate red on hand-broken seam | ☑ | **Chain equal at 1,040 across all six seams** (fetched · raw-index · converted · normalized · doc_meta_staged · documents); all six restored docs present; `integrity_check ok`; validate GREEN incl. `chain_findings=0`; **doctor GOLD LIBRARY: GREEN** (19 pass). Group count **stayed 615** (not ~617 as predicted — all six folded into existing version groups; `slug_stem` correctly strips `r0218`-style revision tokens). Red path proven by 4 permanent integration tests rather than a one-off scratch-lake demo (automated, 3 finding kinds, cannot rot). |
| **P2 — doctor into the DAG** | | | |
| P2.1 | Terminal `doctor` stage (`reports/doctor/doctor.json`, ALWAYS_RERUN, RED ⇒ fail); CLI aliased; `build` tail dropped | ☑ | `74b136b`. `make check` green (1,146 tests, 96.22%). The CLI's inline loader became `server.doctor.diagnose_lake` — one diagnosis path for stage + command; no check logic forked. `requires` gained **REGISTRIES** beyond the plan's three (the doctor policy / gate keep-set / entity-quality declaration are real inputs; ordering unaffected — no producer). `requires_upstream_record=False` (F4) so a wiped `state.db` can't make the gate unrunnable. **`vdocs doctor` + `release` drive the STAGE** (`_run_doctor`), not a stale report: anything that stops the stage completing yields RED, never fail-open. `build --to manifest` → **`--to doctor`** (it would otherwise have stopped one node short of the gate it was meant to end on). |
| P2 ✓ | `vdocs run` ends at doctor GREEN; induced-defect lake exits non-zero | ☑ | Live: `vdocs run` ends **[16/16] doctor GREEN** — 615 gold docs, **19 pass / 0 by-design / 0 warn / 0 fail**; `doctor.json` (2,430 B, 19 checks) written and its verdict matches `vdocs doctor`. Red path: scratch-lake copy with one gold doc's `software_class` blanked → **exit 1 AT the doctor stage**, naming `ACKQ:ackq3_0_p12tm`. Note the plan's suggested red-path lever (re-enable a quarantined entity type) is **not available** — `entity-quality.yaml` currently declares **zero** excluded types, so that check is inert on this lake; a policy-floor field is the working lever. Low-retention re-measured for P3: **still 7** (the six restored docs added none). |
| **P3 — retention gates** | | | |
| P3.1 | Relocated table words credited in `score_retention` | ☐ | low-retention **7** (re-measured 2026-08-01, post-P1) → ___ · 2 QUARANTINE (`PRCA/icd_10_um_tp_4_5_281` 0.14, `PSD/psd_3_p69_um_supv_cp` 0.05), 5 REVIEW (0.53–0.80); 4 of 7 are `_cp` change-pages docs — the uncredited-table-words class R‑5 predicted |
| P3.2 | `retention` block in `capture.yaml`; normalize `contract_ver=2` | ☐ | |
| P3.3 | `validate` Step 6: QUARANTINE blocks; REVIEW needs `registries/retention-signoff.yaml`; validate requires REGISTRIES | ☐ | |
| P3 ✓ | Live green with residual docs PASS/signed-off; synthetic over-strip reds validate | ☐ | |
| **P4 — sound SQLite fingerprints** | | | |
| P4.1 | `sqlite_fingerprint` always content-hash (canonical row encoding) | ☐ | |
| P4.2 | `rows:N` legacy-format migration (accept-once, re-record) | ☐ | |
| P4 ✓ | Same-rowcount cell mutation re-runs `index`; full live run, no spurious drift FAILs | ☐ | |
| **P5 — history lineage truth** | | | |
| P5.1 | `merge_history` supersedes entries on changed `body_sha256`; consolidate `contract_ver=4` | ☐ | |
| P5.2 | `validate` Step 4+: latest member sha == sha(body.md) (`stale-lineage`) | ☐ | |
| P5 ✓ | Forced content change → superseded record + green; hand-staled history reds | ☐ | |
| **P6 — container lead-in chunking** | | | |
| P6.1 | Containers with substantive lead-in become searchable; index `contract_ver=15`; golden nDCG no regression | ☐ | nDCG 0.469 → ___ |
| P6.2 | Re-measure chunk-less share; update all five hardcoded 26.7%-rule sites | ☐ | 27.2% → ___ |
| P6.3 | Not-indexed warning parity: ask CLI + `--json` share the MCP constant | ☐ | |
| P6 ✓ | Chunk-less share < 8% target; FileMan lead-in query answered from `search` | ☐ | |
| **P7 — close-out** | | | |
| P7.1 | Full forced end-to-end run green through doctor stage | ☐ | |
| P7.2 | Audit register rows struck with commit hashes; master-table cells refreshed | ☐ | |
| P7.3 | Operator flagged: vdocs-corpus skill + mounted MCP instructions quote stale % | ☐ | |
| P7.4 | Plan + tracker archived to `docs/historical/` | ☐ | |

**Riders landed opportunistically** (out-of-scope register items that rode a phase): R‑8 (DOCX magic check) landed as P1.3 by plan; **P1.4 was unplanned** — a corruption defect the audit never saw, surfaced only by running the pipeline end-to-end. Lesson for later phases: the acceptance run is not a formality, it is the only step that exercises real WAL/crash states no fixture reproduces. **R‑13 + R‑14 landed with P2.1** (`74b136b`): `_index_fingerprint` now `PRAGMA wal_checkpoint(TRUNCATE)`s before hashing — reproduced red first (a committed write sitting in `-wal` left the AI card's staleness stamp **byte-identical**, so a consumer would have concluded "unchanged" over a corpus that changed); and `_wipe_lake` now spares `reports/validation/` (validate's cross-run drop baseline is *evidence*, not derived state — wiping it disarmed the drop check on exactly the `--fresh` runs most likely to lose documents). Both are WAL/lifecycle bugs of the same family as P1.4.

**Corrections:** the audit named the six lost doc_ids by eyeballing the first element of each duplicate pair — those were the *survivors*. The real six (`CPRS:cprsguitm`, `PSJ:psj_5_0_{nurse,supr}_um`, `PSJ:psj_5_0_tm`, `PSN:psn_4_{tm,um}_r`) were computed as a set difference at P1 close; [S4] and the P1 prompt are corrected. Count, mechanism and impact were right — only the identifiers were wrong.
