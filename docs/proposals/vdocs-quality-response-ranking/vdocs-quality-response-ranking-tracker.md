# vdocs-quality-response-ranking — tracker

| Step | What lands | Status | Commit / notes |
|------|-----------|--------|----------------|
| RR.0 | **Measure first** — re-baseline on the production collection after the report card lands; record the report and confirm its provenance stamp | ✅ | `reports/rr0-baseline.*` — nDCG@10 **0.6386** · MRR 0.7535 · recall@10 **0.7134**, `corpus_content_hash 726d22a4…`, 1,040 docs / 57,895 chunks, 24 labelled / 0 unscoreable. Byte-for-byte identical to the RC close-out run (`rc-final-baseline.*`), rollup **and** every per-query score — so the harness is deterministic and this baseline is reproducible, not a one-off draw. |
| RR.1 | Default result count raised for the assistant path (8 → 15–20); human CLI display kept tight | ✅ | **15, chosen by measurement not taste** — visible share of the 109 judged answers: 61.5% @8 · 69.7% @10 · **77.1% @15** · 78.0% @20 · 79.8% @25, so 15 is the knee and 20 buys +0.9pt. Two constants in `server/search.py` (`ASSISTANT_DEFAULT_K = 15`, `HUMAN_DISPLAY_K = 8`), both assistant surfaces bound to the first (`mcp.DEFAULT_K` re-exports it; `ask --json` uses it, the terminal keeps 8, explicit `--k` wins on either). Measured effect at the default: **67/109 → 83/109 visible (61.5% → 76.1%)** across 11 queries; `reports/rr1-after-default-k.*` confirms **zero** per-query nDCG@10 change — this step moves what a caller *sees*, never the ranking, so the harness at fixed k=10 correctly reports it as flat. ⚠️ Found a third assistant surface still advertising the old default: the published corpus card's query recipe (`--k 8`). Fixed, and the doctor's card-staleness check **widened from the usage rule to the recipe** so the next drift reds instead of shipping — it caught this one live (RED → `vdocs manifest` → GREEN 20/20). |
| RR.2 | Relevance field weights re-swept on the **production** collection; only a measured win adopted | ✅ **NEGATIVE RESULT — weights UNCHANGED** | 120-point grid (`scripts/sweep_weights.py`, real engine via a `weights` override on `lexical_search`, metric math imported from the harness; shipped point inside the grid and it reproduces 0.6386 exactly). **Zero candidates beat the shipped weights without regressing a question.** Best mean (3.0/3.0/0.5) = 0.6693 (+0.031) but regresses **5** questions, worst −0.113. Nearest-to-clean (2.5/**3.0**/**1.0**) = 0.6563 (+0.018), 9 improved / **2 regressed**, worst −0.0045 — rejected: the no-regression rule was pre-registered *before* the data, and relaxing it after seeing a tempting row is the exact failure this rule exists to stop. Best-of-120 on 24 questions is also textbook overfitting; +0.018 is inside that selection noise. **Directional finding worth keeping:** `title` = 3.0 in 9 of the top 10 rows and `section_path` ≤ 1.0 in 9 of 10 — a consistent, explicable signal (section headings under-weighted, path over-weighted) that a larger key could confirm. Do not act on it at n=24. `reports/rr2-weight-sweep.*` |
| RR.3 | Parent headings stop displacing the children that hold the content | ✅ | **Measured first:** 784 title-twin parent/child pairs corpus-wide → 120 with a searchable parent under 300 chars whose child carries ≥3× more (VBECS 71, an artefact of "… UC_61" headings) → probing each with the child's own heading, **68 of 120 returned the parent ahead of the child** (child as low as rank 15 against a parent at 1). Cause: bm25 length normalisation makes a 118-char container restating its child's heading look like a dense perfect match. Fix `search_pure.demote_restating_parents` — a pure reorder, wired into `lexical_search` behind a 3× over-fetch window so the child can actually be promoted into view. It **excludes nothing** (a parent matching alone is still the answer) and fires only on all three conditions: direct parent, prefix-twin titles, parent text < 300 chars. **After: displacement 68 → 2 of 120.** Golden key: `vbecs-accept-order` 0.0509 → **0.1965** (+0.146), **zero** regressions, same hash/chunks. `reports/rr3-after-twin-demotion.*` ⚠️ **Reproducing the 784/120 counts:** a top-level parent has an *empty* `section_path`, so the parent key must be `(path + ' > ' + title).strip(' >')` on both sides — stripping whitespace only gives `"> Title"`, which no child matches. An independent recount that made exactly that mistake returned 486/109; the gap was precisely the 11 top-level parents. Documented in `search_pure` so a naive re-run does not read as a contradiction. |
| RR ✓ | recall@10 > **0.7134** and nDCG@10 > **0.6386** (the RR.0 baseline — the old 0.588/0.5305 targets were measured with the pre-RC key and are not comparable), **no question regresses** | ✅ | **Met: nDCG@10 0.6386 → 0.6447, recall@10 0.7134 → 0.7238, MRR unchanged 0.7535, zero questions regressed** (`reports/rr3-after-twin-demotion.*`, same `corpus_content_hash 726d22a4…` / 57,895 chunks as RR.0). Honest accounting of where the gain is: the *engine* moved on one question (RR.3, +0.146 on `vbecs-accept-order`); RR.1's much larger effect — 61.5% → 76.1% of judged answers visible at the default — is invisible to a harness pinned at k=10 by construction, and RR.2 correctly changed nothing. |

