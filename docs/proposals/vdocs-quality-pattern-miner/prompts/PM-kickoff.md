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
> **`vdocs-quality-crawl-integrity` `CI ✓` and `vdocs-quality-report-card` `RC ✓` must both be ticked before this effort starts** (ordering revised 2026-08-03: crawl integrity first, then the report card). If either is not, stop and run the earliest unfinished one instead.
>
> **Measure before you act.** The first step below is a measurement. No code, configuration, curation or gate lands until it is complete and written down.

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
