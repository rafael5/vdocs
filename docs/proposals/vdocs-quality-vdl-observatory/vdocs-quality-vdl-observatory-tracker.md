# vdocs-quality-vdl-observatory — tracker

*(Revised 2026-08-05 to the adversarially-reviewed proposal — DoD per row = proposal Table 1.)*

| Step | What lands | Status | Commit / notes |
|------|-----------|--------|----------------|
| VO.0 | **Bank the current inventory now** — dated copy of bronze+gold to `inventory/snapshots/2026-06-10/`, sha256-verified, **before** the +174 fetch or any crawl | ☐ | |
| VO.2 | Immutable dated snapshot on every successful crawl — **bronze only**, deduped by canonical content hash (sorted rows) | ☐ | |
| VO.3 | Delta between two snapshots — per-section counts by status, **keyed on `appid`/`secid`**, never parsed names | ☐ | |
| VO.4a | Mass-transition tripwire: >5% of apps changing status in one delta → `SUSPECT-PARSER`, transitions suppressed (`app_status` is a display-suffix regex) | ☐ | |
| VO.1 | *(optional, demoted)* fill-rate report of unused fields — only if VO.3 needs it; CI.0 covered the essentials | ☐ | |
| VO.4b | *(optional)* transition rows in the delta report (status, decommission date, `cots_dependent`) — report rows, **no new channel** | ☐ | |
| VO.5 | The archived-share question answered with evidence — **closes as composition-answered / intent-unestablished** (proposal Table 1: append the explicit "intent unestablished, and why" paragraph to the findings, then ✅ — no further intent work) | 🟡 | **Composition answered ahead of the effort** (operator hypothesis, measured 2026-08-04): [`vo5-archive-meaning-findings.md`](vo5-archive-meaning-findings.md). **36% of the archive share is VBA benefits forms, not documentation**; of the genuine 2,170, **69.6% are older/duplicate copies** (72.2% older, 25.7% same version, 2.1% newer) and the rest are release-pinned documents. ⚠️ **But archive is NOT redundant in our corpus** — `consolidate` already folds the duplicates, and **0 of the 55 surviving archive documents have an active twin**. VA's *intent* stays unestablished; that needs VO.2–VO.4 |
| VO ✓ | VO.0, VO.2, VO.3, VO.4a and VO.5 all ✅ (proposal Table 1 DoDs) — optional rows not required | ☐ | |

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

