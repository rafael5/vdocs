# vdocs-quality-vdl-observatory — tracker

| Step | What lands | Status | Commit / notes |
|------|-----------|--------|----------------|
| VO.1 | **Measure first** — what the current inventory already tells us (labels, dates, commercial-dependency flags) and what it cannot | ☐ | |
| VO.2 | Every crawl's inventory preserved as a dated, immutable record — **time-sensitive** | ☐ | |
| VO.3 | Timeline view: counts and composition per crawl, by section, document type and status | ☐ | |
| VO.4 | Lifecycle transitions surfaced as events (status change, decommission date, commercial-dependency flag) | ☐ | |
| VO.5 | The archived-share question answered with evidence — or declared unestablished, with why | ☐ | |
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
- **`archive` ≠ excluded today:** 589 archived applications are already admitted and in the
  collection, while all 124 `decommissioned` ones are excluded. That asymmetry is the crawl-integrity
  effort's to rule on; this effort supplies the evidence.
