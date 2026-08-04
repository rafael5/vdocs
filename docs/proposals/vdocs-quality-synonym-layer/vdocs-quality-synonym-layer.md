# vdocs-quality-synonym-layer — finish it or stop paying for it

**Status: RULED — *stop*, 2026-08-04** (§10; measurements in [`sl1-findings.md`](sl1-findings.md))
· proposed 2026-08-03 ·
Plan: [`vdocs-quality-synonym-layer-implementation-plan.md`](vdocs-quality-synonym-layer-implementation-plan.md) ·
Tracker: [`vdocs-quality-synonym-layer-tracker.md`](vdocs-quality-synonym-layer-tracker.md) ·
Prompts: [`prompts/`](prompts/) · Register row: **R‑12**

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
- [4. Proposal — a measurement, then a decision](#4-proposal--a-measurement-then-a-decision)
- [5. What we are deliberately not doing](#5-what-we-are-deliberately-not-doing)
- [6. Cost and benefit](#6-cost-and-benefit)
- [7. Acceptance](#7-acceptance)
- [8. Risks](#8-risks)
- [9. References](#9-references)
- [10. Ruling (SL.2)](#10-ruling-sl2)

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

> ⚠️ **The second sentence is wrong twice over, and §10 says so with numbers.** 4,415 is a count of
> *mentions*; the queue is **307** rows. And they are not candidate *equivalences* — 94% of them are
> unresolved mentions of routines, globals and namespaces, which the seed cannot represent at all.

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
| ~~candidate equivalences awaiting approval~~ | ~~**4,415**~~ — ⚠️ **wrong, corrected 2026-08-04 (§10):** that is `resolve`'s *mention* count. The reviewable queue is **307** rows, and they are unresolved mentions, not equivalences |
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

**The SL.1 measurements this proposal was written to obtain**
- [`sl1-findings.md`](sl1-findings.md); artifacts `reports/sl1a-ambiguity.*`,
  `reports/sl1b-vocab-cost.*`, `reports/sl1c-candidate-quality.*`; scripts `scripts/sl1_*.py`

## 10. Ruling (SL.2)

**Stop. Do not build the approval path.** Measured 2026-08-04 on the production lake (1,040
documents, 57,895 chunks), against `vista-meta`'s measured model rather than the feature's own seed:

| §4.1 question | measured |
|---|---|
| (a) How often does the vocabulary mismatch occur? | **233 FileMan files** are split across vocabularies; **1,932 file×document pairs** are reachable by the file-referring name and never by the number; 8,564 chunks sit behind them |
| (b) How many realistic questions does it affect? | **28 of 80** identifier-shaped questions fail for vocabulary reasons alone. The layer as built repairs **3** of them. The ceiling for *any* expansion is **23** |
| (c) What is the quality of the waiting candidates? | The queue is **307** candidates, not 4,415 (that figure is a mention count). **289 (94%)** are structurally inert. Approving the entire queue adds **one** equivalence — `405 → PATIENT MOVEMENT`, a file mentioned once, in one document |

The plan's rule is that *finish* requires all three: widespread, costly, and sound candidates. The
first two hold decisively. The third fails as decisively as it could — the deliverable SL.3a would
build, a bulk review path over the queue, is worth one equivalence for a file mentioned once. So the
ruling is SL.3b.

**The premise was right and the diagnosis was wrong.** §4 says "the gap is not the extraction — it is
the approval step between extraction and use." Measured, the gap is the **projection**. 24 of the 28
repairable failures are dropped by `search_pure.skl_expansion_map`'s own guards: two-digit file
numbers by `len(key) >= 3`, decimal file numbers by `.isalnum()` and, beneath that, by FTS5
tokenising `50.7` into `50` and `7` so a single-token key can never match. And 94% of the queue names
entity types the DD seed cannot represent at all. No amount of curation moves any of that.

### Scope amendment to SL.3b, with the number that forces it

SL.3b says to take the machinery off the default rebuild path. **Measured, that costs more than it
saves, so it is not done.** `resolve` runs in **2.0 s** and `merge` in **31.2 s** — 33 seconds of an
~18-minute rebuild, about 3%. Against that:

- `resolve` feeds two **working** consumers unrelated to equivalences: the 483-term termbase
  `build-termbase` projects, and the Entities section of `gold/glossary.md`.
- `merge`'s three tables are published in **read contract v1** (`v_entity_skl`, `v_entity_synonyms`,
  `v_chunk_entities`). Removing them is a breaking contract change, which ADR-0001's `contract-lint`
  refuses to ship as a MINOR.

Retiring the machinery would mean a breaking contract change to recover 3% of a rebuild. The plan
wrote that instruction before the cost was measured; the measurement supersedes it. **What is retired
is the claim, not the code.** The one working equivalence is retained, as SL.3b requires.

### Recorded, not started: the headroom a different build would reach

The ceiling measured in (b) is real — **23 of 80 questions**, against the 3 reachable today — and it
belongs to a differently-shaped effort than this one: widening the seed past the 21-file DI pilot,
and making the expansion key on two-digit and decimal file numbers (which needs multi-token key
matching in `fts_match_query`, not a loosened guard). Both are **out of this effort's scope** by its
own plan, and neither is started here. It is recorded so the number is not lost, and left for the
operator to schedule against the rest of the programme.

Two things it explicitly does **not** cover: prose synonymy — the `vista-signon-credentials` case
moves 0.1749 → 0.2772 when given the manual's vocabulary, but the SKL has no representation for a
prose synonym pair and never will without a different data model — and vector retrieval, which stays
rejected for this collection.
