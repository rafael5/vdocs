# vdocs-quality-crawl-integrity — tracker

| Step | What lands | Status | Commit / notes |
|------|-----------|--------|----------------|
| CI.1 | Completeness floor on `crawl` — a materially smaller crawl fails and leaves the last good one in place | ☐ | |
| CI.2 | Admitted-set composition baseline — departures reported by document identifier; a deliberate change is acknowledged in a curated file | ☐ | |
| CI ✓ | Shrunken crawl reds · removed application reds naming documents · acknowledged change passes · live collection green | ☐ | |

Proposal: [`vdocs-quality-crawl-integrity.md`](vdocs-quality-crawl-integrity.md) ·
Plan: [`vdocs-quality-crawl-integrity-implementation-plan.md`](vdocs-quality-crawl-integrity-implementation-plan.md) ·
Prompts: [`prompts/`](prompts/)

Independent of the other quality efforts — it touches no search behaviour and can run in parallel if
someone else is measuring retrieval.

## Baseline (verified 2026-08-02/03)

| | |
|---|---|
| completeness check on `crawl` / `catalog` | **none** — no gate, no floor, either stage |
| behaviour on a degraded crawl | a smaller result overwrites the previous good one |
| documents that left the admitted set with **zero** findings | **102** — XOBW 23, KAAJEE 64, LEX 15 |
| how it surfaced | a golden question broke, roughly four weeks later |
| exclusion mechanism | admission gate on `system_type` (*Integration middleware*, *Data patch*) |
| what the chain gate proves | the five processing seams agree **with each other** — not that the set is unchanged |
| crawl politeness | 1.5 s/page against `https://www.va.gov/vdl/` |

## Notes carried in

- **Compare composition, not totals.** Losing 20 documents and gaining 20 nets to zero. The
  acquisition-chain work already paid for this lesson: findings are by document identifier.
- **Reuse, do not invent.** `validate` already runs a cross-run drop check on sidecar counts and a
  five-seam reconciliation by identifier. This is the same machinery pointed one stage earlier.
- **A legitimate scope change must stay cheap to make.** If acknowledging one is expensive, the gate
  gets disabled and the whole effort is wasted.
- **Do not attempt to restore the 102 documents.** Whether XOBW/KAAJEE/LEX belong in scope is a
  product question this effort does not answer.
