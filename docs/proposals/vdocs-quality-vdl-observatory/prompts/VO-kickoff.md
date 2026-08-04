# Kickoff — vdocs-quality-vdl-observatory (VO.1–VO.5)

> **To start the session**, `cd ~/projects/vdocs` and say:
>
> > Read `docs/proposals/vdocs-quality-vdl-observatory/prompts/VO-kickoff.md` and execute it.

> ## ⛔ Check this first
>
> **`vdocs-quality-crawl-integrity` must have landed** — this effort builds the timeline on top of
> the snapshot mechanism and retention rule that effort establishes.
>
> **Measure before you act.** VO.1 establishes what the current inventory already tells us. Several
> of the signals below are captured today and simply unused; no storage format is designed before
> that is known.

**Repo: `vdocs`** (`~/projects/vdocs`) — offline analytical workload. Read `CLAUDE.md`, the proposal
and plan in [`..`](..), and the `vdl` domain skill for what the library is. Tick the tracker per
landed step. **Shared-lake rule:** `pgrep -af "vdocs run"` before touching `~/data/vdocs`.

## Why this exists

The pipeline treats the VDL as a place to copy from: it crawls, takes what is there, and overwrites
what it knew. So "how many technical manuals did the VDL list last quarter?" and "which packages were
marked deprecated this year?" have no answer.

That is a missed primary source. VA publicly labels each application `active`, `archive` or
`decommissioned`, records decommission dates, and flags commercial dependency — that is VA telling
us which parts of VistA are being retired and what replaced them.

## Measured starting point (2026-08-03, 8,907 inventory records)

| label | records | share |
|---|---:|---:|
| `active` | 5,379 | 60.4% |
| `archive` | **3,404** | **38.2%** |
| `decommissioned` | 124 | 1.4% |

Captured and unused: `cots_dependent` **404** · `decommission_date` **115** (2005–2022) ·
`out_of_scope_reason`. Historical snapshots: **none**.

## Do VO.2 early

Every crawl that overwrites its predecessor is a data point **permanently lost**. The timeline cannot
be backdated, so keeping snapshots is the one step whose value decays while you plan it.

## VO.5 — the question worth getting right

**38.2% of the library is `archive` and nobody has established what VA means by it.** Sample the
records, compare the label against what the documents say, and check whether the corresponding VistA
code is still installed (`vista-meta` answers that side). The answer determines how much of the
corpus is historical rather than current.

**If you cannot establish it, say so and record what you tried.** An honest unknown is a result. A
guess written as a finding is the failure mode this project has spent a whole programme correcting.

## Watch out for

- **Do not infer intent from a label.** Record what changed; mark the why unknown when it is.
- **No backfilling.** The timeline starts when snapshots start.
- **`archive` is not exclusion today:** 255 archive-status documents (26 applications) are already
  in the collection while all 124 `decommissioned` records are excluded (CI.0 measurement — the
  draft's "589" reproduced under no definition). That asymmetry is `crawl-integrity`'s to rule on —
  your job is to supply the evidence, not to change admission.
