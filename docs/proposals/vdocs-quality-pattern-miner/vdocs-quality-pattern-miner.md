# vdocs-quality-pattern-miner — 77,000 suggestions, 29 accepted

**Status: DRAFT · proposed 2026-08-03** ·
Plan: [`vdocs-quality-pattern-miner-implementation-plan.md`](vdocs-quality-pattern-miner-implementation-plan.md) ·
Tracker: [`vdocs-quality-pattern-miner-tracker.md`](vdocs-quality-pattern-miner-tracker.md) ·
Prompts: [`prompts/`](prompts/)

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

VA manuals are full of repeated furniture: legal notices, revision tables, "this page intentionally
left blank", navigation links, headers and footers that appear on every page of every document. None
of it answers anybody's question, and all of it dilutes the passages that do.

The system has a design principle for this: **recurring patterns are data, not code.** Rather than
hard-coding a list of things to strip, a mining step reads the whole collection, notices what repeats,
and *proposes* patterns — boilerplate to remove, glossary terms to collect, recurring structures to
recognise. A human then approves the ones that are genuinely furniture, and the cleanup step applies
only what was approved. The principle is sound: it keeps judgement in a reviewable file instead of
buried in code.

**The proposing half runs. The approving half never has.**

Every full rebuild, the miner scans the collection and produces roughly **77,000** proposals. The
curated files it feeds hold **29** entries in total. The suggestions are generated, written down,
and discarded, and it happens again next rebuild.

## 2. What this costs the end user

**Two costs, both modest and both real.**

*In what they read:* passages carry more furniture than they need to. A user who retrieves a section
gets the answer plus the surrounding legal notice and navigation links. It is a readability tax on
every result, not a correctness problem — the answer is there, just noisier. Cleaner passages would
also improve keyword matching slightly, because repeated boilerplate is text that matches queries
without meaning anything.

*In how long a rebuild takes:* the mining step costs **4 minutes 41 seconds** of a roughly 26-minute
full rebuild — about **18%**, the second most expensive stage after document conversion. That is time
spent producing suggestions nobody reads.

**Neither cost is dramatic, and that is exactly why this is last of the five.** No user is blocked by
it. But the current state — paying 18% of every rebuild to generate 77,000 suggestions and act on
29 — is not a defensible steady state in either direction. Either the suggestions are worth
something, in which case we are leaving a readability improvement unclaimed, or they are not, in
which case we are paying for nothing on every rebuild.

## 3. What we measured

Full forced rebuild of the production collection, 2026-08-02 (1,040 documents):

| what the miner proposes, per rebuild | count |
|---|---:|
| phrases (dead text to remove) | **34,822** |
| boilerplate blocks | **23,885** |
| glossary terms | **18,011** |
| scaffold blocks | 4,709 |
| document templates | 36 |
| structures | 9 |
| **total** | **~81,500** |

| what is actually curated and applied | count |
|---|---:|
| curated phrases | **13** |
| curated boilerplate | **16** |
| curated structures | **7** |
| curated glossary | **~0** |

| cost | |
|---|---|
| mining step, full rebuild | **4m41s** |
| full rebuild, all stages | ~26m |
| share of rebuild spent mining | **~18%** |

For context on what curation *does* achieve when it happens: the 16 curated boilerplate patterns
matched **1,014** times across the collection, and 89 shared boilerplate blocks are single-sourced
as a result. So the mechanism works — the ratio between proposed and approved is the issue.

## 4. Proposal — a measurement, then a decision

As with the synonym layer, this proposal commits to a **ruling**, not to a build.

**4.1 Sample what the proposals are worth.** Take a stratified sample across the three large
categories (phrases, boilerplate, glossary) and judge each: genuine furniture, genuine content
(would be harmful to strip), or noise. Estimate from the sample how much text would be removed if
the good ones were approved, and what fraction of a typical retrieved passage that represents.

**4.2 Rule, with the numbers.** Either:

- **Build the curation loop** — a review path that lets a human approve patterns in bulk with
  spot-checks, so the miner's output reaches the collection; or
