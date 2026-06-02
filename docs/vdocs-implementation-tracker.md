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

**Pipeline stages (§8): 8 ✅ · 0 ◐ · 11 ☐** (of 19 = 18 stages + the MCP server; the Phase‑1 spine is
counted separately below). Last updated **2026-06-02**. **The full document-silver pipeline runs
end-to-end on a real 469-doc VA corpus** (seeded offline from v1's `raw/`), not just fixtures.
**Phase 3 silver is complete** — `normalize` finished all F-steps (compliance remediation P0–P2 + P1).

| Phase | Title | Status | Progress |
|---|---|---|---|
| 1 | Spine (kernel · config · models · contracts · orchestrator) | ✅ | 4/4 |
| 2 | Inventory medallion + doc-bronze | ✅ | 4/4 (`fetch` selection surface landed; DOCX-only §1) |
| 3 | Silver — document text (convert · discover · enrich · normalize) | ✅ | `convert` ✅ · `discover` ✅ · `enrich` ✅ · `normalize` ✅ (all F-steps shipped) |
| 4 | Gold derive (consolidate · index · relate · manifest) | ☐ | 0/4 |
| 5 | Gold deliver (fidelity · publish · validate · push · analyze) | ☐ | 0/5 |
| 6 | Machine interface (embed · serve-mcp) | ☐ | 0/2 |
| 7 | Harden (property tests · `--verify` · gc · docs-gen · replay · refresh) | ◐ | 2 ◐ · 1 ⬚ · 3 ☐ |

## Phase / stage summary

| Phase | Stage | Layer | Goal (requires → produces) | Design ref | Status | Evidence | Notes |
|---|---|---|---|---|---|---|---|
| **1 — Spine** | | | the Stage/Artifact abstraction + generic DAG runner, proven by a no-op DAG | §7, §17.1 | ✅ 4/4 | | the contract-enforcing core everything else fills in |
| 1 | kernel | — | text · frontmatter · fingerprint · cas · lineage · db · discovery · **http** (one each, §9.2) | §9.2 | ✅ | `tests/unit/kernel/*` | `http` hardened this session (PoliteClient: UA/retry/429/redirect/final-URL/delay) |
| 1 | config | — | `Settings` off `DATA_DIR`; all lake paths derived; no module-level path constants | §5.3, §9.1 | ✅ | `test_config` | inventory medallion + gold-inventory + registries paths added |
| 1 | models / contracts | — | Pydantic boundary types; `ArtifactContract` (locate/validate/fingerprint); the registry | §7.1 | ✅ | `test_artifact`, `test_registry` | |
| 1 | orchestrator | — | `Stage` base (generic preflight/postflight), DAG engine, `state.db:stage_runs` | §7.1–7.3 | ✅ | `test_noop_dag`, `test_engine_edges` | one execution path; no stage re-implements gating |
| **2 — Inventory medallion + doc-bronze** | | | gold inventory of the whole site + the fetch gate, then a selected bronze | §4, §17.2 | ✅ 4/4 | see [`vdl-crawl-tracker.md`](vdl-crawl-tracker.md) | inventory medallion ✅; `fetch` selection surface ✅ |
| 2 | **crawl** | 🥉 INV | `vdl` → `inventory/bronze:catalog.raw` (polite 3-level walk; final-URL base; skip non-200) | §8; spec §3 | ✅ | `test_crawl_pure`, `test_crawl_stage` | live bounded smoke (B3) still manual |
| 2 | **catalog** | 🥈 INV | `catalog.raw` → `catalog.enriched` (5-pass enrichment + system classification, §5 cols) | §8; spec §4 | ✅ | `test_enrich_pure`, `test_catalog_inventory` | **§7 distributions reproduce exactly** vs the pinned 8,834-row fixture |
| 2 | **serve-inventory** | 🥇 INV | `catalog.enriched` → gold `inventory.{json,csv,db}`; **HARD GATE = the fetch gate** | §8, §7.3; spec §7 | ✅ | `test_serve_pure`, `test_serve_inventory` | gate green on the full corpus; `vdocs inventory --status` |
| 2 | **fetch** | 🥉 DOC | gate `ok` + **selection** (§5.6) + `acquisitions` → `documents/bronze:raw` (CAS) + `index.json` + `acquisitions` | §8, §5.6, §9.5 | ✅ | `test_fetch_pure`, `test_fetch_stage`, `test_bronze_dag`, `test_cli` | CAS, DOCX-pref, index, acquisitions, gate-wired. **Selection surface**: AND-across/OR-within dimension filters (`--app/--section/--status/--doc-type/--group/--select/--all`), **no blind download** (default fetches nothing + prints count), `--dry-run`; **version completeness** via `anchor_key` group expansion; selection in `inputs_fp` (`extra_input_fps`) so it joins `SKIP_IF_UNCHANGED` |
| **3 — Silver (document text)** | | | bytes → conformed, normalized markdown bundles; discovery→registry seam first | §17.3 | ✅ 4/4 | | discover→registry seam built **before** normalize so no pattern is hard-coded |
| 3 | **convert** | 🥈 DOC | `raw`,`index.json` → `text@converted` + `assets` (Pandoc/Docling; CAS images) | §8, §1, ADR-010 | ✅ | `test_convert_pure`, `test_convert_stage` + real 469-doc run | **DOCX-only** (§1). Pandoc GFM + `--extract-media`; images→asset CAS, refs rewritten (markdown + HTML `<img>` by basename). **Per-doc converter routing** via `registries/converter-routing` → Docling (out-of-process CLI; typer conflict forbids in-proc), **routes `CPRS/cprsguium`** — verified end-to-end: bare markers 3,058→0, list items 332→3,230, +559 image refs. EMF/WMF→PNG + the few residual `<!-- image -->` deferred |
| 3 | **discover** | 🥈 DOC | `text@converted` + `catalog.enriched` (doc_code only) → `reports/patterns` (candidate boilerplate/templates/glossary/structure/converter-routing + disposition) | §8, §9.6, §9.8 | ✅ | `test_discover_pure`, `test_discover_stage` + real run | recurring-block miner (template RETAIN / phrase DELETE / boilerplate REFERENCE) **+ near-dup boilerplate clustering** (`kernel/discovery` MinHash/LSH; real 3051→3560) + acronym glossary (PROMOTE) + **structures** miner (callout/TOC/revision-table → CANONICALIZE; 7 curated) + **`(doc_type, era)` template induction** (structural-scaffold clustering; doc_type←catalog `doc_code`, era←title-page date; STRIP + stamp `template_id` + RETAIN schema, §9.8; 2 DIBR templates curated) + **convert-quality probe** (`mine_converter_routing` → Docling ROUTE); evidence + grade; **mutates no content** |
| 3 | **enrich** | 🥈 DOC | `text@converted`,`catalog.enriched` → `text@enriched` (identity FM baked) + `index.db:doc_meta_staged` | §8 | ✅ | `test_enrich_doc_pure`, `test_enrich_stage` | joins each bundle to its inventory record (by `<app>/<slug>`, DOCX-preferred), bakes identity FM via the kernel codec; **computed fields (word_count) staged to index.db, never in the body** (§6.3) |
| 3 | **normalize** | 🥈 DOC | `text@enriched`,`raw`,`registries` → `text@normalized` (+ history/tables/refs sidecars; TOC regen) | §8, §6.7, §6.6, §9.8 | ✅ | `test_normalize_pure`, `test_anchors_pure`, `test_revision_pure`, `test_tables_pure`, `test_template_pure`, `test_normalize_stage`, `test_normalize_props` + real 469-doc run | **F-steps (all shipped)**: **heading recovery** from `_Toc` bookmarks; **revision-history → `history.yaml` sidecar** (§6.6; HTML + GFM-pipe); **anchor substrate → `refs.yaml` sidecar** (§6.7/§5.5: bookmarks, `](#_Toc…)` rewrite w/ `UNRESOLVED` signal, `(stable_id ↔ slug ↔ bookmark)` map, round-trip back-links — `anchors_pure`); strip Pandoc artifacts; subtract `registries/phrases`; **boilerplate REFERENCE** (`subtract_boilerplate` + curated `registries/boilerplate`; shared `kernel/text.block_key`; real 61 docs/89 refs); **complex tables → `tables/*.csv`** (§6.4/§6.5; `tables_pure`, ≥10-row/≥8-col guardrail, `kernel/csv`; real 276 docs/1326 sidecars); **`(doc_type, era)` template STRIP + `template_id` stamp** (§9.8; `template_pure` + curated `registries/templates`; era=`kernel/text.decade_bucket`; real 120 stamped); **heading-level inference** (`infer_heading_levels`: gap-free tree, fence-safe; real 316 adjusted); **legacy in-body TOC stripped** via `registries/structures` CANONICALIZE `toc` (`strip_legacy_toc` keyed on curated `match` variants — closes the duplicate-TOC deviation where the source's text TOC survived next to the derived one); regenerate `## Contents` TOC (GitHub-slug anchors, H2–H3 depth); stamp `source_sha256`. (Glossary PROMOTE is a gold-phase output, not a silver body transform — §8 note.) **Remaining structures consumer:** `callout` CANONICALIZE (admonition→GFM alerts) + `revision-table` heading-shape (the revision *table* already leaves the body to `history.yaml`) — curated in `registries/structures`, not yet applied. |
| **4 — Gold derive (machine)** | | | version groups + the queryable index + knowledge graph + manifests | §17.4 | ☐ 0/4 | | |
| 4 | **consolidate** | 🥇 DOC | `text@normalized`,`assets` → `consolidated` (one anchor per version group; ordered lineage) | §8, §6.6 | ☐ | | `is_latest`; prior bodies as travel-with sidecars |
| 4 | **index** | 🥇 DOC | `text@normalized`,`consolidated` → `index.db` (docs, sections + **FTS5 over is_latest**, entities, quality, **stable IDs**) | §8 | ☐ | | the lexical/structured search surface |
| 4 | **relate** | 🥇 DOC | `index.db` → `index.db:relations` (doc↔entity, doc↔doc xref, entity↔entity) | §8 | ☐ | | the knowledge graph |
| 4 | **manifest** | 🥇 DOC | `consolidated`,`index.db`,`vectors.db`,`state.db` → `corpus-manifest.json` + `discovery.json` | §8, §14 | ☐ | | lineage + machine-discovery descriptor |
| **5 — Gold deliver (humans)** | | | per-doc fidelity verdict → published human tree → hard gate → push | §17.5 | ☐ 0/5 | | |
| 5 | **fidelity** | 🥇 DOC | `text@normalized`,`raw`,`index.db`,`registries` → `reports/fidelity` (per-doc S→T verdict + corpus report) | §8; [`fidelity-framework.md`](fidelity-framework.md) | ☐ | | content/provenance/history axes + template compliance + TOC integrity |
| 5 | **publish** | 🥇 DOC | manifest, `text@normalized`, `consolidated`, `assets`, `catalog.enriched`, `glossary` → `publish` (md-only tree + INDEX) | §8 | ☐ | | markdown-only; images materialized + gitignored |
| 5 | **validate** | 🥇 DOC | `publish`,`text@normalized`,`index.db`,`vectors.db`,`reports/fidelity` → **HARD GATE** (schema·lineage·anchors·IDs·fidelity verdict) | §8, §7.3 | ☐ | | ALWAYS_RERUN; QUARANTINE blocks; REVIEW needs sign-off |
| 5 | **push** | 🚀 DOC | `publish` (+ validate `ok`) → `git:vistadocs/vdl` (anchor files + lineage sidecars) | §8, §6.6 | ☐ | | FORCE_ONLY; commit-replay deferred behind `--replay-history` |
| 5 | **analyze** | ⬩ DOC | `text@normalized` → `reports/{survey,headings,lexicon}` (off critical path) | §8 | ☐ | | diagnostic only |
| **6 — Machine interface (§14)** | | | embeddings + the MCP server (hybrid search) — the headline machine output | §17.6, §14 | ☐ 0/2 | | |
| 6 | **embed** | 🥇 DOC | `index.db:doc_sections` (**is_latest only**) → `vectors.db` (per-chunk embeddings + ANN) | §8, §14.6 | ☐ | | prior-version chunks excluded |
| 6 | **serve-mcp** | 🥇 DOC | `index.db`,`vectors.db`,`corpus-manifest`,`discovery.json` → MCP server (semantic+lexical+structured+graph, RRF) | §14 | ☐ | | MCP Python SDK; read-only stores |
| **7 — Harden** | | | property tests · `--verify` · `gc` · generated stage docs · history-replay · `refresh` | §17.7 | ◐ 2◐ | | filling robustness against a frozen spine |
| 7 | property tests | — | Hypothesis property tests for the pure transforms | §10 | ◐ | `tests/property/*` (text, frontmatter, **normalize** — "no anchor points nowhere", §13) | extend to enrich + the remaining normalize transforms as they land |
| 7 | `--verify` mode | — | upgrade fingerprints to full content hashes for CI/paranoid runs | §7.4 | ◐ | wired in `ArtifactContract.fingerprint(verify=)` | exercise end-to-end |
| 7 | `gc` | — | sweep superseded silver trees | §17.7 | ☐ | | |
| 7 | `docs/stages/` gen | — | per-stage reference generated from contracts | §17.7 | ☐ | | |
| 7 | `push --replay-history` | — | build git commit history from `history.yaml` sidecars + retained prior bodies | §6.6 | ⬚ | | deferred git-native payoff |
| 7 | `refresh` | — | scheduled crawl-diff + incremental re-processing; refresh fidelity/currency verdicts | §7.6 | ☐ | | drift: NEW/SUPERSEDED/CHANGED propagate only |

**Current focus:** **Phase 1 ✅, inventory medallion ✅, the whole document-silver pipeline runs on real
docs** — `convert`/`discover`/`enrich`/`normalize` (v1) all green and verified on a real 469-doc corpus;
pipeline is now **DOCX-only** (§1). `make check` green (316 tests, 100% cov, ruff + mypy clean). The
**anchor substrate is shipped** — `refs.yaml` + bookmark→slug rewrite + round-trip back-links close the
load-bearing Phase-4 prerequisite (§6.7/§5.5). **Next:** finish the remaining deferred `normalize` F-steps
(tables→csv, boilerplate REFERENCE, template STRIP+STAMP, heading-level inference, in that order) **or**
start **Phase 4** (`consolidate`→`index`→`relate`→`manifest`). The
load-bearing ordering rule is to **build `discover` → `registries/` before `normalize`** so no pattern is
ever hard-coded (§9.6, tenet #13): `convert` → `discover` → `enrich` → `normalize`.

**Dependency spine:** Phase 1 ⇒ Phase 2 (crawl→catalog→serve-inventory→**gate**→fetch) ⇒ Phase 3
(convert→discover→enrich→normalize) ⇒ Phase 4 (consolidate→index→relate→manifest) ⇒ Phase 5
(fidelity→publish→validate→push) ⇒ Phase 6 (embed→serve-mcp) ⇒ Phase 7 (harden). The `validate` hard
gate (Phase 5) is the deliver-side analogue of the `serve-inventory` gate.

---

## Lessons Learned

*Append implementation lessons as they accrue (newest first). Inventory-track lessons live in
[`vdl-crawl-tracker.md`](vdl-crawl-tracker.md); cross-phase / architectural lessons go here.*

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
