# Kickoff — remediate the gold title page / revision history / legacy TOC cleanup

You are working in **`~/projects/vdocs`** (the real pipeline). The consolidated gold corpus still
carries three legacy artifacts it is supposed to have shed: raw title pages, revision-history
apparatus, and page-numbered legacy TOCs. Your job is to fix the **root causes** in the existing
`normalize` (and downstream `consolidate`) stages, **capture-before-strip**, then re-run and prove
the corpus is clean — without losing any provenance.

## Read first (source of truth)

- **`docs/gold-titlepage-revhist-toc-findings.md`** — the findings + root causes + measured numbers
  for this task. Start here.
- **`docs/vdocs-design.md`** — the authoritative design. The relevant clauses were **already updated**
  for this work: **§6.3** (`published` identity field + title-page capture-gate), **§6.4** (corrected
  revision-table detection contract, capture-before-strip fail-safe, title-page standardized block),
  **§6.6** (capture-gated declutter), **§6.7** (correlate-before-dropping the legacy TOC). Also §8
  (stage table — authoritative) and §17 (phases). **If code disagrees with the doc, the doc is the
  bug report** — but here the doc already describes the target; you are making code match it.
- **Machine audit (per-document evidence + regression oracle):**
  `~/data/vdocs/reports/fidelity/gold-titlepage-revhist-toc-audit.md`. The audit script that produced
  it is the acceptance check — re-run it after remediation and confirm the counts go to ~0.

## What already exists (do not rebuild)

- `src/vdocs/stages/normalize/revision_pure.py` — `_is_revision_header`, `find_revision_table`,
  `extract_revision_history`, `parse_revision_table` (HTML + GFM pipe dialects). **The bug is the
  detector predicate**, not the parser.
- `src/vdocs/stages/normalize/anchors_pure.py` — `parse_headings`, `rewrite_link_targets`,
  `build_anchor_map`, TOC + back-link generation.
- `src/vdocs/stages/normalize/template_pure.py` (`apply_template`) — strips the `(doc_type, era)`
  template scaffold (the title page is part of this scaffold) and stamps `template_id`; `era` is the
  title-page-date decade bucket (`kernel.decade_bucket`).
- `src/vdocs/stages/normalize/stage.py` — the F-step driver. **Current order:** `extract_revision_history`
  → tables lift → `apply_template` (scaffold/title-page strip) → `normalize_body` (phrases,
  boilerplate, legacy-TOC strip via `registries/structures`, TOC regen).
- `src/vdocs/stages/consolidate/` — folds each member's `revisions.yaml` into `history.yaml` and
  computes `official_date`. `src/vdocs/stages/discover/discover_pure.py` — `_TITLE_PAGE_LINES` window
  + `era` date parse (reuse for date capture); its revision-history heading regex (line ~49) also
  needs broadening.
- `registries/structures` (CANONICALIZE `toc`), `registries/phrases` (dead-text deletion).

**This is a fix-and-re-run task, not a greenfield build.**

## The work (TDD, pure-first, kernel-shared — the usual vdocs discipline)

