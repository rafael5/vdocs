# Search quality & scope integrity — implementation plan (Q1–Q4)

**Status: DRAFT · proposed 2026-08-02** · Tracker:
[`search-quality-and-scope-integrity-tracker.md`](search-quality-and-scope-integrity-tracker.md) ·
Source: register rows **R‑4, R‑12, R‑19** in
[`../reference/pipeline-adversarial-audit.md`](../reference/pipeline-adversarial-audit.md) + the
four genuine retrieval failures found in the P7 close-out run.

The P1–P7 remediation fixed **integrity** — nothing is silently lost, no gate is advisory, no record
lies. It did not touch **quality**: whether a person asking a question gets the answer. This plan is
about that, and it is ordered by *measured end-user impact per unit of cost*, not by register order.

---

## The measured starting point (production lake, 2026-08-02)

Corpus: 1,040 documents / 615 gold anchors, `corpus_content_hash 6dbec1f5…`, 57,895 chunks.
Instrument: `scripts/baseline_golden.py`, 25 golden queries (24 labeled), provenance-stamped.

| | |
|---|---|
| mean nDCG@10 (18 answerable queries) | **0.5305** |
| mean recall@10 | **0.588** |
| queries returning nothing relevant in top-10 | **4 of 18** |
| queries that *cannot* score — every judged section is out of corpus scope | **6** (R‑19) |

**Where the answers actually are.** 51 judged sections across the 18 answerable queries, by the rank
at which the current engine returns them:

| rank of the judged answer | count | share | what it means |
|---|---:|---:|---|
| **1–10** (the user sees it) | 26 | **51.0%** | working today |
| **11–25** | 9 | 17.6% | retrieved, ranked just too low |
| **26–100** | 3 | 5.9% | retrieved, ranked badly |
| **101–500** | 6 | 11.8% | barely retrieved |
| **>500 or absent** | 7 | 13.7% | not retrieved at all |

**This table is the whole cost/benefit argument.** 23.5% of correct answers are *already retrieved*
and merely ranked below the fold — reachable by re-ranking, which is cheap. 25.5% are effectively
unreachable by ranking and need either a different retrieval signal or corrected labels. Recall at
wider cutoffs: **@10 = 51.0%, @25 = 68.6%, @100 = 74.5%** — the curve flattens hard after 25, which
says the same thing: the near band is where the value is.

---

## Q1 — Re-judge the golden set (prerequisite, not a nicety)

**Why first, despite zero direct user impact.** Every later phase is measured with this instrument,
and it is currently untrustworthy in two directions:

1. **Scope rot (measured):** 6 of 24 labeled queries cite sections in XOBW/HWSC, KAAJEE, LEX and
   `XU/kdc1_0ig` — applications the admission gate excludes on `system_type` (*Integration
   middleware* / *Data patch*, not *VistA*). They score a structural 0.000 forever. Already
   *detected* (`unscoreable_queries` in the rollup) but not yet *resolved*.
2. **Label narrowness (measured, and it changes the diagnosis):** for `kids-install-build` the
   judged ideal is `XU/krn_8_0_tm/installation` — a section in a document whose title contains no
   "KIDS" — while the engine returns `XU/krn_8_0_sm_kids_ug/running-installations`, i.e. the actual
   *KIDS User Guide*. For `fileman-add-field` the engine returns `DI/scrn_tut/adding-ssn-field`
   (a tutorial on adding a field) and is scored 0. **Two of the four "retrieval failures" may be
   labelling failures.** Tuning ranking against these labels would tune the engine toward worse
   answers.

**Q1.1 — resolve the 6 unscoreable queries.** For each: either re-label to in-scope sections that
answer the same information need, or retire it with a recorded reason. Do **not** silently delete —
a retired query is evidence about scope.
**Q1.2 — re-judge the top-10 of all remaining queries** against the current corpus, adding
grade‑2/3 labels for genuinely-good answers the set currently scores 0 (the two named above are
known cases). Label by *reading the section*, per the lesson already recorded in the set's own notes.
**Q1.3 — make scope rot a gate, not a report.** `make check` (or the harness) fails when a golden
query is unscoreable, so the set cannot rot silently again. This is R‑19's real fix.

**Cost:** low-moderate — 25 queries × top-10 read. **Benefit:** none to users directly; **unlocks
every measurement in Q2–Q4.** *Measure of done:* `unscoreable_queries == 0`; every 0.000 remaining
is a defect the engine owns, verified by reading its top-10.

---

## Q2 — Harvest the near band (the cheapest real user win)

**The measurement:** 12 of 51 judged answers (23.5%) sit at ranks 11–100 — retrieved, unread.
Two of the four failing queries are near-misses at **rank 13** and **rank 14**, against a default
result count of **8** (`mcp.DEFAULT_K = 8`, `vdocs ask --k 8`).

Ordered cheapest-first; stop when the golden set stops improving:

