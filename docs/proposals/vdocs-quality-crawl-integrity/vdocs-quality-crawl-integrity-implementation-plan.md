# vdocs-quality-crawl-integrity — implementation plan

Proposal: [`vdocs-quality-crawl-integrity.md`](vdocs-quality-crawl-integrity.md) ·
Tracker: [`vdocs-quality-crawl-integrity-tracker.md`](vdocs-quality-crawl-integrity-tracker.md) ·
Prompts: [`prompts/`](prompts/)

⛔ **Do not start before `vdocs-quality-report-card` is ticked `RC ✓`** (operator direction, 2026-08-03). Neither step here changes search behaviour, so this effort *could* technically run alongside the retrieval work — it deliberately does not, because the report card is the underlying issue and gets fixed first.

Three steps, commit subjects `CI.0:` / `CI.1:` / `CI.2:`. House rules: TDD, `make check` green before commit, tick the tracker in the same commit.

## CI.0 — Measure first

Record what the current crawl actually yields (sections and documents discovered) and the
current admitted-set composition. These two numbers *are* the baselines the gates in CI.1 and
CI.2 compare against — building a floor before knowing the floor level is guesswork.

**No gate lands before this exists.**

## CI.1 — A completeness floor on the crawl

`crawl` currently has no `deep_gate` and no floor: whatever it finds becomes the new truth, and a
degraded page or a bad day at the source silently shrinks the collection.

Add a postflight gate: compare this crawl's yield (sections and documents discovered) against the
last **good** crawl. A materially smaller yield fails the stage, and the previous good result is left
in place rather than overwritten.

Design notes:
- **Tolerance, not equality.** The VDL genuinely changes. A floor set too tight cries wolf and gets
  disabled — which is strictly worse than no floor. Pick a threshold you can defend, state it in the
  code beside the constant, and make it configurable.
- **Fail closed on the artifact, not just the run.** The point is that the last good crawl survives.
  A gate that fails the run but has already overwritten bronze has not helped.
- **Distinguish "smaller" from "different".** A same-size crawl that returns entirely different
  sections should not pass silently; that is CI.2's job, and the two should be read together.

*Tests first:* a fixture crawl returning materially less reds and leaves the prior artifact intact;
a crawl within tolerance passes; a first-ever crawl (no baseline) passes with the baseline recorded.

## CI.2 — A baseline for what is in scope

Record the admitted set's composition each run and compare it to the previous one. Departures are
reported **by document identifier**, not as a count — the acquisition-chain work already established
that a net-zero count can hide a swap.

- A deliberate scope change is acknowledged in a curated registry entry (application, date, reason).
  Acknowledged departures pass; unacknowledged ones are a blocking finding naming the documents.
- Reuse the existing machinery rather than inventing: `validate` already performs a cross-run
  count-drop check and a five-seam reconciliation by identifier. This is the same pattern applied to
  the admission decision.
- The finding must name the *application* as well as the documents — 102 documents left as three
  coherent groups, and "XOBW, KAAJEE and LEX are no longer admitted" is the sentence an operator can
  act on.

*Tests first:* a removed application reds with its documents named; the same removal with an
acknowledgement passes; an unchanged set passes silently; a swap of equal size reds.

## Sequencing

CI.0 → CI.1 → CI.2. The floor is the cruder, cheaper net and catches the source-side failure; the composition baseline catches the rules-side failure and is the one that would have caught the measured 102-document departure.

## Verification on the live collection

After both land: run the pipeline and confirm the collection stays green with the new baselines
recorded, then prove each gate bites on a **scratch copy** of the lake rather than the live one —
never induce a defect in the real collection to demonstrate a gate.

## Out of scope

Scheduling or automating crawls; changing politeness; restoring the 102 departed documents (a product
question); and any judgement about whether the current scope rules are correct. This effort makes
scope changes *visible*, not *right*.
