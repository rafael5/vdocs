# vdocs-quality-vdl-observatory — a timeline of the source, not just a copy of it

**Status: DRAFT · proposed 2026-08-03** ·
Plan: [`vdocs-quality-vdl-observatory-implementation-plan.md`](vdocs-quality-vdl-observatory-implementation-plan.md) ·
Tracker: [`vdocs-quality-vdl-observatory-tracker.md`](vdocs-quality-vdl-observatory-tracker.md) ·
Prompts: [`prompts/`](prompts/) ·
Sibling: [`../vdocs-quality-crawl-integrity/`](../vdocs-quality-crawl-integrity/)

> ## ⛔ Two standing rules
>
> **1. Runs after [`vdocs-quality-crawl-integrity`](../vdocs-quality-crawl-integrity/).** That effort
> establishes the snapshot and the retention rule this one builds a timeline on top of. Starting here
> first would mean inventing a snapshot format twice.
>
> **2. Measure before you act.** VO.1 is a measurement of what the current inventory already tells us
> — several of the signals below are captured today and simply unused. Nothing is built before we
> know what is already there.

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

Today the pipeline treats the VA VistA Document Library as a **place to copy from**. It crawls the
site, takes what is currently there, and overwrites what it knew before. Ask "how many technical
manuals did the VDL list last quarter?" or "which packages have been marked deprecated this year?"
and there is no answer, because nothing was kept.

That is a missed opportunity, because **the VDL is itself a primary source about VistA's direction**.
VA marks each application `active`, `archive` or `decommissioned`, records a decommission date, and
flags whether a package depends on a commercial product. Those labels are VA telling us, in public,
which parts of VistA are being retired and what is replacing them. A record of how those labels
change over time is evidence about the modernisation of the system that no single snapshot contains.

Two specific things a timeline would answer that today's single snapshot cannot:

- **Which parts of VistA are being retired, and how fast?** Rate of change per section of the
  library, not a total.
- **What replaced them?** A package moving to `decommissioned` with a commercial-dependency flag is
  the visible half of a procurement decision.

And one question we cannot currently answer at all: **38% of the library is marked `archive` — why?**
That is 3,404 of 8,907 records. It could mean superseded documentation, retired packages, or simply
an editorial convention for older material. The answer changes how much of the corpus should be
treated as historical, and nobody has established it.

## 2. What this costs the end user

**Nothing in a search result — this is analytical capability, not retrieval.** It is the one effort
in the family whose value is to the *researcher* rather than to the person running a query.

But that researcher is the primary audience of this project. The stated purpose of vdocs is
documenting and leveraging VistA's documentation corpus for analytical work, and questions like
*"which packages is VA retiring, and what are they buying instead?"* are exactly that work. Today
they are unanswerable from our own data despite the signal arriving on every crawl and being thrown
away.

There is also a second-order benefit to search: knowing that a package is deprecated and
commercially replaced lets a result be **labelled** rather than hidden — the reader gets the manual
*and* the context that its code is legacy.

## 3. What we measured

Production inventory, 2026-08-03 (8,907 records):

| VA lifecycle label (`app_status`) | records | share |
|---|---:|---:|
| `active` | 5,379 | 60.4% |
| `archive` | **3,404** | **38.2%** |
| `decommissioned` | 124 | 1.4% |

| signal already captured, currently unused | records |
|---|---:|
| `cots_dependent` — package depends on a commercial product | **404** |
| `decommission_date` — spanning **2005–2022** | **115** |
| `out_of_scope_reason` | present in the model, not surfaced |

| | |
|---|---|
| historical snapshots of the inventory | **none** — single-copy files, overwritten every crawl |
| oldest evidence of the source's past state | none beyond the current crawl |

So the raw material for a timeline is *already arriving*; it is being discarded. The first
snapshot cannot be backdated — which is the argument for starting the record soon rather than
perfectly.

## 4. Proposal

**4.1 Keep every inventory snapshot.** Preserve each crawl's inventory as a dated, immutable record
rather than overwriting it. Small, cheap, and the only step that cannot be done retroactively.

**4.2 Build the timeline view.** Counts and composition per crawl — by library section, by document
type, by application status — so rate of change is a query rather than an archaeology project.

**4.3 Track the lifecycle labels as signals.** Surface transitions: an application moving
`active → archive → decommissioned`, the arrival of a decommission date, a commercial-dependency
flag appearing. These are the events worth alerting on.

**4.4 Answer the archived-share question.** Establish what `archive` actually means in VA's usage —
by sampling records, comparing against what the documents themselves say, and checking whether
archived applications' code is still present in VistA. Record the finding; it determines how much of
the corpus is historical rather than current.

## 5. What we are deliberately not doing

- **Not changing what is fetched.** Scope decisions belong to
  [`crawl-integrity`](../vdocs-quality-crawl-integrity/); this effort observes and records.
- **Not inferring VA's intent.** A label change is evidence of a decision, not an explanation of it.
  Where we cannot establish *why*, we record *what* and say the why is unknown.
- **Not backfilling history we do not have.** The timeline starts when we start keeping snapshots.
  Pretending otherwise would manufacture data.

## 6. Cost and benefit

**Cost:** low for 4.1 (keep what we already produce), low-moderate for 4.2/4.3, and 4.4 is research
rather than engineering.

**Benefit:** no search improvement; a genuinely new analytical capability aimed at this project's
core purpose, plus context that makes deprecated documents useful rather than confusing.

**Why it is sequenced after crawl-integrity but need not wait for the retrieval efforts:** it shares
the snapshot mechanism with crawl-integrity and is otherwise independent. **4.1 in particular is
time-sensitive** — every crawl that overwrites its predecessor is a data point permanently lost.

## 7. Acceptance

- Every crawl's inventory is preserved as a dated record, and two consecutive crawls can be
  compared without re-crawling.
- Counts and composition over time are queryable by section, document type and status.
- A lifecycle transition (including a new decommission date or commercial-dependency flag) is
  visible as an event.
- The archived-share question has a written answer with its evidence — or an explicit statement that
  it could not be established and why.

## 8. Risks

- **Snapshot growth.** Keeping every crawl costs storage. Mitigation: the inventory is small relative
  to the documents themselves; keep the structured record, not another copy of the payloads.
- **Reading intent into labels.** "Deprecated" is VA's word and its operational meaning may vary by
  section. Mitigation: 4.4 establishes the meaning before the timeline is interpreted, and unknowns
  stay labelled unknown.
- **A timeline nobody consults.** Mitigation: 4.3's transitions are the useful surface — an event
  someone can be told about beats a table someone must remember to query.

## 9. References

**Evidence**
- Inventory measurements, 2026-08-03: `app_status` distribution, `cots_dependent` (404),
  `decommission_date` (115, 2005–2022), and the absence of historical snapshots — reproducible from
  `$DATA_DIR/inventory/gold/inventory.json`
- Sibling effort establishing scope and retention:
  [`../vdocs-quality-crawl-integrity/`](../vdocs-quality-crawl-integrity/)

**Mechanism**
- Crawl and catalog stages: `src/vdocs/stages/crawl/`, `src/vdocs/stages/catalog/`
- The inventory model carrying the lifecycle fields: `src/vdocs/models/catalog.py`
- The inventory medallion (`inventory/bronze|silver|gold`) described in
  [`../../vdocs-design.md`](../../vdocs-design.md) §4/§5.3

**Domain context**
- The VDL as a catalogue and its structure — the `vdl` domain knowledge skill
- [`../vdl-content-quality-and-ia-strategy.md`](../vdl-content-quality-and-ia-strategy.md)
