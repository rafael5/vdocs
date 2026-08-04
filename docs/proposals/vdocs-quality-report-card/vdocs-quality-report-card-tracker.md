# vdocs-quality-report-card — tracker

| Step | What lands | Status | Commit / notes |
|------|-----------|--------|----------------|
| RC.1 | The six impossible questions resolved — **operator ruled 2026-08-03: retire all six with recorded reasons (XOBW/KAAJEE/LEX stay excluded) and author six replacement questions, each gated on documents that exist in the fetched corpus** | ✅ | Six retired to the key's `retired:` block, reasons recorded; six replacements authored (kids-backup-transport-global · hl7-start-tcpip-link · fileman-file-access-security · vista-signon-credentials · fileman-finder-api · taskman-monitor), every label verified present+latest+searchable **with non-zero chunk text** in production before writing, graded by reading. Bonus: 2 dead XOBW labels stripped from `kids-install-build` (same artefact inside an answerable query). **Corrections:** `XU/kdc1_0ig` is excluded by **doctype-policy IG-omit**, NOT system_type (R‑19/kickoff wrong there); post-CI lake hash is `726d22a4…` (≠ baseline `6dbec1f5…`, metadata-only change — **0 per-query drift** across the 17 untouched queries, so 0.5305 stays comparable). Harness: `unscoreable_queries == 0`, 24 labelled, interim nDCG@10 0.5383 (`reports/rc1-key-repair.*`). |
| RC.2 | Answer key re-judged against the current collection; grades added for good answers currently scored zero | ☐ | |
| RC.3 | An unanswerable question **fails** the harness instead of scoring zero | ☐ | |
| RC ✓ | `unscoreable_queries == 0`; every remaining zero attributed to search or to the key, in writing | ☐ | |

Proposal: [`vdocs-quality-report-card.md`](vdocs-quality-report-card.md) ·
Plan: [`vdocs-quality-report-card-implementation-plan.md`](vdocs-quality-report-card-implementation-plan.md) ·
Prompts: [`prompts/`](prompts/)

🥈 **Runs second, after [`vdocs-quality-crawl-integrity`](../vdocs-quality-crawl-integrity/) is ticked `CI ✓`** (ordering revised 2026-08-03: the six impossible questions are a scope artefact, and RC.1's retire/re-point decision depends on the scope ruling). Every later effort waits on this tracker's `RC ✓`.
📏 **Measure before you act:** RC.1 begins by *confirming* the six questions are out of scope rather than lost — those look identical from the key's side and mean opposite things.

Update **per landed step** (judge → `make check` → commit → tick). A step is DONE only when its measure is demonstrated on the production collection with a provenance-stamped report.

## Baseline (2026-08-02, `corpus_content_hash 6dbec1f5…`, 1,040 documents)

| | |
|---|---|
| labelled questions | 24 of 25 |
| unanswerable (every marked answer outside the collection) | **6** |
| published score with them included / excluded | 0.3979 / **0.5305** |
| questions scoring zero for other reasons | **4** |
| …suspected to be key defects rather than search defects | ≥ 2 |

The six: `kids-delphi-components-install`, `hwsc-rest-from-vista-m`, `hwsc-install-privileges`,
`kaajee-install-procedure`, `lexicon-lookup`, `hwsc-web-service-manager`.

The four: `kids-install-build`, `fileman-add-field`, `rpc-broker-client-call`,
`vbecs-accept-order`.

## Notes carried in

- **Judge by reading the passage, never the title.** The key already contains one label that was
  assigned from a title and was wrong when finally read (`MPIF/…/yesno-indicator-table`, graded 1,
  corrected to 3). The correction *lowered* the reported score, which is the kind worth trusting.
- **Retiring a question is a scope statement.** It says the collection deliberately does not cover
  something. Record the reason; do not delete silently.
- **Do not change search during this effort** — it would contaminate the before/after the ranking
  effort depends on.
