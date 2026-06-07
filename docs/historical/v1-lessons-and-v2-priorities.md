# vdocs — v1 Lessons & v2 Priorities (real-corpus synthesis)

**Status:** Synthesis / decision record. **Date:** 2026-06-04. **Companion to:**
[`vdocs-design.md`](vdocs-design.md) (architectural source of truth),
[`fidelity-framework.md`](fidelity-framework.md) (QA companion),
[`vdocs-implementation-tracker.md`](vdocs-implementation-tracker.md) (build plan).

## 0. Why this document exists

`vdocs` has now been run end-to-end on a **real 1299-document VA corpus** (409 version groups),
through the full pipeline `crawl → … → consolidate → index → relate → manifest → validate`. That is
the first time the design has met a corpus large and messy enough to *measure* — not fixture-test —
its central promise: **maximal human and machine discoverability of the VistA Document Library.**

This note synthesises what that real run taught us. It exists to answer one strategic question that
came up after the audit: *given the gap between the design's discoverability goal and what the search
surface actually looks like today, should the specification be rewritten?*

**The answer recorded here is no — and the reasoning is the point of this document.** The gap is
overwhelmingly **code-vs-spec and plan-sequencing**, not **spec-vs-goal**. The specification is sound
and, on the discoverability axis, *ahead of* the implementation. So the disposition is: **amend the
spec surgically, rewrite the build plan, keep the code.** This note records what real data
**confirmed**, what it **corrected**, and the **priority reframe** that follows — so the framing is
agreed before §-level edits land (those are tracked in the design/fidelity docs and the tracker).

