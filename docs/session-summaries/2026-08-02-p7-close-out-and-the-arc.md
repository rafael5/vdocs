# P7: closing a seven-phase audit remediation, and what the arc actually taught

*2026-08-02 · P7 of the pipeline audit remediation · closes P1–P7*

## What the effort was

On 2026-08-01 an end-to-end adversarial audit read the *executed* pipeline code — not its docs —
and produced a per-stage table, an artifact ledger, and a sixteen-row risk register. Five findings
were significant enough to plan around, and the plan ordered them enforcement-first: fix the one
measured data defect, then make the gates real, then the substrate, then the largest behavioural
change, then close out. Seven phases, one session each, each driven by a kickoff prompt written at
the *previous* phase's close so it could carry measured numbers rather than guesses.

That last rule turned out to be the most valuable structural decision in the whole effort, and not
for the reason it was adopted. It was meant to keep prompts accurate. What it actually did was force
a measurement at every phase boundary — which is where four of the six things we got wrong were
caught.

## What changed, measured on the live lake

| | before | after |
|---|---|---|
| documents lost to a sha-keyed index | 6 (silently, reporting `fetched`) | 0, and a gate joins all five acquisition seams |
| `doctor` | 19 checks, advisory — `vdocs run` never called it | **20 checks, the DAG's terminal stage**; RED fails the run |
| retention verdicts | scored, never gated (`blocks_publish` was dead code) | QUARANTINE blocks; unscored blocks; sign-offs are a registry entry |
| SQLite fingerprints | `rows:N` — blind to content-only change | all content hashes; 0 legacy records left |
| gold anchors whose lineage misdescribed their own body | **615 of 615** | **0 of 615**, gated |
| live sections carrying no indexed text | 13,916 (26.7%) | **5,469 (10.5%)**, and provably contentless |
| golden retrieval, 24 labeled queries | 0.2770 | **0.3979 (+44%)** |

Everything in that table is a number I re-measured on the production lake, several of them twice,
for reasons the next section explains.

## The six mistakes, because they are the useful part

**The audit named the wrong six documents.** It identified the collapsed doc_ids by eyeballing the
first element of each duplicate pair; those were the *survivors*. Computing the set difference at P1
close gave the real six. Count, mechanism and impact were right — only the identifiers were wrong,
which is the failure mode of reading a list instead of deriving one.

**P3's plan step was wrong in both halves.** It said "credit relocated table words" and called the
retention metric "slightly harsh". Measuring showed `normalize` takes its baseline *after* lifting
tables, so those words were never in the denominator — the credit would have turned a document that
truly retained 57% into a PASS at 0.87. The gate was too *lenient*, and the plan's own fix would
have made it more so.

**P4's spec would have been permanent leniency as literally written.** "Accept a legacy fingerprint
once and re-record" — but the producer skips on its own unchanged inputs, so nothing ever
re-records. Implementing the sentence would have created the bug it was meant to remove.

**P6's target was unreachable by P6's own mechanism.** The plan set `< 8%` chunk-less. Running the
shipped shredder over all 615 gold bodies *before writing any code* showed the mechanism's floor is
~14%, and the true residual after both halves is 10.5% — all of it genuinely empty. Struck the
target with its reason instead of missing it quietly.

**A retrieval measurement read the wrong corpus, three times, and agreed with itself.** This is the
one worth remembering. I reported P6.1b as "golden nDCG unchanged, 0 of 20 queries moved" and
diagnosed the golden set as blind to the change. It wasn't: `baseline_golden.py` defaulted to
`~/data/vdocs-dev`, a stale 451-document lake, while its printed rollup named no corpus at all.
Three runs agreed because they were all reading the same wrong thing, and agreement felt like
confirmation. What caught it was not suspicion — it was a *contradiction between two paths*: the
engine ranked a section #1 for a query the harness scored 0.000. Every report now stamps
`index_db`/`documents`/`chunks`/`corpus_content_hash`.

**And an approximation I labelled as one was still wrong in a way I did not predict.** I estimated
P6.1b's cost by filtering the new sections out of the current ranking. The adversarial pass rebuilt
the real pre-change index (45 seconds) and found the aggregate nearly exact — −0.0050 estimated vs
−0.0059 true — and the per-query story wrong in both directions: two queries actually fell to
**0.000**, one *gained* +0.286. The errors cancelled. A cheap estimate agreeing with a measurement
in the mean is not evidence that it agrees at all.

## The one defect the audit did not name

Three separate times, in three different phases, a stage shipped a stale output while every one of
its **inputs** was unchanged: a fingerprint too weak to see the change (P4); another stage
destroying this stage's output (`index` emptying `entity_skl`, which `merge` fills — it survived P4
and recurred in P5); and the output's text living in *code*, so editing it moved no fingerprint at
all (`manifest_pure.USAGE` → a `CORPUS.md` still quoting the number the same commit disproved).

We fixed them one at a time, each as its own surprise, before noticing they were one shape. All
three are now closed by mechanism rather than discipline — content hashes, an output-survival check
in the skip decision, and a `doctor` check comparing the published card to the code that renders it
— and the register gained **R‑18** for the pattern itself, left explicitly open as a class. The
question it leaves behind is the useful artifact: *what could make my recorded output untrue while
my inputs sit still?*

## What P7 itself did

Struck thirteen register rows with their landing commits, refreshed the master-table Credibility
cells, and annotated four footnotes with dated corrections — the audit is a point-in-time record, so
nothing was rewritten. Added R‑18. Ran the forced acceptance from `convert` (the operator's call:
the literal `vdocs run --force` would have re-crawled va.gov and let the upstream corpus shift
during close-out, which is an uncontrolled variable at exactly the wrong moment). Wrote the operator
an exact diff for the two out-of-repo surfaces rather than editing them — the `vdocs-corpus` skill's
worked example is now actively false, naming three sections as unsearchable that all return text
today. Archived the plan and tracker.

## What I would tell the next effort

The prompt-per-phase protocol works, but not because prompts are good documentation. It works
because "write the next prompt" is a checkpoint that cannot be satisfied without measuring, and a
measurement at a phase boundary is the cheapest place to discover that the plan is wrong. Four of
the six errors above surfaced there.

The corollary is the harder discipline: when the measurement is *convenient* — unchanged, agreeing,
confirming — that is exactly when to ask what it actually read.
