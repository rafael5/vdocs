# vdocs-quality-crawl-integrity — watch the front door

**Status: DRAFT · proposed 2026-08-03** ·
Plan: [`vdocs-quality-crawl-integrity-implementation-plan.md`](vdocs-quality-crawl-integrity-implementation-plan.md) ·
Tracker: [`vdocs-quality-crawl-integrity-tracker.md`](vdocs-quality-crawl-integrity-tracker.md) ·
Prompts: [`prompts/`](prompts/) · Register rows: **R‑4**, **R‑19**

## Contents

- [1. Background — in plain terms](#1-background--in-plain-terms)
- [2. What this costs the end user](#2-what-this-costs-the-end-user)
- [3. What we measured](#3-what-we-measured)
- [4. Proposal](#4-proposal)
- [5. What we are deliberately not doing](#5-what-we-are-deliberately-not-doing)
- [6. Cost and benefit](#6-cost-and-benefit)
- [7. Acceptance](#7-acceptance)
- [8. Risks](#8-risks)
- [9. References](#9-references)

## 1. Background — in plain terms

The collection is built by crawling a public VA website, deciding which manuals are in scope,
downloading them, and processing them. Seven phases of recent work went into making sure that
**once a document is in, nothing loses it**: every hand-off between processing steps is now
reconciled, every record is checked against the file it describes, and the whole run ends on a
soundness verdict that fails loudly.

**None of that watches the crawl itself.**

If the VA website has a bad day — a page times out, a section fails to render, a listing changes
shape — the crawl simply finds less. If a scoping rule changes, whole product areas can drop out.
Either way the collection quietly shrinks, and **every downstream check still reports "all good"**,
because those checks confirm that the processing steps agree *with each other*. They have no opinion
about whether something went missing before the first of them ran.

This is not a theoretical gap. **102 documents left the collection at some point and nothing
reported it.** We found out weeks later, by accident, because a test question suddenly had no
answer.

## 2. What this costs the end user

**Today: nothing.** This is a smoke alarm, not a renovation. Shipping it changes no search result.

**The failure it prevents is the worst kind in this system**, because it is silent and it looks like
success. A user searches for a manual that used to be there and gets nothing back. Everything reports
healthy. There is no error, no warning, and no record of when the manual left or why — so the user
cannot tell "this was never covered" from "this was covered last month". Their only rational
conclusion is that the collection is unreliable, which is a far more expensive belief than any single
missing document.

The same silence protects a *legitimate* scope change from scrutiny. Excluding three product areas
was a defensible decision; the problem is that it happened without a record, so nobody could
distinguish it from a fault, and it took a broken test question to surface it.

Given how much effort went into guaranteeing nothing is lost *inside* the pipeline, leaving the
entrance unwatched is the obvious remaining hole.

## 3. What we measured

Verified on the code and the production collection, 2026-08-02/03:

| | |
|---|---|
| completeness check on `crawl` | **none** — no gate, no floor |
| completeness check on `catalog` | **none** |
| behaviour on a degraded crawl | a smaller result overwrites the previous good one |
| documents that left the admitted set unreported | **102** (XOBW 23, KAAJEE 64, LEX 15) |
| how it was found | a golden question broke, ~4 weeks later |
| what the existing chain gate proves | the five processing seams agree **with each other** |
| what nothing proves | that the admitted set is the same shape it was yesterday |
| crawl politeness delay (for cost estimates) | 1.5 s per page against `https://www.va.gov/vdl/` |

For contrast, the checks that *do* exist downstream: the acquisition chain is reconciled across five
independent sources; sidecar counts are compared against the previous run and a drop is a blocking
finding; every gold bundle is verified against a signed manifest; the run ends on a 20-check
soundness gate. The machinery for exactly this kind of check is already built and proven — it simply
has never been pointed at the front door.

## 4. Proposal

**4.1 A completeness floor on the crawl.** A crawl that finds materially less than the last good one
fails instead of overwriting it. The previous good crawl stays in place until a human looks. This is
the same "a drop is a finding" rule the pipeline already applies to sidecar counts, applied one step
earlier.

**4.2 A baseline for what is in scope.** Record the admitted set's composition each run and compare
it to the previous one, reporting departures by document identifier. A deliberate scope change then
becomes a one-line acknowledgement in a curated file; an accidental one becomes a blocking finding
that names exactly which documents left.

Together these close the two halves of the same hole: 4.1 catches "the source gave us less", 4.2
catches "our own rules admitted less".

## 5. What we are deliberately not doing

- **Not re-crawling on a schedule, and not touching politeness.** The crawl stays operator-triggered
  and polite; this effort adds a check, not traffic.
- **Not preventing scope changes.** Excluding an application is a legitimate decision. The goal is
  that it is *recorded and visible*, not that it is blocked.
- **Not attempting to recover the 102 documents.** Whether XOBW, KAAJEE and LEX should be back in
  scope is a separate product question this effort deliberately does not answer — it only ensures the
  next such change is announced.

## 6. Cost and benefit

**Cost:** low-to-moderate. Both pieces are variations on gates that already exist and are proven
elsewhere in the pipeline; neither requires new concepts.

**Benefit:** no direct improvement to search results — this is insurance. Its value is that the
failure it prevents is invisible, arbitrarily large, and currently has no upper bound: there is no
number of documents that could vanish and trigger an alert.

**Why third of five:** ranked below the two efforts that improve what a user actually gets today, and
above the two that are decisions about dormant features. Insurance is worth buying, after the roof.

## 7. Acceptance

- A deliberately shrunken crawl **fails** and leaves the previous good result untouched.
- A deliberately removed application **fails**, naming the departed documents by identifier.
- A genuine, acknowledged scope change passes cleanly with its acknowledgement recorded.
- The live collection stays green throughout — this adds a check, not a change in behaviour.

## 8. Risks

- **False alarms on legitimate change.** The VDL genuinely changes; a floor set too tight will cry
  wolf and get disabled, which is worse than not having it. Mitigation: compare against the last
  *good* crawl with a tolerance, and make acknowledging a change cheap.
- **A floor that only measures totals can miss a swap.** Losing 20 documents and gaining 20 others
  nets to zero. Mitigation: 4.2 compares composition by identifier, not just the count — the same
  lesson the acquisition-chain work already paid for.
- **Insurance is easy to defer forever.** It never wins a comparison against a feature. Mitigation:
  it is sequenced explicitly here rather than left to compete for attention.

## 9. References

**Findings and evidence**
- Register rows **R‑4** (no crawl completeness floor; empty crawl overwrites) and **R‑19** (scope
  changes unmeasured; the answer key rotted against them) —
  [`../../reference/pipeline-adversarial-audit.md`](../../reference/pipeline-adversarial-audit.md)
- Programme rationale and ordering —
  [`../search-quality-and-scope-integrity-implementation-plan.md`](../search-quality-and-scope-integrity-implementation-plan.md)

**The machinery to reuse**
- The acquisition-chain gate (five seams reconciled by document identifier) and the cross-run
  count-drop check — `src/vdocs/stages/validate/` (`chain_pure.py`, `reconcile_pure.py`)
- The admission gate whose decisions need recording — `src/vdocs/stages/fetch/policy.py`
- `src/vdocs/stages/crawl/stage.py`, `src/vdocs/stages/catalog/stage.py` — the two ungated stages

**Precedent for the failure class**
- [`../../historical/pipeline-audit-remediation-tracker.md`](../../historical/pipeline-audit-remediation-tracker.md)
  — P1, where six documents were found to have collapsed silently out of the collection, and the
  chain gate that was built in response
- [`../../session-summaries/2026-08-01-pipeline-audit-and-p1.md`](../../session-summaries/2026-08-01-pipeline-audit-and-p1.md)
