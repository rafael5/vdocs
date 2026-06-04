# vdocs — Implementation Plan & Tracker (whole pipeline)

**Living document.** The build plan *and* running tracker for the **entire vdocs pipeline** — both
medallions, all stages, against **[`docs/vdocs-design.md`](vdocs-design.md)** (the architectural source
of truth: §8 stage table, §17 phased build plan, §4 two medallions). The **inventory medallion**
(`crawl`→`catalog`→`serve-inventory`) has its own detailed sub-tracker —
**[`vdl-crawl-tracker.md`](vdl-crawl-tracker.md)** — and component spec
(**[`vdl-crawl-spec.md`](vdl-crawl-spec.md)**); this document is the umbrella and is authoritative for
*cross-phase* status. QA/fidelity is specified by **[`fidelity-framework.md`](fidelity-framework.md)**.

**How to use.** Build the **spine before the stages** (§17). As each stage lands, flip its **Status** +
fill **Evidence** here, append a **Change Log** entry, and record any **Lessons Learned**. The §8 stage
table is authoritative for `requires`/`produces`/idempotency; this tracker tracks *progress* against it.
Keep every increment green: `make check` (ruff line 100 · mypy · pytest random-order · coverage ≥95%).

**Status legend:** ☐ todo · ◐ in progress / partial · ✅ done (tests + `make check` green) · ⏸ blocked ·
⬚ deferred · 🔁 re-run/iterative

**Tenets that gate every stage:** contract-bound (preflight/postflight), idempotent, pure transforms in
`*_pure.py` + thin I/O drivers, one shared `kernel/` (no copy-paste), discovery-is-data (`registries/`,
never hard-coded), atomic writes (temp+rename), fail-loud preflight with remediation.

---

## Overall status

**Pipeline stages (§8): 13 ✅ · 1 ◐ · 5 ☐** (of 19 = 18 stages + the MCP server; the Phase‑1 spine is
counted separately below). Last updated **2026-06-04** (status audit). **Phases 1–4 complete; Phase 5
in progress** on branch `feat/phase-5-sidecar-verification` (**not yet merged** to `master`; far ahead
of it). Phases 1–3 merged to `master` (PRs #3/#4/#5); Phase 4 (`consolidate`→`index`→`relate`→
`manifest`) ✅; Phase 5 so far = the **`validate` HARD GATE** ✅ (sidecar-verification slice — typed
absence · count reconciliation · ref resolution · signed-bundle integrity) **plus a full gold-cleanup
remediation pass** (title-page/revision-history/legacy-TOC strip-with-capture, §6.3/§6.4/§6.7).

**The lake has been expanded and fully re-run since the prior update: 469 → 1299 docs / 290 → 409
version groups.** The whole pipeline `crawl`→…→`validate` ran green on the 1299-doc lake on
**2026-06-03** (convert 1301 docs/23 185 assets; normalize 1299; consolidate 409 groups; index 1299
docs/70 613 sections/24 999 FTS; relate 46 263 edges; manifest 1299 docs/409 groups, semantic
unavailable; **validate gate PASSES** — `blocking=false`, `severed=[]`, `reconcile_findings=[]`,
`bundle_findings=[]`, the only soft signal is the known `_Toc` ref-resolution gap, unmapped_rate 0.76).
Gold cleanup audit (290-doc baseline): legacy title page 256→5, revision-history 202→23, legacy TOC
226→1, "clean on all three" 9→**263/290 (91%)**, every residual carries a `flags.yaml` (zero silent
residue). `make check` green (**681 tests, coverage 98.71% / gate ≥95%**, ruff+mypy clean). Uncommitted
WIP: the code-review Stage-4 §9.2 follow-ups (read-only-URI single-sourcing, `_MONTH`→kernel,
`load_mapping` widening) + refs-metric refinements — all 681 tests green.
**Next (REPLANNED 2026-06-04 → substrate-first; see [`v1-lessons-and-v2-priorities.md`](v1-lessons-and-v2-priorities.md)
+ the Phases 5–6 workstreams below).** The real-corpus run showed the validate gate passing over a
*weak* search surface (14.2% hollow chunks, 4 entity types, no semantic mode), and disproved the C5
`_Toc`-recovery hypothesis (the `_Toc` fix `f6e4767` recovers ~1/534; unmapped refs are non-heading by
construction, `severed`=0 is the real floor). Spec amended doc-first (C5 · concrete chunking · entity
coverage · tenet #14). **Build order is now substrate → measure → gate:** start **A1 structure-aware
chunking + A2 heading-recovery-v2 + a B3 retrieval-quality baseline**, then A3 entities → B1 fidelity →
D1 embed → C gate → publish. A gate certifies discoverability; it cannot create it.**

| Phase | Title | Status | Progress |
|---|---|:--:|:--:|
| 1 | Spine (kernel·config·models·contracts·orchestrator) | ✅ | 4/4 |
| 2 | Inventory medallion + doc-bronze | ✅ | 4/4 |
| 3 | Silver — document text (convert·discover·enrich·normalize) | ✅ | 4/4 |
| 4 | Gold derive (consolidate·index·relate·manifest) | ✅ | 4/4 |
| 5–6 | **Deliver + Machine interface — REPLANNED substrate-first** (A chunking/headings/entities → B measure → C gate → D embed/serve/publish) | ◐ | validate ✅ · fidelity ◐ · substrate A/B/C/D ☐ |
| 7 | Harden (property·--verify·gc·docs-gen·replay·refresh) | ◐ | 2◐·1⬚·3☐ |

## Phase / stage summary

*Compact, page-width view — terse goal only. **Full evidence, test counts, and rationale live in the
Change Log** below and in `vdocs-design.md` §8. Status: ✅ done · ◐ partial · ☐ todo · ⬚ deferred.
Layer: 🥉 bronze · 🥈 silver · 🥇 gold; INV = inventory medallion, DOC = document medallion.*

**Phase 1 — Spine** ✅ 4/4

| Stage | Layer | St | Ref | Goal |
|---|:--:|:--:|---|---|
| kernel | — | ✅ | §9.2 | primitives: text·cas·db·http·discovery |
| config | — | ✅ | §5.3 | `Settings` off `DATA_DIR`; paths derived |
| models/contracts | — | ✅ | §7.1 | types; `ArtifactContract`; registry |
| orchestrator | — | ✅ | §7.1 | `Stage` + DAG + `stage_runs` |

**Phase 2 — Inventory medallion + doc-bronze** ✅ 4/4

| Stage | Layer | St | Ref | Goal |
|---|:--:|:--:|---|---|
| crawl | 🥉 INV | ✅ | §8 | vdl → catalog.raw |
| catalog | 🥈 INV | ✅ | §8 | catalog.raw → enriched (5-pass) |
| serve-inventory | 🥇 INV | ✅ | §7.3 | → gold inv; **HARD GATE** |
| fetch | 🥉 DOC | ✅ | §5.6 | gate+sel → bronze raw (CAS) |

**Phase 3 — Silver document text** ✅ 4/4

| Stage | Layer | St | Ref | Goal |
|---|:--:|:--:|---|---|
| convert | 🥈 DOC | ✅ | §1 | raw → converted + assets |
| discover | 🥈 DOC | ✅ | §9.6 | converted → patterns → registries |
| enrich | 🥈 DOC | ✅ | §8 | converted → enriched (FM) |
| normalize | 🥈 DOC | ✅ | §6.7 | enriched → normalized (+TOC/refs) |

**Phase 4 — Gold derive** ✅ 4/4

| Stage | Layer | St | Ref | Goal |
|---|:--:|:--:|---|---|
| consolidate | 🥇 DOC | ✅ | §6.6 | normalized → consolidated (lineage) |
| index | 🥇 DOC | ✅ | §8 | → index.db (FTS5, IDs) |
| relate | 🥇 DOC | ✅ | §8 | index.db → relations (graph) |
| manifest | 🥇 DOC | ✅ | §14 | → corpus-manifest + discovery |

**Phases 5–6 — Deliver + Machine interface — REPLANNED 2026-06-04 (substrate-first).** The old
linear order (`fidelity → publish → validate → push`, then `embed → serve-mcp`) is **superseded** by
the **substrate-first** workstreams below, per **tenet #14** (discoverability is built upstream of the
gate, then measured) and the real-corpus findings in
[`v1-lessons-and-v2-priorities.md`](v1-lessons-and-v2-priorities.md). The stages still exist; what
changed is the *order* and the addition of explicit substrate-fix + measurement work the linear plan
assumed away. The validate gate already passing on 1299 docs is **not** the finish line — it certifies
a search surface that is currently weak (14.2% hollow chunks, 4 entity types, no semantic mode).

