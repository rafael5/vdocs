# vdocs-quality-vdl-observatory — a timeline of the source, not just a copy of it

**Status: ACTIVE · proposed 2026-08-03 · revised 2026-08-05 after adversarial review** ·
Plan: [`vdocs-quality-vdl-observatory-implementation-plan.md`](vdocs-quality-vdl-observatory-implementation-plan.md) ·
Tracker: [`vdocs-quality-vdl-observatory-tracker.md`](vdocs-quality-vdl-observatory-tracker.md) ·
Prompts: [`prompts/`](prompts/) ·
Sibling: [`../vdocs-quality-crawl-integrity/`](../vdocs-quality-crawl-integrity/)

> ## ⛔ Standing rules (revised 2026-08-05)
>
> **1. There is no shared snapshot mechanism to wait for.** The original rule sequenced this effort
> after `crawl-integrity` "to avoid inventing a snapshot format twice." Crawl-integrity closed
> (2026-08-03) having built a floor, retention, label capture and a composition baseline — **and no
> snapshot mechanism** (its own CI.0 baseline records "historical snapshots: none";
> `crawl/stage.py` still overwrites bronze in place). VO.2 is greenfield. The sequencing gate is
> satisfied and void.
>
> **2. Fixed endpoints, not discovery.** Every item below has a measurable endpoint and a
> definition of done. When the DoD is met, the item is closed — no extending scope mid-flight.
> Measurement questions that arise during implementation are recorded as candidates for a *future*
> proposal, not chased.

## Bottom line up front

### Table 1 — High priority: survives adversarial review, actively recommended

| # | Item | Measurable endpoint | Definition of done |
|---|---|---|---|
| **VO.0** | **Bank the current inventory NOW** — one manual dated copy, before the pending `vdocs fetch --all` / any re-crawl can trigger an overwrite. No design work; a copy command. | `$DATA_DIR/inventory/snapshots/2026-06-10/` exists holding copies of `bronze/catalog.raw.{json,csv}` and `gold/inventory.{json,csv}` + a one-paragraph `SNAPSHOT.md` naming the source crawl (2026-06-10 per `stage_runs`) | `sha256sum` of each copy equals its original; done **before** the +174 fetch/rebuild |
| **VO.2** | Immutable dated snapshot on every successful crawl — **bronze layer only** (the source of record). Snapshot identity = canonical content hash over sorted (section, app, doc) rows, not file bytes. | `crawl` writes `snapshots/<crawl-date>/catalog.raw.json` in the same run that writes bronze | Three tests green: (a) two crawls → two snapshots; (b) the earlier snapshot is byte-identical after the later crawl; (c) a re-crawl with identical canonical content creates **no** new snapshot |
| **VO.3** | Timeline delta between any two snapshots, **keyed on the VDL's own numeric ids** (`appid`/`secid`, already captured in every crawled URL) — never on parsed names. | One command/report: per-section counts by `app_status` and doc count deltas between two named snapshots | Fixture tests green: an app renamed but keeping its `appid` reports as a rename, not a departure+arrival; an unchanged section reports **0**, not absent |
| **VO.4a** | Mass-transition tripwire. `app_status` is a **regex over a display suffix** (`" - ARCHIVE"`, `crawl_pure.py:24`), so a VDL cosmetic change would read as mass lifecycle change. | Delta report emits `SUSPECT-PARSER` and **zero** transition rows when >5% of apps change status in one delta | Fixture test green: a cosmetic suffix change across all apps → one `SUSPECT-PARSER` flag, no transitions; a single genuine transition → one row, no flag |
| **VO.5** | **Close it.** Composition is answered ([`vo5-archive-meaning-findings.md`](vo5-archive-meaning-findings.md)); VA's *intent* is declared **unestablished** — a timeline starting 2026 cannot explain labels applied 2005–2022. | Findings file carries the explicit "intent: unestablished, and why" paragraph | Tracker VO.5 ✅; no further intent work scheduled anywhere |

Order: VO.0 immediately (it is insurance, not design), then VO.2 → VO.3 → VO.4a. VO.5 closes with a
paragraph, independent of the rest.

### Table 2 — Lower priority: optional, only after Table 1 is done

| # | Item | Measurable endpoint | Definition of done |
|---|---|---|---|
| VO.1 | Fill-rate report of the unused fields (`cots_dependent` 404, `decommission_date` 115, `out_of_scope_reason`). Largely covered by CI.0 already. | One report file under `reports/` | Distributions + fill rates listed; **no** new questions opened from it |
| VO.4b | Transition rows in the delta report (status change, decommission date arriving, `cots_dependent` set) — **as report rows, not a new channel** | Delta report lists transitions by `appid` with both states named | Fixture test: one transition between two snapshots → exactly one row |
| VO.3b | Gold-layer snapshots stamped with the registry/code fingerprint that produced them (for auditing *our* classifier drift, distinct from VDL drift) | Each gold snapshot carries the producing fingerprint | Only if a concrete classifier-drift question arises; otherwise never |

### Table 3 — Rejected or counterproductive

| Item | Why rejected |
|---|---|
| Waiting on crawl-integrity's "shared snapshot mechanism" | It was never built; the premise was false. Waiting longer loses data points for nothing. |
| Keying the timeline on parsed names / `app_code` | Both are extracted from the display string; a VA rename reads as decommission+birth. `appid`/`secid` are stable and already captured. |
| Building the timeline on the **gold** inventory | Gold embeds our registry-driven classification; deltas would conflate VDL change with our classifier change — the known "different ruler" landmine. Bronze is the source of record. |
| A new alerting/event channel for VO.4 | The pipeline has no event surface, and this effort will not add one. A row in the delta report is the deliverable. |
| Backfilling history | Manufactures data. The timeline starts at VO.0's banked snapshot. (Unchanged from the original proposal.) |
| Establishing VA's *intent* behind `archive` via the timeline | Open-ended discovery with no reachable endpoint from a 2026-start record. Closed as unestablished (Table 1, VO.5). |
| Storage-growth engineering (compression, pruning, rotation) | ~18 MB per crawl at a roughly monthly cadence is a non-issue. Revisit only if `snapshots/` exceeds 2 GB. |

