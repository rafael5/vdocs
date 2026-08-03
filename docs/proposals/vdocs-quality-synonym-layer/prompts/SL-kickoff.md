# Kickoff — vdocs-quality-synonym-layer (SL.1–SL.3)

> **To start the session**, `cd ~/projects/vdocs` and say:
>
> > Read `docs/proposals/vdocs-quality-synonym-layer/prompts/SL-kickoff.md` and execute it.

**Repo: `vdocs`** (`~/projects/vdocs`) — offline analytical workload. Read `CLAUDE.md`, the proposal
and plan in [`..`](..), register row **R‑12** in `docs/reference/pipeline-adversarial-audit.md`, and
the feature's original design in [`../../skl-proposal.md`](../../skl-proposal.md). Tick the tracker
per landed step. **Shared-lake rule:** `pgrep -af "vdocs run"` before touching `~/data/vdocs`.

> ## ⛔ Check this first
>
> **`vdocs-quality-report-card` must be ticked `RC ✓` before this effort starts** — the family-wide rule (operator direction, 2026-08-03). If it is not, stop and run that effort instead.
>
> **Measure before you act.** The first step below is a measurement. No code, configuration, curation or gate lands until it is complete and written down.

## This is a decision, not a build — and "stop" is a legitimate outcome

VistA documentation names the same thing two ways: *file 200* in one manual, *NEW PERSON* in
another. We built a feature to teach search they are equivalent. **It currently knows exactly one
equivalence.** 4,415 candidates wait unapproved. The machinery runs on every rebuild; the approving
step never has.

The one live equivalence moved its question from **0.131 to 0.417** — roughly tripled. That single
point is why this is worth measuring rather than quietly abandoning, and it is *also* not enough
evidence to justify building on. Your job is to turn it into a number and a ruling.

## Measured starting point (2026-08-02)

| | |
|---|---|
| equivalences search uses | **1** (`200` → `NEW PERSON`) |
| entity records reaching the search index | **6** |
| knowledge store: entities / terms / relationships | 21 / 483 / 111 |
| candidates awaiting approval | **4,415** |

## SL.1 — the three measurements

1. **How common is the ambiguity?** Identifiers appearing under two or more names (file number ↔
   name ↔ global, and the same for options/routines), and how much text sits behind each.
2. **How many realistic questions does it cost?** The answer key has exactly one such question *by
   construction*, so it cannot answer this — build a sample of identifier-shaped questions and count
   those that fail for vocabulary reasons alone (the passage exists and is indexed, under the other
   name).
3. **How sound are the candidates?** Sample and judge correct/wrong/harmful. **Stratify** — easy
   candidates are probably right, hard ones probably wrong, and a flat sample will flatter the result.

## Then rule, with the numbers in the ruling

- **Finish** → build bulk review (grouped by pattern, spot-checked; never 4,415 individual
  decisions), state the expected gain *before* building, measure after, and let no unreviewed
  candidate reach the surface.
- **Stop** → take the unused machinery off the default rebuild path, keep the one working
  equivalence, and **correct every surface that claims the capability**. Leaving the claim after
  ruling against it is the same defect as a stale coverage constant.

A ruling without its numbers is an opinion. This project has paid repeatedly for treating opinions as
measurements.

## Watch out for

- **A wrong equivalence is worse than none** — it merges two things a reader needs kept apart.
- **Sunk cost.** Real effort built this. "Stop" must stay available as an honest answer; a capability
  delivering one synonym is already failing, and naming that is the improvement.
- **Do not reopen vector search.** This is a curated vocabulary map; the embedding path was evaluated
  and rejected for this collection.
- If SL.1(b) leans on the answer key, land `vdocs-quality-report-card` first or you will misattribute
  vocabulary failures.
