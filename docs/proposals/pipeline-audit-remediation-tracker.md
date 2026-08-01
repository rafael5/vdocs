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
| P1.1 | `raw/index.json` v2: derived from acquisitions ⋈ inventory, keyed by `doc_id`; fetch `contract_ver=2`; convert/normalize readers adapted | ☐ | |
| P1.2 | `validate` Step 5 chain reconciliation (fetched ⊆ admitted; raw-index == fetched; converted == normalized == indexed-raw), findings by doc_id | ☐ | |
| P1.3 | DOCX magic check before CAS put; `bad_content` acquisition status | ☐ | |
| P1 ✓ | Live: 1,040 == 1,040 == 1,040 == 1,040; six doc_ids in `doc_meta_staged`; gate red on hand-broken seam | ☐ | group count shift from 615: ___ |
| **P2 — doctor into the DAG** | | | |
| P2.1 | Terminal `doctor` stage (`reports/doctor/doctor.json`, ALWAYS_RERUN, RED ⇒ fail); CLI aliased; `build` tail dropped | ☐ | |
| P2 ✓ | `vdocs run` ends at doctor GREEN; induced-defect lake exits non-zero | ☐ | |
| **P3 — retention gates** | | | |
| P3.1 | Relocated table words credited in `score_retention` | ☐ | low-retention 7 → ___ |
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

**Riders landed opportunistically** (out-of-scope register items that rode a phase): none yet.
