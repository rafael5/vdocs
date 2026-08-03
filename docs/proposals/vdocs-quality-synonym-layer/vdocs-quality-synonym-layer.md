# vdocs-quality-synonym-layer — finish it or stop paying for it

**Status: DRAFT · proposed 2026-08-03** ·
Plan: [`vdocs-quality-synonym-layer-implementation-plan.md`](vdocs-quality-synonym-layer-implementation-plan.md) ·
Tracker: [`vdocs-quality-synonym-layer-tracker.md`](vdocs-quality-synonym-layer-tracker.md) ·
Prompts: [`prompts/`](prompts/) · Register row: **R‑12**

> ## ⛔ Two standing rules before any work starts
>
> **1. `vdocs-quality-report-card` comes first — for every effort in this family.**
> The answer key we grade search with is currently wrong in two directions: six questions cite
> applications the collection deliberately excludes and can never pass, and at least two fail search
> for returning a *better* answer than the key names. Until it is repaired, every measurement taken
> anywhere in this family can mislead — including the ones that would justify this effort's own
> decisions. Do not start this effort until that tracker's **RC ✓** row is ticked.
>
> **2. Measure before you act — in this effort too.**
> No code, configuration, curation or gate lands here until this effort's own measurement step is
> complete and written down. Every proposal in this family names that step explicitly, and it is
> always the first one. A plan step is a hypothesis; this project has had four of them turn out
> wrong in ways only measuring caught.

## Contents