*Stage status (inventory):* validate ✅ (gate built/wired/**passes**: typed-absence · count-reconcile ·
ref-resolution · signed-bundle integrity; schema · ID · fidelity-verdict axes still to fold in) ·
fidelity ◐ (pure oracles `compliance_pure`/`overstrip_pure` exist, **not DAG-wired**) · publish ☐
(no `publish/` dir, no publish tree) · push ☐ · analyze ☐ · embed ☐ · serve-mcp ☐. *Built since the
prior update (all on `feat/phase-5-sidecar-verification`, unmerged): the gold-cleanup remediation
`01df238`→`8f3e6ed` and the validate gate + signed manifest `982046c`→`8f8cfc3`; the `_Toc`-correlation
fix + spec/plan reframe `f6e4767`→ this commit.*

**Workstream A — Fix the retrieval substrate (highest leverage; gates everything downstream).**

| ID | St | Where | Task |
|---|:--:|---|---|
| **A1** | ☐ | `index/index_pure.shred_sections` | **Structure-aware chunking** (§14.6 concrete contract): never emit a hollow content chunk (fold a container heading's lead-in into its first child / synthesized summary), bound oversized leaf chunks (split w/ overlap, stable `section_id` suffix), carry context as metadata. **Target: ≈0% hollow** (baseline 14.2%). Re-index + re-measure. |
| **A2** | ☐ | `normalize/recover_headings` | **Heading recovery v2**: promote `**bold**`+`_Toc`/`_Ref`-span pseudo-headings to real `##` **even when the doc already has headings** (the disproven-`_Toc` finding); give the 24 structureless `is_latest` docs a tree. Side effect: recovers the genuinely-recoverable cross-ref subset + improves the human TOC. |
| **A3** | ☐ | `registries/entities` + `entities_pure` | **Entity depth + denoise**: seed the missing high-value VistA types (RPCs, options, routines, protocols, HL7 segments, mail groups, build/patch); **de-weight/demote ubiquitous raw globals** from the primary discovery surface (keep as evidence). Largest lift for structured+graph discovery. |

**Workstream B — Measure it (the throughline; prove the lift, don't assert it).**

| ID | St | Where | Task |
|---|:--:|---|---|
| **B1** | ☐ | new `fidelity` stage (wire `overstrip_pure`/`compliance_pure`) | **T-only fidelity record first** (FF §12 shape): hollow/over-strip rate, heading-tree sanity, TOC integrity, template self-conformance, capture completeness — deterministic, no source needed. Cheap, immediate signal. |
| **B2** | ☐ | new pipeline-independent DOCX extractor | **Source-anchored `S→T` recall** (FF C1/C3/C4 via `python-docx`): token / table-cell / image recall. The institutional proof. Heavier; after the substrate is good. |
| **B3** | ☐ | new retrieval-quality harness (FF §10.5) | **Golden query set** (50–100 labeled: factual · entity/file-number · cross-doc · version-sensitive) → precision@k / nDCG / **redundancy@k** / **version-correctness**; **ablation** with/without condensation. Run after each A-fix to turn it into a measured number. |

**Workstream C — Gate honestly (`validate`, extend the existing gate).**

| ID | St | Where | Task |
|---|:--:|---|---|
| **C1** | ☐ | `validate/refs_pure` + FF (done doc-side) | **C5 recalibration** already amended in the spec (severed=0 floor; unmapped = reported navigation-completeness, not a recoverability target). Align the code's metric labels/report to match. |
| **C2** | ☐ | `validate` + frontmatter schema | **Frontmatter schema gate + ID/anchor integrity** (design: non-optional before `push`); then **consume the B1 fidelity verdict** (PASS / REVIEW-w-signoff / QUARANTINE blocks). |

**Workstream D — Semantic layer + serving (after A1, so we never embed hollow chunks).**

| ID | St | Ref | Task |
|---|:--:|---|---|
| **D1 embed** | ☐ | §14.6 | `doc_sections` (`is_latest`) → `vectors.db` (ANN over anchor-only chunks); model id+version gates the DB. B3 then measures semantic vs lexical vs hybrid. |
| **D2 serve-mcp** | ☐ | §14 | MCP server fusing semantic + lexical + structured + graph (RRF); resources/tools/prompts over the stable-ID scheme. |
| **publish/push** | ☐ | §8/§6.6 | human GitHub tree + INDEX (resolves `_shared/` depth, §5.3) → git, **after** A1/A2 (publish bakes the navigation the substrate fixes produce). |

**Sequence (critical path):** **A1 + A2 + B3-baseline first** (highest leverage, no external dep,
improve human TOC *and* machine chunks together; B3 makes every later change a number) → **A3** →
**B1** → **D1 embed** → **B3 semantic/ablation** → **C** gate → **publish/push**. **B2** (independent
source recall) and the full FF §9 human-calibration are the institutional-grade tail — staged after the
substrate is good, so calibration isn't run against a weak surface.

**Phase 7 — Harden** ◐ 2◐·1⬚·3☐

| Stage | Layer | St | Ref | Goal |
|---|:--:|:--:|---|---|
| property tests | — | ✅ | §10 | Hypothesis tests, pure transforms (7 invariants + branch cov) |
| --verify | — | ◐ | §7.4 | full-content-hash fingerprint |
| gc | — | ☐ | §17.7 | sweep superseded silver |
| docs/stages gen | — | ☐ | §17.7 | per-stage ref from contracts |
| push --replay-history | — | ⬚ | §6.6 | commits from history.yaml |
| refresh | — | ☐ | §7.6 | crawl-diff + reprocess |

*Ref `FF` = [`fidelity-framework.md`](fidelity-framework.md).*

**Phase-4 prerequisites (decided in the design `2026-06-02`; do these as the first commits of Phase 4):**
- **`normalize` sidecar rename `history.yaml` → `revisions.yaml` (Phase-4 STEP 0).** The design now reserves
  `history.yaml` for `consolidate`'s version-group lineage (§6.6) and names `normalize`'s per-document
  revision-table extract `revisions.yaml` (§6.4/§5.2). The shipped `normalize` code still writes
  `history.yaml` (`stages/normalize/stage.py` + `revision_pure.py` + tests) — a tracked, transitional
  doc-vs-code deviation; rename it TDD-first before `consolidate` consumes it.
- **`registries/entities` (new, EXTRACT) seeded for `index`.** §8/§9.7 now define a curated VistA-domain
  entity registry (namespaces, FileMan file numbers, routines, options, RPCs, protocols, HL7, mail groups,
  globals, build/patch ids) consumed by `index`'s generic `entities_pure` pass → `index.db:entities` keyed
  by `(type, canonical-name)`. Seed `registries/entities/` (starter set + README) when building `index`.

**Open follow-ups (non-blocking, carried out of dropped detail columns):**
- `normalize` — `callout`→GFM-alert + `revision-table`-heading **CANONICALIZE** consumers are curated in
  `registries/structures` but **not yet applied** (the `toc` consumer shipped; these are their own increment).
- `normalize` — template-governed **TOC depth** is still the **H2–H3 fallback** (§6.7) until
  `registries/templates` depth is consumed (seam marked in `anchors_pure`/`stage.py`).
- `normalize` — **`_Toc`→heading legacy-TOC-correlation recovery** (the C5 resolvability gap; triage
  2026-06-03). ~0.76 of `_Toc…` cross-refs are `UNRESOLVED` (534 of 705 on the 1299-doc lake)
  because Pandoc drops some heading
  bookmark spans, so `anchors_pure` can't capture a `_Toc…` span on the heading line. The mapping is
  recoverable: the legacy TOC (already captured to `toc.yaml`) records `_Toc… ↔ heading-title`, and
  the title → the github slug — so an `anchors_pure` pass could correlate bookmark→title→slug and
  resolve these refs. Not built; `validate` now reports `_Toc` (C5-bounded) and `_Ref`
  (expected-unmapped, non-heading) separately so the metric is honest. The `_Ref` class (~64% of
  unmapped) is expected-by-construction (figures/tables/spans) and stays unmapped.
- Phase 7 — extend **property tests** to `enrich` + remaining `normalize` transforms; exercise `--verify` e2e.
- `normalize` — **`github_slug` global-uniqueness:** `anchors_pure.github_slug` uses GitHub's per-base
  `-N` rule, which can collide a repeated heading's suffixed slug with a literal same-named heading
  (`Example`/`Example 1` → both `example-1`; 3 docs in the corpus). `index` guards its `section_id` PK
  with a `-dup-N` disambiguator; align `normalize` to a globally-unique slug rule so `refs.yaml`,
  the published anchors, and `index` agree on the disambiguated form (a silver change; Phase-4 §14.6 note).
- `publish` — resolve `normalize`'s gold-root-relative boilerplate refs (`_shared/boilerplate/<id>.md`,
  `SHARED_BOILERPLATE_DIR`) to each bundle's published depth when materialising the human tree (PUBLISH
  SEAM marked in `normalize_pure.subtract_boilerplate`, §5.3/§9.7).
- Both **dependabot PRs** (#1 actions/checkout→v6, #2 setup-uv→v7) are **merged** to `master`; `ci.yml`
  is on the upgraded pins. (The stale `docs/phase-4-kickoff` branch that downgraded them was retired.)

**Current focus → Phase 4 `consolidate`.** Phases 1–3 are ✅ and **merged to `master`** (origin tip
`224ab51` at merge); the **pre-Phase-4 hardening pass** then landed on
`fix/compliance-remediation-pre-phase4` (reliability R1–R9 [R4 split to a follow-up], redundancy
D1–D5, `revisions.yaml` rename, drift reconciliation, property suite) — pending merge to `master`.
The inventory medallion + gated bronze, and the full document-silver pipeline
(`convert`→`discover`→`enrich`→`normalize`), all green on a real 469-doc corpus, **DOCX-only** (§1);
`make check` 458 tests, branch cov 99.7% (gate ≥95%). `normalize` shipped every F-step incl. the **legacy-TOC strip**
(`registries/structures` CANONICALIZE `toc`). **Next:** `consolidate` (§6.6) — version-group grouping +
anchor document + append-only `history.yaml` lineage — then `index`→`relate`→`manifest`. Kickoff prompt:
[`docs/prompts/next-session-phase-4-kickoff.md`](prompts/next-session-phase-4-kickoff.md).

**Dependency spine:** Phase 1 ⇒ Phase 2 (crawl→catalog→serve-inventory→**gate**→fetch) ⇒ Phase 3
(convert→discover→enrich→normalize) ⇒ Phase 4 (consolidate→index→relate→manifest) ⇒ **Phases 5–6
(REPLANNED substrate-first, 2026-06-04):** A (chunking·heading-recovery·entities) → B (fidelity·source-recall·
retrieval-harness) → C (gate) → D (embed·serve-mcp·publish/push) ⇒ Phase 7 (harden). The old linear
`fidelity→publish→validate→push` then `embed→serve-mcp` order is superseded (tenet #14: substrate →
measure → gate). The `validate` hard gate remains the deliver-side analogue of the `serve-inventory`
gate, but it now **certifies** the substrate A/B produce — it does not stand in for them.

---

## Lessons Learned

*Append implementation lessons as they accrue (newest first). Inventory-track lessons live in
[`vdl-crawl-tracker.md`](vdl-crawl-tracker.md); cross-phase / architectural lessons go here.*

- **2026-06-02 — A "stable id" derived from GitHub heading slugs is not guaranteed unique — real
  data proved it (the case for smoke-running every gold stage).** `index` keys `doc_sections` on
  `section_id = <doc_key>/<slug>` (matching `refs.yaml`), a PRIMARY KEY. On the 469-doc lake the build
  hit a `UNIQUE constraint failed` on **3 docs / 12 sections**: GitHub's per-base `-N` rule slugs a
  repeated `## Example` heading to `example`/`example-1`/… while a literal `## Example 1` heading
  *also* slugs to `example-1` — a genuine GitHub anchor ambiguity (GitHub itself emits the colliding
  anchor). Fix: a deterministic `-dup-N` disambiguator in `index`'s `shred_sections` so section ids
  stay unique; the GitHub anchor for those rare headings is ambiguous regardless, so `refs.yaml`
  can't disambiguate either. **Follow-up:** align `normalize`'s `anchors_pure.github_slug` to a
  globally-unique rule (track emitted slugs, not a per-base counter) so the published anchors,
  `refs.yaml`, and `index` agree on the disambiguated slug — a silver change, deferred out of Phase 4.
  Lesson: pure-unit fixtures with tidy headings never produce this; only the real corpus does. Smoke
  every gold stage on the full lake before declaring it done.
- **2026-06-02 — The grouping key a downstream stage needs may already be reconstructible from the
  artifact it already requires.** `consolidate` (§8) `requires` only `text@normalized` + `assets`,
  yet must group members by `anchor_key` and order by patch number — data `catalog` computes and that
  lives in `catalog.enriched` / `index.db:doc_meta_staged`, neither of which is a `consolidate` input.
  The reflex is to add an input (doc-first §8 change). But `anchor_key = app:pkg:doc_code` and the
  normalized bundle's **identity frontmatter already carries `app_code` + `pkg_ns` + `doc_type`
  (=`doc_code`)** — and `enrich` bakes the *final, post-inference* `doc_code` as `doc_type`, so a
  reconstructed `anchor_key` equals catalog's value **byte-for-byte** (verified on the 469-doc lake:
  290 groups, all non-empty). So the right move was to **promote the formula to `kernel.ids.anchor_key`
  (now shared by `catalog` + `consolidate`, §9.2)** and reconstruct from the FM — no new input, no
  silver re-run, the §8 `requires` honoured literally. Lesson: before widening a contract, check
  whether the required artifact's frontmatter/path already determines the missing key; a faithful
  reconstruction beats a new dependency. (Ordering needs a stable final tiebreak: the real corpus has
  groups whose members share one `patch_id` — e.g. `CPRS:CPRS:TM` ×4 all `CPRS*3.0` — so sort on
  `(patch_num, official_date, doc_slug)`, not patch number alone, or the order is non-deterministic.)
- **2026-06-02 — A curated registry with no consumer is a silent deviation.** `discover` mined the
  structural conventions (P2.2a) and they were curated into `registries/structures` (7 entries:
  callouts, `toc:contents`, `revision-table`), and the design names `normalize` as their consumer
  (§9.6 CANONICALIZE) — but `normalize` never loaded the registry. The visible symptom was a
  **duplicate table of contents**: `normalize` *adds* a derived `## Contents` but the source's legacy
  text TOC (heading + page-numbered entries) was never *removed* — `strip_existing_toc` only matched
  `normalize`'s own `## Contents` output (for idempotency), not legacy variants like
  `# Table of Contents`, which then also leaked in as a TOC entry (`parse_headings` skips only the
  exact text "Contents"). Fix: a registry-driven `strip_legacy_toc` F-step keyed on a curated `match`
  variant list, run *before* TOC regeneration. Lesson: a registry is only "built" when a stage
  *consumes* it — track producer **and** consumer; `discover`→curate→`normalize` is one seam, not two
  independent ✅s. The other two structures conventions (callout, revision-table heading) remain
  unconsumed and are now explicitly logged as follow-ups in row 60, not left implied-done.
- **2026-06-02 — Unifying onto a library means inheriting its opinions.** Collapsing the two mojibake
  fixers onto `ftfy` (§9.2) was the right call — but `ftfy.fix_text`'s default `uncurl_quotes` *straightens*
  smart quotes (`"` → `'`, `"…"` → `"…"`), which the old custom kernel round-trip preserved. The catalog
  already ran ftfy, so the corpus inventory was unaffected and the pinned fixture reproduced byte-for-byte;
  the only thing that changed was the kernel's own (consumer-less) `clean()` and its tests, which were
  rewritten to assert ftfy's behavior. Lesson: when you replace a hand-rolled transform with a library,
  diff the *behavior* not just the call site — and confirm the canonical choice is the one already validated
  against real data (it was). If body-text normalization ever consumes `kernel/text.clean`, revisit whether
  uncurled quotes are wanted there and pass `uncurl_quotes=False` if not.
- **2026-06-01 — Measure the RIGHT signal — and check the prior art (correcting the entry below).**
  My first Docling probe measured **heading count** and concluded "Docling doesn't help" — wrong on both
  ends: it flagged 45 zero-heading docs Docling can't help *and missed `cprsguium`*, the one doc it does.
  The v1 `vista-docs` converter code named the real pathology: a handful of DOCX wrap lists in Word
  `[[…]](#_Toc…)` cross-reference fields that **Pandoc explodes into thousands of bare list markers**;
  Docling reconstructs them. Re-probing on the correct signal (`[[` cross-ref wraps + bare markers) flags
  **exactly `cprsguium`** (5,092 wraps, 3,058 bare markers — 65% of all bare markers in the corpus), and
  routing it to Docling was verified end-to-end: **bare markers 3,058→0, list items 332→3,230**, lists
  restored, images extracted. Lesson: *headings ≠ lists*; pick the metric that matches the failure, and
  read the prior art before declaring a fix dead. (Docling still runs out-of-process — it pins
  `typer<0.22` vs our `>=0.26.5`.) The zero-heading docs are a *separate*, real issue whose fix is heading
  recovery (§6.7), not a converter swap.
- **2026-06-01 — Real documents found a bug synthetic fixtures hid (the case for processing real
  docs).** Running `convert` on 469 real VA DOCX (seeded offline from v1's `raw/`, all 90 CPRS included)
  exposed that **Pandoc emits images as HTML `<img src="…">` with absolute temp paths**, not markdown
  `![]()` — so `rewrite_image_refs` missed them and **91% of bodies (428/469) carried dead `/tmp/…`
  image refs** even though the bytes were correctly in the CAS. Real VA docs are also far more
  image-heavy (5k+ assets) and use EMF/WMF/GIF. Fix: rewrite both syntaxes, match by **basename**
  (robust to Pandoc's path form). Lesson: keep the unit fixtures, but **drive a real corpus through
  each document-medallion stage** — the mess is the requirement, and you can't fixture what you haven't
  seen. (EMF/WMF→PNG rendering + per-doc convert resilience noted for later.)
- **2026-06-01 — Optional outputs don't gate.** A doc with no images yields an *empty* asset CAS, which
  `TREE_ASSET_CAS.validate()` rejects as empty. Rather than special-case it, the generic postflight/skip
  now ignore `optional` produces (and only fingerprint produced artifacts that actually validate). `convert`
  marks `assets` optional. This is a reusable rule for any stage whose output is conditionally present.
- **2026-06-01 — Inject the heavy backend; keep the stage pure-testable.** `convert`'s binary→markdown step
  (Pandoc/Docling) is an injected callable, so the stage is fully tested with a fake converter (no Pandoc in
  the test path) and the real Pandoc default is exercised by a one-off smoke check. Same pattern as the
  crawl page-fetcher and the fetch byte-fetcher.
- **2026-06-01 — Generate replication data from the v1 source, don't hand-copy.** The registries (196-app
  system map, 95 manual overrides, 57 ordered doc-type regexes, …) were ported by a one-off generator that
  `ast.literal_eval`-extracts the v1 literals — then deleted, with the YAML committed as the in-repo source
  of truth. Exact-count matches verified fidelity. Same principle will apply to any future v1-derived
  vocabulary (boilerplate/template/glossary candidates in Phase 3 `discover`).
- **2026-06-01 — Validate transforms against a pinned real corpus, not just synthetic fixtures.** Pinning
  the 8,834-row v1 `vdl_inventory.csv` (gzipped, 142KB) turned the §7 sanity targets into *exact* unit
  assertions and proved no-information-loss end-to-end. Phase 3+ transforms (convert/normalize/fidelity)
  should likewise pin a small set of real documents as golden fixtures.
- **2026-06-01 — Make the gate real by wiring it into `requires`, not by convention.** A "hard gate" only
  gates if a downstream stage *requires* the gated artifact: `fetch` requires `GOLD_INVENTORY`, so the
  generic consumer-preflight refuses to fetch until `serve-inventory` is `ok`. The same pattern wires the
  Phase-5 `validate` gate before `push`.
- **2026-06-01 — Keep mutable status out of deterministic artifacts.** Per-document fetch status lives in
  `state.db:acquisitions` (keyed by the stable `doc_id`), joined *to* the inventory via `inventory_status`,
  never baked into `catalog.enriched` — which must stay a pure function of the crawl (idempotency).
- **2026-06-01 — Thread the post-redirect *final* URL end-to-end.** `kernel/http` returns the final URL;
  the crawl driver resolves each level's links against *that* (not the requested URL). The bug was
  invisible to parser-only fixtures — a driver-level test with a redirecting fake caught it.

## Change Log

*Newest first. One entry per meaningful tracker/implementation change.*

- **2026-06-04** — **Phases 5–6 REPLANNED substrate-first + doc-first spec amendments (the v1→v2
  reframe).** After the real-corpus audit + the disproven C5 hypothesis, decided (with the maintainer)
  *not* to rewrite the sound spec but to **amend it surgically + rewrite the build plan + keep the
  code**. Landed, doc-only: (1) **[`v1-lessons-and-v2-priorities.md`](v1-lessons-and-v2-priorities.md)**
  (`bc6a0bd`) — the synthesis/decision record (what real data confirmed vs corrected; the substrate-first
  principle; the scope decision). (2) **Spec amendments** (`77accc4`): `fidelity-framework.md` C5
  recalibrated (severed=0 floor; unmapped = reported navigation-completeness over non-heading targets;
  the ≤0.02 `_Toc` target withdrawn) + §10.5 over-strip calibrated to the 14.2%-hollow baseline;
  `vdocs-design.md` §14.6 concrete chunking contract + §8 entity-coverage build requirement + **tenet
  #14** (discoverability is built upstream of the gate, then measured). (3) **This tracker**: Phases 5–6
  rewritten into the substrate-first workstreams **A** (chunking·heading-recovery·entities) → **B**
  (T-only fidelity·source-recall·retrieval-harness) → **C** (gate) → **D** (embed·serve-mcp·publish),
  superseding the old linear `fidelity→publish→validate→push`/`embed→serve-mcp` order; summary table +
  dependency spine + header recommendation updated. **Critical path:** A1 chunking + A2 heading-recovery
  + B3 retrieval baseline first. No code changed in the reframe; `make check` still green at 683.
- **2026-06-04** — **`_Toc` bookmark-correlation fix built + real-data finding that the C5 recovery
  hypothesis is wrong (`f6e4767`, TDD).** Implemented the documented-but-unbuilt §6.7/FF-C5 remediation:
  `normalize_pure.correlate_bookmarks_by_title` composes the legacy TOC's `bookmark ↔ title` (toc.yaml)
  with the derived `title → slug` to recover heading bookmarks conversion dropped, threaded through
  outbound resolution + the legacy-TOC resolved/unresolved views (refs.yaml stays consistent; inline
  spans win via setdefault). +2 unit tests; `make check` green (**683 tests, 98.71%**). **Then validated
  on the real 1299-doc lake (`run --from normalize --to validate --force`) — and it recovers only ~1 of
  534 (unmapped 534→533).** Corpus analysis: of 533 unmapped `_Toc` refs, **480 are in-body cross-refs
  (not TOC entries) and 53 are TOC entries to stripped/headingless front matter**; of the 336 whose target
  span survives conversion, **0 are on a heading line** — they point at bold-text pseudo-headings Pandoc
  rendered as `**bold**` (e.g. `**Reminder Location List Menu**`), table/figure captions, and stripped
  sections (Revision History / List of Figures). None are GitHub heading anchors, so the C5 "unmapped"
  rate (0.76) is measuring a largely-unrecoverable class. `severed` stays **0** (the real silent-loss
  floor is sound). **Next remediation is A (recalibrate C5 doc-first → expected-unmapped) or B (extend
  `recover_headings` to promote `**bold**`+`_Toc`-span paragraphs to headings).** The correlation fix is
  kept — correct + harmless, recovers genuine cases where they exist; the finding is the deliverable.
- **2026-06-04** — **Whole-pipeline status audit + corpus-quality assessment (tracker reconciliation).**
  Audited the running lake vs. this tracker (which had drifted: it framed a 469-doc / 290-group / Phase-4
  state and "524 tests"). **Reality on disk:** the lake was expanded to **1299 docs / 409 version groups**
  and the full pipeline (`crawl`→`validate`) re-run green on **2026-06-03**; `feat/phase-5-sidecar-verification`
  carries a complete **gold-cleanup remediation** (title/revhist/legacy-TOC) *and* the **`validate` HARD GATE**
  beyond what the tracker recorded — none merged to `master`. `make check` green at **681 tests / 98.71%**.
  Reconciled the Overall-status block, the Phase-5 detail table, and the phase summary above.
  **Corpus state & quality:** silver 1299/1299 normalized; gold derive complete; the validate gate **passes**
  (`severed=[]`, reconcile 0, bundle 0); gold-cleanup audit shows **91% of docs clean** on all three legacy
  artifacts with zero silent residue (every residual flagged). **Coverage of the genuine in-scope DOCX
  inventory (3 728 docx; pipeline is DOCX-only §1): 1299 docs = 35%, 409/764 version-groups = 53%, 140/175
  apps = 80%** — by section: Clinical 1007/2544 (40%), Infrastructure 163/235 (69%), Financial-Admin 78/643
  (12%), GUI-Hybrids 50/305 (16%), Monograph 1/1. The corpus is a deliberate, representative *selection*
  (CPRS+clinical, pharmacy family, tier-2, 6-package — the `select-*.txt` sets), not full coverage; not a bug.
  **Single biggest quality gap:** the known **`_Toc` cross-ref resolution** — 534/705 `_Toc…` refs UNRESOLVED
  (unmapped_rate 0.76, above the C5 ≤0.02 target) because Pandoc drops heading bookmark spans; recoverable in
  `normalize` via legacy-TOC title→slug correlation (`toc.yaml` already captures `_Toc↔title`). It degrades
  in-corpus navigation but does **not** block the gate. **Recommendation: close the `_Toc` gap in `normalize`
  before building `publish`** (publish bakes the navigation links into the human tree), then proceed
  `publish`→`push`. Secondary: land the uncommitted code-review §9.2 WIP and merge the branch; widen the
  `fidelity` oracles into a wired stage. No code changed in this audit; doc-only reconciliation.
- **2026-06-03** — **Phase 5 ref-resolution recalibration: split the C5 unmapped metric (`_Toc`
  recoverable vs `_Ref` expected), doc-first + TDD.** A real-lake triage of the validate gate's 88%
  unmapped-ref rate (1378/1549 on the 1299-doc lake) found the old "~92% expected" framing
  **miscalibrated**: it conflated two classes. `_Ref…` cross-refs (~64% of unmapped) target
  **non-heading** objects (figures/tables/numbered items/page spans) — 0 of 844 ever resolve;
  unmappable to a heading anchor by construction → now classified **expected-unmapped**, reported but
  **outside** the C5 rate. `_Toc…` cross-refs (TOC fields → headings) are the **C5-bounded,
  recoverable** class — ~0.76 unmapped today (534/705) because Pandoc drops some heading bookmark spans (so
  `anchors_pure` captures nothing inline), but reconstructible from the legacy TOC (`_Toc… ↔ title`
  in `toc.yaml`): logged as a `normalize` legacy-TOC-correlation follow-up. **Code (TDD):**
  `refs_pure` gains `EXPECTED_UNMAPPED` + a `_Toc`-prefix split in `resolve_refs`; `validate`'s report
  splits `unmapped_count` (the `_Toc` C5 class) from `expected_unmapped_count` and computes
  `unmapped_rate` over the heading-targeting universe (`outbound_total − expected_unmapped`); **gate
  blocking behaviour unchanged** (still severed + reconcile + bundle only). **Doc-first:**
  `vdocs-design.md` §8 validate row + §8 notes, `fidelity-framework.md` C5. Tests: +1 refs_pure unit,
  +1 validate integration, property test updated to exercise both UNRESOLVED branches. `severed: []`
  confirmed corpus-wide (the hard floor is sound; only the aggregate metric was wrong).
- **2026-06-03** — **Code-review Stage 4 + Theme-1 kernel-adoption cleanup (§9.2), TDD.** Full
  six-reviewer compliance/quality/reliability/coherency pass (no CRITICAL/HIGH) captured in
  [`docs/code-review-stage4.md`](code-review-stage4.md), with the follow-up plan in
  [`docs/prompts/code-review-stage-4-plan.md`](prompts/code-review-stage-4-plan.md). Closed the §9.2
  findings: read-only SQLite URI single-sourced through `kernel.db.connect` (`fingerprint.py`,
  `models/artifact.py`; locked by an architectural guard test), catalog's private `_MONTH` table
  folded onto `kernel.text.month_year_iso` (behaviour-preserving), and `kernel.registry.load_mapping`
  widened to any YAML mapping with the six inline sidecar reads in
  `consolidate`/`index`/`validate` repointed onto it.
- **2026-06-03** — **Phase 5 Step 4: signed bundle manifest (§5.3) + per-stage attestation note
  (§5.4), TDD.** Raises the proof from "flagged" to "verifiable." New pure `kernel/bundle.py`
  (`build_manifest` — part list + per-part `sha256`/bytes + folded capture outcomes + `source_sha256`
  roots + `bundle_digest` = sha256 over sorted `path:sha256`; `verify_manifest` — recompute vs disk →
  typed integrity findings: missing/extra part, hash mismatch, digest mismatch). `consolidate` writes
  `bundle.yaml` into each anchor bundle **last** (it manifests every *other* part, never itself).
  `validate` gains a 4th gate behavior — **bundle integrity**: for each `consolidated` anchor bundle,
  recompute every part hash, confirm the part set matches `bundle.yaml` exactly, recompute the digest;
  any mismatch (tamper/incompleteness) blocks. `validate.requires` += `CONSOLIDATED` (§8). **"Signed" =
  a verifiable content digest** (key-free, tamper-evident); a keyed GPG/cosign signature over
  `bundle_digest` is a future increment. **§5.4 (partial):** per-stage consumed/produced artifact
  hashes already live in `state.db:stage_runs` (`inputs_fp`/`outputs_fp`); the manifest anchors each
  bundle to its `source_sha256` roots + `tool_ver`; a formal exportable in-toto/SLSA chain is deferred.
  Doc-first: `vdocs-design.md` §6.6/§8, `fidelity-framework.md` §6, `doc-sidecar-design.md` §4/§5.6.
- **2026-06-03** — **Phase 5 STEP 0 (doc-first): sidecar-verification design folded into the source of
  truth.** Implements the [`doc-sidecar-design.md`](doc-sidecar-design.md) §5 recommendations §5.1/§5.2/
  §5.5 (the typed-absence / count-reconciliation / ref-resolution gap, §4 of that note). **Mechanism
  decided: a new per-bundle `capture.yaml`** (not an extension of `flags.yaml`) — `flags.yaml` is the
  *sparse* attention signal (present ⇒ needs attention), `capture.yaml` is the *dense* always-written
  completeness manifest (every capture attempt + a typed outcome `captured`/`failed`/`absent-expected`/
  `absent-unexpected`, plus an independent residue re-scan). Conflating them would destroy the sparse
  property §2 of the note relies on; `capture.yaml` is also the seed of the §5.3 signed bundle manifest.
  **Design edits:** `vdocs-design.md` §5.2 (bundle parts), §6.4 (the typed capture-attempt subsection),
  §8 (`normalize` writes `capture.yaml`; `consolidate` propagates the latest member's; the `validate`
  row now specifies the **sidecar-verification slice** — typed-absence gate + count reconciliation +
  ref-resolution gate — built ahead of full `fidelity`), §8 notes, §17 Phase 5. `fidelity-framework.md`
  C2 (sidecar completeness / count reconciliation), C5 (ref-resolution gate generalising the TOC
  round-trip to all cross-refs), §6 provenance (capture completeness as part of "provable, not
  asserted"). **Scope:** `validate` is built as the single verification consumer (the §8 HARD GATE);
  the broader `fidelity` S→T axes (C1/C3/C4…) and the full `validate` schema/ID/vector gate remain
  TODO and feed the same gate later. Code (Steps 1–3) lands in the following commits.
- **2026-06-03** — **Phase 5 Steps 1–3 (code): typed absence + count reconciliation + ref
  resolution (TDD).** **Step 1 (§6.4):** `normalize` now writes a **`capture.yaml` for every bundle**
  via the pure `stages/normalize/capture_pure.py` (scan_residue — an independent, deliberately-broad
  second-signal re-scan + classify into captured/failed/absent-expected/absent-unexpected +
  build_manifest); `tables_pure.count_qualifying_tables` is the table residue post-condition; the
  driver surfaces `capture_sidecars` + `absent_unexpected` counts; `consolidate` propagates the
  latest member's `capture.yaml` to the anchor (like flags/toc). **Steps 2–3 (§8 HARD GATE):** a new
  **`validate` stage** (the §8 gate's first slice, `ALWAYS_RERUN`) with pure cores
  `stages/validate/reconcile_pure.py` (per-doc absent-unexpected + corpus-zero whole-detector failure
  + cross-run count-drop, reading the emitted `stage_runs[normalize].counts` + the prior report as
  the baseline) and `stages/validate/refs_pure.py` (severed vs. unmapped outbound-ref classification);
  the driver writes `reports/validation/verification.json` and fails loudly via `deep_gate`. New
  `VALIDATION_REPORT` contract + `cfg.validation_report` + the `validate` CLI command + DAG wiring.
  **Ref-gate semantics (doc refined to match code):** severed cross-refs hard-floor zero; `UNRESOLVED`
  is the already-flagged measured class bounded by the C5 ≤0.02 rate (FF C5, §8 validate row updated).
  Tests: 16 `capture_pure` + 6 `refs_pure` + 6 `reconcile_pure` unit + 4 property + 3 normalize / 1
  consolidate / 8 validate integration. **`make check` green: 652 tests, coverage 98.72%** (gate
  ≥95%), ruff + mypy clean. **DoD met:** a missing sidecar is no longer ambiguous — benign absence
  (`absent-expected`) is distinct from a silent detector failure (`absent-unexpected`), and the gate
  fails loudly on the latter. (Not yet smoke-run on the full 469-doc lake; pure+integration only.)
- **2026-06-02** — **Phase 4 Increment 4: `manifest` ✅ — Phase 4 COMPLETE (§14.4, D3).** Final
  gold-derive stage: the agent front door. Pure assembler `manifest_pure` builds `corpus-manifest.json`
  (counts, lineage `tool_ver`/`generated_at`, the stable-ID scheme, the MCP capability manifest) +
  `discovery.json` (corpus schema + entity-type vocabulary + ID scheme + capabilities) from corpus
  counts the driver gathers off `index.db`. **D3 — `vectors.db` is OPTIONAL:** built against
  `consolidated` + `index.db` alone it omits the embedding-model id+version and marks **semantic search
  unavailable** (`capabilities.semantic=false`, `embedding=null`); the lexical/structured/graph modes
  are live. A test proves the Phase-6 flip: a `vectors.db` with an `embedding_model` row turns semantic
  on. `generated_at` tracks the clock (so a forced rebuild's timestamp differs by design; the *counts*
  are a pure function of inputs), and the no-force SKIP path never rewrites. `CORPUS_MANIFEST` +
  `DISCOVERY_JSON` contracts + the `manifest` CLI + DAG wiring (`…relate → manifest`). Tests: 5
  `manifest_pure` + 5 integration (JSON schema, counts == index.db, semantic-off, semantic-flip,
  vectors-without-meta, skip, forced-rerun count stability). **Real lake (DoD):** the whole gold-derive
  layer regenerated in one `vdocs run --from consolidate --to manifest --force` pass (consolidate 290
  groups → index 469 docs/25 981 sections/16 756 FTS → relate 24 366 edges → manifest 469 docs/290
  groups, semantic unavailable); a no-`--force` re-run **SKIPs all four**. **Pipeline tally: 12 ✅** (8
  + the 4 gold-derive stages). **524 tests, branch cov 99.7%**, ruff+mypy clean.
- **2026-06-02** — **Phase 4 Increment 3: `relate` ✅ (knowledge graph, §8).** Third gold-derive
  stage — cheap, re-runnable, adds **only edges** over the entities `index` extracted (no new
  extraction). Pure core `relate_pure.derive_edges` builds three edge families from the same mention
  rows: **`mentions`** (doc→entity, weight = mention count), **`cooccurs`** (entity↔entity within a
  *section* — the tight, bounded scope; undirected, `src<dst`), and **`xref`** (doc↔doc via a shared
  *significant* entity — `XREF_TYPES` = build/fileman_file/package_namespace, excluding ubiquitous raw
  globals so the doc graph stays meaningful). Thin driver reads `entity_mentions ⋈ entities` and
  appends the `relations` table. **§9.2 promotion:** `enrich`'s atomic single-table-swap extracted to
  **`kernel.db.replace_table_atomic`** (build a side table → drop-old/rename-new in one
  `BEGIN IMMEDIATE`); `enrich` repointed onto it, `relate` uses it to add `relations` **without
  touching `index`'s tables in the same file** — and because the cheap SQLite fingerprint is
  per-table row-count, relate's write doesn't invalidate `index`'s recorded fingerprints (both skip on
  a clean re-run, verified). `RELATIONS` contract + the `relate` CLI + DAG wiring (`…index → relate`).
  Tests: 6 `relate_pure` + 3 integration (edge families, per-type counts, idempotent + index tables
  untouched) + 2 new `kernel.db` (swap + failed-build preservation). **Real lake:** 469 docs → **24 366
  edges** (3 099 mentions / 17 368 cooccurs / 3 899 xref); index's documents/entities/doc_meta_staged
  intact; clean re-run skips. **514 tests, branch cov 99.7%**, ruff+mypy clean.
- **2026-06-02** — **Phase 4 Increment 2: `index` ✅ (derived corpus index, §5.5/§14.6).** Second
  gold-derive stage. Builds `index.db` fresh via `kernel.db.build_atomic`: `documents` (keyed by the
  URL-safe `doc_key` = bundle path, with the inventory colon `doc_id` alongside — the D4 ID
  reconciliation), `doc_sections` (ALL sections, each with `is_latest`; section id = `refs.yaml`'s
  `<doc_key>/<slug>`) **+ FTS5 over `is_latest` sections only** (the anchor-only search surface, §14.6),
  `entities` + `entity_mentions` (generic registry-driven extraction, anchor-only), and a `quality`
  view. **TDD pure cores:** `entities_pure` (a generic recognizer driven by `registries/entities` —
  pattern- or terms-mode, no patterns in stage code) + `index_pure.shred_sections` (structure-aligned
  chunking, fence-aware, slugs matching `refs.yaml`). **`registries/entities/` seeded** (D2): build /
  global / fileman_file / package_namespace recognizers + README (EXTRACT disposition). **Two
  doc-first decisions** (§5.5 + §8 updated): (1) derived stores key on the URL-safe `doc_key`, keeping
  the colon `doc_id` for join-back — resolves the 3 `/`-bearing app codes (`AR/WS`); (2) `index`
  `requires` `doc_meta_staged` explicitly **and carries it forward** in the rebuild, so a fresh
  `build_atomic` doesn't wipe the table it consumes (re-runnable). **Real-data fix:** a `section_id`
  PK collision on 3 docs from the GitHub-slug `-N` quirk → a `-dup-N` guard in `shred_sections` (see
  Lessons; `github_slug` global-uniqueness logged as a `normalize` follow-up). Contracts
  `INDEX_DOCUMENTS`/`INDEX_SECTIONS`/`INDEX_ENTITIES` + the `index` CLI + DAG wiring (`…consolidate →
  index`). Tests: 6 `index_pure` + 8 `entities_pure` + 5 integration (documents/sections/entities,
  is_latest, FTS anchor-only, refs.yaml-id match, staged carry-forward, forced-rebuild survival,
  empty-staged, refs toc_depth). **Real lake (no re-fetch):** 469 docs → 25 981 sections / 16 756
  is_latest FTS rows / 290 `is_latest` documents (== version groups) / 1 796 entities / 22 870
  mentions; `doc_meta_staged` survives; 0 FTS rows on non-latest; clean re-run skips. **503 tests,
  branch cov 99.7%**, ruff+mypy clean.
- **2026-06-02** — **Phase 4 Increment 1: `consolidate` ✅ (gold version rollup, §6.6).** First
  gold-derive stage, on branch `feat/phase-4-gold-derive` (off the fast-forwarded `master` tip
  `e725f5a` = the full hardening pass; no PR existed, so the branch was FF-merged, not reviewed).
  TDD RED→green: pure core `stages/consolidate/consolidate_pure.py` (`parse_patch_num`,
  `group_by_anchor_key` [standalone docs with empty `anchor_key` stay separate via a `doc_id`
  fallback], `order_members` [`(patch_num, official_date, doc_slug)`], `anchor_relpath` [version-free
  `<app>/<pkg_doc_code>`], `build_history`, **append-only** `merge_history`) + thin driver
  `stage.py` (`requires=[text@normalized, assets]`, `produces=[consolidated]`, SKIP_IF_UNCHANGED).
  It reconstructs each member's `anchor_key` from the bundle's identity FM (`app_code:pkg_ns:doc_type`)
  — **the formula promoted to `kernel.ids.anchor_key`** and shared with `catalog` (§9.2), so no new
  input and no silver re-run (see Lessons). Output: one anchor bundle per version group at a stable
  version-free path (`documents/gold/consolidated/<app>/<pkg_doc_code>/{body.md=latest, history.yaml}`),
  every member's normalized body retained write-once in the body CAS
  (`documents/gold/_shared/history/<sha>.md`, `kernel.cas`) and referenced by `body_sha256` from the
  ordered `history.yaml` (which folds each member's `revisions.yaml`); the deferred git replay is
  **not** built. Reused the hardened `cas.atomic_write` content-skip + `cas.prune_bundles` + the
  `doc_error_gate` per-document isolation. **Contract** `CONSOLIDATED` (TREE_TEXT) + config
  `history_bodies` + the `consolidate` CLI command + DAG wiring (topo order `…normalize → consolidate`
  verified). **Doc-first:** §6.6 gained the concrete consolidated layout + body-CAS path +
  `history.yaml` schema (was under-specified); §8 `requires` already matched (no change). Tests:
  17 unit (`test_consolidate_pure`) + 7 integration (`test_consolidate_stage` — ordered lineage, CAS
  retention, skip, force-idempotent byte-identical, append-only on a later patch, no-revisions bundle,
  per-doc isolation, systemic-gate) + 3 property (`order_members` determinism, `merge_history`
  idempotent + append-only). **484 tests, branch cov 99.7%** (gate ≥95%), ruff+mypy clean.
- **2026-06-02** — **Pre-Phase-4 hardening pass (reliability · non-redundancy · doc reconciliation).**
  A multi-increment TDD pass on the built scope (Phases 1–3), each increment its own commit. Running
  detail (newest sub-item first):
  - **F — data lake regenerated from immutable bronze (no re-crawl/fetch).** Ran
    `catalog`/`serve-inventory`/`convert`/`discover`/`enrich`/`normalize` `--force` over the
    preserved bronze evidence (469 docx, `catalog.raw.json`, `state.db` acquisitions). Results:
    convert 469 docs / 5289 assets / 0 errors; normalize 469 docs / 22 `revisions.yaml` / 0 errors.
    **Verified:** `CPRS/cprsguium/body.md` has 0 legacy `heading<TAB>page` TOC lines, 0
    `########### Table of Contents`, exactly one `## Contents`; corpus-wide **0/469** bundles carry
    any `>6-#` heading or tab+page-number TOC line; 469 normalized bundles; **0** `history.yaml`,
    **22** `revisions.yaml`. **One-time migration cleanup:** 22 stale `history.yaml` from a
    pre-A2-rename run lingered (each beside a now-correct `revisions.yaml`) and were deleted — they
    expose that bundle-level R5 pruning does **not** remove a *renamed sidecar within a still-kept
    bundle*; the deferred **R4** full-tree (`OUT.tmp` rebuild) eliminates this class of intra-bundle
    stale file, so the follow-up should land R4 before the next rename.
  - **E — doc reconciliation + bounded gate distributions.** (C1/D-dec-1) Reworded §8's `catalog`
    row so drift detection (NEW/SUPERSEDED/CHANGED/UNCHANGED/WITHDRAWN) is owned by the §7.6
    scheduled/incremental layer (Phase 7), stating `catalog.enriched` is a **pure function of one
    crawl**. (C3) Amended §6.7 to note `strip_legacy_toc` recognises >6-`#` (invalid-GFM) legacy-TOC
    headings, and added the missing Change Log entry for `e1e3b44` (below). (C4/D-dec-5) Added a
    bounded distribution assertion to `serve_pure.evaluate_gate` — the gold inventory now fails if
    **no genuine document** survives (every record classified as noise = systemic enrichment bug),
    making the §8 "sane distributions (crawl-spec §7)" clause enforced rather than aspirational;
    with a unit test. (C5) Refreshed the test-count/coverage line and the stale origin-tip framing.
    B3 (URL/text helper dedup) was **deliberately skipped** — optional in the plan, lowest-value,
    and not worth destabilising the Phase-C work.
  - **D — property tests + branch coverage + Hypothesis profile (§12).** Added 7 Hypothesis
    `@given` property tests under `tests/property/`: `kernel.csv.to_csv` adversarial round-trip
    (commas/quotes/newlines — confirmed correct, no escaping bug); `normalize_body` idempotency over
    generated heading trees; `github_slug` determinism + uniqueness + monotonic `-N` suffix;
    `extract_tables` idempotency; `revision_pure` HTML↔pipe dialect equivalence + `_norm_date`
    idempotency; `tree_fingerprint` order-independence + single-byte sensitivity; and
    `estimate_jaccard ≈ exact_jaccard` within MinHash tolerance (making `exact_jaccard` a live
    reference oracle — closes A1's note). Enabled `branch = true` in the coverage gate and registered
    a `vdocs` Hypothesis profile (`max_examples=200`, `deadline=None`) in `tests/conftest.py`. The ◐
    property-test tracker row flips to ✅. 457 tests; branch coverage 99.7% (gate ≥95%).
  - **C-rel-8 — stale-output pruning (R5); tree-atomicity (R4) SPLIT to a follow-up.** This was the
    largest item and was split as the plan sanctioned — **R5 landed first**, R4 deferred. New shared
    `kernel.cas.prune_bundles(root, kept)` removes any `<app>/<slug>` bundle under a silver-tree root
    not in this run's **input** set (keyed to inputs, not successes, so a transient per-doc failure
    never prunes a prior-good bundle — only a *vanished input* prunes); now-empty `<app>` parents go
    too. Wired into `convert`/`enrich`/`normalize` (each surfaces a `pruned` count); `discover` is
    corpus-global (single report files), so bundle-pruning is N/A. A withdrawn/renamed doc no longer
    lingers as a ghost bundle read as live (§7.6). Tests: kernel prune unit + a convert end-to-end
    prune (doc withdrawn from `raw/index.json` → ghost removed). **R4 (write to `OUT.tmp/` +
    hardlink-unchanged + atomic-rename for whole-tree crash-atomicity, §7.4) is deferred to its own
    follow-up** — it reshapes how all four silver stages write and warrants isolated review;
    per-file writes remain atomic (`atomic_write`) in the meantime.
  - **C-rel-7 — per-document error isolation in `convert` + `normalize` (R6).** One bad document
    aborted the whole batch after partial writes. Each per-doc iteration is now wrapped: a failure
    is logged (structlog WARN with the doc id), counted, and skipped — the batch continues. The
    `errors` count is surfaced in `RunResult.counts`, and a new shared `Stage.doc_error_gate`
    (named limit `DOC_ERROR_RATE_LIMIT = 0.5`) fails the stage in postflight only when the failure
    *rate* is systemic (not a silent swallow, §9.5). Tests: a single failure is isolated (rest
    processed, `errors=1`); an all-fail batch fails the stage.
  - **C-rel-6 — `fetch` merges `raw/index.json` (R1).** `fetch` overwrote the index with only the
    current selection, so a selective re-fetch dropped previously-fetched docs and `convert` then
    skipped them. It now reads the existing index and unions this run's entries over it (new keys
    added, re-fetched keys refreshed). Test: a prior run's entry survives a later selective fetch.
  - **C-rel-5 — guard malformed frontmatter (R8).** `kernel.frontmatter.parse` let a `yaml.YAMLError`
    from a bad `---` block propagate and crash the run. It now catches `yaml.YAMLError`, logs a
    structlog WARN, and treats the document as having no frontmatter (whole text intact as body) —
    isolating one bad doc instead of aborting `normalize`/`enrich`.
  - **C-rel-4 — retry crawl/fetch on transport errors (R3).** `kernel.http._request` only retried
    429/5xx; an uncaught `httpx.TransportError` (connect/read timeout, protocol error) aborted the
    whole crawl/fetch. It now retries transport errors in the same exponential-backoff loop and,
    on exhaustion, returns `None` — `get_page` maps that to a `status_code=0` empty page and
    `get_bytes` to `None`, the existing skip-with-WARN sentinels (§3.6), never an exception.
  - **C-rel-3 — deterministic strong `sqlite_fingerprint` (R9).** Strong mode hashed `repr(row)`
    ordered `BY 1`, leaving ties (rows sharing the first column) in undefined order — so a
    byte-identical DB built in a different insert order could fingerprint differently. Now encodes
    each row from its typed cell values (NULL distinct from `''`) and sorts the encoded rows in
    Python → a canonical content order independent of insert/row order. Tests: insert-order
    independence + single-cell-change sensitivity.
  - **C-rel-2 — `build_atomic` WAL hardening (R7).** The atomic DB build opened the temp in WAL
    and renamed only the main file, so a crash could orphan `.<name>.tmp-wal`/`.tmp-shm`.
    `kernel.db.connect` gained a `journal_mode` flag; `build_atomic` now builds the temp in
    `DELETE` mode (no WAL siblings can exist) and sweeps any `.tmp`/`.tmp-wal`/`.tmp-shm` orphans
    on both the success and failure paths. Tests: DELETE-mode honored, no siblings after build,
    a prior crash's orphaned siblings swept.
  - **C-rel-1 — content-skip in `kernel.cas.atomic_write` (R2 / D-dec-3).** A no-op re-write
    (new bytes hash-match the existing file) now leaves the file untouched (mtime preserved),
    so the cheap `size:mtime_ns` fingerprint stays stable and `SKIP_IF_UNCHANGED` actually skips
    on no-op re-runs instead of being defeated by an unconditional rewrite. Guarded on
    `path.is_file()` (a non-file at the path falls through to the tmp+rename failure path).
  - **B2 — `kernel.text.slugify`: one slug primitive (D3).** Added
    `slugify(text, *, sep="-", fallback="")` (the GitHub-anchor rule); `github_slug_base` is now a
    thin alias and `discover_pure._slug` calls it with `fallback="section"` — so a discovered
    section's slug **provably matches** the GitHub anchor `normalize` emits for the same heading
    (new cross-check test), closing the latent `index`-join divergence. **Hard-blocker surfaced &
    decided (doc-first):** `catalog.make_doc_slug` is a genuinely different transform — a
    *filesystem-path* slug that **collapses** every non-alnum run (so `DG_5.3` → `dg_5_3`), where
    the anchor rule **drops** punctuation (`v22.2` → `v222`). A single `slugify(sep=…)` cannot
    produce both without breaking one of the two pinned tests, so `make_doc_slug` stays catalog-local
    with a docstring explaining the deliberate distinction (it has one consumer → not a §9.2 dup).
  - **B1 — `kernel/markdown.py`: the single markdown-primitive home (D1, D2).** New kernel module
    owning `HEADING_RE` (canonical `#+`), `FENCE_RE`, `MULTI_BLANK`, and a fence-aware
    `iter_headings(body) → (line_idx, level, text)` generator (skips fenced code + the generated
    `## Contents`). Migrated all five hand-rolled fence-aware heading scans onto it
    (`normalize_pure.infer_heading_levels`, `anchors_pure.parse_headings` + `insert_back_links`,
    `template_pure.strip_template_scaffold`, `discover_pure.parse_scaffold`) and collapsed the
    five `_TAG_RE` copies onto one `kernel.text.TAG_RE`/`strip_tags` (re-exported by `markdown`).
    **Behavior delta (intended unification):** `template_pure` and `discover.parse_scaffold` move
    `#{1,6}` → `#+`, so they now recognize oversized (>6-`#`) headings — matching the `e1e3b44`
    legacy-TOC fix; `parse_scaffold` is now fence- + Contents-aware too. 424 tests.
  - **A2 — `normalize` revision sidecar renamed `history.yaml` → `revisions.yaml`.** Closes the
    latent filename collision with `consolidate`'s version-group lineage (§6.4 vs §6.6). Renamed
    `revision_pure.history_sidecar` → `revision_sidecar`, the emitted filename, and the
    `history_sidecars` count key → `revision_sidecars`. The design doc (§6.4/§6.6/§8) already
    reserved the two grains; the code now matches.
  - **A1 — dead code removed.** Deleted `convert_pure.image_targets` (no `src/` caller) + its two
    tests. Documented `kernel.discovery.exact_jaccard` as the reference oracle for the
    `estimate_jaccard` property test (Phase D) — it stops being dead once that test lands.
- **2026-06-02** — **`normalize` strips legacy in-body TOC behind oversized (>6 `#`) headings
  (`e1e3b44`).** Pandoc emits invalid-GFM oversized ATX headings (e.g. `########### Table of Contents`)
  from deep DOCX outline levels; `strip_legacy_toc` now recognises a curated legacy-contents heading
  at H1–H3 **or** at >6 `#` (the hash count is an upstream artifact, so the text match is trusted),
  so the oversized legacy TOC is removed before the derived `## Contents` is generated — no duplicate,
  no stray invalid heading. (Change Log entry added retroactively in the Phase-E reconciliation.)
- **2026-06-02** — **Phase-4 kickoff prep: resolved 3 design seams + retired a stale branch (doc-only).**
  Wrote the Phase-4 kickoff prompt the tracker references
  ([`docs/prompts/next-session-phase-4-kickoff.md`](prompts/next-session-phase-4-kickoff.md)) and
  **resolved in `vdocs-design.md` the three seams** the draft had flagged as open:
  (1) **the two revision sidecars are now distinct** — `normalize` emits the per-document
  **`revisions.yaml`** (its own revision-history table, §6.4/§5.2) and `consolidate` owns the
  version-group **`history.yaml`** lineage (§6.6), which folds each member's `revisions.yaml` + a CAS ref
  to its retained body; `history.yaml` is reserved for the lineage (the dominant §6.6/§13/ADR-016
  meaning). (2) **entity extraction is `index`'s job, vocabulary is DATA** — new `EXTRACT` disposition +
  curated `registries/entities` (VistA domain: namespaces, FileMan file numbers, routines, options, RPCs,
  protocols, HL7, mail groups, globals, build/patch ids) recognized by a generic `entities_pure` pass →
  `index.db:entities` keyed by `(type, canonical-name)`; `relate` only adds edges (tenet #13, §8/§9.6/§9.7).
  (3) **`manifest`'s `vectors.db` input is now OPTIONAL** (Phase 6) — manifest builds against
  `consolidated` + `index.db` alone and marks semantic search unavailable until `embed` lands (§8/§14.4),
  the same "optional produces don't gate" rule as `convert`'s `assets`. Logged the two carried code tasks
  as **Phase-4 prerequisites** above (the `normalize` `history.yaml`→`revisions.yaml` rename = STEP 0; seed
  `registries/entities`). **Git hygiene:** retired the stale `docs/phase-4-kickoff` branch (it predated the
  compliance work — would have regressed the tracker to 385 tests and reverted the dependabot CI upgrades
  checkout@v6/setup-uv@v7 back to v4/v5); harvested its `consolidate` build-recipe into the canonical
  kickoff. No code change this commit; the design is now unambiguous for the Phase-4 build.
- **2026-06-02** — **Pre-Phase-4 compliance-review remediation (8 low-severity findings, TDD-first).** A
  full code-vs-design audit of Phases 1–3 confirmed the spine substantially faithful (contract_ver gating
  real, pure/IO split clean, one-kernel-each holds, hard gate blocks, no-blind-download); eight
  low-severity items were closed. **Kernel promotions (§9.2/§11):** (1) `kernel/db.build_atomic(path,
  build_fn)` — the temp-build + `os.replace` atomic-DB-build primitive, repointed `serve-inventory` off
  its hand-rolled rename (the next DB-builders `index`/`relate`/`embed` reuse it); (2) `kernel/registry.
  load_mapping(path, *, missing_ok)` — the repeated `exists?→read→safe_load or {}` registry-YAML loader,
  repointed `catalog`/`convert`/`normalize` (~10 sites); (3) `kernel/text.github_slug_base` — the
  GitHub-slug rule promoted once to the kernel, `anchors_pure.github_slug` now layers `-1/-2` dedup on
  it. **Hardening:** (4) `Stage._input_fps` now raises if `extra_input_fps` keys collide with a `requires`
  key (was docstring-only); (5) `fetch` accrues `acquisitions.attempts` across retries and preserves
  `first_attempt_at` (was unconditional `attempts=1`) — the §7.6 retry/CHANGED_IN_PLACE prerequisite.
  **Docs/hygiene:** (6) `subtract_boilerplate`'s `_shared/boilerplate/<id>.md` ref documented as an
  explicit **publish seam** (gold-root-relative; `publish` resolves depth — not silently bundle-relative);
  (7) `vdl-crawl-spec.md` mojibake caveat corrected (kernel now *is* the ftfy call, §9.2 unification);
  (8) stale `catalog_pure` docstring + orphaned bytecode cleaned. **411 tests** (+14: 4 `test_registry`,
  4 `test_db.build_atomic`, 4 `test_text.github_slug_base`, 1 collision, 1 fetch-accrual), 100% cov,
  ruff+mypy clean. No design-doc change needed — code now matches §9.2/§7.4/§5.5.
- **2026-06-02** — **`normalize` legacy-TOC strip (closes the duplicate-TOC deviation) + Phase 3 merged +
  tracker compacted.** Wired the previously-orphaned `registries/structures` `toc` convention into
  `normalize` as a registry-driven `strip_legacy_toc` F-step (keyed on a curated `match` variant list):
  it removes the source's in-body table of contents — the legacy heading (`Table of Contents`/`Contents`,
  H1–H3) plus its page-numbered entries up to the next heading — **before** the derived `## Contents` is
  generated, so the normalized body carries exactly one TOC (§6.7/§9.6 CANONICALIZE). Root cause: a
  curated registry with no consumer (see Lessons). The `callout` + `revision-table` structures consumers
  remain curated-but-unbuilt (logged as follow-ups). Design §6.7/§8 + `registries/structures` README +
  this tracker reconciled. TDD: unit + integration tests first (RED on missing `strip_legacy_toc`).
  **385 tests, 100% cov.** PRs **#3** (Phase-3 P0–P2 + normalize), **#4** (5 compliance deviations), **#5**
  (legacy-TOC) all **merged to `master`** (`224ab51`); only the two dependabot PRs remain open. Also
  **compacted this tracker** to a page-width stage table (verbose Goal/Evidence/Notes columns → terse
  one-liners; detail preserved here in the Change Log). Next: Phase 4 `consolidate`
  ([`docs/prompts/next-session-phase-4-kickoff.md`](prompts/next-session-phase-4-kickoff.md)).
- **2026-06-02** — **Design-compliance audit remediation (5 deviations fixed).** A full code-vs-design
  sweep of Phases 1–3 found the spine substantially faithful; five deviations were fixed TDD-first
  (397 tests, 100% cov, ruff+mypy clean). (1) **`contract_ver` now actually gates (§7.3 step 2).** It
  was recorded in `stage_runs` but never read, so a `produces[]` shape bump did *not* invalidate
  downstream (the stated purpose, design.md:786). Fixed in `orchestrator/stage.py`: a stage no longer
  skips when its own `contract_ver` changed (self-invalidation), and each internal upstream's recorded
  `contract_ver` is folded into the consumer's `inputs_fp` (so a bump propagates even when the cheap
  fingerprint is shape-blind). (2) **Document medallion moved under `documents/` (§5.3/§4).** Config +
  contract relpaths were at the lake root (only `inventory/` was namespaced), breaking the two-subtree
  medallion symmetry; added `cfg.documents` and prefixed bronze/assets/silver/gold + the
  `RAW_*`/`TEXT_*`/`ASSETS` relpaths (contract *keys* unchanged). CLAUDE.md lake diagram reconciled.
  (3) **`doc_id` promoted to `kernel/ids` (§9.2).** The `app_code:doc_slug` join key was copy-pasted in
  4 sites (enrich/serve/fetch ×2); now one model-free Protocol-typed primitive, re-exported so
  `ep.doc_id`/`sp.doc_id` still resolve. (4) **`enrich` `doc_meta_staged` write made atomic (§7.4).**
  Was `DROP`-then-rebuild in place; now builds a side table and swaps via drop-old + rename-new in one
  transaction, so a failed rebuild never destroys the prior table (regression test pins it). (5)
  **Shared HTML/GFM table-cell mechanics extracted to `kernel/table` (§9.2).** `_flatten`/`pipe_cells`/
  table+pipe regexes were duplicated across `normalize/revision_pure` + `tables_pure`; now one kernel
  module (base `pipe_cells` keeps md-links; `tables_pure` composes `strip_md_links`). **Known gaps left
  as-is** (downstream halves of unbuilt stages, documented seams): template-governed TOC depth (still
  H2–H3 fallback, §6.7), `structures` CANONICALIZE proposed but not applied in `normalize` (§9.6),
  heading-recovery level inference (flat H2). No design-doc change needed — §5.3 already specified
  `documents/`; the code now matches it.
- **2026-06-02** — **P1.b: `normalize` F-step — boilerplate REFERENCE (§9.6).** Promoted block
  identity to a shared kernel primitive (`kernel/text.block_key`, used by both `discover` mining and
  this step — §9.2; `discover.block_key` now re-exports it). New `normalize_pure.subtract_boilerplate
  (body, registry)`: replaces each body block whose `block_key` matches a curated entry with a
  **reference link** to the canonical shared copy (`_shared/boilerplate/<id>.md`) — REFERENCE, kept
  once + de-duplicated, *distinct* from `subtract_phrases` (DELETE). Wired into `normalize_body`
  after phrase subtraction; idempotent (the reference link is not a registered block). **Curated**
  `registries/boilerplate/boilerplate.yaml` (5 high-confidence generic VA install/DIBR blocks, the
  top auto-graded near-dup boilerplate candidates from P2.1, ≤600 chars, evidence 54–70 docs); a
  validity test pins each `key` == `block_key(text)`. **Regression caught by real-corpus verify:**
  P1.d's `infer_heading_levels` was re-leveling the generated `## Contents` heading on the second
  pass, breaking `normalize_body` self-idempotency (corpus 92/469); fixed by skipping the Contents
  marker in `infer` (as `parse_headings` does) → **443/469** self-idempotent, matching the
  pre-existing baseline (444 with `infer` disabled — the residual ~25 are a pre-existing TOC/anchor
  edge case on real Word-TOC constructs, *not* introduced here; the §7.4 contract + property test
  hold). **Real corpus:** 61 docs → 89 boilerplate references. §8 `normalize` boilerplate clause
  flipped to done. 368 tests, 100% cov.
- **2026-06-02** — **P1.c: `normalize` F-step — `(doc_type, era)` template STRIP + `template_id`
  stamp → `normalize` ✅ (Phase 3 complete).** The last deferred F-step. New pure
  `stages/normalize/template_pure.py` (mirrors `revision_pure`/`tables_pure`): `apply_template(body,
  doc_type, era, templates)` matches the curated `(doc_type, era)` template, **strips the unfilled
  scaffold sections** (a schema heading with no prose and no subsections — the literal skeleton
  remnant; filled sections + non-scaffold headings retained, fence-aware) and returns the
  `template_id`. The stage stamps `template_id` into the **frontmatter** (identity provenance, §6.3 —
  mirroring `source_sha256`); the structural schema stays RETAINED in `registries/templates` (§9.8).
  era is the title-page decade bucket via the new shared `kernel/text.decade_bucket` (§9.2 — also
  used by `discover`; `discover.extract_era` now delegates, and its private date constants moved to
  the kernel). doc_type is the baked identity FM. Consumes P2.2b's curated `registries/templates`.
  Idempotent. **Real corpus (469 docs):** 120 docs stamped (DIBR 2010s/2020s), 5 had empty scaffold
  stripped, idempotent 469/469. **Doc-first:** §8 `normalize` row reconciled — template clause →
  done, and glossary **PROMOTE** clarified as a gold-phase output (not a silver body transform), so
  §8 no longer over-claims. `normalize` flips to **✅**; Phase 3 silver **✅ 4/4**. 378 tests,
  100% cov (7 `test_template_pure` + 1 normalize integration + 2 `decade_bucket` kernel).
- **2026-06-02** — **P1.d: `normalize` F-step — heading-level inference (§6.7).** New pure
  `normalize_pure.infer_heading_levels(body)`: rewrites heading `#` prefixes so the heading tree has
  **no skipped levels** (H1→H4 jumps compacted to nest one level at a time), giving the regenerated
  TOC a sane nesting. Each heading is reassigned to its depth in a gap-free hierarchy anchored at
  the document's *shallowest* heading level — so an H2-rooted doc stays H2-rooted (H1, the doc
  title, is never fabricated). Fence-aware (code blocks untouched), idempotent, and slug-preserving
  (slugs key on heading text, not level, so the anchor-map/recovery paths are unaffected). Wired
  into `normalize_body` **after** phrase subtraction and **before** the parse-once/TOC-regen
  (deliberate F-step order; `normalize_body(normalize_body(x)) == normalize_body(x)` still holds —
  property test green). **Real corpus (469 docs):** 316 docs' heading levels adjusted, idempotent
  316/316. 358 tests, 100% cov (5 new `test_normalize_pure`).
- **2026-06-02** — **P1.a: `normalize` F-step — complex tables → `tables/*.csv` sidecars
  (§6.4/§6.5).** New pure module `stages/normalize/tables_pure.py` (mirrors the `revision_pure`
  split): `extract_tables(body)` finds HTML `<table>` (Pandoc) and GFM pipe (Docling) tables,
  lifts the **qualifying** ones — tall (≥10 rows) or very wide (≥8 cols), the §6.5 guardrail
  thresholds calibrated on the real corpus so ~75% of small tables stay inline — to a
  `tables/table-NN.csv` bundle sidecar, and replaces each in the body with a markdown reference
  link. Serialisation **reuses `kernel/csv.to_csv`** (§9.2 — no new writer), with header cells
  uniquified into column names. Runs as a stage-level pre-step **after** `revision_pure` (so it
  never grabs the revision table) and **before** `normalize_body`; the stage writes the CSVs under
  `<bundle>/tables/` and counts `tables_sidecars`. Idempotent (the reference links are not tables →
  a second pass extracts nothing). **Real corpus (469 docs):** 276 docs → **1326 CSV sidecars**,
  idempotent 276/276; spot-checked. §8 `normalize` `tables/*.csv` clause flipped from
  forward-looking to done. 353 tests, 100% cov (9 new `test_tables_pure` + 1 normalize integration).
- **2026-06-02** — **P2.2b: `discover` `(doc_type, era)` template induction → `registries/templates`
  (STRIP + RETAIN schema, §9.8/ADR-018,019).** Second half of P2.2, completing P2.2. **Input-seam
  decision (raised before coding, per the prompt):** investigated three publication-date sources on
  the real corpus and chose the title-page body date — DOCX core metadata is 100%-present but
  collapses to a 2020–21 VA bulk-re-export window (era-invalid); VDL `file_date` is populated for
  <1%; the **title-page date covers ~95% with a real 1989→2026 spread**. So `era` needs no new
  input (it's in the body `discover` already reads); only `doc_type` does → added `catalog.enriched`
  to `discover.requires` for `doc_code` alone (classification stays a `catalog` decision, tenet
  #13). era = decade bucket + explicit `unknown` (kept/flagged, never dropped). New kernel
  structural primitives (test-first): `structural_fingerprint` (exact ordered-scaffold sha =
  `template_id` basis) + `scaffold_shingles` (heading-sequence shingles feeding the existing
  near-dup clustering); also made `cluster_near_duplicates` auto-derive LSH `bands` from the
  threshold so banding never drops a true near-dup (fixed a latent recall bug at low thresholds).
  New `mine_templates` buckets bodies by `(doc_type, era)`, near-dup clusters each bucket by heading
  scaffold, and emits one `TemplateCandidate` per cluster with a stamped `template_id` and a
  **retained consensus structural schema** (`TemplateSection`: ordered sections, required-vs-optional,
  toc_level). **Curated** the high-confidence starter into `registries/templates/templates.yaml` —
  the two DIBR templates (47-doc 2020s + 20-doc 2010s, 40-section scaffolds, scaffold fp stable
  across eras); degenerate empty-schema clusters left to curation. **Real corpus (469 docs):**
  469/469 joined to a doc_type, 16 template candidates, 24 unknown-era. Doc-first: §8 discover row +
  §9.8 era-determination note. `discover` still mutates no content. 343 tests, 100% cov.
- **2026-06-02** — **P2.2a: `discover` structural-convention miner → `registries/structures`
  (CANONICALIZE).** First half of the P2.2 split (the prompt sanctioned splitting it). New pure
  `mine_structures` detects three convention families across the corpus and proposes one
  `StructureCandidate` per convention (disposition CANONICALIZE), each carrying the distinct source
  `variants` as canonicalization evidence: **callout/admonition** styling (the same label rendered
  a dozen ways — `**Note:`, `NOTE:`, `**Note** :` — mapped to GitHub alert syntax `> [!NOTE]`, or a
  bold blockquote for non-alert labels like Example), the **contents** heading shape, and the
  **revision-history** heading shape. New `structures` field on `PatternReport`; the stage wires it
  in with a `structures` count. **Curated** the high-confidence starter set into
  `registries/structures/structures.yaml` from the real-corpus mining (note 236 docs, example 65,
  revision-table 56, toc 55, warning 44, important 20, caution 3 — 7 conventions, 6 auto-graded);
  a validity test pins the curated canonical forms to the miner's logic. No new stage input
  (structures are mined from bodies alone); `discover` still mutates no content. The
  `(doc_type, era)` template miner (P2.2b) is split out — it needs a doc_type+era join that
  `discover` does not have today (catalog.enriched carries `doc_code` but **no publication date**),
  a §8 input seam raised before coding. 329 tests, 100% cov (4 new structures tests + integration
  callout assertion).
- **2026-06-02** — **P2.1: `discover` near-duplicate boilerplate via `kernel/discovery` (retires
  the P0.2 dead-code finding).** `mine_recurring_blocks`'s boilerplate path used exact
  whitespace-collapsed equality (`block_key`), so boilerplate that drifts by a word across docs
  under-counted (§9.6 step 1). Added two near-dup primitives to `kernel/discovery` (test-first):
  `lsh_candidate_pairs` (LSH banding → candidate pairs) and `cluster_near_duplicates` (union-find
  over candidate pairs verified by `estimate_jaccard ≥ threshold`; returns a deterministic
  partition incl. singletons). `discover` now keeps exact-match as the cheap pre-bucket, then
  near-dup clusters **only** the boilerplate-shaped buckets (default Jaccard 0.8) — union of each
  cluster's doc sets, dominant spelling as identity; headings/phrases stay exact-keyed so their
  curation identities stay sharp. `kernel/discovery` is now imported by production code, so the
  P0.2 note flips to "used by `discover`". **Real-corpus (469 docs):** boilerplate candidates
  3051 (exact-only) → **3560** with near-dup (the +509 are sub-`min_docs` spellings that only
  qualify once unioned); still proposals-only, no content mutated. 325 tests, 100% cov (8 new: 5
  `test_discovery` clustering, 2 `test_discover_pure` near-dup, 1 over-cluster guard).
- **2026-06-02** — **P0.2/P0.3 compliance remediation: honest dead-code + §8 over-claim
  reconciled.** Two doc/comment-only audit fixes. (P0.2) `kernel/discovery.py` (shingling / MinHash
  / Jaccard) is imported by no production code today — only its own unit test. Added a module
  docstring note that it is the substrate for the P2 `discover` near-dup boilerplate miner (the
  import lands in P2.1) so it is not latent, untracked dead code in the interim. **Do not delete.**
  (P0.3) The §8 `normalize` produces cell read as if `tables/*.csv`, boilerplate-referenced,
  template-stripped + `template_id`-stamped, and glossary-single-sourced were done; they are the
  deferred F-steps the `normalize ◐` row records. Split the cell into **done** (history/refs
  sidecars, phrase deletion, TOC regen) vs **⏳ forward-looking** (the four deferred clauses, each
  flipped to plain in the same commit as its P1 step) so §8 never over-claims relative to code. No
  test changes (doc + comment only); 318 tests, 100% cov.
- **2026-06-02** — **P0.1 compliance remediation: `registries/` reshaped to the §11 subdirectory
  layout.** The audit found the curated tree was flat files at `registries/` root, where §11/§9.7
  specify per-registry **subdirectories**. Moved (`git mv`, byte-identical) `phrases.yaml →
  phrases/`, `converter-routing.yaml → converter-routing/`, and the nine inventory-track configs
  (`package-master`, `doc-types`, `manual-labels`, `system-types`, `section-codes`, `doc-labels`,
  `noise-domains`, `abbrev-fallback`, `typo-corrections`) → **`registries/inventory/`**. Created the
  four present-but-empty pattern dirs (`boilerplate/`, `templates/`, `glossary/`, `structures/`)
  with README stubs so they track and self-document (populated in P2/P1). Repointed every consumer:
  `catalog/registries.load_registries` (reads `inventory/`), `normalize` phrases loader, `convert`
  converter-routing loader; the `REGISTRIES` tree fingerprint still covers the whole reshaped tree
  (recursive walk), so a curation edit still invalidates `normalize`. **Doc-first:** §9.7 + §11
  amended to record `registries/inventory/` as the (non-§9.6-pattern) home for the catalog-track
  vocabularies. 318 tests, 100% cov (2 new layout/loader tests; existing registry-loader +
  normalize/convert integration tests stay green on the byte-identical move).
- **2026-06-02** — **`normalize` F-step: anchor substrate → `refs.yaml` sidecar (§6.7/§5.5).** Closed the
  load-bearing deferred F-step the whole Phase-4 retrieval layer hangs off
  (`index`/`relate`/`embed`/`serve-mcp`). New pure module `stages/normalize/anchors_pure.py` (mirrors the
  `revision_pure` split): `Heading` now carries `bookmark` + `stable_id`; `parse_headings`/`recover_headings`
  **capture** the `_Toc…`/`_Ref…` Word bookmark (inline on the `##` line or on the line immediately above)
  instead of dropping it; `rewrite_link_targets` rewrites every `](#_Toc…)`/`](#_Ref…)` cross-ref to its
  GitHub slug (unmapped → `UNRESOLVED`, left untouched, never crashes) then drops the redundant anchor spans;
  `build_anchor_map` emits one row per heading `(stable_section_id="<doc_id>/<slug>", slug, bookmark, level,
  title, toc_level)` + `toc_depth` + outbound map; `insert_back_links` adds idempotent round-trip
  "↑ Back to Contents" links under each TOC-targeted heading. `normalize_body` now returns
  `(body, anchor_map)` with a fixed F-step order (parse-once → rewrite → regen-TOC → back-links); the stage
  writes `refs.yaml` conditionally (like `history.yaml`) with a `refs_sidecars` count. TOC depth is the
  H2–H3 fallback (Decision 2; template seam marked in `anchors_pure`/`stage.py` for when
  `registries/templates` lands); `stable_id` is `<doc_id>/<slug>` (Decision 1; `index` will own ID
  persistence). `TEXT_NORMALIZED` is a `TREE_TEXT` bundle contract so `refs.yaml` needs no new contract —
  noted as a recognised sidecar in the module docstrings. No design changes (the design already specified
  all of it). 316 tests, 100% cov (12 new: 9 `test_anchors_pure` incl. fence-safety, 2
  `test_normalize_stage`, 1 `test_normalize_props` "no anchor points nowhere", §13).
- **2026-06-02** — **CSV serialiser promoted to `kernel/csv` (§9.2/§11) + §8 `normalize.requires`
  tightened.** Two follow-ups from the doc-vs-code deviation audit. (A3) The flat-table CSV writer
  was copy-pasted three ways — `_to_csv` in `crawl`/`catalog`/`serve-inventory` stages, each rolling
  its own `csv.DictWriter` over slightly different columns — a §11 "primitive used by ≥2 stages lives
  in the kernel" violation. Collapsed the serialisation mechanics (header + ordered cells, tolerate
  `model_dump()` extras) into one pure `kernel/csv.to_csv(columns, rows, *, strict=False)`; each stage
  keeps only its stage-specific row-building and delegates. Test-first (`tests/unit/kernel/test_csv.py`);
  the three stages' integration CSV outputs are byte-identical. (B3) Amended §8 to say `normalize`
  requires `raw/index.json` (metadata only, for `source_sha256`) not the misleadingly-broad `raw` —
  the code (`requires=[…, RAW_INDEX, …]`) never reads the binary tree; the doc now matches. No behavior
  change. 302 tests, 100% cov.
- **2026-06-02** — **`fetch` selection surface (§5.6) — Phase 2 finished.** Replaced fetch's
  "download every genuine row" with an explicit selection: a pure `Selection` value object (six
  dimension filters — `--app/--section/--status/--doc-type/--group/--select`, AND across dimensions,
  OR within; plus `--all`), applied by `select_fetch_targets` after the always-on noise gate + DOCX
  scope. **No blind download**: with no selection `vdocs fetch` fetches nothing and prints the available
  count; `--dry-run` previews a selection's match count. **Version completeness** (invariant 2) via
  `anchor_key` group expansion — selecting one patch pulls the whole lineage. The resolved selection's
  predicate enters fetch's `inputs_fp` through a new generic `Stage.extra_input_fps` hook, so it
  participates in `SKIP_IF_UNCHANGED` (the expanded id-set is covered transitively by the
  `GOLD_INVENTORY` require). §5.6 refined to document the realization. 295 tests, 100% cov.
- **2026-06-02** — **`kernel/text.clean` made idempotent again after the ftfy switch.** Follow-up to the
  mojibake unification: a Hypothesis seed found `clean(clean(x)) != clean(x)` for inputs like
  `"Â\x0c\x80"` — an interstitial control byte hid adjacent mojibake from ftfy on the first pass and it
  surfaced on the second. Fix: scrub control chars **before** the mojibake repair (was after), so byte
  adjacency is stable. Brute-force over messy 3-char inputs: 12 non-idempotent cases → 0. Kernel-only
  (no production consumer of `clean` yet); the catalog `fix_mojibake` path is unaffected.
- **2026-06-02** — **One mojibake fixer in the kernel (§9.2).** Pre-Phase-4 compliance fix A2. Two
  codepaths existed: a dead custom cp1252 round-trip in `kernel/text.repair_mojibake` (imported by nobody)
  and `catalog/enrich_pure.fix_mojibake` rolling its own `ftfy.fix_text`. Collapsed to one: the kernel
  function now wraps `ftfy.fix_text(text, normalization="NFC")` (already a dep, already what runs on the
  real corpus) and catalog delegates to it (dropping its direct `ftfy` import). Catalog behavior is
  byte-identical — the pinned 8,834-row inventory fixture's §7 distributions still reproduce exactly.
  Kernel tests updated to ftfy's canonical behavior (see Lessons). 279 tests, 100% cov.
- **2026-06-02** — **Reconciled `acquisitions` / `inventory_status` doc-vs-code (§8, §5.5).** Pre-Phase-4
  compliance fix B1, resolved in the **doc-amend** direction (the code was already right). §8 listed
  `state.db:acquisitions` in `serve-inventory.requires`, but the stage requires only `catalog.enriched`
  and acquisitions is deliberately mutable orchestrator state (§5.5), not an `ArtifactContract`. Amended §8
  (serve-inventory requires `catalog.enriched`; fetch reads/writes acquisitions as *out-of-contract* state)
  and §5.5 (acquisitions is not a contract; `inventory_status` = enriched ⋈ acquisitions is a query-time
  **CLI report/view**, never baked into the gold artifact — modelling it as a serve-inventory input would
  churn the artifact and create a serve-inventory→fetch→acquisitions→serve-inventory cycle). Marked
  `serve_pure.inventory_status` as the `vdocs inventory --status` report helper, not a stage output. No
  behavior change; 277 tests, 100% cov.
- **2026-06-02** — **`registries` is now a declared `ArtifactContract` in `normalize.requires` (§8, §7.3).**
  Pre-Phase-4 compliance fix B2. `normalize` loaded `registries/phrases.yaml` locally but declared only
  `[text@enriched, raw/index]`, so a curation edit did **not** change its input fingerprint —
  `SKIP_IF_UNCHANGED` would wrongly skip re-normalization after curation (the stale-input bug §7.3 exists
  to prevent). Added a `REGISTRIES` contract (`Kind.TREE_TEXT`, `produced_by=None`, new `root=REGISTRIES`
  selector so it resolves against `cfg.registries` in the **repo**, not the lake) and put it in
  `normalize.requires`. A real tree fingerprint over the curated registries now participates in
  `normalize`'s `inputs_fp`; §8 already listed `registries` as a normalize input, so code now matches the
  doc. 277 tests, 100% cov.
- **2026-06-02** — **`safe_component` promoted to `kernel/text` (§9.2/§11).** Pre-Phase-4 compliance fix A1.
  The bundle-path slug sanitiser was defined in `convert_pure` and imported across stage boundaries
  (`enrich`/`normalize` reaching into `convert`); moved byte-identical to `kernel/text.safe_component` with
  all four call sites repointed. Its unit test moved to `tests/unit/kernel`.
- **2026-06-02** — **`normalize` F-step: revision-history → `history.yaml` sidecar (§6.6).** Word manuals
  carry a revision-history table; `normalize` now strips that version apparatus from the body and captures
  it as a structured `history.yaml` bundle sidecar (the lineage `push --replay-history` will replay into
  commit history). Ported v1's `revision_pure` (both dialects: Pandoc HTML `<table>` and Docling GFM pipe;
  date normalisation, column detection, redacted PM/TW columns dropped, anchor refs kept). The first
  bundle **sidecar** beyond `body.md`. Real corpus: **22 high-precision sidecars** (header must carry
  date+change+version/patch), table removed from the body — e.g. `or_30_243rn`: 5 revisions, real change
  text + refs. Recall can be broadened (more header synonyms) later. 275 tests, 100% cov.
- **2026-06-02** — **Docling image handling: alt-text + media from the DOCX XML (Thread A).** Docling
  parses no alt-text and emits `<!-- image -->` placeholders. Ported v1's approach to a pure
  `convert/docx_images.py`: read each picture's alt-text + media straight from the DOCX OOXML (document
  order: `<wp:docPr descr>` → `<pic:cNvPr>` fallback; `<mc:AlternateContent>`→Choice; VML `<v:imagedata>`)
  and inject `![alt](media)` 1:1 against the placeholders. `_docling_convert` now uses placeholder mode +
  injection. Verified on real cprsguium: 564 pics ↔ 564 placeholders → **562 image refs with alt-text**
  ("VA logo", …), only 2 residual (linked, no bytes) — and lists still clean (bare markers 0). Caught a
  latent bug porting it (ElementTree truthiness on empty `<mc:Choice>`). 266 tests, 100% cov.
- **2026-06-02** — **Heading recovery in `normalize` (Thread B, §6.7).** Docs Pandoc flattened (no Word
  heading styles) carry their headings as plain paragraphs behind Word `_Toc` bookmark anchors.
  `recover_headings` promotes `<span id="_Toc…"></span>Heading` paragraphs to `## ` (only when the body
  has no markdown headings), run before TOC regen. Real `CPRS/or_30_243rn`: 0 → 56 headings with a full
  navigable TOC. The genuinely-structureless docs Docling couldn't help now get structure from their own
  bookmarks — confirming the earlier finding that this was a `normalize` job, not a converter swap.
- **2026-06-01** — **Corrected the convert-quality probe to v1's signal; Docling now routes `cprsguium`.**
  The probe was measuring heading count (wrong — missed `cprsguium`, which has 573 headings *and* 3,058
  bare markers). Re-read the v1 `vista-docs` converter: the real trigger is the Word `[[…]](#_Toc…)`
  cross-ref explosion. `mine_converter_routing` now counts `[[` wraps + bare markers (`count_xref_wraps`,
  `count_bare_markers`); on the real corpus it flags **exactly `CPRS/cprsguium`** (5,092 wraps). Curated
  `registries/converter-routing` to route it; a real re-convert (docling=1) confirms the fix: bare markers
  3,058→0, proper list items 332→3,230, `[[` 5,092→0, +559 image refs. This supersedes the empty-registry
  conclusion below. 255 tests, 100% cov.
- **2026-06-01** — **Docling routing wired, then curated to OFF by real-data verification (ADR-010).**
  `convert` gained per-document converter routing: it reads `registries/converter-routing` and converts
  listed `<app>/<slug>` docs with **Docling** (run out-of-process via the `docling` CLI — Docling pins
  `typer<0.22`, conflicting with the project's `typer>=0.26.5`, so in-process is impossible) and Pandoc
  otherwise. Mechanism is tested with injected fakes. But the curation registry is **empty**: installing
  Docling and measuring it on the worst flagged CPRS RN + 3 more docs showed **0 headings recovered**
  (same as Pandoc) — these DOCX have no source heading styles, which Docling reads structurally, so no
  converter helps. The real remedy (heading recovery, §6.7) is deferred. 255 tests, 100% cov.
- **2026-06-01** — **Convert-quality probe added to `discover` (ADR-010 evidence).** New
  `mine_converter_routing` flags substantial documents Pandoc converted with **no recovered heading
  structure** (a bare-marker explosion) as Docling ROUTE candidates → `reports/patterns.converter_routing`,
  feeding the `registries/converter-routing` curation. On the real 469-doc corpus it flags **45 docs, 25 of
  them CPRS** (worst: a 23,932-word CPRS RN with 0 headings) — confirming the real CPRS conversion problems
  and giving an evidence base for wiring Docling. (Docling itself: not installed, not wired — convert is
  Pandoc-only today; routing + Docling backend deferred behind this evidence.) 253 tests, 100% cov.
- **2026-06-01** — **Phase 3 `normalize` v1 shipped (◐) + DOCX-only decided (§1).** `normalize` applies
  the first F-steps per-document & deterministically: strip Pandoc artifacts → subtract the curated
  `registries/phrases` (the discover→curate→normalize loop closed with a real starter registry) →
  regenerate `## Contents` from the real heading tree with GitHub-slug anchors → stamp `source_sha256`.
  Verified on the real 469-doc corpus (dead `<!-- -->` 79→0; correct nested TOC on a real DIBR). Separately
  the pipeline became **DOCX-only** (§1): PDF is out of scope and flagged `out_of_scope`, not silently
  dropped. 251 tests, 100% cov. Deferred normalize F-steps tracked in its row. `scripts/seed_from_v1.py`
  makes the real corpus reproducible offline.
- **2026-06-01** — **Real-corpus run through the document-silver stages (pivot from fixtures).** Seeded
  469 real VA DOCX offline from v1's `raw/` (3 docs/app across 138 apps + **all 90 CPRS docs**) into bronze,
  then ran the real `convert` → `discover` → `enrich`. Outcome: 469 converted bundles + **5,143 CAS images**
  (png/jpeg/wmf/emf/gif/tiff); discover proposed 1,105 template / 3,698 phrase / 3,048 boilerplate block
  candidates + a glossary; enrich baked identity FM onto all 469 (4.89M words staged). **Findings driving
  `normalize`:** (a) headings are inconsistent — some docs have `#`/`##`, many render title/section text as
  plain lines → TOC must be regenerated from whatever heading tree exists; (b) complex tables come through
  as raw HTML `<table>` (revision-history, data-dictionary) → extract to `tables/*.csv` + move revision
  history to `history.yaml`; (c) Pandoc artifacts (`<!-- -->`, `**  \n**`) and title-page furniture
  (Department of Veterans Affairs / OIT) are the real `registries/phrases` + `boilerplate` targets; (d)
  images are HTML `<img>` with sized attrs (now CAS-referenced). Two real bugs/heuristic-faults were found
  and fixed *because* of real data (convert image-ref rewriting; discover heading/glossary dispositions).
- **2026-06-01** — **Phase 3 `enrich` shipped (✅).** New `enrich` stage joins each `text@converted`
  bundle to its inventory record (by the `<app>/<slug>` bundle path, DOCX-preferred, noise excluded) and
  bakes the **identity frontmatter** (title/doc_type/app_code/section/pkg_ns/version/patch_id/source_url)
  into `body.md` via the kernel codec → `text@enriched` (02-enriched); computed `word_count` and the full
  identity are staged into `index.db:doc_meta_staged` for `index`. Per §6.3, **computed fields never enter
  the body** (so a body diff stays a real content diff). `TEXT_ENRICHED` + `DOC_META_STAGED` contracts,
  `silver_enriched` config, `vdocs enrich` CLI; reuses `convert`'s `safe_component` (no copy-paste).
  230 tests, 100% cov.
- **2026-06-01** — **Phase 3 `discover` shipped (✅).** New `discover` stage mines the converted corpus
  (proposals only, mutating nothing): a recurring-block miner keyed by block identity proposes
  `boilerplate` (REFERENCE) for longer meaningful blocks and `phrases` (DELETE) for short paper-era
  furniture, and an acronym miner proposes `glossary` (PROMOTE) terms — each with evidence (doc_count,
  sample doc_ids) and an `auto`/`review` curation grade — to `reports/patterns/patterns.json`. This builds
  the discover→registry seam **before** `normalize` (tenet #13). `PATTERNS` contract + `patterns_report`
  config + `vdocs discover` CLI. Template/structural-clustering miners deferred. 223 tests, 100% cov.
- **2026-06-01** — **Phase 3 `convert` shipped (◐).** New `convert` stage: reads the fetched raw CAS +
  `raw/index.json`, converts each doc to markdown via an injected backend (Pandoc DOCX→GFM with
  `--extract-media`; PDF/Docling deferred), extracts images into the shared asset CAS, rewrites body image
  refs to `<sha>.<ext>`, and writes `text@converted` bundles at `<app>/<slug>/body.md`. Added `doc_slug`
  to the fetch index entry (the bundle path key), `silver_converted` config path, `TEXT_CONVERTED` +
  (optional) `ASSETS` contracts, the `vdocs convert` CLI command, and the optional-produces rule in the
  orchestrator. 215 tests, 100% cov. Pandoc default smoke-verified end-to-end.
- **2026-06-01** — Added an **Overall status** rollup (per-phase status + progress counts + a
  pipeline-stage tally: 3 ✅ · 1 ◐ · 15 ☐) above the table, and per-phase progress on each header row.
  Corrected Phase 2 to ◐ (the inventory medallion is ✅; `fetch`'s explicit selection flags remain).
- **2026-06-01** — **Tracker created** (this document): whole-pipeline plan + status table for all 7
  phases / 18 stages + the MCP server + harden items, derived from `vdocs-design.md` §8/§17. Seeded with
  the Phase 1–2 work already shipped this session and the cross-phase lessons above. The inventory
  medallion's detailed rows live in [`vdl-crawl-tracker.md`](vdl-crawl-tracker.md); this is the umbrella.
- **2026-06-01** — **Phase 2 complete (inventory medallion + gated doc-bronze).** 7 commits
  (`a30a5ac`→`afa385f`): crawler + HTTP hardening + inventory lake layout (A1/A2/B1/B2); registries port
  + loader (A3); pure 5-pass enrichment engine (C1–C9); CatalogStage wiring + §7 fidelity gate (C10); gold
  inventory + HARD GATE = the fetch gate (D1/D2); acquisitions + `inventory_status` + CLI (D3/D4); gold
  inventory published as CSV. The real lake's gold inventory is populated (8,834 records, gate green) and
  `vdocs inventory --status` works. See [`vdl-crawl-tracker.md`](vdl-crawl-tracker.md) for the detail.
- **2026-06-01** — **Phase 1 complete (the spine).** Kernel (text/frontmatter/fingerprint/cas/lineage/
  db/discovery/http), Pydantic config + artifact contracts + registry, models, and the generic
  orchestrator (preflight→run→postflight + `state.db:stage_runs`), proven by a no-op two-stage DAG.
