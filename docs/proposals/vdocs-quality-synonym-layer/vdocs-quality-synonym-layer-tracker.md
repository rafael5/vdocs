# vdocs-quality-synonym-layer — tracker

| Step | What lands | Status | Commit / notes |
|------|-----------|--------|----------------|
| SL.1 | Headroom measured: how often the number/name mismatch occurs, how many realistic questions it costs, and what fraction of the 4,415 candidates are sound | ✅ | [`sl1-findings.md`](sl1-findings.md) · `reports/sl1{a,b,c}-*.{md,json}` · **(a)** 233 files / 1,932 docs split · **(b)** 28 of 80 questions fail on vocabulary, the layer repairs **3**, ceiling 23 · **(c)** the queue is **307** rows not 4,415 (that is a mention count), 94% structurally inert, approving all of it adds **1** equivalence |
| SL.2 | **Ruling** — finish it or stop claiming it, with the SL.1 numbers stated in the ruling | ✅ | **STOP** — [proposal §10](vdocs-quality-synonym-layer.md#10-ruling-sl2). (a) and (b) hold; (c) fails decisively, so SL.3a's deliverable is worth one equivalence. Amends SL.3b's retirement scope with the measured cost (33 s of an ~18-min rebuild vs a breaking read-contract change) |
| SL.3a | *(if finish)* Bulk approval path; expected gain stated before building, measured after | ⛔ n/a | Not taken — approving the entire queue adds **1** equivalence |
| SL.3b | *(if stop)* Machinery off the default rebuild path; the one working equivalence retained; every surface claiming the capability corrected | ✅ | Claims corrected: corpus card recipe (`manifest` `contract_ver` 4→5 so it republishes), `search.skl_expansions` docstring, user guide, docs index, `skl-proposal`, `skl-implementation-plan` (S4/S5 ruled against), in-repo SKL memory, programme tracker, R‑12. `resolve` now reports `proposal_candidates` + `proposal_mentions` so a mention count can never read as a backlog again. **Machinery deliberately kept** — see the §10 scope amendment. The one equivalence is retained |
| SL ✓ | A ruling exists with its numbers, and the system's claims match what it does | ✅ | 2026-08-04 |

Proposal: [`vdocs-quality-synonym-layer.md`](vdocs-quality-synonym-layer.md) ·
Plan: [`vdocs-quality-synonym-layer-implementation-plan.md`](vdocs-quality-synonym-layer-implementation-plan.md) ·
Prompts: [`prompts/`](prompts/)

⛔ **Prerequisites: [`vdocs-quality-crawl-integrity`](../vdocs-quality-crawl-integrity/) `CI ✓` and [`vdocs-quality-report-card`](../vdocs-quality-report-card/) `RC ✓`, in that order** (revised 2026-08-03). Status: `CI ✓` and `RC ✓` both ticked 2026-08-03 — prerequisites met; programme order runs `response-ranking` first. Scope decides what the collection contains; every measurement here is then taken with the answer key, which currently fails search for returning better answers than it names.
📏 **Measure before you act:** the first step below is a measurement, and no code, configuration, curation or gate lands until it is complete and written down.

**This effort is a decision, not a build.** SL.1 (measurement) and SL.2 (the ruling) are mandatory; exactly one of SL.3a/SL.3b follows.

## Baseline (2026-08-02, production collection)

| | |
|---|---|
| equivalences search actually uses | **1** (`200` → `NEW PERSON`) |
| entity records reaching the search index | **6** |
| knowledge store: entities / terms / relationships | 21 / 483 / 111 |
| ~~candidates awaiting approval~~ | ~~**4,415**~~ → **307** (the 4,415 was a mention count — SL.1c) |
| measured effect of the one live equivalence | `fileman-file-200-new-person` **0.131 → 0.417** |

## Notes carried in

- **A wrong equivalence is worse than none** — it merges two things a reader needs kept apart. No
  unreviewed candidate reaches the surface under either ruling.
- **Stratify the sample.** 4,415 candidates are not uniform; easy ones are probably right and hard
  ones probably wrong, so a flat sample will flatter the result.
- **"Stop" is a legitimate outcome.** A capability that delivers one synonym is already failing;
  naming that is the improvement, not an admission.
- **Do not reopen vector search.** This is a curated vocabulary map; the embedding path was
  evaluated and rejected for this collection.