Proposal: [`vdocs-quality-response-ranking.md`](vdocs-quality-response-ranking.md) ·
Plan: [`vdocs-quality-response-ranking-implementation-plan.md`](vdocs-quality-response-ranking-implementation-plan.md) ·
Prompts: [`prompts/`](prompts/)

⛔ **Prerequisites: [`vdocs-quality-crawl-integrity`](../vdocs-quality-crawl-integrity/) `CI ✓` and [`vdocs-quality-report-card`](../vdocs-quality-report-card/) `RC ✓`, in that order** (revised 2026-08-03). Status: `CI ✓` ticked 2026-08-03 (`801f48c`) and `RC ✓` ticked 2026-08-03 — **this effort is UNBLOCKED**; the kickoff prompt carries the post-RC baseline (nDCG@10 0.6386) and sizing table. Scope decides what the collection contains; every measurement here is then taken with the answer key, which currently fails search for returning better answers than it names.
📏 **Measure before you act:** the first step below is a measurement, and no code, configuration, curation or gate lands until it is complete and written down.

Tuning against an unrepaired key would optimise search toward measurably worse answers — that is the specific risk this ordering exists to prevent.

## Baseline — RR.0, 2026-08-03 (`corpus_content_hash 726d22a4…`, 1,040 documents / 57,895 passages)

Measured on the **post-report-card key** (24 labelled questions, 109 judged answers, 0 unscoreable).
Report: `reports/rr0-baseline.*`.

| | |
|---|---|
| nDCG@10 | **0.6386** |
| MRR | **0.7535** |
| recall@10 | **0.7134** |
| correct answers in positions 1–10 | 76 of 109 (**69.7%**) |
| …in 11–25 | 11 (10.1%) |
| …in 26–100 | 7 (6.4%) |
| …in 101–500 | 7 (6.4%) |
| …beyond 500 or not returned | 8 (7.3%) |
| share visible at list length 10 / 25 / 100 | **69.7% / 79.8% / 86.2%** |
| current defaults | `mcp.DEFAULT_K = 8`, `ask --k 8`, engine default 10 |
| current weights | doc title 2.5 · section title 2.0 · path 1.5 · body 1.0 (**fitted on the 451-doc dev collection**) |

The near band this effort targets (ranks 11–100, retrieved but never shown) is **16.5%** of judged
answers. Search-owned failures inherited from RC.2, in full: `fileman-add-field` **0.000** (the only
zero — ScreenMan-tutorial lexical trap, the real answers rank below 10), `vbecs-accept-order`
**0.051** (parent/child twins — RR.3's case), `vista-signon-credentials` **0.175** (vocabulary gap).
No question's failure is the key's fault any more.

> ⚠️ **The pre-RC figures are a different ruler, not a worse score.** The superseded table read
> nDCG@10 0.5305 / recall 0.588 over *18 answerable* questions with 51.0% visible@10 and a 23.5%
> near band. Do not treat 0.5305 → 0.6386 as a search improvement (nothing in search changed), and
> do not compare any RR result against it.

## Notes carried in

- **Compare per question, never only the mean.** An earlier change looked flat on the average while
  two questions silently fell to 0.000, and a filtered estimate of the same change was right in
  aggregate and wrong in every particular.
- **Both sides of a comparison must share `corpus_content_hash` *and* passage count.** The hash
  identifies the document set, not the index build — two indexes with different chunking carry the
  same hash (measured: 48,769 vs 57,895 passages, one hash).
- **Measured twin case to start from:** `VBECS/…/accept-orders-cancel-a-pending-order-uc_61`
  (parent) outranks `…/accept-orders-cancel-a-pending-order` (child) for the same query.
- **The key is frozen for this effort.** RC.3 made the harness exit non-zero on an unscoreable
  question, so if a run reds, the key rotted — that is not licence to edit labels mid-effort, which
  would contaminate the before/after this whole effort rests on.
