# vdocs-quality-crawl-integrity — watch the front door, and never lose a document

**Status: DRAFT · proposed 2026-08-03 · reordered to FIRST 2026-08-03** ·
Plan: [`vdocs-quality-crawl-integrity-implementation-plan.md`](vdocs-quality-crawl-integrity-implementation-plan.md) ·
Tracker: [`vdocs-quality-crawl-integrity-tracker.md`](vdocs-quality-crawl-integrity-tracker.md) ·
Prompts: [`prompts/`](prompts/) · Register rows: **R‑4**, **R‑19** ·
Sibling: [`../vdocs-quality-vdl-observatory/`](../vdocs-quality-vdl-observatory/)

> ## 🥇 This effort runs first — ahead of the report card
>
> **Scope decides what the collection contains, and everything else is measured against that.** The
> report card's six unanswerable questions are a *scope* artefact, and repairing the key before the
> scope policy is settled risks retiring questions that a corrected policy would make answerable
> again. Fix the boundary, then fix the instrument that measures inside it.
>
> **Measure before you act.** CI.0 records what the crawl currently yields and what the admission
> gate currently keeps. No floor, gate or retention rule lands before those numbers exist — a floor
> built without knowing the floor level is a guess with a threshold on it.

## Contents

- [1. Background — in plain terms](#1-background--in-plain-terms)
- [2. What this costs the end user](#2-what-this-costs-the-end-user)
- [3. What we measured](#3-what-we-measured)
- [4. A correction to this proposal's own first draft](#4-a-correction-to-this-proposals-own-first-draft)
- [5. Proposal](#5-proposal)
- [6. What we are deliberately not doing](#6-what-we-are-deliberately-not-doing)
- [7. Cost and benefit](#7-cost-and-benefit)
- [8. Acceptance](#8-acceptance)
- [9. Risks](#9-risks)
- [10. References](#10-references)

## 1. Background — in plain terms

The collection is built by crawling a public VA website (the VistA Document Library), deciding which
manuals are in scope, downloading them, and processing them. Seven phases of recent work made sure
that **once a document is in, nothing loses it** — every hand-off is reconciled and the run ends on
a soundness verdict that fails loudly.

**None of that watches the front door.** If the VA site has a bad day, the crawl simply finds less
and the smaller result becomes the new truth. If a scoping rule changes, whole product areas move in
or out. Nothing compares today's crawl to yesterday's, and nothing records what the source looked
like at any point in time.

There is a second, sharper problem, and it is about **what VA's own labels do to us**. The VDL marks
applications `active`, `archive` or `decommissioned`. Today the admission gate keeps archived
applications but excludes **every** decommissioned one. That is a policy decision nobody made
explicitly, and it is the wrong default for this corpus:

**VA deprecating a package does not remove the code from VistA.** The routines are still installed,
still running, and still need documentation explaining what they do and why they exist. A site
running that code has *more* need of the manual, not less, precisely because nobody is maintaining
it any more. And deprecation is itself a signal worth keeping: when VA retires a package it is
usually because a commercial product replaced it, which is exactly the kind of fact someone
researching VistA's direction needs to know.

So the rule this effort establishes is: **once we have fetched a document, we keep it.** The
collection is a master set that only grows. VA's lifecycle labels become *metadata we record*, never
a reason to discard something we already hold.

## 2. What this costs the end user

**Today, in search results: nothing.** No result changes when this ships.

**What it prevents is the failure that looks like success.** A user searches for a manual that the
collection used to hold. Nothing is returned, everything reports healthy, and there is no record of
when or why it left. The user cannot distinguish "never covered" from "covered last month", and
their only rational conclusion is that the collection is unreliable — a far more expensive belief
than any single missing document.

**What it prevents specifically, and this is the live risk:** a document we already downloaded being
dropped because VA relabelled its application. The pipeline removes documents that fall out of scope
— that behaviour is deliberate and tested (a withdrawn document should not leave a ghost bundle) —
but it makes no distinction between *"this was never ours"* and *"we have had this for a year and VA
just marked the package deprecated"*. For a corpus documenting code that is still running in
production hospitals, the second case is exactly the one worth keeping.

## 3. What we measured

Verified on the code, the inventory and the production collection, 2026-08-02/03.

**Gating — there is none at the front:**

| | |
|---|---|
| completeness check on `crawl` / `catalog` | **none** — no gate, no floor, either stage |
| behaviour on a degraded crawl | the smaller result overwrites the previous good one |
| historical snapshots of the source | **none** — inventory files are single-copy, overwritten each crawl |

**What VA's labels do to admission today:**

| `app_status` | inventory records | admitted | share admitted |
|---|---:|---:|---:|
| `active` | 5,379 (60.4%) | 1,604 | 29.8% |
| `archive` | **3,404 (38.2%)** | 589 | 17.3% |
| `decommissioned` | 124 (1.4%) | **0** | **0.0%** |
| **total** | **8,907** | | |

So archived applications *are* partly admitted — the corpus already contains 589 of them — while
decommissioned ones are excluded outright. That asymmetry is undocumented and, on the reasoning
above, backwards.

**Signals VA gives us that we capture and then ignore:**

| field | records carrying it | used anywhere? |
|---|---:|---|
| `cots_dependent` (replaced by a commercial product) | **404** | no |
| `decommission_date` (spanning 2005–2022) | **115** | no |
| `out_of_scope_reason` | present in the model | not surfaced |

**Retention today:** 1,040 documents fetched, 1,034 distinct payloads in the raw store (six pairs are
byte-identical siblings — the P1 finding). The raw store is write-once, so the *bytes* of anything
ever fetched survive; what does not survive a scope change is the processed document, its bundle and
its presence in search.

## 4. A correction to this proposal's own first draft

The first version of this proposal claimed that **102 documents (XOBW 23, KAAJEE 64, LEX 15) had left
the collection with nothing reporting it.** That is false, and the correction matters because it was
this proposal's headline evidence.

Those applications were **never acquired in production** — `acquisitions = 0` for all three. They
appear in the golden answer key because the key was curated against the **dev lake** (451 documents),
which admits applications production does not. It is the same dev-lake contamination that made three
consecutive retrieval measurements read the wrong corpus; having found one instance, I inferred a
second, more dramatic one instead of checking.

**What survives the correction:** nothing tracks the admitted set's composition over time, so a real
departure *would* be equally silent. The gap is genuine; the dramatic proof of it was not. That is
also the strongest possible argument for this effort's own measure-first rule.

## 5. Proposal

**5.1 A completeness floor on the crawl.** A crawl finding materially less than the last good one
fails instead of overwriting it, and the previous good result stays until a human looks.

**5.2 A master-set retention rule.** Once a document has been fetched, it stays in the collection.
Removal from the VDL, an `archive` relabel or a `decommissioned` relabel are recorded as facts about
the document, never as reasons to drop it. Search may *rank* or *badge* such documents differently;
it does not lose them.

**5.3 Capture VA's lifecycle labels as first-class metadata.** Persist `app_status`,
`decommission_date`, `cots_dependent` and `out_of_scope_reason` through to the collection, so a user
or an assistant can see *"this documents a deprecated package — the code is still installed; VA
replaced the package with a commercial product in 2022"*. That sentence is more useful than the
document's absence.

**5.4 An admitted-set composition baseline.** Record what is admitted each run and report departures
by document identifier, with a deliberate change acknowledged in a curated file rather than passing
silently.

## 6. What we are deliberately not doing

- **Not deciding the scope policy by ourselves.** Whether decommissioned applications should now be
  admitted is a product decision. This effort surfaces the choice with its numbers and implements
  whatever is ruled — it does not quietly widen the corpus.
- **Not re-crawling on a schedule or changing politeness.** The crawl stays operator-triggered.
- **Not building the longitudinal analysis here.** The timeline of the source — rate of change per
  segment, tag trends, the "why is 38% archived?" question — is a distinct capability, proposed
  separately as [`vdocs-quality-vdl-observatory`](../vdocs-quality-vdl-observatory/).

## 7. Cost and benefit

**Cost:** low-to-moderate. The floor and the composition baseline are variations on gates already
proven elsewhere in the pipeline. The retention rule is mostly a policy change plus a guard against
the existing prune path.

**Benefit:** no direct improvement to search results, but it is the precondition for trusting any
other measurement — and the retention rule protects documentation for code that is still running,
which is the corpus's whole reason to exist.

**Why first:** scope defines the collection. The report card's unanswerable questions are a scope
artefact, and retiring them before the scope policy is settled could delete questions a corrected
policy would make answerable.

## 8. Acceptance

- A deliberately shrunken crawl **fails** and leaves the previous good result untouched.
- A document that has been fetched **cannot** be removed by a scope or lifecycle relabel — proven by
  a test that reds if it is.
- VA's lifecycle labels are visible on a document in the collection, including its decommission date
  and commercial-replacement flag where VA supplies them.
- An unacknowledged change in the admitted set **fails**, naming the documents; an acknowledged one
  passes.
- The live collection stays green throughout.

## 9. Risks

- **Widening scope silently.** The retention rule only protects what we already fetched; it must not
  become an accidental argument for fetching everything. Scope stays a deliberate, recorded decision.
- **A floor set too tight cries wolf** and gets disabled, which is worse than no floor. Tolerance
  against the last *good* crawl, and acknowledging a legitimate change must stay cheap.
- **Totals hide swaps.** Losing 20 documents and gaining 20 nets to zero; composition is compared by
  identifier, not by count — the lesson the acquisition-chain work already paid for.
- **Keeping deprecated documents can mislead** if they are presented as current. Mitigation is 5.3:
  the lifecycle label travels *with* the document so a reader sees the status rather than inferring
  currency from presence.

## 10. References

**Findings and evidence**
- Register rows **R‑4** (no crawl completeness floor; empty crawl overwrites) and **R‑19** (scope
  changes unmeasured; corrected 2026-08-03) —
  [`../../reference/pipeline-adversarial-audit.md`](../../reference/pipeline-adversarial-audit.md)
- Programme rationale —
  [`../search-quality-and-scope-integrity-implementation-plan.md`](../search-quality-and-scope-integrity-implementation-plan.md)

**The machinery to reuse or guard**
- Admission gate: `src/vdocs/stages/fetch/policy.py`, `src/vdocs/stages/fetch/fetch_pure.py`
  (`select_fetch_targets`)
- Chain reconciliation and cross-run drop checks: `src/vdocs/stages/validate/chain_pure.py`,
  `reconcile_pure.py`
- The prune path a retention rule must guard: `kernel/cas.py:prune_bundles`
- Inventory model carrying the lifecycle fields: `src/vdocs/models/catalog.py`

**Related**
- [`../vdocs-quality-vdl-observatory/`](../vdocs-quality-vdl-observatory/) — the longitudinal record
  of the source, including the archived-share question
- [`../../historical/pipeline-audit-remediation-tracker.md`](../../historical/pipeline-audit-remediation-tracker.md)
  — P1, where six documents did genuinely collapse out of the collection