Write the failing test first → red → implement → green → `make check` (≥95% cov) before each commit.
Pure transforms get a Hypothesis property test where it fits. No pattern is hard-coded in stage code —
recurring patterns are curated data in `registries/` (tenet #13). Do the tasks **in order**: each
later task depends on the capture the earlier one persists.

### Task 0 — Baseline

Run the audit script (in the machine report's header, or re-derive it) and confirm the current
numbers: 290 docs, P1 255, P2 200 (0/168 tables detected), P3 210, 30 clean. This is your regression
baseline.

### Task 1 — Fix revision-table detection (P2 root cause; unblocks P1's date too)

In `revision_pure.py`, replace `_is_revision_header` with the **§6.4 corrected contract**: header
(with `**bold**`/markup stripped, case-folded) has a **date** column AND a change-description column
(`description` **or** `change`), optionally a version-ish column (`version` **or** `revision` **or**
`patch`). Add a **heading-proximity guard** so a matching table is only treated as the revision table
when it sits under a revision-history section header — broaden that header detector (here and in
`discover_pure.py`) beyond `#`-ATX to the **bold / blockquote / plain** forms: `Revision History`,
`Documentation Revisions`, `Template Revision History`, `Documentation Revision History`.

- Tests first, using the real header dialects from the findings doc: `Date·Revision·Description·Author`,
  `Date·Version·Description·Author` (+ bold), `Date·Description·Author`, the
  `Date·Description (Patch # if applic.)·Project Manager·Technical Writer` dialect, and a negative
  (a date/description table **not** under a revision heading must NOT be stripped).
- Acceptance: detection rate over the corpus goes from 0/168 to ≈ full coverage.

### Task 2 — Capture the publication date (P1 capture; must precede any title-page strip)

Add a pure title-page date extractor (reuse the `_TITLE_PAGE_LINES` window + the `era` Month-YYYY
parse) that lifts the publication date into the identity frontmatter **`published`** field, and feed
`official_date` (so `consolidate` no longer depends solely on the revision table). Wire it into
`normalize` **before** `apply_template` strips the title page.

- Tests: `published` populated from a legacy cover; idempotent; absent date → field omitted (and the
  title-page strip in Task 3 is blocked for that doc).

### Task 3 — Standardize + gated-strip the title page (P1 strip)

Replace the raw legacy cover with a **standardized block** built from frontmatter (`title`,
`version`/`patch_id`, `published`, `source_url`). **Gate:** the legacy cover is removed only when
`published` is present (Task 2). Route the residual furniture ("This page intentionally left blank",
etc.) through `registries/phrases`. Keep this within the template/scaffold F-step seam.

- Tests: standardized block emitted; strip blocked when `published` missing; furniture gone.

### Task 4 — Gated-strip the revision history (P2 strip)

Confirm the apparatus (heading + table + the descriptive boilerplate "the following table displays the
revision history…") is removed **only after** capture to `revisions.yaml`. A revision-history heading
with **no parseable table** → **leave it in the body and flag it** (fidelity signal), never delete
blind. Route the descriptive boilerplate through `registries/phrases`.

- Tests: detected table → body stripped + `revisions.yaml` written; unparseable apparatus →
  retained + flagged; descriptive boilerplate deleted.

### Task 5 — Correlate + gated-drop the legacy TOC (P3)

In `anchors_pure` (and the `registries/structures` `toc` strip), implement §6.7:
- Extend the legacy-TOC recogniser to fire on a **plain-text** `Table of Contents` line (not only ATX
  headings) followed by the page-numbered `[Title [n](#anchor)](#anchor)` entry block.
- **Role-1 cross-check:** every legacy-TOC entry's `(#anchor)` must map to a heading in the derived
  `## Contents`. Misses (`#_Toc…`/`#_Ref…` bookmarks, or slugs with no heading) become **heading-recovery
  inputs (role 2) + fidelity flags** — not silent losses.
- **Gate:** drop the legacy TOC only once correlation is clean (or misses are recovered/flagged).
- Also generate `## Contents` for the **30 docs that lack it**.

- Tests: legacy TOC under a plain-text header is stripped; correlation flags an unresolved entry;
  derived Contents present and complete; idempotent (a prior run's `## Contents` rebuilds identically).

### Task 6 — Re-run the pipeline and verify

Re-run `normalize → consolidate` (then `index` / `manifest` as the §8 DAG requires) over the corpus.
Then re-run the **audit script as the regression gate** and write the result to
`~/data/vdocs/reports/fidelity/`:

- `revisions.yaml` / `history.yaml › revisions` populated; `published` / `official_date` populated.
- P1/P2/P3 affected-doc counts at ~0 (residue only where a doc genuinely lacks a date/table → flagged,
  not silently stripped).
- No body lost its publication date or its revision facts (capture-before-strip held).

## Constraints & acceptance

- **Capture-before-strip is the inviolable rule** — never remove a legacy block before the unique fact
  it carries is persisted. When in doubt, retain + flag.
- Update `docs/vdocs-design.md` in the same commit as any further change to a stage's
  inputs/outputs/CLI (the §6.x clauses are already updated for the target design).
- Shared primitives live **once** in `kernel/` — copy-paste across stages is a build-breaking review
  failure (§9.2). `discover` only proposes; it never mutates a body.
- `make check` green (lint + mypy + coverage ≥95%) before each commit. Commit only when asked; clean,
  per-task commit history.
- **Done when:** Tasks 1–5 implemented with tests; Task 6's re-run + regression report committed under
  `reports/`, showing P1/P2/P3 driven to ~0 with zero provenance loss. End with a short findings note
  on any docs that legitimately could not be cleaned (no date on the cover, no parseable revision
  table) and how they were flagged.

Ask only if something genuinely blocks you; otherwise proceed and let the corpus set the thresholds.