- **Take the miner off the default rebuild path** — keep it runnable on demand for when someone
  actually intends to curate, and recover ~18% of every rebuild.

**4.3 Whichever is ruled, stop the silent waste.** The status quo — generating and discarding —
should not survive this effort in either direction.

## 5. What we are deliberately not doing

- **Not hard-coding the patterns.** "Discovery is data, not code" is a deliberate architectural
  choice and this proposal does not challenge it. The question is whether the data ever gets
  reviewed, not whether it should be data.
- **Not auto-approving.** Stripping text automatically on a frequency heuristic is how documents get
  silently gutted. This collection has already had one incident where content was deleted with no
  record; nothing here reintroduces that risk.
- **Not deleting the miner.** Even if it comes off the default path, the code and its output remain
  available — the judgement being made is about *when it runs*, not whether it exists.

## 6. Cost and benefit

**Cost of the measurement:** low — sampling and judging, no pipeline change.
**Cost of building curation:** moderate, and mostly the review mechanism rather than the pipeline.
**Cost of removing from the default path:** near zero, and it *returns* ~4m41s per rebuild.

**Benefit:** the smallest of the five in user-visible terms — cleaner passages, marginally better
matching. Its honest value is removing an ongoing, unexamined cost and settling a question that has
been open since the mining step was written.

**Why last:** nobody is blocked by it, and both possible rulings are cheap. It is the right thing to
do after the efforts that change what a user actually gets.

## 7. Acceptance

- A written ruling — *build curation* or *off the default path* — with the sample numbers in it.
- If **build**: a review path exists, some patterns are actually approved, and the effect on
  retrieved-passage cleanliness is measured rather than asserted.
- If **off the default path**: rebuild time recovered is stated, the miner still runs on demand, and
  no documentation implies the collection is being continuously cleaned when it is not.
- Either way: no document loses content without a record — the existing capture-before-strip
  guarantee is untouched.

## 8. Risks

- **Stripping real content.** The single largest risk, and it has precedent here: a previous strip
  removed page-numbered table-of-contents entries with no record at all, and only an unexplained
  content-loss score revealed it. Mitigation: nothing is approved without being read, and the
  capture-before-strip rule stays absolute.
- **Sample bias.** The most frequent patterns are the most obviously furniture; a frequency-ordered
  sample will look better than the population. Mitigation: stratify, and judge the low-frequency
  stratum honestly.
- **Deciding nothing.** The genuine failure mode for this effort is a third rebuild-and-discard
  cycle while the ruling stays "later". Mitigation: 4.3 — the status quo is explicitly not an
  acceptable outcome.

## 9. References

**Findings and evidence**
- Programme rationale and ordering —
  [`../search-quality-and-scope-integrity-implementation-plan.md`](../search-quality-and-scope-integrity-implementation-plan.md)
- Stage timings and proposal counts: the P7 acceptance run recorded in
  [`../../historical/pipeline-audit-remediation-tracker.md`](../../historical/pipeline-audit-remediation-tracker.md)
  (P7.1 row)

**The mechanism**
- The mining stage: `src/vdocs/stages/discover/`
- The curated files it feeds: `registries/phrases`, `registries/boilerplate`, `registries/glossary`,
  `registries/structures`
- Where approved patterns are applied: `src/vdocs/stages/normalize/normalize_pure.py`
  (`subtract_phrases` and the boilerplate single-sourcing)
- The design principle: "discovery is data, not code" (tenet #13) in
  [`../../vdocs-design.md`](../../vdocs-design.md)

**Precedent for the stripping risk**
- [`../../session-summaries/2026-08-01-pipeline-audit-and-p1.md`](../../session-summaries/2026-08-01-pipeline-audit-and-p1.md)
  and the P3 rows in
  [`../../historical/pipeline-audit-remediation-tracker.md`](../../historical/pipeline-audit-remediation-tracker.md)
  — content deleted with no record, found only via an unexplained retention score