This is the same discipline the project already practises (CLAUDE.md: *"If the code and that document
disagree, the document is the bug report"*) applied one level up: when the *plan* and the *measured
reality* disagree, re-derive the plan from the measurement.

---

## 1. The evidence base (what was measured, 2026-06-04)

All figures are from the live lake (`~/data/vdocs`), not estimates.

**Pipeline health.** 1299 docs through silver; 409 consolidated gold groups; gold-derive complete
(`index`/`relate`/`manifest`); the `validate` HARD GATE passes (`severed=[]`, reconcile 0, bundle 0).
`make check`: **683 tests, 98.71% coverage**, ruff+mypy clean. Gold-cleanup audit: **91% of docs
clean** on title-page/revision-history/legacy-TOC, every residual flagged (zero silent residue).

**The search surface (`index.db`), measured:**

| Signal | Reality | Reading |
|---|---|---|
| Section chunks (`is_latest`) | 24,999; body length **8 → 144,908** chars (avg 1,362) | unbounded — neither human- nor embedding-friendly |
| **Hollow chunks** (<80 chars) | **14.2%** (3,539) — bare heading + back-link, no body | the chunker spans heading→next-heading, so **container headings index as empty chunks** |
| Thin chunks (<400 chars) | **40.8%** | over-fragmented; many chunks can't stand alone |
| Oversized chunks (>10k) | 346 | should be split on sub-structure |
| **Entity types** | **4 only**: `global` 2,041 · `fileman_file` 292 · `build` 193 · `package_namespace` 19 | the high-value discovery entities are **missing** (see §3.3) |
| Structureless `is_latest` docs | **24** with zero indexed sections | invisible to section/semantic search |
| Semantic search | `vectors.db` absent | AI discovery is lexical + graph only today |
| Cross-ref navigation | `severed = 0`; `_Toc` unmapped ≈ 76% | links never *broke*; they were never heading targets (see §3.1) |

---

## 2. What real data CONFIRMED (do not relitigate)

These design decisions were *validated* by the corpus and are load-bearing. A rewrite would put them
back on the table for no reason.

1. **The medallion + stage/contract/orchestrator spine.** 17 stages, generic orchestrator, pure
   `*_pure.py` + thin I/O drivers, contract-bound preflight/postflight, `state.db` lineage — ran
   clean on 1299 real docs with per-document error isolation and idempotent skips. The architecture
   scales.
2. **Stable IDs shared across the human and machine corpora** (§5.5/§14). `doc_key` / `section_id` /
   `(type, canonical-name)` give one identity that markdown anchors, FTS rows, graph nodes, and the
   eventual MCP URIs all reference. This is exactly the right discoverability substrate — the problem
   is *chunk quality under* the IDs, not the ID scheme.
3. **Anchor-doc version groups + retained-body CAS + `history.yaml` lineage** (§6.6). 1299 docs
   collapse to 409 anchors with full patch lineage retained, not lost. The "search corpus is
   anchor-only; evidence corpus is complete" split (§14.6) is the correct foundation for
   version-correctness in retrieval.
4. **Discovery-is-data** (tenet #13). Boilerplate/phrase/template/structure registries drove the gold
   cleanup to 91%-clean with every removal traceable to a curated entry. The model works.
5. **Capture-before-strip + signed bundle manifest** (§6.4/§6.6). Typed `capture.yaml` + `bundle.yaml`
   made "nothing silently dropped" *provable*, and the `validate` gate enforces it. Provenance is the
   most-achievable axis, as the framework predicted.
6. **Smoke every gold stage on the full lake before declaring done** (a v1 lesson, now doctrine). The
   `section_id` slug collision, the residue false-positives, and — below — the C5 hypothesis were all
   findings that *only the real corpus produced*. Fixture tests cannot surface them.

**Implication:** the spec's architecture and its fidelity *framework* (dimensional C1–C7, provenance
hard gate, currency axis, retrieval-quality §10.5, calibration §9) are keepers. They are more complete
than the code that implements them.

---

## 3. What real data CORRECTED (the genuine lessons)

Four items where reality diverged from the plan. Note their *kind*: three are **unbuilt spec**
(the design says the right thing; the code doesn't do it yet) and one is a **spec hypothesis error**
(the design says something real data disproved). None is architectural.

### 3.1 C5 `_Toc` cross-refs are NOT recoverable from the legacy TOC — *spec hypothesis error*

The fidelity framework (§5 C5) and the design (§6.7) state the unmapped `_Toc…` cross-refs are the
"recoverable, C5-bounded" class — reconstructible because "the legacy TOC records `_Toc… ↔
heading-title`." **The real corpus disproves this.** Of 533 unmapped `_Toc` refs:

- **480 are in-body cross-refs, not TOC entries** — the legacy TOC doesn't contain their bookmark id.
- **53 are TOC entries to stripped/headingless front matter** (Revision History, List of Figures).
- Of the 336 whose target span survives conversion, **0 are on a heading line**. They point at
  **bold-text pseudo-headings Pandoc never styled as `##`** (e.g. `**Reminder Location List Menu**`),
  table/figure captions, and stripped sections — **none are GitHub heading anchors.**

A legacy-TOC title-correlation fix was built and proven on fixtures (`f6e4767`) but recovers **~1 of
534** on the real lake. **`severed` stays 0** — no reference to a *live* heading is broken. So the
honest model is: the dead-anchor hard floor (severed=0) is the real, sound gate; the `_Toc` "unmapped
rate" is a **navigation-completeness metric over largely non-heading targets**, not a recoverable
resolvability gap. C5 must be recalibrated accordingly (spec amendment #1).

The *genuinely* recoverable subset is the **bold pseudo-heading** class — addressed not by TOC
correlation but by heading recovery (§3.2 / priority A2).

### 3.2 Chunking is unbuilt to spec — *unbuilt spec (highest discoverability cost)*

§14.6 says "**chunk on structure, not on bytes**"; §10.5 specifies the hollow-chunk/over-strip
guardrail in full. The code (`index_pure.shred_sections`) instead spans each heading to the next, so:
**14.2% of indexed chunks are hollow** container headings (substance lives in their subsections),
**40.8% are thin**, and a few are 145 KB monsters. This is the single largest drag on *both* human
navigation and (once `embed` lands) semantic recall. The spec is right; the chunker doesn't implement
it. `overstrip_pure` already exists as the measurement core — it just isn't wired or enforced, and the
chunker it would grade hasn't been fixed.

### 3.3 Entity extraction is shallow and skewed — *unbuilt spec*

§5.5 lists the entity types verbatim: "package namespaces, FileMan file numbers, routines, **options,
RPCs, protocols, HL7 segments, mail groups**, globals, build/patch ids." Only **4** are seeded in
`registries/entities`, and the surface is dominated by **2,041 raw globals** — ubiquitous, low-signal
(the design itself excludes raw globals from xref edges for being too common). The
discovery-rich types (RPCs, options, routines, protocols, HL7, mail groups) — exactly what an agent
or engineer searches the VistA corpus *for* — are entirely absent. This is the biggest lift available
for **structured + graph** discoverability, and it is pure registry + `entities_pure` work the design
already sanctions.

### 3.4 24 structureless latest docs are invisible — *unbuilt spec*

`recover_headings` only fires when a doc has *no* markdown headings, and several docs defeat even that
(no `_Toc`-span paragraphs to promote). They index with zero sections → unreachable by section or
semantic search. Heading recovery v2 (run even when *some* headings exist; handle bold+bookmark
pseudo-headings) closes both this and the recoverable slice of §3.1.

---

## 4. The reframe principle

One sentence, and it is the throughline of the v2 priorities:

> **Discoverability quality is determined upstream of the gate — by chunk quality, structural
> recovery, and entity richness. A gate can certify discoverability; it cannot create it.**

v1 built the *certification* machinery (the `validate` HARD GATE, signed bundles, capture
verification, gold-derive) before the *substrate* it certifies (good chunks, recovered structure,
rich entities) was good. That is the sequencing error. Both halves are in the spec; they were built in
the wrong order. The v2 plan inverts it: **fix the substrate, measure it, then gate on the
measurement** — and make the retrieval-quality harness (§10.5) the throughline that turns every
substrate fix into a measured lift, not an asserted one.

---

## 5. v2 priorities (substrate-first)

The detailed, sequenced version lands in the tracker (Phase 5/6 rewrite); the shape:

- **A. Fix the retrieval substrate** — A1 structure-aware chunking (`shred_sections`: no hollow
  containers, bounded size, structure-aligned), A2 heading recovery v2 (bold+`_Toc` pseudo-headings;
  the 24 structureless docs), A3 entity depth + global-denoise (the missing VistA types).
- **B. Measure it** — B1 wire `fidelity` as a stage, T-only checks first (reuse `overstrip_pure`,
  `compliance_pure`), B2 independent `S→T` recall (C1/C3/C4 via a pipeline-independent DOCX
  extractor), B3 the retrieval-quality harness (golden query set; precision@k/nDCG/redundancy/
  version-correctness; ablation) as the throughline.
- **C. Gate honestly** — recalibrated C5 (§3.1), frontmatter schema gate + ID/anchor integrity, consume
  the fidelity verdict.
- **D. Semantic layer** — `embed → vectors.db` over the *now-good* chunks; hybrid RRF; B3 measures
  semantic vs lexical vs hybrid.

Sequence: **A1+A2 and a B3 baseline first** (highest leverage, no external dependency, improve human
TOC *and* machine chunks together; B3 makes every later change a number) → A3 → B1 → D embed → C gate
→ publish. B2 and the full §9 human-calibration are the institutional-grade tail — staged after the
substrate is good, so calibration isn't run against a weak surface.

---

## 6. Scope decision: amend + re-plan, do NOT rewrite

The test applied: *would a from-scratch rewrite change the architecture, stages, contracts, or
medallion?* **No.** *Would it change the build sequence and a few metrics/thresholds?* **Yes.** That is
the definition of a plan rewrite, not a spec rewrite.

Against a rewrite, concretely:

- **It's already the rewrite.** `vdocs` is the greenfield v2 of `vista-docs`. A from-scratch v3 is
  second-system risk for a system whose architecture real data just *validated* (§2).
- **It discards proven assets.** 683 tests, 98.71% coverage, a clean architecture running end-to-end
  on 1299 real docs. The defects are ~3 pure functions (`shred_sections`, `recover_headings`,
  `entities_pure`), one registry (`registries/entities`), and one metric (C5).
- **The project's own protocol says fix-the-code.** Doc-vs-code disagreement is a code bug report, not
  a doc rewrite trigger.

**Disposition:** (1) surgical doc-first spec amendments for the real lessons — recalibrate C5,
concretize the chunking spec with the measured thresholds, promote full entity-type coverage to a
build requirement, add the §4 substrate-first principle; (2) rewrite the **build plan** (tracker Phase
5/6) to the substrate-first sequence; (3) keep the code and remediate it against the amended spec.
This document is step 0 of that disposition.
