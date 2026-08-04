# vdocs-quality-vdl-observatory — tracker

| Step | What lands | Status | Commit / notes |
|------|-----------|--------|----------------|
| VO.1 | **Measure first** — what the current inventory already tells us (labels, dates, commercial-dependency flags) and what it cannot | ☐ | |
| VO.2 | Every crawl's inventory preserved as a dated, immutable record — **time-sensitive** | ☐ | |
| VO.3 | Timeline view: counts and composition per crawl, by section, document type and status | ☐ | |
| VO.4 | Lifecycle transitions surfaced as events (status change, decommission date, commercial-dependency flag) | ☐ | |
| VO.5 | The archived-share question answered with evidence — or declared unestablished, with why | 🟡 | **Composition answered ahead of the effort** (operator hypothesis, measured 2026-08-04): [`vo5-archive-meaning-findings.md`](vo5-archive-meaning-findings.md). **36% of the archive share is VBA benefits forms, not documentation**; of the genuine 2,170, **69.6% are older/duplicate copies** (72.2% older, 25.7% same version, 2.1% newer) and the rest are release-pinned documents. ⚠️ **But archive is NOT redundant in our corpus** — `consolidate` already folds the duplicates, and **0 of the 55 surviving archive documents have an active twin**. VA's *intent* stays unestablished; that needs VO.2–VO.4 |
| VO ✓ | Two consecutive crawls comparable without re-crawling; transitions visible; `archive` meaning recorded | ☐ | |

Proposal: [`vdocs-quality-vdl-observatory.md`](vdocs-quality-vdl-observatory.md) ·
Plan: [`vdocs-quality-vdl-observatory-implementation-plan.md`](vdocs-quality-vdl-observatory-implementation-plan.md) ·
Prompts: [`prompts/`](prompts/)

⛔ **Runs after [`vdocs-quality-crawl-integrity`](../vdocs-quality-crawl-integrity/)** — it shares that
effort's snapshot mechanism and retention rule.
⏳ **VO.2 is time-sensitive:** every crawl that overwrites its predecessor is a data point
permanently lost. It cannot be backdated.

## Baseline (production inventory, 2026-08-03 — 8,907 records)

| VA lifecycle label | records | share |
|---|---:|---:|
| `active` | 5,379 | 60.4% |
| `archive` | **3,404** | **38.2%** |
| `decommissioned` | 124 | 1.4% |

| already captured, currently unused | records |
|---|---:|
| `cots_dependent` (commercial replacement signal) | **404** |
| `decommission_date` (2005–2022) | **115** |
| `out_of_scope_reason` | in the model, not surfaced |

Historical snapshots of the source: **none**. Single-copy files, overwritten every crawl.

## Notes carried in

- **The raw material already arrives and is discarded.** This is mostly about keeping and shaping
  what the crawl already produces, not extracting anything new.
- **Do not infer VA's intent from a label.** Record what changed; where the *why* is unknown, say so.
- **The timeline starts when we start.** No backfilling — manufactured history is worse than none.
- **Do not quote "38.2% archive" unqualified** (VO.5 finding, 2026-08-04): 36% of that share is VBA
  benefits forms the pipeline already excludes as noise. The documentation share is 2,170 records.
- **`archive` ≠ excluded today:** 255 archive-status documents (26 applications) are already
  admitted and in the collection, while all 124 `decommissioned` records are excluded (CI.0
  measurement, 2026-08-03 — the draft's "589" reproduced under no definition). That asymmetry is the
  crawl-integrity effort's to rule on; this effort supplies the evidence.