- [1. Background — in plain terms](#1-background--in-plain-terms)
- [2. What this costs the end user](#2-what-this-costs-the-end-user)
- [3. What we measured](#3-what-we-measured)
- [4. Proposal — a measurement, then a decision](#4-proposal--a-measurement-then-a-decision)
- [5. What we are deliberately not doing](#5-what-we-are-deliberately-not-doing)
- [6. Cost and benefit](#6-cost-and-benefit)
- [7. Acceptance](#7-acceptance)
- [8. Risks](#8-risks)
- [9. References](#9-references)

## 1. Background — in plain terms

VistA documentation names the same thing two ways. One manual says **file 200**; another says
**NEW PERSON**; a third says `^VA(200,`. They are the same thing, and a reader who knows VistA knows
that. A keyword search does not.

So a user who asks *"what is file 200?"* gets documents that happen to contain the digits 200, while
the manuals that actually explain it — the ones that call it *NEW PERSON* throughout — do not
surface at all. The question is answerable; the vocabulary just does not line up.

We built a feature to fix this. It reads the collection, works out which numbers, names and global
variables refer to the same underlying thing, and teaches search to treat them as equivalent.

**In production it currently knows exactly one such equivalence** — `200` → `NEW PERSON`. There are
**4,415 candidate equivalences** sitting in a queue that nobody has approved. The machinery runs on
every rebuild; the approving step has essentially never run.

The one equivalence it does know is not a rounding error. On the question that needed it, it moved
the score from **0.131 to 0.417** — roughly tripling it. That single data point is the entire
argument for finding out what the other 4,414 are worth.

## 2. What this costs the end user

**The failure is silent and it looks like absence.** A user asks a question using the vocabulary of
one manual, and the manuals that answer it — written in the other vocabulary — never appear. There
is no error and no hint that a rephrasing would have worked. The user concludes the collection does
not cover the topic.

That is the same false-negative failure this project treats as its most expensive, arriving by a
different route: not "we never indexed the text", but "we indexed it under a name you did not use".

**Who it hits hardest:** exactly the audience vdocs is for. VistA's documentation is full of numeric
identifiers — file numbers, option names, routine names, global variables — and developers move
between the number and the name constantly. This is not an edge case in this corpus; it is the
corpus's native ambiguity.

**But we do not yet know how big it is.** One measured question improved dramatically. Whether that
generalises to hundreds of questions or to three is unmeasured — and that uncertainty is precisely
why this proposal's first step is a measurement rather than a build.

## 3. What we measured

Production collection, 2026-08-02:

| | |
|---|---|
| equivalences search actually uses | **1** (`200` → `NEW PERSON`) |
| entity records reaching the search index | **6** |
| entity records in the knowledge store | 21 |
| terms in the knowledge store | 483 |
| relationships in the knowledge store | 111 |
| candidate equivalences awaiting approval | **4,415** |
| measured effect of the one live equivalence | `fileman-file-200-new-person`: **0.131 → 0.417** |

So the pipeline that produces this knowledge runs and produces something; almost none of it reaches
the surface where a user's query would benefit. The gap is not the extraction — it is the approval
step between extraction and use.

## 4. Proposal — a measurement, then a decision

This proposal deliberately does **not** commit to building anything. It commits to finding out
whether the remaining 4,414 candidates are worth approving, and then to a written ruling either way.

**4.1 Measure the headroom.** Three questions, each answerable with the collection we already have:

1. **How often does the vocabulary mismatch occur?** Count the identifiers (file numbers, globals,
   option and routine names) that appear in the collection under two or more names, and how much text
   sits behind each.
2. **How many realistic questions does it affect?** The current answer key has one such question by
   construction. Sample real identifier-shaped questions against the collection and measure how many
   fail for vocabulary reasons alone.
3. **What is the quality of the waiting candidates?** Sample the 4,415 and judge what fraction are
   correct, wrong, or harmful if approved.

**4.2 Rule, and record the number behind the ruling.** Either:

- **Finish it** — build the approval path so candidates can be reviewed in bulk, with the expected
  gain stated up front and measured after; or
- **Stop claiming it** — keep the one working equivalence, take the unused machinery off the default
  rebuild path, and remove the capability from what we tell users and assistants the system can do.

Both outcomes are acceptable. What is not acceptable is the status quo: paying for the machinery on
every rebuild and describing a capability that delivers one synonym.

## 5. What we are deliberately not doing

- **Not approving 4,415 candidates by hand.** If the ruling is "finish it", the mechanism has to be
  bulk review with sampling and spot-checks, not an individual decision per row.
- **Not auto-approving.** A wrong equivalence actively damages search — it merges two things a
  reader needs kept apart. Whatever the ruling, unreviewed candidates do not reach the surface.
- **Not reopening semantic/vector search.** This is a curated vocabulary map, not embeddings; the
  vector path was evaluated and rejected for this collection.

## 6. Cost and benefit

**Cost of the measurement:** low — it reads data we already have.
**Cost of finishing (if ruled so):** unknown until measured; the review mechanism dominates.
**Cost of stopping:** near zero, and it *recovers* rebuild time and removes a false claim.

**Benefit:** unmeasured by construction, bounded below by one data point where the effect was large
(0.131 → 0.417 on the affected question). The value of this effort is that it converts an open-ended
"we have a semantic layer" into a number and a decision.

**Why fourth of five:** it is the higher-value of the two dormant investments — the corpus's native
number/name ambiguity is real and the one live equivalence performed well — but it sits behind the
efforts that improve results today.

## 7. Acceptance

- A written ruling — *finish* or *stop* — with the three measurements from 4.1 stated in it.
- If **finish**: the expected gain is stated before building, and measured after, on the answer key
  with a provenance-stamped report; no question regresses.
- If **stop**: the machinery comes off the default rebuild path, the one working equivalence is
  retained, and every user-facing surface that claims the capability is corrected.

## 8. Risks

- **A wrong equivalence is worse than none.** Merging two distinct concepts corrupts results for
  everyone who needed them separate. Mitigation: no unreviewed candidate reaches the surface, ever.
- **Sampling can flatter.** 4,415 candidates are not uniform; the easy ones are probably right and the
  hard ones probably wrong. Mitigation: stratify the sample, and judge the hard stratum honestly.
- **Sunk cost.** Real effort went into building this. The measurement must be allowed to conclude
  "stop" without that being read as a failure — a capability that delivers one synonym is already
  failing; naming it is the improvement.

## 9. References

**Findings and evidence**
- Register row **R‑12** (limited reach: entities reconciled, expansions nearly empty, proposals
  uncurated) — [`../../reference/pipeline-adversarial-audit.md`](../../reference/pipeline-adversarial-audit.md)
- Programme rationale and ordering —
  [`../search-quality-and-scope-integrity-implementation-plan.md`](../search-quality-and-scope-integrity-implementation-plan.md)

**The feature as built**
- Original design and phases: [`../skl-proposal.md`](../skl-proposal.md),
  [`../skl-implementation-plan.md`](../skl-implementation-plan.md)
- Code: `src/vdocs/stages/resolve/` (extraction), `src/vdocs/stages/merge/` (projection into the
  search index), `src/vdocs/server/search.py:skl_expansions` (what search actually consumes)
- Data: `knowledge.db` (entities, terms, relationships), `index.db:entity_skl` / `entity_synonyms`

**Measured effect of the single live equivalence**
- Question `fileman-file-200-new-person` in `registries/golden-queries.yaml`; reports
  `reports/p6-golden-PROD-before-p61.*` (0.131) and `reports/p7-golden-final.*` (0.417)
