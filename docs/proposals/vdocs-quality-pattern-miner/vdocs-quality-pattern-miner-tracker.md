# vdocs-quality-pattern-miner — tracker

| Step | What lands | Status | Commit / notes |
|------|-----------|--------|----------------|
| PM.1 | Stratified sample of the proposals judged: genuine furniture / genuine content / noise, with the text-volume estimate | ☐ | |
| PM.2 | **Ruling** — build the curation loop, or take the miner off the default rebuild path — with the PM.1 numbers in it | ☐ | |
| PM.3a | *(if build)* Bulk review path; patterns actually approved; effect on retrieved-passage cleanliness measured | ☐ | |
| PM.3b | *(if off-path)* Miner runs on demand only; recovered rebuild time stated; no doc implies continuous cleaning | ☐ | |
| PM ✓ | A ruling exists with its numbers; generate-and-discard no longer happens on every rebuild | ☐ | |

Proposal: [`vdocs-quality-pattern-miner.md`](vdocs-quality-pattern-miner.md) ·
Plan: [`vdocs-quality-pattern-miner-implementation-plan.md`](vdocs-quality-pattern-miner-implementation-plan.md) ·
Prompts: [`prompts/`](prompts/)

⛔ **Prerequisites: [`vdocs-quality-crawl-integrity`](../vdocs-quality-crawl-integrity/) `CI ✓` and [`vdocs-quality-report-card`](../vdocs-quality-report-card/) `RC ✓`, in that order** (revised 2026-08-03). Status: `CI ✓` ticked 2026-08-03 (`801f48c`); `RC ✓` still open, so this effort stays blocked. Scope decides what the collection contains; every measurement here is then taken with the answer key, which currently fails search for returning better answers than it names.
📏 **Measure before you act:** the first step below is a measurement, and no code, configuration, curation or gate lands until it is complete and written down.

**A decision, not a build.** PM.1 (measurement) and PM.2 (the ruling) are mandatory; exactly one of PM.3a/PM.3b follows. Sequenced last of the five.

## Baseline (full forced rebuild, 2026-08-02, 1,040 documents)

| proposed per rebuild | | curated and applied | |
|---|---:|---|---:|
| phrases | **34,822** | curated phrases | **13** |
| boilerplate | **23,885** | curated boilerplate | **16** |
| glossary terms | **18,011** | curated glossary | **~0** |
| scaffold blocks | 4,709 | curated structures | **7** |
| templates / structures | 36 / 9 | | |
| **total** | **~81,500** | **total** | **29** |

Cost: mining takes **4m41s** of a ~26-minute full rebuild — **~18%**, second only to document
conversion.

Evidence the mechanism works when curation happens: the 16 curated boilerplate patterns matched
**1,014** times, single-sourcing 89 shared blocks.

## Notes carried in

- **Never auto-approve.** Frequency-based stripping is how documents get silently gutted. This
  collection already had one incident — page-numbered contents entries deleted with **no record at
  all**, surfaced only by an unexplained content-loss score.
- **Capture-before-strip stays absolute.** Nothing in this effort weakens it.
- **Stratify the sample.** The most frequent patterns are the most obviously furniture; a
  frequency-ordered sample will flatter the population.
- **"Later" is the real failure mode.** A third generate-and-discard cycle with the ruling still
  open is the outcome this effort exists to prevent.
