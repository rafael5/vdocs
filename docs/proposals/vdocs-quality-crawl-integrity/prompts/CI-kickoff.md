# Kickoff — vdocs-quality-crawl-integrity (CI.1–CI.2)

> **To start the session**, `cd ~/projects/vdocs` and say:
>
> > Read `docs/proposals/vdocs-quality-crawl-integrity/prompts/CI-kickoff.md` and execute it.

**Repo: `vdocs`** (`~/projects/vdocs`) — offline analytical workload. Read `CLAUDE.md`, the proposal
and plan in [`..`](..), then register rows **R‑4** and **R‑19** in
`docs/reference/pipeline-adversarial-audit.md`. Tick the tracker per landed step.
**Shared-lake rule:** `pgrep -af "vdocs run"` before any command touching `~/data/vdocs`.

> ## ⛔ Check this first
>
> **`vdocs-quality-report-card` must be ticked `RC ✓` before this effort starts** — the family-wide rule (operator direction, 2026-08-03). If it is not, stop and run that effort instead.
>
> **Measure before you act.** The first step below is a measurement. No code, configuration, curation or gate lands until it is complete and written down.

This effort touches no search behaviour, so it *could* technically run alongside the retrieval work. It deliberately does not — the report card is the underlying issue and is fixed first.

## Why this exists

Seven phases made sure nothing is lost *inside* the pipeline. **Nothing watches the crawl.** Verified
2026-08-02: `crawl` and `catalog` have no gate and no floor of any kind, and a degraded crawl
overwrites the last good one.

⚠️ **Correction to this prompt's first draft:** it claimed 102 documents had *left* the collection
unreported. They were never acquired in production — the golden answer key that "proved" it was
curated on the **dev lake**. The gap is still real (nothing would notice a genuine departure), but
the dramatic evidence was not. Treat that as this effort's own measure-first lesson.

## What you are building, and what already exists to copy

- **CI.0 — measure** the current crawl yield, admitted-set composition, and what VA's labels do.
- **CI.1 — a completeness floor:** a crawl finding materially less than the last good one fails, and
  the previous good artifact stays in place.
- **CI.2 — master-set retention:** a document we have fetched is **never** dropped by a scope or
  lifecycle relabel. VA deprecating a package does not remove its code from VistA — the routines are
  still installed and still need documentation.
- **CI.3 — capture the lifecycle labels** (`app_status`, `decommission_date`, `cots_dependent`,
  `out_of_scope_reason`) so a reader sees *"deprecated; code still installed; commercially replaced
  in 2022"* instead of an absence.
- **CI.4 — admitted-set composition baseline:** departures by document identifier, with a curated
  acknowledgement making a deliberate change cheap to declare.

**Reuse, do not invent.** `validate` already runs a cross-run count-drop check
(`reconcile_pure.py`) and a five-seam reconciliation by identifier (`chain_pure.py`). This is that
machinery pointed one stage earlier.

## The traps, measured or paid for previously

- **A count can hide a swap.** Lose 20, gain 20, net zero. Report by identifier — P1 paid for this
  lesson when six documents collapsed out of the collection last-writer-wins.
- **A floor set too tight gets disabled.** The VDL genuinely changes. Choose a defensible tolerance,
  justify it beside the constant, and make acknowledging a legitimate change cheap — an alarm nobody
  can silence quietly becomes an alarm nobody keeps.
- **Fail closed on the artifact, not just the run.** A gate that reds *after* overwriting bronze has
  not helped.
- **Name the application, not only the documents.** "XOBW, KAAJEE and LEX are no longer admitted" is
  what an operator can act on; 102 identifiers are not.

## Proving it works

Demonstrate both gates biting on a **scratch copy** of the lake. Never induce a defect in the live
collection to show a gate works — the P2 precedent used a scratch-lake copy for exactly this.

## Close-out

Tick CI.1–CI.2 and CI ✓ citing the scratch-lake red paths and a green live run, then record in the
tracker whether the 102 departed documents should be revisited as a scope question — flag it for the
operator; do not decide it here.
