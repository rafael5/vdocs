# Kickoff — vdocs-quality-report-card (RC.1–RC.3)

> **To start the session**, `cd ~/projects/vdocs` and say:
>
> > Read `docs/proposals/vdocs-quality-report-card/prompts/RC-kickoff.md` and execute it.
>
> Self-contained: it names every document to read and carries the measured baseline.

> ## ⛔ Check this first
>
> **`vdocs-quality-crawl-integrity` must be ticked `CI ✓` before this effort starts** (ordering revised 2026-08-03: RC.1's retire/re-point decision depends on the scope ruling). If it is not, stop and run that effort instead. Every *later* effort remains blocked on this tracker's `RC ✓` row.
>
> **Measure before you act:** RC.1 opens by *confirming* the six questions are out of scope rather than lost — those look identical from the key's side and mean opposite things.

**Repo: `vdocs`** (`~/projects/vdocs`) — an offline analytical workload. Read `CLAUDE.md`, then the
proposal and plan in [`..`](..), then register row **R‑19** in
`docs/reference/pipeline-adversarial-audit.md`. Tick the tracker per landed step.
**Shared-lake rule:** `pgrep -af "vdocs run"` before any command touching `~/data/vdocs`.

## Why this runs ahead of all retrieval work

The answer key we grade search with is stale, and the two failure modes point in opposite
directions: six questions can never pass (they cite three applications the admission gate excludes),
and at least two questions fail search for returning a *better* answer than the key names. Until
both are fixed, any ranking work would be tuned against measurably wrong targets. It runs *after*
`vdocs-quality-crawl-integrity` because those six questions are a scope artefact, and the
retire-vs-re-point call depends on the scope ruling.

**You are not allowed to change search in this effort.** The next effort's before/after depends on
this baseline holding still.

## The measured baseline (2026-08-02, `corpus_content_hash 6dbec1f5…`, 1,040 documents)

| | |
|---|---|
| score, 18 answerable questions | **0.5305** nDCG@10 · recall@10 **0.588** |
| score if the impossible six are included | 0.3979 (~13 points of pure artefact) |
| unanswerable questions | **6** — `kids-delphi-components-install`, `hwsc-rest-from-vista-m`, `hwsc-install-privileges`, `kaajee-install-procedure`, `lexicon-lookup`, `hwsc-web-service-manager` |
| zeros not explained by scope | **4** — `kids-install-build`, `fileman-add-field`, `rpc-broker-client-call`, `vbecs-accept-order` |

Reproduce with `.venv/bin/python scripts/baseline_golden.py --k 10 --out reports/<name>.md` and
check the rollup's `corpus_content_hash` and `chunks` match before comparing anything.

## Two things measured for you, so you don't re-derive them

1. **The six are out of scope, not lost.** XOBW (23 inventory documents), KAAJEE (64) and LEX (15)
   are present in the gold inventory and excluded by the admission gate on `system_type`
   (*Integration middleware* / *Data patch*, not *VistA*), as is `XU/kdc1_0ig`. Confirm rather than
   trust — "missing" and "out of scope" look identical from the key's side and mean opposite things.
2. **Two of the four zeros look like key defects.** `kids-install-build` scores the actual *KIDS User
   Guide* as wrong; `fileman-add-field` scores a tutorial on adding a field as wrong. All four
   questions' judged sections are `ok`, searchable, latest, with real text — so nothing is missing
   from the collection; this is about labels and ranking.

## Watch out for

- **Judge by reading the passage, never the title.** This key already carries one label that was
  assigned from a title and was wrong when read (`MPIF/…/yesno-indicator-table`: graded 1, corrected
  to 3 — and the correction *lowered* the score).
- **Leave the deliberate decoys alone.** Several questions have near-miss lexical traps unlabelled on
  purpose (identically-titled sections belonging to other packages). They are discriminators, not
  omissions.
- **Retiring a question is a scope decision.** Surface the retire-vs-re-point split for the operator
  rather than settling it yourself.

## Close-out

Tick RC.1–RC.3 and the RC ✓ row, publish the corrected baseline with its provenance stamp (it
becomes the number `vdocs-quality-response-ranking` compares against), and write that effort's
kickoff prompt carrying the real count of *search-owned* zeros — which is the input that sizes it.
