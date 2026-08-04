# vdocs-quality-response-ranking — tracker

| Step | What lands | Status | Commit / notes |
|------|-----------|--------|----------------|
| RR.0 | **Measure first** — re-baseline on the production collection after the report card lands; record the report and confirm its provenance stamp | ☐ | |
| RR.1 | Default result count raised for the assistant path (8 → 15–20); human CLI display kept tight | ☐ | |
| RR.2 | Relevance field weights re-swept on the **production** collection; only a measured win adopted | ☐ | |
| RR.3 | Parent headings stop displacing the children that hold the content | ☐ | |
| RR ✓ | recall@10 > 0.588 and nDCG@10 > 0.5305, **no question regresses** | ☐ | |

Proposal: [`vdocs-quality-response-ranking.md`](vdocs-quality-response-ranking.md) ·
Plan: [`vdocs-quality-response-ranking-implementation-plan.md`](vdocs-quality-response-ranking-implementation-plan.md) ·
Prompts: [`prompts/`](prompts/)

⛔ **Prerequisites: [`vdocs-quality-crawl-integrity`](../vdocs-quality-crawl-integrity/) `CI ✓` and [`vdocs-quality-report-card`](../vdocs-quality-report-card/) `RC ✓`, in that order** (revised 2026-08-03). Status: `CI ✓` ticked 2026-08-03 (`801f48c`); `RC ✓` still open, so this effort stays blocked. Scope decides what the collection contains; every measurement here is then taken with the answer key, which currently fails search for returning better answers than it names.
📏 **Measure before you act:** the first step below is a measurement, and no code, configuration, curation or gate lands until it is complete and written down.

Tuning against an unrepaired key would optimise search toward measurably worse answers — that is the specific risk this ordering exists to prevent.

## Baseline (2026-08-02, `corpus_content_hash 6dbec1f5…`, 1,040 documents / 57,895 passages)

| | |
|---|---|
| nDCG@10 (18 answerable questions) | **0.5305** |
| recall@10 | **0.588** |
| correct answers in positions 1–10 | 26 of 51 (**51.0%**) |
| …in 11–25 | 9 (17.6%) |
| …in 26–100 | 3 (5.9%) |
| …in 101–500 | 6 (11.8%) |
| …beyond 500 or not returned | 7 (13.7%) |
| share visible at list length 10 / 25 / 100 | **51.0% / 68.6% / 74.5%** |
| current defaults | `mcp.DEFAULT_K = 8`, `ask --k 8`, engine default 10 |
| current weights | doc title 2.5 · section title 2.0 · path 1.5 · body 1.0 (**fitted on the 451-doc dev collection**) |

Two of the four failing questions have their answer at **rank 13** (`rpc-broker-client-call`) and
**rank 14** (`vbecs-accept-order`).

## Notes carried in

- **Compare per question, never only the mean.** An earlier change looked flat on the average while
  two questions silently fell to 0.000, and a filtered estimate of the same change was right in
  aggregate and wrong in every particular.
- **Both sides of a comparison must share `corpus_content_hash` *and* passage count.** The hash
  identifies the document set, not the index build — two indexes with different chunking carry the
  same hash (measured: 48,769 vs 57,895 passages, one hash).
- **Measured twin case to start from:** `VBECS/…/accept-orders-cancel-a-pending-order-uc_61`
  (parent) outranks `…/accept-orders-cancel-a-pending-order` (child) for the same query.
