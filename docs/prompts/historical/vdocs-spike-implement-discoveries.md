# Kickoff — capture all templates & boilerplate (act on the vdocs-spike discoveries)

You are working in **`~/projects/vdocs`** (the real pipeline — *not* the spike). Your job is to make
the `discover` stage actually capture, for the whole corpus, the recurring **`(doc_type, era)`
templates** and the recurring **boilerplate** blocks, and to prove that capture flows cleanly through
the curation seam into `normalize`, `fidelity`, and the search index — exactly the value the
`vdocs-spike` scouting run demonstrated.

## Read first (source of truth)

- **`docs/vdocs-design.md`** §8 (stage table — authoritative), **§9.6** (induction↔application split,
  the registry family + dispositions), **§9.7** (registry index), **§9.8** (templates as computable
  structural schemas — the validation oracle), §6.7 (TOC regeneration), §17 (phases: `discover`/
  `normalize` = Phase 3, `fidelity` = Phase 5). The doc is the source of truth; if code disagrees,
  the doc is the bug report.
- **The spike discoveries:** `~/projects/vdocs-spike/docs/vdocs-spike-discoveries.md`
  (repo: <https://github.com/rafael5/vdocs-spike>). It records the empirical findings, the proven
  methods, and the gap list this prompt acts on. Treat its YAML output
  (`~/projects/vdocs-spike/out/{templates,boilerplate}-by-doctype.yaml`) as a **ground-truth
  reference** to diff against — not as something to copy blindly.

## What already exists (do not rebuild)

`src/vdocs/stages/discover/` already implements `mine_templates` (buckets by `(doc_type, era)`,
MinHash scaffold clustering via `kernel/discovery`, consensus schema with `template_id`) and
`mine_recurring_blocks` (classifies blocks into templates / phrases / boilerplate). `registries/
templates/templates.yaml` and `registries/boilerplate/boilerplate.yaml` exist and are partly curated.
**This is an audit-and-close-gaps task, not a greenfield build.** The spike (which used a simpler
exact-anchor method and *no* era axis) is the independent cross-check that surfaced the gaps below.

## The work (TDD, pure-first, kernel-shared — the usual vdocs discipline)

Write the failing test first → red → implement → green → `make check` (≥95% cov) before each commit.
Pure transforms get a Hypothesis property test. No pattern is ever hard-coded in stage code — it is
discovered and curated into `registries/` (tenet #13). `discover` only **proposes**; it must never
mutate a body.

### Task 1 — Filter markdown artifacts before block-splitting (highest-value, concrete)

The spike proved that the dominant boilerplate *noise* is structural markdown, not prose:
`[↑ Back to Contents](#contents)` (in all 120 DIBR docs), secondary plain-text TOC lines like
`[1 Introduction [1](#introduction)](#introduction)`, `<img src="…">` figure tags, and
`_[Table 1 (extracted to CSV)](tables/table-01.csv)_` markers. The current
`discover_pure.split_blocks` splits on blank lines only and keeps all of these, so they surface as
high-frequency "boilerplate."

- Make `split_blocks` (or a new pre-filter it calls) drop a block whose content is *entirely* a
  markdown link / image / table-CSV marker / nav line, while **keeping** prose paragraphs that merely
  contain an inline link. Reference implementation + tests:
  `vdocs-spike/src/vdocs_spike/parse_pure.py::split_blocks` and its `_ARTIFACT_RE`
  (anchored: `<img …>` | `[…](…)`-only lines with optional `_`/`*`/`↑` wrappers).
- Tests: artifact-only lines dropped; a sentence with an inline `[link](url)` kept; the existing
  block-grain behavior unchanged.

### Task 2 — Complete the §9.8 template schema

`TemplateSection` currently carries `{section_id, title, level, required, toc_level}`. §9.8 specifies
a richer **computable** schema. Add the missing fields so the retained schema is a real validation
oracle and reuse asset:

- `title_pattern` — a regex (not just a literal title), induced by clustering near-identical section
  titles in a `(doc_type, era)` cluster (e.g. `Introduction` / `1. Introduction` / `1 Introduction`
  → `^(?:\d+\.?\s+)?Introduction$`). This also tightens cross-doc alignment.
- `semantic_role` — the section's meaning/role where inferable (e.g. `orientation`, `installation`,
  `back-out`, `glossary`); leave null when unknown rather than guessing.
- `repeatable` — whether the section legitimately recurs (e.g. per-patch subsections).
- Keep `required`/`toc_level`. **Re-examine the `required` rule:** today it is *present in every
  cluster member*; the spike found real DIBR sections at 60–94% coverage (not 100%). Decide between
  "every member" and a ratio (the spike used ≥ 0.5) and document the choice in §9.8 / the registry
  README — whichever you pick, justify it against the observed coverage distribution.

### Task 3 — Validate the miners against the corpus ground truth

Run `discover` over the real corpus and **diff** its output against the spike's reference, then write
the result into `reports/`:

- `DIBR` template: confirm the induced `(DIBR, 2010s)` / `(DIBR, 2020s)` schemas reproduce the
  ~39-section Deployment/Installation/Back-out/Rollback skeleton the spike found and that already
  matches `registries/templates/templates.yaml`. This is the regression anchor.
- **The heterogeneous types** (`IG`, `RN`, `TM`, `UM`, `UG`, `DG`): the spike's exact-anchor method
  found *no* required skeleton for these; vdocs's `(doc_type, era)` bucketing + MinHash clustering
  *should* do better. **Verify whether it actually does** — for each, report how many per-era
  template clusters it induces and their coverage. If it still misses, that is the finding to chase
  (likely needs `title_pattern` alignment from Task 2, or era buckets are too coarse/fine).
- Boilerplate: confirm the post-Task-1 block miner surfaces the clean head the spike reported
  (VA title-page furniture, the DIBR/CAPRI description paragraphs, KIDS install prompts, standard
  table captions) and that the artifact noise is gone.

### Task 4 — Prove the seam end-to-end (induction → curation → application → validation)

The spike only does induction. Confirm the rest of the §9.6 loop is wired and works on a small
fixture corpus (real objects, no mocks):

1. `discover` → `reports/patterns/` candidates with evidence + proposed disposition.
2. Curation promotes a candidate into `registries/{templates,boilerplate}` (graded auto/PR).
3. `normalize` consumes the curated registry and applies the disposition deterministically:
   **STRIP** template scaffold + stamp `template_id`; **REFERENCE** boilerplate to `gold/_shared/`;
   regenerate the TOC from headings (§6.7). Assert `normalize` is a pure fn of `(doc, registry)` —
   same registries in, same body out (idempotent).
4. `fidelity` consumes the retained schema as the **template-compliance oracle** (§9.8): score a doc
   vs. its own `(doc_type, era)` template (extraction-independent bug oracle) and the era-template vs.
   the canonical `doc_type` schema (source-drift signal). Confirm `validate` gates on the verdict.

### Task 5 — Promote the validated patterns

Hand-merge through the curation gate (a `registries/` PR, recorded in version control):

- The validated **`DIBR` template** (low risk — already cross-validated).
- The clean top-evidence **boilerplate** for `DIBR`, `IG`, `TM`, `DG` (boilerplate pays off even
  where templates don't — it does not require a coherent skeleton).
- **Hold** the small-cohort "strong" templates (`API`, `CFG`, `POM`, `AG`) for human review — `API`
  is a heading dump (8 near-identical docs), `CFG`/`AG` are plausible.
- **Defer** `RN`/`IG`/`TM`/`UG`/`DG` templates until Task 3 shows the era+pattern approach induces a
  real skeleton; promote their boilerplate now regardless.

## Constraints & acceptance

- Update `docs/vdocs-design.md` in the same commit as any change to a stage's inputs/outputs/CLI or to
  §9.8 (e.g. the new `TemplateSection` fields, the `required` policy decision).
- Shared primitives (shingling/MinHash/clustering, artifact filtering if reused) live **once** in
  `kernel/discovery/` — copy-paste across stages is a build-breaking review failure (§9.2).
- `make check` green (lint + mypy + coverage ≥95%) before each commit. Commit only when asked; clean,
  per-task commit history.
- **Done when:** Tasks 1–2 implemented with tests; Task 3 validation report committed under `reports/`
  (DIBR regression-anchored, heterogeneous types characterized); Task 4 seam proven end-to-end on a
  fixture; Task 5 promotions opened as a reviewable `registries/` change. End with a short findings
  note: which doc_types now have curation-worthy templates vs. which remain heterogeneous and why.

Ask only if something genuinely blocks you; otherwise proceed and let the corpus set the thresholds.
