# Planning what comes after the audit — and being wrong twice while doing it

*2026-08-03 · commits `9307075` … `16eb041` · follows the P1–P7 remediation*

## Where this picked up

The seven-phase audit remediation closed the day before. It fixed **integrity**: nothing is silently
lost, no gate is advisory, no record lies. The question left on the table was whether anything from
the final acceptance run should change the pipeline's direction, and whether the register's remaining
open items were still worth acting on.

The answer turned out to be sitting inside the number I had published as P7's headline result an
hour earlier.

## The finding: ten questions returning nothing, and why that split three ways

The golden answer key said four of eighteen questions failed. Looking at the production collection
properly, **ten of twenty-four returned nothing relevant at all** — recall zero, not merely poor
ranking. Splitting them was the whole exercise:

- **Six were structurally unscoreable.** Every marked answer sits in an application the admission
  gate excludes. They score a permanent 0.000 and were dragging every published figure down by
  ~13 points. The metric was measuring label rot, not the engine.
- **Four were genuine.** Their answers exist, are indexed, and search does not surface them.

Corrected figures of record over the eighteen answerable questions: **0.3694 → 0.5305**, the same
+44% relative as before but a far healthier absolute than the 0.2770 → 0.3979 I had published. I
fixed the instrument rather than the number — the harness now detects an unscoreable question,
excludes it from the means, and reports the count (register row **R‑19**).

Then, sizing the four real failures, a second measurement changed the shape of the work again: of 51
correct answers across the answerable questions, **51% are in the top ten, 23.5% sit at ranks 11–100,
and 25.5% are never retrieved**. Nearly a quarter of correct answers are found and shown to nobody,
against a default result list of eight. That single table is what the whole plan ended up being
ordered by.

## What got built: a family of proposals, not a plan

The four items became five self-contained efforts under a common root (`vdocs-quality-*`), each with
a proposal, an implementation plan, a tracker and a prompts folder — then six, after the operator's
challenge below. Every proposal opens with a plain-language background section written for someone
who does not work on the pipeline, because the question that actually decides ordering is "what does
this cost the person searching", and that question cannot be answered in the vocabulary of chunks and
fingerprints.

Two of them — the synonym layer and the pattern miner — are deliberately framed as **decisions rather
than builds**: measure the headroom, then rule either way, with the numbers in the ruling, and "stop"
is explicitly an acceptable outcome. A feature that delivers one synonym is already failing; naming
that is the improvement, not an admission. The same for a mining step that proposes ~81,500 patterns
per rebuild against 29 curated ones, at 18% of rebuild time.

## Two things I got wrong

**First, the ordering.** I had the report card going first, on the grounds that "every measurement in
this family is taken with that answer key". The operator pushed back: corpus scope determines what is
in the collection at all, so shouldn't scope come first? That is right, and my reason was not merely
weaker — it was **false for the effort in question**. Crawl integrity does not touch the answer key.
The real dependency runs the other way: the report card's central action is retiring or re-pointing
six questions, and *that decision depends on the scope ruling*. Retire them first, and a corrected
scope policy would have us resurrecting them.

**Second, and worse, the evidence.** I had published that **102 documents left the collection with
nothing reporting it** — the headline justification for the crawl-integrity effort. Checking the
operator's premise, I found that those applications were **never acquired in production at all**.
They appear in the answer key because the key was curated against the dev lake, which admits
applications production does not. Having found one instance of dev-lake contamination the day before,
I inferred a second, more dramatic one instead of checking it. It is the identical mistake, one level
up: not "the measurement read the wrong corpus" but "I reasoned from a measurement that had".

What survives the correction is narrower and still real: nothing tracks the admitted set's
composition over time, so a genuine departure would be equally silent. The gap is real; the proof of
it was not. That correction is now recorded in the audit register, both umbrella documents, and all
four crawl-integrity artefacts.

## What the operator's domain knowledge added that measurement alone would not have

The push on ordering came with a requirement I would not have derived: **once a document is fetched,
never lose it**, because VA deprecating a package does not remove the code from VistA. The routines
stay installed and still need documentation — arguably more so, since nobody is maintaining them. And
a deprecation is itself intelligence: it usually means a commercial product replaced the package.

Measuring against that framing showed the current behaviour is quietly backwards. VA's labels already
decide admission: **589 archived applications are admitted while all 124 decommissioned ones are
excluded** — an asymmetry nobody chose explicitly. And the signals that would make a deprecated
document *useful* rather than confusing are already arriving and being discarded: `cots_dependent` on
404 records, `decommission_date` on 115 spanning 2005–2022, `out_of_scope_reason` in the model and
surfaced nowhere.

That produced the sixth effort, a **VDL observatory**: the pipeline treats the document library as a
place to copy from and keeps no history, so "which packages were deprecated this year?" is
unanswerable despite the answer arriving on every crawl. One of its steps is flagged time-sensitive
for a reason worth repeating — every crawl that overwrites its predecessor is a data point
permanently lost, and it cannot be backdated. It also carries the open question of why **38.2% of the
library (3,404 of 8,907 records) is marked archive**, written as an investigation with an explicit
escape hatch: if it cannot be established, say so and record what was tried.

## What I would carry forward

The standing rules now stated in all four artefacts of every effort are the compressed form of two
days of being wrong: **fix the boundary before the instrument that measures inside it**, and
**measure before you act — including in the effort whose whole purpose is measuring**.

The sharper lesson is the one behind the second correction. Every measurement mistake in this
programme has been the same shape: a number that was easy to accept because it fit. The dev lake
agreed with itself three times. The filtered approximation agreed in the mean. The 102 documents
agreed with a story I had just written. **When a measurement confirms what you already believe, that
is the moment to ask what it actually read** — and when you are reasoning from someone else's
measurement, including your own from yesterday, the question is the same.
