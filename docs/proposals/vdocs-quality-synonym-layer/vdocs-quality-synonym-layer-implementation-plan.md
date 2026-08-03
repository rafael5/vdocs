# vdocs-quality-synonym-layer — implementation plan

Proposal: [`vdocs-quality-synonym-layer.md`](vdocs-quality-synonym-layer.md) ·
Tracker: [`vdocs-quality-synonym-layer-tracker.md`](vdocs-quality-synonym-layer-tracker.md) ·
Prompts: [`prompts/`](prompts/)

Commit subjects `SL.1:` / `SL.2:` / `SL.3a:` or `SL.3b:`. **SL.1 and SL.2 are mandatory; exactly one
of SL.3a/SL.3b follows.** House rules: `make check` green before commit, tick the tracker in the same
commit.

## SL.1 — Measure the headroom

Three measurements, all against data we already have. Read-only; no pipeline changes.

**(a) How common is the ambiguity?** Count the identifiers in the collection that appear under two or
more names — file number ↔ file name ↔ global reference, and the equivalent for options and
routines — and how much text sits behind each. This bounds the population the feature could ever
help.

**(b) How many realistic questions does it cost?** The answer key contains exactly one such question
by construction, so it cannot answer this. Build a sample of identifier-shaped questions
(*"what is file 63?"*, *"what does ^DPT hold?"*) and measure how many fail for vocabulary reasons
alone — i.e. the answering passage exists and is indexed, but under the other name.

**(c) How sound are the 4,415 waiting candidates?** Sample and judge: correct / wrong / harmful.
**Stratify** — the easy candidates are probably right and the hard ones probably wrong, so a flat
random sample will overstate quality.

*Measure of done:* three numbers written down, each reproducible.

## SL.2 — Rule, with the numbers in the ruling

Write the ruling into the proposal as an accepted decision:

- **Finish it** if (a) shows the ambiguity is widespread, (b) shows it costs real questions, and
  (c) shows the candidates are mostly sound. Proceed to SL.3a.
- **Stop claiming it** otherwise. Proceed to SL.3b.

The ruling must state the three numbers. A ruling without them is an opinion, and this project has
paid repeatedly for treating opinions as measurements.

## SL.3a — *(if finish)* Build the approval path

- **Bulk review, not row-by-row.** 4,415 individual decisions is not a plan. Group candidates by
  pattern, review the pattern, spot-check members.
- **State the expected gain before building**, then measure it after on the answer key with a
  provenance-stamped report. Both sides of the comparison must share `corpus_content_hash` **and**
  passage count.
- **No unreviewed candidate reaches the surface.** A wrong equivalence merges two things a reader
  needs apart, and damages results for everyone.
- **No question regresses** — compared per question, not on the average.

*Tests first:* an approved equivalence expands a query and surfaces the other-vocabulary passage; a
rejected one does not; an unreviewed one is inert.

## SL.3b — *(if stop)* Retire it honestly

- Take the unused extraction/projection work off the default rebuild path (keep it runnable on
  demand — the data may be worth something later).
- **Retain the one working equivalence.** It measurably helps and costs nothing.
- Correct every surface that claims the capability: the corpus card, the assistant-facing
  instructions, and any documentation describing a "semantic knowledge layer" as a live search
  feature. Leaving the claim in place after ruling against it is the same defect as a stale
  coverage constant — a documented capability the system does not have.

*Measure of done:* rebuild time recovered is stated, and no user-facing surface claims more than the
system does.

## Sequencing and dependency

Independent of the retrieval efforts in mechanism, but **measure after `vdocs-quality-report-card`
lands** if SL.1(b) uses the answer key at all — an unrepaired key would misattribute vocabulary
failures.

## Out of scope

Vector/semantic retrieval (evaluated and rejected for this collection), and any change to how
entities are *extracted*. This effort is about the gap between extraction and use, which is where
the measured shortfall is.
