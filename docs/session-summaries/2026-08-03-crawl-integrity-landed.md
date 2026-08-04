# Crawl integrity lands whole — and the gate that blocked it was a doc bug

*2026-08-03 (evening) · commits `d23f961` … `801f48c` · follows the quality-programme planning
session earlier the same day*

## Where this picked up

The session was asked to execute the **vdl-observatory** kickoff. Its gate said crawl-integrity
must land first — correct, and it hadn't. Redirected to the **crawl-integrity** kickoff, whose own
gate said *report-card* must land first. That contradicted the tracker sitting next to it ("runs
FIRST, reordered 2026-08-03"). Two kickoffs in a row walked into gates pointing in opposite
directions.

## The first fix was to the documents, not the code

The reorder commit (`16eb041`) had moved crawl-integrity to first and corrected the proposals — but
left the pre-reorder "report-card must be `RC ✓` first" blocks standing in the CI kickoff, both the
CI and RC implementation plans, the RC tracker ("prerequisite for the whole family"), and the three
downstream efforts' gates. The ruling's latest commit wins over the first gate one happens to read;
`d23f961` made all fourteen files agree, and expanded the CI plan from three steps to the five its
own tracker already listed.

## CI.0: measure first — and the draft's numbers were wrong again

The effort's own proposal claimed **1,604 active / 589 archive admitted**. Seven definitions were
tested against the live inventory and current registries; *none* reproduces those numbers. Computed
with the pipeline's own gate code and reconciled three ways (`select_fetch_targets`, `vdocs gate`,
`state.db` acquisitions), the truth:

- funnel: **8,907 → 3,770 genuine → 1,044 admitted targets → 1,040 fetched**
- by status: active **789 targets (111 apps)** / archive **255 (26 apps)** / decommissioned **0**
- "589 archived applications are already in the collection" was doubly wrong: **255 documents,
  26 applications**

The finding the numbers argued — archive partly admitted, decommissioned excluded outright, nobody
chose that — **survives**. The numbers themselves did not. Same lesson as the 102-document
correction that morning: having been burned once, the draft still carried an unmeasured claim as a
measured one. Corrected in the proposal, tracker, and both VO surfaces that inherited it.

## What landed (CI.1–CI.4, each TDD, each committed on a green gate)

- **CI.1, the completeness floor** (`1ce3103`): checked inside `run()` *before* the bronze write, so
  a red leaves the last good catalog byte-identical — the baseline *is* the artifact on disk, which
  is by construction the last crawl that passed. Two rules because the sections are skewed
  (Monograph: 2 docs; Infrastructure: 8.7%): a 90% total floor and per-section non-zero.
  `vdocs crawl --accept-shrink` is the cheap acknowledgement.
- **CI.2, master-set retention** (`bbbe043`): `build_raw_index` carries forward every prior entry
  the fresh derivation no longer produces (`retained` key). The non-obvious choice: retention keys
  off the **prior index**, not the acquisitions table — an entry is only ever created from a
  `fetched` acquisition, so the entry itself is the proof of fetch. That closed two loss paths
  nobody had noticed: a failed `--refetch` (status flips to `failed` while the CAS holds the bytes)
  and a wiped `state.db` both silently dropped documents before this. "Never ours" still leaves —
  R‑10's ghost-bundle rule is intact.
- **CI.3, lifecycle labels** (`3ad207b`): `app_status` / `decommission_date` / `cots_dependent` /
  `out_of_scope_reason` baked into gold FM and projected onto `v_documents`. Read contract
  **v1.5 → v1.6** (additive MINOR, capability `lifecycle_labels`); enrich cv 1→2, index cv 15→16.
  `out_of_scope_reason` turned out not to be "captured and unused" as claimed — it drives the DOCX
  invariant internally; it was merely never *surfaced*.
- **CI.4, the composition baseline** (`e2e6979`): fetch records the admitted set
  (`inventory/gold/admitted-baseline.json`) and its `deep_gate` reds on unacknowledged departures —
  by doc_id, **grouped by application**, because "ADT is no longer admitted (14 documents)" is a
  sentence an operator can act on. The baseline only advances on green, so the alarm repeats until
  answered; answering is one `{app_code, date, reason}` entry in the new
  `registries/inventory/scope-changes.yaml`. With CI.2 in place the red loses nothing.

## Proving it (`801f48c`)

On a **scratch copy** of the real lake (the live collection was never touched): a dead-VDL crawl
red named all five sections and left bronze byte-identical; denying `archive` in a scratch policy
red named the departed applications while all 1,040 documents stayed indexed (255 retained) and the
baseline stayed frozen; acknowledging the apps turned the same run green and advanced the baseline
1,044 → 789 — numbers that reconcile exactly with CI.0.

Then the live run: **16 stages GREEN, 0 warn, doctor 20/20 over 615 gold documents, validate 0
blocking, 57,895 chunks unchanged** (no retrieval regression). One planned one-time cost: the raw
index's new `retained` key changed its bytes, so convert re-ran all 1,040 documents (~15 min).
The lake now shows 785 active / 255 archive documents with 30 flagged commercially replaced,
contract v1.6, baseline 1,044 recorded.

## Left deliberately undecided — the operator's two scope rulings

Recorded in the CI tracker, not settled here:

1. **Admit the never-acquired 102 (XOBW 23 / KAAJEE 64 / LEX 15)?** Excluded by `system_type`; six
   golden questions cite them. **RC.1's retire-or-re-point decision depends on this ruling** — it
   should be made at report-card kickoff.
2. **Admit `decommissioned` applications?** All 124 records excluded while archive is partly
   admitted. Retention now protects what is fetched either way; widening admission is a product
   decision (`denied_app_status` in `scope-policy.yaml`, re-run from `serve-inventory`).

## Where this leaves the programme

Crawl-integrity is **complete** — the first of the six quality efforts. `vdocs-quality-report-card`
is unblocked and next (`docs/proposals/vdocs-quality-report-card/prompts/RC-kickoff.md`), ideally
opened with ruling 1 in hand. One known gap carried in the tracker: a CI.2-retained document whose
inventory record vanishes entirely keeps its last-enriched labels — enrich cannot re-join it; its
retained index entry is the record of that state.
