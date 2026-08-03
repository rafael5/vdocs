# Search quality & scope integrity — programme rollup

**SUPERSEDED as a step tracker (2026-08-03).** Work is tracked in five per-effort trackers; this
page is the rollup. Step rows below are retained as the record of how the programme was scoped.

| effort | tracker | status |
|---|---|---|
| 1. Report card | [`vdocs-quality-report-card-tracker.md`](vdocs-quality-report-card/vdocs-quality-report-card-tracker.md) | ☐ not started — **blocks 2** |
| 2. Response ranking | [`vdocs-quality-response-ranking-tracker.md`](vdocs-quality-response-ranking/vdocs-quality-response-ranking-tracker.md) | ☐ blocked on 1 |
| 3. Crawl integrity | [`vdocs-quality-crawl-integrity-tracker.md`](vdocs-quality-crawl-integrity/vdocs-quality-crawl-integrity-tracker.md) | ☐ independent — may run in parallel |
| 4. Synonym layer | [`vdocs-quality-synonym-layer-tracker.md`](vdocs-quality-synonym-layer/vdocs-quality-synonym-layer-tracker.md) | ☐ decision, not a build |
| 5. Pattern miner | [`vdocs-quality-pattern-miner-tracker.md`](vdocs-quality-pattern-miner/vdocs-quality-pattern-miner-tracker.md) | ☐ decision, not a build |

---

## Original scoping (retained)

Plan:
[`search-quality-and-scope-integrity-implementation-plan.md`](search-quality-and-scope-integrity-implementation-plan.md)
· Register rows: **R‑4, R‑12, R‑19** in
[`../reference/pipeline-adversarial-audit.md`](../reference/pipeline-adversarial-audit.md).
Update **per landed step** (TDD → `make check` → commit → tick). A step is DONE only when its
measure is demonstrated on the **production lake** with a provenance-stamped report — per query,
not only in the mean.

**Baseline (2026-08-02, `corpus_content_hash 6dbec1f5…`, 1,040 docs / 57,895 chunks):**
nDCG@10 **0.5305** · recall@10 **0.588** · 4 of 18 answerable queries return nothing relevant ·
6 queries unscoreable · judged answers by rank: **51.0%** in 1–10, **23.5%** in 11–100,
**25.5%** at >100 or absent · recall @10/@25/@100 = **51.0% / 68.6% / 74.5%**.
Reports: `reports/p7-golden-final.*` (after), `reports/p6-golden-PROD-before-p61.*` (pre-P6).

| Step | What lands | Status | Commit / notes |
|------|-----------|--------|----------------|
| **Q1 — re-judge the golden set (prerequisite)** | | | |
| Q1.1 | Resolve the 6 unscoreable queries — re-label to in-scope sections or retire with a reason | ☐ | The 6: `kids-delphi-components-install`, `hwsc-rest-from-vista-m`, `hwsc-install-privileges`, `kaajee-install-procedure`, `lexicon-lookup`, `hwsc-web-service-manager`. All cite XOBW (23 inventory docs) / KAAJEE (64) / LEX (15) / `XU/kdc1_0ig` — excluded by the admission gate on `system_type`. Retire ≠ delete: record that the app is out of scope. |
| Q1.2 | Re-judge the top-10 of the remaining queries; add grade‑2/3 for good answers currently scored 0 | ☐ | **Two known label defects, measured:** `kids-install-build` scores the *KIDS User Guide* (`XU/krn_8_0_sm_kids_ug/running-installations`) as 0 while its "ideal" is a section in a doc with no "KIDS" in the title; `fileman-add-field` scores `DI/scrn_tut/adding-ssn-field` as 0. Both engine answers look defensible. **Until this lands, "4 retrieval failures" is an upper bound — some of it is labelling.** |
| Q1.3 | Unscoreable golden query becomes a **gate**, not a report | ☐ | Detection already shipped (`unscoreable_queries` in the rollup, `9307075`). This makes it fail. R‑19's real fix. |
| Q1 ✓ | `unscoreable_queries == 0`; every remaining 0.000 verified by reading its top-10 | ☐ | |
| **Q2 — harvest the near band (highest impact per unit cost)** | | | |
| Q2.1 | Raise the default result count (`mcp.DEFAULT_K` 8 → 15–20; `ask --k` likewise) | ☐ | Section-level recall **51.0% @10 → 68.6% @25**. Two of the four failing queries have their answer at **rank 13** and **rank 14** against a default of **8**. Near-zero cost; no ranking change. Keep the human CLI display tight even if the retrieved set widens. |
| Q2.2 | BM25 field-weight sweep on the **production** corpus | ☐ | Current `doc_title 2.5 / title 2.0 / section_path 1.5 / body 1.0` were set by a sweep on the **dev lake** (see `reports/README.md`) — never validated at production scale. Adopt only a measured win, per query. |
| Q2.3 | Container/leaf twins stop competing | ☐ | Measured P6.1b side-effect: `VBECS/…/accept-orders-cancel-a-pending-order-uc_61` (`container`) outranks its own leaf twin `…/accept-orders-cancel-a-pending-order` (`ok`). Quantify the twin population before choosing a fix. |
| Q2 ✓ | recall@10 > 0.588 and nDCG@10 > 0.5305, **no query regresses** | ☐ | Per-query comparison mandatory — the mean hid two queries falling to 0.000 in P6. |
| **Q3 — scope integrity at the front door (R‑4 + R‑19)** | | | |
| Q3.1 | `crawl` completeness floor — a materially smaller crawl fails instead of overwriting bronze | ☐ | Verified 2026-08-02: `crawl` and `catalog` have **no `deep_gate`, no floor**. Everything downstream of them is gated; they are not. |
| Q3.2 | Admitted-set composition baseline in `validate`, findings by `doc_id` | ☐ | 102 documents left the admitted set with **zero** findings — discovered only because a golden query broke. `validate` already runs this exact drop-check for sidecar counts; apply it to scope. A deliberate scope change becomes a registry acknowledgement. |
| Q3 ✓ | Hand-shrunk crawl reds; hand-removed app reds naming doc_ids; live lake green | ☐ | |
| **Q4 — decide the dormant investments** | | | |
| Q4.1 | SKL headroom measured → curate or stop claiming it (R‑12) | ☐ | Production reach today: expansion map = **1 entry** (`200`→`NEW PERSON`), `entity_skl` = **6** rows, knowledge.db 21 entities / 483 terms / 111 relationships, **4,415 proposals uncurated**. The one entry is worth real points (`fileman-file-200-new-person` 0.131 → 0.417), which is the argument for measuring the rest. |
| Q4.2 | `discover` — build the curation loop or take it off the default path | ☐ | Per build it proposes **34,822** phrases / **23,885** boilerplate / **18,011** glossary terms against curated registries of **13** / **16** / **~0**. The proposal side runs every build; the curation side never runs. |
| Q4 ✓ | A written ruling per item, each with the number behind it | ☐ | |

**Out of scope (still open in the register):** R‑15 (per-doc error budget unconsumed), R‑16 (no
measured baseline for heuristic classification). Both real; neither changes what a user gets from a
search today.

**Deferred by direction (2026-08-02):** the documentation sweep — 9 broken relative links in live
docs, 44 more inside frozen `historical/` records, and no link gate. Docs hygiene is perpetual and
gets in the way of forward progress; it happens once the pipeline is complete and corrected.