**Q2.1 — raise the default result count** (`DEFAULT_K` 8 → 15–20, `ask --k` likewise). Near-zero
cost, no ranking change, and section-level recall goes **51.0% → 68.6% at k=25**. For the MCP/agent
path especially, more candidates is nearly free; for the human CLI path, keep the display tight.
**Q2.2 — BM25 field-weight sweep.** Weights are `doc_title 2.5 / title 2.0 / section_path 1.5 /
body 1.0` and have never been swept against the *production* corpus (the sweep that set them ran on
the dev lake — see `reports/README.md`). Grid-search on the golden set; adopt only a measured win.
**Q2.3 — de-duplicate competing siblings.** Measured side-effect of P6.1b: `VBECS/…/accept-orders-
cancel-a-pending-order-uc_61` (a `container`, now searchable) outranks its own leaf twin
`…/accept-orders-cancel-a-pending-order` (`ok`) for the same query. A container that merely
restates its child's heading should not displace the child. Quantify how widespread the twin
pattern is before choosing a fix.

**Cost:** low. **Benefit — the highest per unit cost in this plan:** a user asking a real question
gets the right section instead of nearly-the-right one. *Measure of done:* recall@10 up from
**0.588**; nDCG@10 up from **0.5305**; no query regresses (per-query check, not just the mean —
that lesson is already paid for).

---

## Q3 — Scope integrity: the front door (R‑4 + R‑19)

**Why after Q2 despite being a bigger *risk*:** it is **insurance, not improvement**. It prevents a
future loss; it does not answer a single question better today. But it is cheap and the exposure is
real and measured: `crawl` and `catalog` have **no `deep_gate` and no completeness floor** (grep:
zero gate machinery), while everything downstream of them is now gated. 102 documents (XOBW 23 +
KAAJEE 64 + LEX 15) left the admitted set at some point and **nothing reported it** — we found out
because a golden query broke.

**Q3.1 — crawl completeness floor.** A crawl returning materially fewer sections/documents than the
last good crawl fails instead of overwriting bronze (R‑4's "empty crawl overwrites bronze").
**Q3.2 — admitted-set baseline in `validate`.** The chain gate proves the five seams agree *with
each other*; add the missing axis — the admitted set's **composition** vs the prior run, findings by
`doc_id`. `validate` already does exactly this drop-check for sidecar counts; this is the same
mechanism applied to scope. A deliberate scope change is then a one-line registry acknowledgement,
not a silent 102-document disappearance.

**Cost:** low-moderate; both are variations on gates that already exist. **Benefit:** the corpus
cannot quietly shrink. *Measure of done:* a hand-shrunk crawl fixture reds; a hand-removed app reds
with the doc_ids named; the live lake stays green.

---

## Q4 — Decide the two dormant investments (measure, then commit or stop)

Both are **decisions**, not builds. Each currently consumes real resource and returns approximately
nothing, and either finishing or stopping them is better than the status quo.

**Q4.1 — the SKL (R‑12).** Measured in production: the query-expansion map that `search` actually
uses holds **one entry** (`200` → `NEW PERSON`); `index.db:entity_skl` has **6** rows; `knowledge.db`
has 21 entities, 483 terms, 111 relationships; 4,415 proposals sit uncurated. The one entry it does
have is worth something (`fileman-file-200-new-person` scored 0.131 → 0.417). **Measure the
headroom first**: how many golden queries — and how much of the corpus — exhibit the number↔name
mismatch the SKL exists to bridge? Then either curate the proposals into real reach, or stop
describing the SKL as a search capability.

**Q4.2 — `discover` (tenet #13's other half).** Per full build it proposes **34,822** phrases,
**23,885** boilerplate blocks and **18,011** glossary terms, against curated registries holding
**13**, **16** and **~0**. The proposal side runs every build; the curation side never runs. Either
build the curation loop (potentially a large normalize-quality win) or take `discover` off the
default path and run it on demand. Measure the value of a sample of proposals before choosing.

**Cost:** measurement first, then a decision that could go either way. **Benefit:** unknown by
construction — which is the point. *Measure of done:* a written ruling per item with the number
behind it.

---

## Ordering, and why it is not the register's order

| | phase | user impact | cost | why here |
|---|---|---|---|---|
| 1 | **Q1** re-judge | none directly | low-mod | everything downstream is measured with it, and it is currently wrong in two directions |
| 2 | **Q2** near band | **highest** | **low** | 23.5% of correct answers are already retrieved and unseen |
| 3 | **Q3** scope gates | none directly | low-mod | insurance against a measured, recurring loss class |
| 4 | **Q4** SKL / discover | unknown | measure first | stop paying for dormant capability, or finish it |

R‑15 (error-budget consumption) and R‑16 (classification golden sets) stay out of scope — real, but
neither changes what a user gets from a search today.

**House rules apply per step:** TDD, `make check` green before commit, `contract_ver` bump on any
produced-shape change, update `vdocs-design.md` in the same commit when a stage's behaviour changes,
tick the tracker per landed step. **And the rule this effort exists because of:** every claim of
improvement is measured on the production lake with a provenance-stamped report, compared per query
and not only in the mean.
