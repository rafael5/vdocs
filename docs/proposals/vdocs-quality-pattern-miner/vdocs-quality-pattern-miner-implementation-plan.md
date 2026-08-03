# vdocs-quality-pattern-miner — implementation plan

Proposal: [`vdocs-quality-pattern-miner.md`](vdocs-quality-pattern-miner.md) ·
Tracker: [`vdocs-quality-pattern-miner-tracker.md`](vdocs-quality-pattern-miner-tracker.md) ·
Prompts: [`prompts/`](prompts/)

Commit subjects `PM.1:` / `PM.2:` / `PM.3a:` or `PM.3b:`. **PM.1 and PM.2 are mandatory; exactly one
of PM.3a/PM.3b follows.** House rules: `make check` green before commit, tick the tracker in the same
commit.

## PM.1 — Sample what the proposals are worth

Read-only; no pipeline change. Take a **stratified** sample across the three large categories —
phrases (34,822), boilerplate (23,885), glossary (18,011) — and judge each item:

- **furniture** — safe to strip, adds nothing to any answer;
- **content** — would be harmful to strip;
- **noise** — neither, an artefact of the mining heuristic.

Stratify by frequency. The most common patterns are the most obviously furniture, so a
frequency-ordered sample will overstate quality; the low-frequency stratum is where the harmful ones
will be, and it must be judged honestly.

Then estimate: if the *furniture* fraction were approved, how much text leaves the collection, and
what share of a typical retrieved passage is that? That number — not the raw proposal count — is the
benefit side of the ruling.

*Measure of done:* the three judgements and the volume estimate, written down and reproducible.

## PM.2 — Rule, with the numbers

Write the ruling into the proposal as an accepted decision:

- **Build the curation loop** if the furniture fraction is high and the volume is material enough to
  change what a reader sees.
- **Take the miner off the default rebuild path** otherwise — keep it runnable on demand, for when
  someone actually intends to curate.

State the numbers in the ruling. A ruling without them is an opinion.

## PM.3a — *(if build)* The curation loop

- **Bulk review with spot-checks.** Group proposals by pattern, review the group, sample its members.
  Tens of thousands of individual decisions is not a plan and will not happen.
- **Never auto-approve.** Frequency is not evidence of furniture. This collection has already had
  content deleted with no record — page-numbered contents entries, found only via an unexplained
  retention score — and the capture-before-strip guarantee stays absolute.
- **Measure the effect** on retrieved-passage cleanliness rather than asserting it: sample passages
  before and after and state the change in furniture-per-passage.
- **No document loses content without a record**, and the content-retention gate stays green.

*Tests first:* an approved pattern is stripped and captured; a rejected one is untouched; an
unreviewed one is inert.

## PM.3b — *(if off-path)* Run it on demand

- Remove the mining step from the default rebuild while keeping the command available.
- State the recovered time (**~4m41s of ~26m**, about 18%).
- Correct any documentation implying the collection is continuously cleaned — the same honesty rule
  that applies to any capability claim the system does not deliver.

*Measure of done:* a default rebuild no longer includes mining; an explicit run still produces the
proposals.

## Sequencing

Last of the five quality efforts. Nothing depends on it and nobody is blocked by it, and both
rulings are cheap — which is exactly why it must not be allowed to drift: the failure mode is a third
generate-and-discard cycle with the decision still open.

## Out of scope

Hard-coding patterns (the "discovery is data, not code" principle is not being challenged — only the
missing review half), deleting the miner, and any change to how stripping itself is captured and
recorded.