| VO.8a | Assess Docling conversion quality on all 19 PDF-only documents before admitting any | ✅ | [`vo8-pdf-conversion-quality-assessment.md`](vo8-pdf-conversion-quality-assessment.md). **19/19 converted, 4,089 pages, coverage 1.160 — no text lost.** OCR rescued the Blood Bank manual (**71% of its pages have no text layer**; 38,721 → 142,156 words, 92.4% lexicon-recognised, 1.65% OCR noise as lost word-spaces). Caught a defect first: `_docling_convert` fed PDFs to DOCX zip image-recovery → all 19 would have failed (`8ce880a`) |
| VO.8b | ✅ **Table-shaped TOCs parsed, captured and stripped** | ✅ | `a246931`. Docling emits the TOC as ONE table: cells duplicated 4×, several entries per cell, and a single entry split ACROSS cells. Entries are **found** (title+leader+page), not split out — a section number is itself a valid page-number match. A contiguous table run that proves itself with ≥1 entry is the TOC block. **dot-leaders 7,198 → 991 (86%), entries captured 1 → 3,921, body −22.7%** (Kernel DG 2.39 MB → 1.24 MB). Capture-before-strip held by construction: an unparsable dropped row is recorded title-only |
| VO.8c | ✅ **Outline rebuilt from section numbering** | ✅ | `8038f37`. `level_headings_from_numbering` — depth = numbering components, guarded to documents with no hierarchy (ignoring a lone title). Kernel SM **839 flat → 175/146/341/153/24 across 5 levels**; nested `## Contents` + GitHub-slug anchors + 381 back-links. **Blast radius measured: 2 of 615 existing gold docs, both improvements.** Limitation: CPRS TMs + Blood Bank have unnumbered headings and stay flat — their outline is in `toc.yaml` |
| VO.8e | ✅ **Section headings re-created by correlating the TOC to the body** | ✅ | `396d263`. Docling's heading detection is visual, so a section set in body-text style arrives as a paragraph; the captured TOC is the author's index of every section. **+815 sections** on 5,400 detected (478 Kernel DG, 319 Kernel SM). Conservative: exact full-line match, occurring **exactly once**, prose, not already a heading, not in a fence. Captions excluded — a "List of Tables" entry names a figure, not a section. **Blast radius on 150 sampled existing enriched bodies: 9 docs, +34 headings, all genuine sections.** Two defects caught by measuring: promoting to the *shallowest* level swamped the Kernel DG's lone title and silently killed VO.8c's 5-level outline (now uses the **modal** level), and table captions were being promoted |
| VO.8f | ✅ **Docling and Pandoc converge on the same `toc.yaml`** | ✅ | `8d0407c`. They already wrote the same *file*; two of its four columns were dead on the PDF path. A Word TOC carries `](#_Toc…)` links, a printed PDF TOC carries none — so every Docling entry was `anchor: ''`, `resolved: false`, and `resolved` meant two different things. `resolve_toc_anchors_by_title` gives an anchorless entry the slug of the heading it names (same correlation as `correlate_bookmarks_by_title`, keyed on title). **3,921 entries, 2,564 resolved (65%), up from 0** — CPRS TMs 94–96%, Blood Bank 88%, Kernel binders 61/52% (a binder repeats section names). **P3.1 held: an unmatched entry stays anchorless, never a manufactured flag.** A/B on 120 existing enriched bodies: unresolved flags 3,284 → 3,284, resolved +1 — a no-op for Pandoc by design |
| VO.8d | ✅ **PDF figures reach the shared asset CAS, as DOCX figures do** | ✅ | `b92e17b`. **1,337 figures** existed only as `<!-- image -->` placeholders (Kernel DG 539, Kernel SM 372, AHOBP 188). Note there is **no images sidecar** — DOCX figures go to `documents/assets/` (content-addressed, 15,705 files) with refs rewritten to `<sha>.<ext>`; PDFs now land in the same store, which is what vdocs-web's `/api/asset` serves. The fix is one setting per format: DOCX keeps `placeholder` (we recover media **and alt-text** from the source zip — the alt-text is worth more than the pixels), a PDF has neither, so Docling must export them (`referenced`). The stage's CAS-and-rewrite-by-basename path was already format-agnostic. Verified end to end: 11 images, 0 placeholders left, 11/11 refs rewritten |

**Net effect:** fetch targets **1,044 → 1,218** (+174), **0 departures** so the CI.4 composition gate
stays green and needs no acknowledgement. 1,326 tests, coverage 96.28%, `make check` exit 0.

⚠️ **The +174 are not yet fetched.** The gate admits them; acquiring them needs a `vdocs fetch --all`
and a rebuild. Until then the corpus still holds 1,040 documents.

Proposal: [`vdocs-quality-vdl-observatory.md`](vdocs-quality-vdl-observatory.md) ·
Plan: [`vdocs-quality-vdl-observatory-implementation-plan.md`](vdocs-quality-vdl-observatory-implementation-plan.md) ·
Prompts: [`prompts/`](prompts/)

⚠️ **Sequencing premise corrected (2026-08-05):** crawl-integrity closed **without** building a
snapshot mechanism — there is nothing to share; VO.2 is greenfield.
⏳ **VO.0 is the time-sensitive step:** the only held crawl (2026-06-10) is overwritten by the next
explicit crawl, and the pending +174 `vdocs fetch --all` + rebuild makes one likely. Bank it first.

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