## 1. Background — in plain terms

Today the pipeline treats the VA VistA Document Library as a **place to copy from**. It crawls the
site, takes what is currently there, and overwrites what it knew before. Ask "how many technical
manuals did the VDL list last quarter?" or "which packages have been marked deprecated this year?"
and there is no answer, because nothing was kept.

That is a missed opportunity, because **the VDL is itself a primary source about VistA's direction**.
VA marks each application `active`, `archive` or `decommissioned`, records a decommission date, and
flags whether a package depends on a commercial product. A record of how those labels change over
time is evidence about the modernisation of the system that no single snapshot contains.

Two things a timeline answers that a single snapshot cannot: **which parts of VistA are being
retired, and how fast** (rate of change per section), and **what replaced them** (a move to
`decommissioned` with a commercial-dependency flag is the visible half of a procurement decision).

> ⚠️ **The archive-share question is largely answered** (VO.5, 2026-08-04). Never quote "38.2%
> archive" unqualified: **36% of that share is VBA benefits forms**, not documentation — the genuine
> documentation share is 2,170 records, of which 69.6% are older/duplicate copies. `consolidate`
> already folds the duplicates, and 0 of the 55 surviving archive documents have an active twin.
> What remains open is VA's *intent*, which this effort closes as unestablished (Table 1).

## 2. What this costs the end user

**Nothing in a search result — this is analytical capability, not retrieval.** The researcher is the
primary audience: questions like *"which packages is VA retiring, and what are they buying
instead?"* are this project's stated purpose, and today they are unanswerable from our own data
despite the signal arriving on every crawl and being thrown away. Second-order benefit to search:
a deprecated, commercially-replaced package's manual can be **labelled** rather than hidden.

## 3. What we measured

Source crawl 2026-06-10 (the only one held; measured 2026-08-03), 8,907 records:

| VA lifecycle label (`app_status`) | records | share |
|---|---:|---:|
| `active` | 5,379 | 60.4% |
| `archive` | 3,404 | 38.2% — **see §1 warning: 36% of this is VBA forms** |
| `decommissioned` | 124 | 1.4% |

Captured and unused: `cots_dependent` **404** · `decommission_date` **115** (2005–2022) ·
`out_of_scope_reason` (internal only). Historical snapshots: **none** — single-copy files,
overwritten on every explicit crawl (`crawl` is FORCE_ONLY, so overwrite happens only when a crawl
is requested — but the pending +174 fetch/rebuild makes the next one likely soon).

Two provenance facts the design must respect (adversarial review, 2026-08-05):

- **`app_status` is parsed, not served**: a regex over the application's displayed name suffix
  (`" - ARCHIVE"` / `" - DECOMMISSIONED <date>"`). Hence VO.4a's tripwire.
- **Stable identity exists and is already captured**: every application URL carries `appid=N`,
  every section `secid=N`. Hence VO.3's keying rule.

## 4. Design constraints (what keeps this out of rabbit holes)

1. **Bronze is the timeline's substrate.** VA's raw statement, before any of our classification.
2. **Identity = VDL numeric ids.** Names are display strings; ids are keys.
3. **A snapshot is evidence**: dated, immutable, named by its crawl, deduplicated by canonical
   content hash (sorted rows) so re-runs and page reorders cannot fabricate history.
4. **Deliverables are reports and tests, not services.** No event channel, no dashboard, no store
   beyond files in the existing inventory medallion.
5. **Every item stops at its DoD.** New questions found en route are written down for later, not
   pursued.

## 5. Scope notes

- **Fetching/admission stays with [`crawl-integrity`](../vdocs-quality-crawl-integrity/)** — this
  effort observes and records. **Recorded exception:** the completeness workstream VO.6–VO.9
  (fetch targets 1,044 → 1,218) landed under this effort's tracker on explicit operator sign-off of
  [`archive-inclusion-and-exclusion-accounting-proposal.md`](archive-inclusion-and-exclusion-accounting-proposal.md)
  — a deliberate override of this boundary, not a precedent.
- **Not inferring VA's intent.** A label change is evidence of a decision, not an explanation of it.
- **Not backfilling.** The timeline starts at VO.0's banked snapshot.

## 6. Acceptance

Table 1's DoD column **is** the acceptance criteria. The effort is done when all five rows are ✅ in
the tracker; Table 2 items are explicitly not required for closure.

## 7. References

**Evidence**
- Inventory measurements 2026-08-03 (crawl of 2026-06-10): reproducible from
  `$DATA_DIR/inventory/gold/inventory.json`
- Archive-share findings: [`vo5-archive-meaning-findings.md`](vo5-archive-meaning-findings.md)
- Adversarial review 2026-08-05: findings folded into this revision (standing rule 1, Tables 1–3,
  §3 provenance facts)

**Mechanism**
- Crawl stage (overwrite semantics, FORCE_ONLY, status regex): `src/vdocs/stages/crawl/`
- The inventory model carrying the lifecycle fields: `src/vdocs/models/catalog.py`
- The inventory medallion (`inventory/bronze|silver|gold`):
  [`../../vdocs-design.md`](../../vdocs-design.md) §4/§5.3

**Domain context**
- The VDL as a catalogue — the `vdl` domain knowledge skill
- [`../vdl-content-quality-and-ia-strategy.md`](../vdl-content-quality-and-ia-strategy.md)
