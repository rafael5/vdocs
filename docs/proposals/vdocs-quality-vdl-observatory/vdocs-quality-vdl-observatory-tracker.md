# vdocs-quality-vdl-observatory — tracker

| Step | What lands | Status | Commit / notes |
|------|-----------|--------|----------------|
| VO.1 | **Measure first** — what the current inventory already tells us (labels, dates, commercial-dependency flags) and what it cannot | ☐ | |
| VO.2 | Every crawl's inventory preserved as a dated, immutable record — **time-sensitive** | ☐ | |
| VO.3 | Timeline view: counts and composition per crawl, by section, document type and status | ☐ | |
| VO.4 | Lifecycle transitions surfaced as events (status change, decommission date, commercial-dependency flag) | ☐ | |
| VO.5 | The archived-share question answered with evidence — or declared unestablished, with why | 🟡 | **Composition answered ahead of the effort** (operator hypothesis, measured 2026-08-04): [`vo5-archive-meaning-findings.md`](vo5-archive-meaning-findings.md). **36% of the archive share is VBA benefits forms, not documentation**; of the genuine 2,170, **69.6% are older/duplicate copies** (72.2% older, 25.7% same version, 2.1% newer) and the rest are release-pinned documents. ⚠️ **But archive is NOT redundant in our corpus** — `consolidate` already folds the duplicates, and **0 of the 55 surviving archive documents have an active twin**. VA's *intent* stays unestablished; that needs VO.2–VO.4 |
| VO ✓ | Two consecutive crawls comparable without re-crawling; transitions visible; `archive` meaning recorded | ☐ | |

### Completeness workstream (VO.6–VO.9) — separate from the timeline above

Added 2026-08-04 on operator sign-off of
[`archive-inclusion-and-exclusion-accounting-proposal.md`](archive-inclusion-and-exclusion-accounting-proposal.md).
**These do not overlap VO.1–VO.5**: those record the *source over time*, these define and enforce
what the *corpus contains*. `VO ✓` above does not cover them.

| Step | What lands | Status | Commit / notes |
|------|-----------|--------|----------------|
| VO.6a | Re-derive the sole-survivor set with the patch-identity correction | ✅ | 488 → **445** (43 were genuinely superseded). VO.7 target 166 → **159** |
| VO.6 | Explicit exclusion reason on every excluded record, from a closed vocabulary | ✅ | `serve_inventory/completeness_pure.py`. Four gates excluded records; one wrote a reason. Now: `not-vista:vba-form` (the operator's ask), `not-vista:system-type=X`, `format:pdf-duplicate` vs `format:pdf-only`, `doctype-omitted:CODE` |
| VO.7 | Sole-survivor admission rule | ✅ | `fetch_pure.sole_survivors` — admit an archived, omitted-type document nothing newer supersedes. **159 admitted, not the 1,766 a blanket doctype flip would take** |
| VO.8 | A document is not excluded for being unreadable by our converter | ✅ | Rule, not an allowlist: admit a non-DOCX record when no DOCX exists anywhere. Recovers **both CPRS Technical Manuals + both Kernel 8.0 binders**. `convert` routes by format (`needs_docling`) since Pandoc cannot read PDF; preflight now demands Docling when a PDF is pending |
| VO.9 | Completeness defined and made checkable | ✅ | `vdocs completeness` (+`--json`), exits non-zero on any unreachable document. **Live verdict: COMPLETE** — every one of the 8,907 records is held, outside the library, or excluded for a recorded reason |

**Net effect:** fetch targets **1,044 → 1,218** (+174), **0 departures** so the CI.4 composition gate
stays green and needs no acknowledgement. 1,326 tests, coverage 96.28%, `make check` exit 0.

⚠️ **The +174 are not yet fetched.** The gate admits them; acquiring them needs a `vdocs fetch --all`
and a rebuild. Until then the corpus still holds 1,040 documents.

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
