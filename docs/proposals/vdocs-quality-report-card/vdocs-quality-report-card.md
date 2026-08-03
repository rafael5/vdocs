# vdocs-quality-report-card — restore the instrument we grade search with

**Status: DRAFT · proposed 2026-08-03** ·
Plan: [`vdocs-quality-report-card-implementation-plan.md`](vdocs-quality-report-card-implementation-plan.md) ·
Tracker: [`vdocs-quality-report-card-tracker.md`](vdocs-quality-report-card-tracker.md) ·
Prompts: [`prompts/`](prompts/) · Register row: **R‑19**

## Contents

- [1. Background — in plain terms](#1-background--in-plain-terms)
- [2. What this costs the end user](#2-what-this-costs-the-end-user)
- [3. What we measured](#3-what-we-measured)
- [4. Proposal](#4-proposal)
- [5. What we are deliberately not doing](#5-what-we-are-deliberately-not-doing)
- [6. Cost, benefit, and why this goes first](#6-cost-benefit-and-why-this-goes-first)
- [7. Acceptance](#7-acceptance)
- [8. Risks](#8-risks)
- [9. References](#9-references)

## 1. Background — in plain terms

vdocs collects VA VistA manuals from a public website, cleans them up, and lets a person or an AI
assistant ask a question and get back the exact passage that answers it, with a citation.

To know whether that works, we keep an **answer key**: about 25 realistic questions, each with the
passages that correctly answer them marked by hand. Every time we change how search works, we re-run
those questions and compare. It is the only objective measure of whether search got better or worse.

**The answer key has gone stale, in two different ways.**

First, **six of its questions point at manuals the collection no longer carries.** Three product
areas were ruled out of scope some time ago — a deliberate, reasonable decision — but nobody went
back and updated the answer key. Those six questions are now marked wrong every single time, no
matter how well search performs. They cannot be passed.

Second, and more damaging: **for some questions the key names one "correct" passage while search is
returning an equally good or better one, and we score that as a failure.** In one case a user asks
how to install a software build; search returns the guide literally titled *KIDS User Guide*; we
mark it wrong because the key names a section in a different manual whose title does not even
contain the word "KIDS".

So the report card is failing search for finding good answers, and failing it for questions that
cannot be answered at all. Its grades are not measuring search quality.

## 2. What this costs the end user

**Directly: nothing.** This work changes no search result. A user would not notice it shipping.

**Indirectly: it is the difference between improving search and damaging it.** Every other quality
improvement we make is judged by this key. If we "improve" search by tuning it until the grades go
up, we will have tuned it to prefer the answers the stale key names — which, in at least two
measured cases, are *worse* answers than the ones search already finds. We would be paying to make
the user's experience worse and congratulating ourselves with a rising number.

There is also a reporting cost. The key's six impossible questions drag the published score down by
roughly **13 points**, so every summary of "how good is search" has been understating it. Decisions
about where to invest have been made against a number that was wrong in a knowable way.

## 3. What we measured

Production collection, 2026-08-02 (1,040 documents, `corpus_content_hash 6dbec1f5…`):

| | |
|---|---|
| labelled questions in the key | 24 (of 25 total) |
| questions where **every** marked answer is outside the collection | **6** |
| documents behind those six | XOBW 23, KAAJEE 64, LEX 15 (inventory), plus `XU/kdc1_0ig` |
| why they are outside | admission gate excludes them on `system_type` (*Integration middleware*, *Data patch* — not *VistA*) |
| effect on the published score | 0.5305 over the 18 answerable vs **0.3979** when the impossible six are included |
| questions scoring zero that are **not** explained by scope | 4 |
| …of those, cases where search's own answer looks defensible | at least **2** (`kids-install-build`, `fileman-add-field`) |

The six impossible questions: `kids-delphi-components-install`, `hwsc-rest-from-vista-m`,
`hwsc-install-privileges`, `kaajee-install-procedure`, `lexicon-lookup`,
`hwsc-web-service-manager`.

## 4. Proposal

**4.1 Resolve the six impossible questions.** For each, either re-point it at in-scope passages that
answer the same information need, or retire it with the reason recorded. Retiring is not deleting —
a retired question is evidence about what the collection deliberately does not cover.

**4.2 Re-judge the answer key against the current collection.** Read the top ten results for every
remaining question and add grades for genuinely good answers the key currently scores zero. Judge by
*reading the passage*, never by its title — the key's own notes already record that rule, and it was
broken once (a label assigned from a title alone turned out to be wrong when read).

**4.3 Make staleness impossible to ignore.** A question whose marked answers are all outside the
collection should **fail** the harness, not quietly score zero. Detection already ships (the harness
reports `unscoreable_queries`); this turns the report into a gate.

## 5. What we are deliberately not doing

- **Not expanding the key's size.** More questions is a separate, later question; a bigger broken key
  is worse than a small correct one.
- **Not re-judging beyond the top ten.** Ten is what a user sees; grading deeper invites us to
  optimise for positions nobody reads.
- **Not changing search itself.** Any ranking change made during this work would contaminate the
  before/after comparison that the next effort depends on.

## 6. Cost, benefit, and why this goes first

**Cost:** low-to-moderate, and almost entirely human judgement rather than engineering — 25
questions × ten results to read, plus a small gate.

**Benefit:** no direct user impact, and it still goes first, because it is a *prerequisite*. Both the
ranking effort and any future retrieval work are measured with this instrument. Fixing search while
holding a broken ruler is not a saving; it is a way to spend effort and not know what you bought.

## 7. Acceptance

- `unscoreable_queries == 0` on the production collection.
- Every question still scoring zero has been checked by reading its top ten, and is recorded as
  *search's fault* rather than *the key's fault* — with a one-line note saying which.
- A question whose answers all fall outside the collection fails the harness (proven by a test that
  reds).
- The corrected baseline is published with its provenance stamp, and becomes the number every later
  effort compares against.

## 8. Risks

- **Re-judging is a judgement call, not a measurement.** Two people can reasonably disagree about
  whether a tutorial section answers a developer's question. Mitigation: record the reason for each
  new or changed grade, so a later reader can disagree with the reasoning rather than guess at it.
- **Retiring questions narrows what the key claims to cover.** That is a scope decision and should be
  visible, not buried — hence "record the reason", and hence the operator sign-off in the plan.
- **Optimism bias.** We are grading our own system, and the temptation is to mark search's answers
  correct. Mitigation: grades are assigned by reading the passage against the question's stated
  information need, which is written down for each question and does not move.

## 9. References

**Findings and evidence**
- Register row **R‑19** (scope rot; the golden set rotted against corpus scope) —
  [`../../reference/pipeline-adversarial-audit.md`](../../reference/pipeline-adversarial-audit.md)
- Programme rationale and ordering —
  [`../search-quality-and-scope-integrity-implementation-plan.md`](../search-quality-and-scope-integrity-implementation-plan.md)
- Measured reports (provenance-stamped): `reports/p7-golden-final.*` (current),
  `reports/p6-golden-PROD-before-p61.*` (pre-P6 baseline), `reports/README.md` (how to read them)

**The instrument itself**
- The answer key: `registries/golden-queries.yaml`
- The harness: `scripts/baseline_golden.py` (records `index_db`, `documents`, `chunks`,
  `corpus_content_hash`, `unscoreable_queries`)

**Context on why the instrument is distrusted**
- [`../../session-summaries/2026-08-02-p6-searchable-is-not-kind.md`](../../session-summaries/2026-08-02-p6-searchable-is-not-kind.md)
  — the harness read a stale collection for three consecutive runs and agreed with itself
- [`../../session-summaries/2026-08-02-p7-close-out-and-the-arc.md`](../../session-summaries/2026-08-02-p7-close-out-and-the-arc.md)
  — the seven-phase arc and the six measurement mistakes that preceded this effort
