# vdocs-quality-crawl-integrity — tracker

| Step | What lands | Status | Commit / notes |
|------|-----------|--------|----------------|
| CI.0 | **Measure first** — current crawl yield, admitted-set composition, and what VA's lifecycle labels do to admission today | ☐ | |
| CI.1 | Completeness floor on `crawl` — a materially smaller crawl fails and leaves the last good one in place | ☐ | |
| CI.2 | **Master-set retention** — a document that has been fetched is never dropped by a scope or lifecycle relabel | ☐ | |
| CI.3 | VA's lifecycle labels captured as first-class metadata on the document (`app_status`, `decommission_date`, `cots_dependent`, `out_of_scope_reason`) | ☐ | |
| CI.4 | Admitted-set composition baseline — departures reported by document identifier; a deliberate change acknowledged in a curated file | ☐ | |
| CI ✓ | Shrunken crawl reds · a fetched document cannot be lost to a relabel · lifecycle visible on a document · unacknowledged scope change reds · live collection green | ☐ | |

Proposal: [`vdocs-quality-crawl-integrity.md`](vdocs-quality-crawl-integrity.md) ·
Plan: [`vdocs-quality-crawl-integrity-implementation-plan.md`](vdocs-quality-crawl-integrity-implementation-plan.md) ·
Prompts: [`prompts/`](prompts/) ·
Sibling: [`../vdocs-quality-vdl-observatory/`](../vdocs-quality-vdl-observatory/)

🥇 **This effort runs FIRST in the `vdocs-quality-*` family** (reordered 2026-08-03). Scope decides
what the collection contains; the report card measures inside that boundary and its repairs depend on
the scope ruling.
📏 **Measure before you act:** CI.0 is a measurement, and no floor, retention rule or gate lands
before it exists.

## Baseline (verified 2026-08-02/03)

| | |
|---|---|
| completeness check on `crawl` / `catalog` | **none** — no gate, no floor, either stage |
| behaviour on a degraded crawl | the smaller result overwrites the previous good one |
| historical snapshots of the source | **none** — single-copy files, overwritten each crawl |

**What VA's labels do to admission today** (8,907 inventory records):

| `app_status` | inventory | admitted | share |
|---|---:|---:|---:|
| `active` | 5,379 (60.4%) | 1,604 | 29.8% |
| `archive` | **3,404 (38.2%)** | 589 | 17.3% |
| `decommissioned` | 124 (1.4%) | **0** | **0.0%** |

**Captured and unused:** `cots_dependent` **404** · `decommission_date` **115** (2005–2022) ·
`out_of_scope_reason`.

**Retention today:** 1,040 documents fetched, 1,034 distinct raw payloads (six byte-identical
sibling pairs — the P1 finding). Raw bytes are write-once and survive; the *processed* document,
its bundle and its presence in search do not survive a scope change.

## ⚠️ Correction carried in (2026-08-03)

This effort's first draft claimed **102 documents (XOBW 23, KAAJEE 64, LEX 15) had left the
collection unreported**. **False.** They were never acquired in production (`acquisitions = 0` for
all three); they appear in the golden answer key because that key was curated on the **dev lake**
(451 documents), which admits applications production does not. Same dev-lake contamination that made
three retrieval measurements read the wrong corpus — one instance was found, and a second, more
dramatic one was inferred instead of checked.

**What survives:** nothing tracks the admitted set's composition over time, so a real departure
*would* be equally silent. The gap is genuine; the dramatic proof of it was not.

## Notes carried in

- **Deprecation is not deletion.** VA marking a package deprecated does not remove its code from
  VistA. The routines are still installed and still need documentation — arguably more so, since
  nobody is maintaining them. Once fetched, we keep it.
- **Deprecation is intelligence.** A package moving to `decommissioned`, especially with a
  commercial-dependency flag, is the visible half of a procurement decision. Record it; do not
  discard the document over it.
- **Compare composition, not totals.** Losing 20 and gaining 20 nets to zero — the acquisition-chain
  work already paid for this lesson; findings are by document identifier.
- **A floor set too tight gets disabled**, which is worse than no floor. Tolerance against the last
  *good* crawl, and acknowledging a legitimate change stays cheap.
- **Do not widen scope by accident.** Retention protects what we already have; whether
  `decommissioned` applications should now be admitted is a product decision to surface, not to make.
