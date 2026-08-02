# P6: one line of code hid 8,447 sections, and my own measurement hid the proof

*2026-08-02 · phase P6 of the pipeline audit remediation · commits `e374d9a`, `d984f8a`, `5fa9a65`*

## How this started — a question I'd have answered wrong

P5 closed the day before, and I'd written the P6 kickoff prompt with what I thought were solid
measurements: 27% of live sections carry no indexed text, P6.1 would roughly halve it, and the
plan's `< 8%` target was unreachable because the residual is genuinely empty. I'd even checked
whether normalize's heading re-leveling was manufacturing those containers (it wasn't, materially).
I was fairly confident the floor was the documents, not the pipeline.

Then the operator asked a question I hadn't thought to ask: *a section might consist of just a
table — and if that table was lifted to a CSV sidecar, wouldn't it look empty?*

The mechanism is real. `substantive_tokens` counts a referent line as zero tokens by design. But
measuring it closed it: `index`'s B3b table-chunk path (`stage.py:294`) is `for s in secs:`,
ungated by `searchable`, so an extracted table is re-introduced as an FTS chunk whatever its
section's kind — 24 of 24 such containers already carried one. That also explained the 254
containers with chunks that `mcp._has_chunks` exists to respect.

But the decomposition I ran to answer it found something else, and it was bigger than the question.

## The actual defect: one taxonomy, two consumers

Splitting all 14,170 unsearchable sections by *what they actually held* showed 1,896 carrying 1–7
tokens of genuine prose — under the 8-token floor, so no chunk, so **no `chunks_fts` row at all**,
so neither their text nor their own heading was findable. Real examples: `TABLE 0136 - YES/NO
INDICATOR` → "VALUE DESCRIPTION / Y YES / N NO" (an HL7 table definition), `GETDATA^ACKQAG02` →
"Provides the data for START^ACKQAG02.", and "There are no QUASAR package-wide variables." The last
one is a complete answer to a real question, and the identically-titled section in LR, XWB and AMT
was searchable — because those sentences happened to run past eight words.

`MIN_SUBSTANTIVE_TOKENS = 8` is an **over-strip detector**: it answers "did normalize gut this
section?", where a thin section is legitimately not evidence of damage. `searchable = kind in
("ok","stub")` reused that judgement as a retrieval gate, which asserts something quite different
and false — that under eight words isn't worth finding. The same line made the container mistake:
that a section with children has no text of its own, when 6,779 of 11,543 carried a substantive
lead-in that in a reference manual *is* the API contract.

Neither component is wrong in isolation. That's why it survived years of review. The fix is a
separate predicate — `kernel.markdown.is_searchable`, `tokens > 0 or has_referent` — leaving `kind`
untouched, which I verified by checking the kind distribution came out identical to the section.
Chunk-less share went **26.70% → 10.49%**, and the residual is exactly the population I'd predicted
would remain, to the section.

The operator asked for it immediately rather than waiting for P6's session, so P6.1b landed first
and subsumed P6.1 (it's the same predicate). P6.2 rode along, because leaving five hardcoded "26.7%"
constants in place would actively mislead an agent into reading a body file for text `search` now
hands it.

## Where I was wrong, and how it nearly stuck

I reported the golden set as unchanged at nDCG@10 0.5134 with **0 of 20 queries changing a single
ranked hit**, and explained it as the set being blind to the class — no queries for short reference
entries, so it could neither credit nor regress. That explanation was plausible, I wrote it into the
tracker, the design doc, a commit message and two messages to the operator, and I proposed adding
queries (P6.4) to fix the gap.

It was wrong. `scripts/baseline_golden.py` defaulted to `~/data/vdocs-dev` — a stale 451-document
lake from June that P6.1b never touched — and its printed rollup named no corpus at all. Three runs
in a row measured the wrong lake and agreed with each other, which is precisely what made it read as
confirmation rather than as a bug. The markdown report did name the lake; the JSON rollup, the thing
that gets pasted into a tracker, did not.

What caught it was not suspicion. It was a **contradiction between two paths**: while writing the
P6.4 queries I probed the engine directly and found `ACKQ/ackq3_0tm/package-wide-variables` ranked
**#1** for a query the harness had scored **0.000**. Both could not be true. I'd like to claim I
suspected the metric on principle — the house rule literally says to — but in fact I'd already
built an elaborate story on top of the bad number and only tripped over it by accident.

On production the same set gives **0.751** across the five new queries, two of them a perfect 1.000
against a single judged section that had zero chunks before P6.1b — so those queries scored exactly
0.000 before, by construction. That's the proof of gain the first measurement couldn't give.

The harness now defaults to `Settings().data_dir`, refuses a missing index.db with a sentence
instead of a traceback, and stamps `index_db`/`documents`/`chunks`/`corpus_content_hash` into every
rollup. A number that can't say what it measured isn't evidence. One consequence worth flagging
loudly: **every golden number in this repo predating today is a dev-lake number, including the
audit's 0.469.**

## The trade, stated honestly

Having got the measurement right, I stopped saying "no regression". The original 19 queries move
**0.3122 → 0.3072** — a −0.0050 mean nDCG@10 dip, −1.6% relative, concentrated in four queries with
the worst at −0.056. Twenty-six newly-searchable sections enter an original top-10 and five outrank
a judged hit. Against that: a whole class of reference lookups goes from unanswerable to answered at
rank 1. Worth it, clearly — but the cost is real and rounding it to zero would have been the same
kind of error as the dev lake, just quieter. (The before-figure is an approximation: the current
ranking with newly-searchable sections filtered out, not a rebuilt pre-P6.1b index.)

## Other things worth knowing later

`manifest` skipped after the rebuild and published a `CORPUS.md` still quoting 26.7%, because
`USAGE` lives in *code* and editing it moves no input fingerprint. That's now the third distinct way
this pipeline can ship a stale output with every input unchanged (P4: weak fingerprint; P5: another
stage wiped it; P6: the text is code). Three instances is a pattern, and I've suggested P7 give it a
register row rather than a third footnote.

P6.3 turned out to be more than plumbing. The MCP surface is forbidden from saying a zero-hit search
means the corpus lacks the fact — the rule exists because four researchers once retracted a report
of "missing" FileMan APIs. Meanwhile `vdocs ask` printed "no matches in the gold corpus." and
`--json` emitted a bare array with no warning. The lesson had been learned on exactly one of the
three surfaces that needed it.
