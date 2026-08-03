# vdocs-quality-response-ranking — show the answer we already found

**Status: DRAFT · proposed 2026-08-03** ·
Plan: [`vdocs-quality-response-ranking-implementation-plan.md`](vdocs-quality-response-ranking-implementation-plan.md) ·
Tracker: [`vdocs-quality-response-ranking-tracker.md`](vdocs-quality-response-ranking-tracker.md) ·
Prompts: [`prompts/`](prompts/) · **Depends on** `vdocs-quality-report-card`

> ## ⛔ Two standing rules before any work starts
>
> **1. Order: [`crawl-integrity`](../vdocs-quality-crawl-integrity/) → [`report-card`](../vdocs-quality-report-card/) → this effort.**
> Scope decides what the collection contains; the report card measures inside that boundary. Both must
> be settled before anything here is trusted — and the report card's own repairs depend on the scope
> ruling, so it cannot go first either. Do not start until `CI ✓` **and** `RC ✓` are ticked.
>
> **2. Measure before you act — in this effort too.**
> No code, configuration, curation or gate lands here until this effort's own measurement step is
> complete and written down. It is always the first step in the plan. A plan step is a hypothesis;
> this project has had five of them turn out wrong in ways only measuring caught.
## Contents

- [1. Background — in plain terms](#1-background--in-plain-terms)
- [2. What this costs the end user](#2-what-this-costs-the-end-user)
- [3. What we measured](#3-what-we-measured)
- [4. Proposal](#4-proposal)
- [5. What we are deliberately not doing](#5-what-we-are-deliberately-not-doing)
- [6. Cost and benefit](#6-cost-and-benefit)
- [7. Acceptance](#7-acceptance)
- [8. Risks](#8-risks)
- [9. References](#9-references)

## 1. Background — in plain terms

When someone asks vdocs a question, it returns a short ranked list of passages — by default the top
**eight**. The user reads those, and if the answer is not among them, they conclude the collection
does not have it.

We measured where the correct answers actually turn up. About **half** are in the top ten, where the
user sees them. But **roughly another quarter are found and then ranked somewhere between 11th and
100th** — retrieved successfully, and then shown to nobody.

Two of the four questions our own report card calls "failures" have their correct answer at position
**13** and position **14**. The system found the right passage and displayed eight other things.

This is not a search engine that cannot find things. It is a search engine that finds them and then
buries them just below where anyone looks.

## 2. What this costs the end user

This is the effort with the most direct user impact of the five, and the failure it causes is
specific and expensive.

A user searches, does not see the answer in the visible results, and reasonably concludes **"this
collection doesn't cover that."** What happens next is one of:

- they open a 400-page PDF and read it by hand — the exact work vdocs exists to remove;
- they report the documentation as missing, and someone else spends time discovering it was there;
- an AI assistant answers "not in the vdocs gold corpus" and the false negative is now in writing.

That last case is not hypothetical. Four researchers once retracted a report of "missing" FileMan
documentation that had been present the whole time. Every warning surface in the system now carries
a rule about it, because the cost of the false negative is so much higher than the cost of showing
one more result.

**After this effort, a user asking a question that vdocs can already answer sees the answer.** That
is the whole point.

## 3. What we measured

Production collection, 2026-08-02 (1,040 documents, `corpus_content_hash 6dbec1f5…`, 57,895
passages). 51 correct answers across the 18 answerable questions, by the position search returns
them at:

| position of the correct answer | count | share | what it means |
|---|---:|---:|---|
| **1–10** (the user sees it) | 26 | **51.0%** | working today |
| **11–25** | 9 | 17.6% | found, ranked just too low |
| **26–100** | 3 | 5.9% | found, ranked badly |
| **101–500** | 6 | 11.8% | barely found |
| **>500 or not returned** | 7 | 13.7% | genuinely not retrieved |

Share of correct answers a user would see at different list lengths: **10 → 51.0%, 25 → 68.6%,
100 → 74.5%.** The curve flattens hard after 25 — which says the value is concentrated in the near
band, not in the long tail.

Current defaults: `mcp.DEFAULT_K = 8`, `vdocs ask --k 8`, engine default 10.

Current relevance weighting: document title ×2.5, section title ×2.0, section path ×1.5, body ×1.0
— **set by a sweep on a 451-document development collection**, never validated against the 1,040-
document production one.

One measured side-effect of recent work: `VBECS/…/accept-orders-cancel-a-pending-order-uc_61` (a
parent heading, made searchable in P6.1b) now outranks its own child
`…/accept-orders-cancel-a-pending-order` for the same query. Parents can displace the children that
hold the real content.

## 4. Proposal

Three changes, cheapest first, each adopted only on a measured win.

**4.1 Show more results.** Raise the default list length (8 → 15–20) for the MCP/assistant path,
where more candidates cost almost nothing and the consumer filters them anyway. Keep the human CLI
display tight. This is a configuration change with no ranking risk and it moves the share of correct
answers a user sees from about a half to about two-thirds.

**4.2 Re-tune relevance weighting against the real collection.** Sweep the four field weights on the
production collection and adopt only what measurably wins. The current values were fitted to a
collection less than half the size; competition between documents is the thing that changed most.

**4.3 Stop parents displacing their children.** Quantify how common the parent/child twin pattern is,
then prevent a parent heading that merely restates its child from outranking it.

## 5. What we are deliberately not doing

- **No semantic or vector search.** That path was evaluated and rejected for this collection
  (cost, and a full re-embed on every document change). Nothing here reopens it.
- **No chunking changes.** The last one was the largest behavioural change in the programme and it is
  finished; mixing chunking with ranking would make both unmeasurable.
- **Not chasing the 25.5% that is genuinely not retrieved.** Some of it is the answer key's fault and
  is being fixed separately; the rest needs a different retrieval signal and is a later, bigger
  question. This effort harvests what is already found.

## 6. Cost and benefit

**Cost:** low. One configuration change, one parameter sweep, one bounded fix.

**Benefit:** the largest user-visible improvement available for the least work — up to **12 of 51**
correct answers (23.5%) move from invisible to visible. Nothing else in the quality programme has
that ratio.

**Why it is second rather than first:** it is measured with the answer key, and the key is currently
wrong in ways that would mislead the tuning. `vdocs-quality-report-card` must land first.

## 7. Acceptance

- Share of correct answers in the visible results (recall@10) up from **0.588**; ranking quality
  (nDCG@10) up from **0.5305**.
- **No question regresses** — compared per question, not only on the average. The average has hidden
  real regressions in this project before: an earlier change looked flat in the mean while two
  questions silently dropped to zero.
- Every number produced on the production collection with a provenance-stamped report, and both
  sides of any comparison sharing a `corpus_content_hash` **and** passage count.

## 8. Risks

- **Overfitting to 18 questions.** A weight sweep can find values that suit this key and nothing
  else. Mitigation: prefer small, explicable moves; treat a large gain on one question as a warning,
  not a win.
- **Longer lists shift work to the reader.** More results is not free for a human. Mitigation: widen
  the retrieved set for assistants, keep the human display short.
- **The near band may partly be label error.** Some of the 11–100 answers may be near-misses the key
  over-credits. The report-card effort lands first precisely so this is known before tuning.

## 9. References

**Findings and evidence**
- Programme rationale and ordering —
  [`../search-quality-and-scope-integrity-implementation-plan.md`](../search-quality-and-scope-integrity-implementation-plan.md)
- Register rows **R‑7** (chunk coverage, fixed) and **R‑19** (scope rot) —
  [`../../reference/pipeline-adversarial-audit.md`](../../reference/pipeline-adversarial-audit.md)
- Reports: `reports/p7-golden-final.*`, `reports/p6-golden-PROD-before-p61.*`, `reports/README.md`

**Code touched**
- `src/vdocs/server/search.py` (relevance weighting, the shared result envelope)
- `src/vdocs/server/mcp.py` (`DEFAULT_K`), `src/vdocs/cli/app.py` (`ask --k`)
- The answer key `registries/golden-queries.yaml` and harness `scripts/baseline_golden.py`

**Why the false negative is treated as the expensive failure**
- The not-indexed rule and its incident: `src/vdocs/server/search.py:NOT_INDEXED_RULE`
- [`../../session-summaries/2026-08-02-p6-searchable-is-not-kind.md`](../../session-summaries/2026-08-02-p6-searchable-is-not-kind.md)
  — coverage work that made 8,447 passages findable, and the measurement error that nearly hid it
