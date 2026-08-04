# vdocs-quality-pattern-miner — tracker

| Step | What lands | Status | Commit / notes |
|------|-----------|--------|----------------|
| PM.1 | Stratified sample of the proposals judged: genuine furniture / genuine content / noise, with the text-volume estimate | ✅ | 198 judged across 4 frequency bands. **Furniture ≈149 patterns ≈59 KB = 0.073% of gold = 0.6 chars of a median passage** (95% UB 1.26% / ~11 chars). Frequency is a *poor* predictor both ways — see below |
| PM.2 | **Ruling** — build the curation loop, or take the miner off the default rebuild path — with the PM.1 numbers in it | ✅ | **Ruled: off the default path.** Proposal §10 |
| PM.3a | *(if build)* Bulk review path; patterns actually approved; effect on retrieved-passage cleanliness measured | ⛔ | Not taken — the benefit is 0.6 chars of a median passage |
| PM.3b | *(if off-path)* Miner runs on demand only; recovered rebuild time stated; no doc implies continuous cleaning | ✅ | Generic `Stage.on_demand` (orchestrator, not a special case) + `DiscoverStage.on_demand = True`. Recovers **4m41s of ~26m (18%)**. Docs corrected: `de-novo-run.md` §2, design §8 row + §9.6 steps 2 & 4 |
| PM ✓ | A ruling exists with its numbers; generate-and-discard no longer happens on every rebuild | ✅ | 1,283 tests green, coverage 96.27%, `make check` exit 0. No document changed — the RR.3 ruler is untouched |

Proposal: [`vdocs-quality-pattern-miner.md`](vdocs-quality-pattern-miner.md) ·
Plan: [`vdocs-quality-pattern-miner-implementation-plan.md`](vdocs-quality-pattern-miner-implementation-plan.md) ·
Prompts: [`prompts/`](prompts/)

⛔ **Prerequisites: [`vdocs-quality-crawl-integrity`](../vdocs-quality-crawl-integrity/) `CI ✓` and [`vdocs-quality-report-card`](../vdocs-quality-report-card/) `RC ✓`, in that order** (revised 2026-08-03). **Status: all four preceding efforts are closed — `CI ✓` `RC ✓` `RR ✓` (2026-08-03) and `SL ✓` (2026-08-04, ruled *stop*). This effort is next and nothing is ahead of it.** Scope decides what the collection contains; every measurement here is then taken inside that boundary.
📏 **Measure before you act:** the first step below is a measurement, and no code, configuration, curation or gate lands until it is complete and written down.

**A decision, not a build.** PM.1 (measurement) and PM.2 (the ruling) are mandatory; exactly one of PM.3a/PM.3b follows. Sequenced last of the five. **Closed 2026-08-04 — PM.3b taken; see Outcome below.**

## Baseline (full forced rebuild, 2026-08-02, 1,040 documents)

| proposed per rebuild | | curated and applied | |
|---|---:|---|---:|
| phrases | **34,822** | curated phrases | **13** |
| boilerplate | **23,885** | curated boilerplate | **16** |
| glossary terms | **18,011** | curated glossary | **~0** |
| scaffold blocks | 4,709 | curated structures | **7** |
| templates / structures | 36 / 9 | | |
| **total** | **~81,500** | **total** | **109** |

Cost: mining takes **4m41s** of a ~26-minute full rebuild — **~18%**, second only to document
conversion.

Evidence the mechanism works when curation happens: the 89 curated boilerplate patterns matched
**1,014** times, single-sourcing one shared block each.

## Notes carried in

- **Never auto-approve.** Frequency-based stripping is how documents get silently gutted. This
  collection already had one incident — page-numbered contents entries deleted with **no record at
  all**, surfaced only by an unexplained content-loss score.
- **Capture-before-strip stays absolute.** Nothing in this effort weakens it.
- **Stratify the sample.** The most frequent patterns are the most obviously furniture; a
  frequency-ordered sample will flatter the population.
- **"Later" is the real failure mode.** A third generate-and-discard cycle with the ruling still
  open is the outcome this effort exists to prevent.

## Outcome (2026-08-04) — ruled *off the default path*

**The benefit was the thing that decided it.** Approving every furniture proposal the miner makes
would remove ~59 KB from an 81.6 MB corpus — **0.073%**, about **0.6 characters** of a median
retrieved passage (975 chars). The 95% upper bound, taken honestly on the bands where the sample saw
zero furniture, is 1.26% / ~11 characters. Against 4m41s of a ~26-minute rebuild, there is nothing
to build a curation loop for.

**Frequency is a poor predictor of furniture in both directions** — the sample's most useful finding,
and the opposite of the "frequency-ordered sample will flatter the population" warning carried in:

| phrases | ≥100 docs | 30–99 | 10–29 | 3–9 |
|---|---:|---:|---:|---:|
| population | 23 | 134 | 2,207 | **32,458** |
| furniture | 22% | 20% | 0% | 0% |
| content | 9% | 52% | **92%** | **92%** |
| *harmful if approved* | **16/23** | 6/25 | 1/25 | 1/25 |

The top band is 70% single characters and markdown debris (`A`, `#`, `.`, `\|`) split out of screen
captures — the band an auto-approve rule would have taken first is the band that would have gutted
documents. Below 30 documents, 92% is genuine content: transcripts, VistA prompts, drug names,
example output.

Boilerplate: 0 harmful in 50, but its three genuine top-band items (title-17 notice, hyperlink
disclaimer, revision-page instructions) are **already absent from gold** — the 89 curated entries
removed them. Glossary: removes no text at all (PROMOTE), ~18% promotable, ~25% M routine names the
SKL entity layer already carries properly, the rest noise.

## Landmines found (carry these forward)

- **The curated total was 109, not 29** — 13 phrases + **89** boilerplate + 7 structures. The
  proposal's "16 curated boilerplate" was wrong and the "89 shared blocks" was the same 89 counted
  from the other end. Corrected in the proposal §3 + §10.3 and above.
- **Proposal counts here ARE distinct patterns** (verified: 34,822 / 23,885 / 18,011 unique keys) —
  the mentions-vs-candidates trap that inflated the synonym layer's queue does not apply.
- **`discover` mines 1,040 converted docs; the reader sees 615 gold version groups.** Most apparent
  cross-document recurrence is the same manual at many versions, which `consolidate` already folds —
  a 64-document VS GUI block survives into **2** gold bodies. Any future corpus-frequency claim must
  say which corpus it counted.
- **`registries/templates` is curated (30 KB) and stamps nothing** — `templates_stamped: 0` on the
  last normalize run. A second, quieter dead loop; out of scope here, recorded so it is not mistaken
  for a working one.
- **Design §9.6 claimed high-frequency candidates "auto-approve".** No code ever did, and PM.1
  measured it to be the wrong rule. Struck.
