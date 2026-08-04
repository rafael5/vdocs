# vdocs-quality-pattern-miner — 81,500 suggestions, 109 accepted

**Status: RULED · proposed 2026-08-03 · decided 2026-08-04 — [see §10](#10-ruling-2026-08-04)** ·
Plan: [`vdocs-quality-pattern-miner-implementation-plan.md`](vdocs-quality-pattern-miner-implementation-plan.md) ·
Tracker: [`vdocs-quality-pattern-miner-tracker.md`](vdocs-quality-pattern-miner-tracker.md) ·
Prompts: [`prompts/`](prompts/)

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
- [10. Ruling (2026-08-04)](#10-ruling-2026-08-04)

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

Every full rebuild, the miner scans the collection and produces roughly **81,500** proposals. The
curated files it feeds hold **109** entries in total. The suggestions are generated, written down,
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
it. But the current state — paying 18% of every rebuild to generate 81,500 suggestions and act on
109 — is not a defensible steady state in either direction. Either the suggestions are worth
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
| curated boilerplate | **89** |
| curated structures | **7** |
| curated glossary | **~0** |
| **total** | **109** |

| cost | |
|---|---|
| mining step, full rebuild | **4m41s** |
| full rebuild, all stages | ~26m |
| share of rebuild spent mining | **~18%** |

For context on what curation *does* achieve when it happens: the 89 curated boilerplate patterns
matched **1,014** times across the collection, single-sourcing one shared block each. So the
mechanism works — the ratio between proposed and approved is the issue.

> **Corrected 2026-08-04 (§10.3).** This section originally read "16 curated boilerplate" and a
> curated total of 29. The registry holds **89** entries; the total is **109**. The proposals are
> distinct patterns, not mentions — verified against `patterns.json`.

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

## 10. Ruling (2026-08-04)

**Ruled: take the miner off the default rebuild path** (PM.3b). It runs on demand, `vdocs discover`.

### 10.1 Why — the benefit side, measured

PM.1 judged a stratified sample of 198 proposals — 98 phrases, 50 boilerplate, 60 glossary — drawn
with a fixed seed across four frequency bands (≥100 documents / 30–99 / 10–29 / 3–9), and estimated
the text volume by matching each candidate's block identity against the **gold** bodies, which is
where a reader actually meets it.

| if every furniture proposal were approved | |
|---|---:|
| furniture patterns, estimated from the sample | **~149** of 58,707 phrase + boilerplate proposals |
| text that would leave gold | **~59 KB** of 81.6 MB |
| share of the corpus | **0.073%** |
| share of a median retrieved passage (975 chars) | **0.6 characters** |
| 95% upper bound (rule of three on the zero-furniture bands) | **1.26%** of gold — **~11 characters** |

Even the pessimistic bound is a rounding error in a retrieved passage. The cost is 4m41s of a
~26-minute rebuild — **18%** — to produce it, and the approving half was never going to happen at a
scale of 81,500.

### 10.2 What the sample actually found

**Frequency is a poor predictor of furniture, in both directions.** The proposal anticipated that a
frequency-ordered sample would flatter the population. It does worse than that — the *most* frequent
band is the *least* usable:

| phrases | ≥100 docs | 30–99 | 10–29 | 3–9 |
|---|---:|---:|---:|---:|
| population | 23 | 134 | 2,207 | **32,458** |
| furniture | 22% | 20% | 0% | 0% |
| genuine content | 9% | 52% | **92%** | **92%** |
| noise | 70% | 28% | 8% | 8% |
| *harmful if approved* | **16/23** | 6/25 | 1/25 | 1/25 |

The ≥100-document band is dominated by single characters (`A`, `C`, `M`, `R`, …), bare markdown
(`#`, `##`, `.`, `\|`) and `<!-- -->` — blocks split out of screen captures and tables. Approving
that band on frequency would be the destructive outcome, not the beneficial one. Below 30 documents
— 34,665 of the 34,822 phrase proposals — the candidates are transcript lines, VistA prompts, drug
names, and example output: **content**, and much of it is exactly the kind of text a user searches
for.

Boilerplate is cleaner (0 harmful in 50) but no more valuable: 3 of the 5 top-band candidates are
the genuine furniture — the title-17 copyright notice, the hyperlink-endorsement disclaimer, the
revision-page instructions — and **all three are already gone from gold**, removed by the 89 curated
boilerplate entries. The residue is content. In the 3–9 band, 15 of 15 were content.

**Two structural findings explain the gap:**

1. **Most of the "recurrence" is version duplication, not boilerplate.** `discover` mines the 1,040
   converted documents, which include every version of every manual; `consolidate` then folds those
   into 615 version groups. A block in 64 documents of the VS GUI family survives into **2** gold
   bodies. The proposal counts measure a corpus that the reader never sees.
2. **The glossary miner is answered elsewhere.** Its 18,011 terms remove no text at all (disposition
   PROMOTE). Of the sample, ~18% are promotable terms, ~25% are M **routine names** already carried
   properly by the SKL entity layer, and the rest is noise — ordinary uppercase words lifted out of
   screen captures (`LIMIT`, `VERIFY`, `PROFILE`, `ACTION`, `AUG`).

### 10.3 Corrections to this proposal's own baseline

- **The curated total is 109, not 29** — 13 phrases + **89** boilerplate + 7 structures. §3's "16
  curated boilerplate" conflated the registry with something else; the 89 shared blocks in
  `gold/_shared/boilerplate/` are one per registry entry, and the 1,014 matches are REFERENCE
  insertions across 1,040 documents. The proposed:approved ratio is ~750:1, not ~2,800:1. It does
  not change the ruling.
- **The proposal counts are distinct patterns, not mentions** — verified against
  `reports/patterns/patterns.json` (34,822 / 23,885 / 18,011 unique keys). The mentions-vs-candidates
  trap that inflated the synonym layer's queue does not apply here.
- **`registries/templates` is curated (30 KB) and stamps nothing** — the last normalize run reports
  `templates_stamped: 0`. Out of scope here; recorded so it is not mistaken for a working loop.

### 10.4 What changed

`Stage.on_demand` — a generic orchestrator selection flag, not a special case for one stage. An
on-demand stage stays a registered DAG node (so the topological order and `--only` are unchanged)
but is excluded from every range selection, including the full `crawl → doctor` build. `discover`
sets it.

- **Recovered:** 4m41s of a ~26-minute rebuild, ~18%.
- **Still available:** `vdocs discover --force` rewrites `reports/patterns/patterns.json`.
- **Unchanged:** `normalize` subtracts the curated `registries/` on every build exactly as before.
  Nothing was approved, nothing was stripped, and capture-before-strip is untouched — this ruling
  removes a cost, it does not touch any document.
- **Documentation corrected** where it implied continuous cleaning: `docs/de-novo-run.md` §2 and
  design §9.6 steps 2 and 4. Design §9.6's "high-frequency candidates auto-approve" was also struck
  — no code ever implemented it, and PM.1 measured it to be the wrong rule.

### 10.5 Reproducing the numbers

`reports/patterns/patterns.json` (the 2026-08-02 forced rebuild, 1,040 documents) against the gold
bodies under `$DATA_DIR/documents/gold/consolidated`. Judge candidates by block identity
(`discover_pure.block_key` over `split_blocks`), stratify by `doc_count`, and weight each band's
sampled furniture fraction by its population. Index ruler: `corpus_content_hash 726d22a4…`, 57,895
chunks, 93.9 MB of chunk text — the RR.3 baseline, untouched by this effort (no document changed).
