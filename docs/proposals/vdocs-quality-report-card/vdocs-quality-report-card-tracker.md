# vdocs-quality-report-card — tracker

| Step | What lands | Status | Commit / notes |
|------|-----------|--------|----------------|
| RC.1 | The six impossible questions resolved — **operator ruled 2026-08-03: retire all six with recorded reasons (XOBW/KAAJEE/LEX stay excluded) and author six replacement questions, each gated on documents that exist in the fetched corpus** | ✅ | Six retired to the key's `retired:` block, reasons recorded; six replacements authored (kids-backup-transport-global · hl7-start-tcpip-link · fileman-file-access-security · vista-signon-credentials · fileman-finder-api · taskman-monitor), every label verified present+latest+searchable **with non-zero chunk text** in production before writing, graded by reading. Bonus: 2 dead XOBW labels stripped from `kids-install-build` (same artefact inside an answerable query). **Corrections:** `XU/kdc1_0ig` is excluded by **doctype-policy IG-omit**, NOT system_type (R‑19/kickoff wrong there); post-CI lake hash is `726d22a4…` (≠ baseline `6dbec1f5…`, metadata-only change — **0 per-query drift** across the 17 untouched queries, so 0.5305 stays comparable). Harness: `unscoreable_queries == 0`, 24 labelled, interim nDCG@10 0.5383 (`reports/rc1-key-repair.*`). |
| RC.2 | Answer key re-judged against the current collection; grades added for good answers currently scored zero | ✅ | Top-10 of all 24 queries read and judged (~50 passages): 34 labels added, 2 downgraded — `kids-install-build` was the KEY's fault as suspected (the KIDS UG's own Running Installations was #1 graded 0 → g3; its two ORIGINAL Kernel-TM labels were about installing Kernel itself → 3/2→1) and so was `rpc-broker-client-call` (top-3 hits all answer); but `fileman-add-field`'s suspicion is REFUTED — the scrn_tut hits place fields on FORMS, not the DD; zeros correct, search-owned. PSO patch-manual near-dup triple graded equally (Q2.3 evidence). **Attribution: 1 remaining zero (`fileman-add-field`) + 2 low (`vbecs-accept-order` 0.05 container/leaf twins, `vista-signon-credentials` 0.17 vocabulary) — ALL search-owned; 0 key-owned.** nDCG@10 0.5383→**0.6386**, recall 0.713; 3 micro-dips are IDCG-denominator effects of honest labels (rankings identical). `reports/rc2-key-rejudged.*` |
| RC.3 | An unanswerable question **fails** the harness instead of scoring zero | ✅ | TDD: `tests/unit/test_baseline_golden_gate.py` (4 tests, real fixture index.db, no mocks) red→green; `gate_exit_code()` + `main()` exits 1 with a GOLDEN KEY: RED message, report still written first. Hand-staled fixture key reds; **live lake passes exit 0** (`reports/rc-final-baseline.*`). |
| RC ✓ | `unscoreable_queries == 0`; every remaining zero attributed to search or to the key, in writing | ✅ | **Published corrected baseline: nDCG@10 0.6386 · MRR 0.7535 · recall@10 0.7134** (24 labelled, 109 labels, hash `726d22a4…`, 57,895 chunks) — the number `response-ranking` compares against. Attribution in writing (RC.2 row + query notes): 1 zero + 2 low, all search-owned, 0 key-owned. RR-kickoff rewritten with the post-RC sizing table (69.7% visible@10; near band 16.5%). |

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
