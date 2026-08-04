# Kickoff — vdocs-quality-pattern-miner (PM.1–PM.3)

> **To start the session**, `cd ~/projects/vdocs` and say:
>
> > Read `docs/proposals/vdocs-quality-pattern-miner/prompts/PM-kickoff.md` and execute it.

**Repo: `vdocs`** (`~/projects/vdocs`) — offline analytical workload. Read `CLAUDE.md`, the proposal
and plan in [`..`](..), and tenet #13 ("discovery is data, not code") in `docs/vdocs-design.md`.
Tick the tracker per landed step. **Shared-lake rule:** `pgrep -af "vdocs run"` before touching
`~/data/vdocs`.

> ## ⛔ Check this first
>
> **`CI ✓`, `RC ✓`, `RR ✓` and `SL ✓` are all ticked** (the first three 2026-08-03, `SL ✓` 2026-08-04) — **this effort is next in the programme order and nothing is ahead of it.**
>
> **The ruler, if you measure retrieval at all:** `reports/rr3-after-twin-demotion.*` — nDCG@10 **0.6447** · recall@10 **0.7238**, `corpus_content_hash 726d22a4…`, 57,895 chunks, 24 labelled / 0 unscoreable. Figures quoting 0.5305 / 18 answerable predate the report card and are a different ruler. (SL touched no ranking, so this is still current.)
>
> **Measure before you act.** The first step below is a measurement. No code, configuration, curation or gate lands until it is complete and written down.
>
> ### Two things `vdocs-quality-synonym-layer` learned the hard way — apply both here
>
> SL was the same shape as this effort (a dormant proposal side, an approval side that never ran) and
> **both of its headline framings turned out to be wrong**. Read
> [`../../vdocs-quality-synonym-layer/sl1-findings.md`](../../vdocs-quality-synonym-layer/sl1-findings.md)
> before trusting any number below.
>
> 1. **Check what the queue count counts.** SL's "4,415 candidates awaiting approval" was a count of
>    *mentions* — the stage reported `len(unresolved)` while the artifact it wrote aggregated to one
>    row per `(type, surface)`. The real queue was **307**. The wrong figure reached the proposal, the
>    plan, the tracker, this effort's sibling kickoff and the audit register before anyone opened the
>    file. **So: open `discover`'s actual output artifacts and count the rows a curator would face**,
>    for each of the three streams separately (34,822 phrases / 23,885 boilerplate / 18,011 glossary
>    terms). Do not carry those numbers into a ruling until you have.
> 2. **Establish the consumers before costing the retirement.** SL's "stop" turned out to be blocked:
>    `resolve` fed two *working* consumers nobody had listed (the 483-term termbase and the glossary
>    Entities section), and `merge`'s tables are published in **read contract v1**, so removal is a
>    breaking change `contract-lint` refuses as a MINOR. Retiring it would have traded a breaking
>    change for 33 s of an ~18-minute rebuild. **Here the cost is far larger (4m41s, ~18%), so the
>    trade may well go the other way — but find `discover`'s consumers and contract surface first, or
>    the ruling is unexecutable.** Note also that a ruling can be *stop the claim, keep the code*;
>    that third option is what SL took.

## This is a decision, not a build

Every full rebuild, the miner proposes about **81,500** cleanup patterns — 34,822 phrases, 23,885
boilerplate blocks, 18,011 glossary terms. The curated files it feeds hold **29 entries in total**.
The proposing runs every time; the approving essentially never has.

It costs **4m41s of a ~26-minute rebuild — about 18%**, second only to document conversion.

Neither outcome is dramatic, and that is why this is last: nobody is blocked. But generating 81,500
suggestions and acting on 29, forever, is not defensible in either direction.

## PM.1 — sample, stratified

Judge a stratified sample of phrases / boilerplate / glossary as **furniture** (safe to strip),
**content** (harmful to strip), or **noise**. Then estimate: if the furniture were approved, how much
text leaves, and what share of a typical retrieved passage is that? *That* number is the benefit
side — not the raw proposal count.

**Stratify by frequency.** The most common patterns are the most obviously furniture; a
frequency-ordered sample will flatter the population, and the harmful ones live in the low-frequency
tail.

## PM.2 — rule, with the numbers in it

**Build the curation loop** if the furniture fraction and volume would change what a reader sees.
Otherwise **take the miner off the default rebuild path**, keeping it runnable on demand.

## The risk that dominates everything here

**Never auto-approve on frequency.** Stripping text because it repeats is how documents get silently
gutted — and this collection has already had that incident: page-numbered contents entries were
deleted with **no record at all**, and only an unexplained content-loss score revealed it. Nothing in
this effort weakens capture-before-strip.

Evidence the mechanism does work when curation happens: the 16 curated boilerplate patterns matched
**1,014** times and single-source 89 shared blocks. The ratio between proposed and approved is the
problem, not the machinery.

## What "done" looks like

A written ruling with its numbers, and generate-and-discard no longer happening on every rebuild. The
real failure mode for this effort is a third cycle with the decision still open — if you find
yourself deferring, record the deferral and its reason in the tracker rather than leaving it silent.
