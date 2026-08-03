# Kickoff — vdocs-quality-crawl-integrity (CI.1–CI.2)

> **To start the session**, `cd ~/projects/vdocs` and say:
>
> > Read `docs/proposals/vdocs-quality-crawl-integrity/prompts/CI-kickoff.md` and execute it.

**Repo: `vdocs`** (`~/projects/vdocs`) — offline analytical workload. Read `CLAUDE.md`, the proposal
and plan in [`..`](..), then register rows **R‑4** and **R‑19** in
`docs/reference/pipeline-adversarial-audit.md`. Tick the tracker per landed step.
**Shared-lake rule:** `pgrep -af "vdocs run"` before any command touching `~/data/vdocs`.

Independent of the retrieval efforts — this touches no search behaviour, so it can run in parallel
with someone else's measurement work.

## Why this exists

Seven phases made sure nothing is lost *inside* the pipeline. **Nothing watches the crawl.** Verified
2026-08-02: `crawl` and `catalog` have no gate and no floor of any kind, and a degraded crawl
overwrites the last good one.

Measured consequence: **102 documents left the collection with zero findings** — XOBW (23), KAAJEE
(64), LEX (15), excluded by the admission gate on `system_type`. That exclusion was legitimate; the
silence was not. It surfaced roughly four weeks later, by accident, when a golden question broke.

## What you are building, and what already exists to copy

- **CI.1 — a completeness floor:** a crawl that finds materially less than the last good one fails,
  and the previous good artifact stays in place.
- **CI.2 — an admitted-set composition baseline:** departures reported **by document identifier**,
  with a curated acknowledgement making a deliberate scope change cheap to declare.

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
