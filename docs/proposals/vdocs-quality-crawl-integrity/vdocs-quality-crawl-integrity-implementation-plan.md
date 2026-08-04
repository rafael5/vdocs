# vdocs-quality-crawl-integrity — implementation plan

Proposal: [`vdocs-quality-crawl-integrity.md`](vdocs-quality-crawl-integrity.md) ·
Tracker: [`vdocs-quality-crawl-integrity-tracker.md`](vdocs-quality-crawl-integrity-tracker.md) ·
Prompts: [`prompts/`](prompts/)

🥇 **This effort runs first in the `vdocs-quality-*` family — nothing gates it** (ordering revised 2026-08-03: scope decides what the collection contains, and the report card's retire/re-point decision depends on the scope ruling; every other effort waits on `CI ✓`).

Five steps, commit subjects `CI.0:` … `CI.4:`. House rules: TDD, `make check` green before commit, tick the tracker in the same commit.

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
  sections should not pass silently; that is CI.4's job, and the two should be read together.

*Tests first:* a fixture crawl returning materially less reds and leaves the prior artifact intact;
a crawl within tolerance passes; a first-ever crawl (no baseline) passes with the baseline recorded.

## CI.2 — Master-set retention

Once a document has been fetched, it stays in the collection. Removal from the VDL, an `archive`
relabel or a `decommissioned` relabel are recorded as facts about the document (CI.3), never as
reasons to drop it — VA deprecating a package does not remove its code from VistA, and the manual
for unmaintained-but-installed code is *more* needed, not less.

- The raw bytes already survive (write-once CAS); what must now survive a scope change is the
  *processed* document, its bundle and its presence in search.
- Guard the prune path (`kernel/cas.py:prune_bundles`) so it distinguishes *"never ours"* from
  *"ours, then relabelled"*. The existing withdrawn-document prune behaviour stays for the former.
- **Do not widen scope.** Retention protects what was already fetched; whether `decommissioned`
  applications should now be *admitted* is a product decision to surface, not to make here.

*Tests first:* a fetched document whose application flips to `decommissioned` (or out of scope)
survives in the collection with its label recorded; a never-fetched out-of-scope document is still
not admitted; the withdrawn-ghost-bundle behaviour is unchanged for documents that were never
retained.

## CI.3 — Lifecycle labels as first-class metadata

Persist `app_status`, `decommission_date`, `cots_dependent` and `out_of_scope_reason` from the
inventory through to the document in the collection, so a reader sees *"documents a deprecated
package; code still installed; commercially replaced in 2022"* instead of an absence. The inventory
model (`src/vdocs/models/catalog.py`) already carries the fields — this step is propagation and
visibility, not new capture.

*Tests first:* a document whose application carries the labels exposes them on the collection
surface; absent labels stay absent rather than defaulting.

## CI.4 — A baseline for what is in scope

Record the admitted set's composition each run and compare it to the previous one. Departures are
reported **by document identifier**, not as a count — the acquisition-chain work already established
that a net-zero count can hide a swap.

- A deliberate scope change is acknowledged in a curated registry entry (application, date, reason).
  Acknowledged departures pass; unacknowledged ones are a blocking finding naming the documents.
- Reuse the existing machinery rather than inventing: `validate` already performs a cross-run
  count-drop check and a five-seam reconciliation by identifier. This is the same pattern applied to
  the admission decision.
- The finding must name the *application* as well as the documents — departures arrive as coherent groups, and "XOBW, KAAJEE and LEX are no longer admitted" is the sentence an operator can
  act on.

*Tests first:* a removed application reds with its documents named; the same removal with an
acknowledgement passes; an unchanged set passes silently; a swap of equal size reds.

## Sequencing

CI.0 → CI.1 → CI.2 → CI.3 → CI.4. The floor is the cruder, cheaper net and catches the source-side
failure; retention and the labels make a relabel harmless and visible; the composition baseline
catches the rules-side failure — the net that a genuine departure (the thing the corrected 102-story
showed nothing watches) would hit.

## Verification on the live collection

After all five land: run the pipeline and confirm the collection stays green with the new baselines
recorded, then prove each gate bites on a **scratch copy** of the lake rather than the live one —
never induce a defect in the real collection to demonstrate a gate.

## Out of scope

Scheduling or automating crawls; changing politeness; admitting the 102 never-acquired documents
(XOBW/KAAJEE/LEX — a product question to surface, not decide); and any judgement about whether the
current scope rules are correct. This effort makes scope changes *visible*, not *right*.
