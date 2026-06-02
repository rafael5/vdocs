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

**Pipeline stages (§8): 7 ✅ · 1 ◐ · 11 ☐** (of 19 = 18 stages + the MCP server; the Phase‑1 spine is
counted separately below). Last updated **2026-06-02**. **The full document-silver pipeline runs
end-to-end on a real 469-doc VA corpus** (seeded offline from v1's `raw/`), not just fixtures.

| Phase | Title | Status | Progress |
|---|---|---|---|
| 1 | Spine (kernel · config · models · contracts · orchestrator) | ✅ | 4/4 |
| 2 | Inventory medallion + doc-bronze | ✅ | 4/4 (`fetch` selection surface landed; DOCX-only §1) |
| 3 | Silver — document text (convert · discover · enrich · normalize) | ◐ | `convert` ✅ · `discover` ✅ · `enrich` ✅ · `normalize` ◐ (v1) |
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
| **3 — Silver (document text)** | | | bytes → conformed, normalized markdown bundles; discovery→registry seam first | §17.3 | ◐ 2.5/4 | | discover→registry seam built **before** normalize so no pattern is hard-coded |
| 3 | **convert** | 🥈 DOC | `raw`,`index.json` → `text@converted` + `assets` (Pandoc/Docling; CAS images) | §8, §1, ADR-010 | ✅ | `test_convert_pure`, `test_convert_stage` + real 469-doc run | **DOCX-only** (§1). Pandoc GFM + `--extract-media`; images→asset CAS, refs rewritten (markdown + HTML `<img>` by basename). **Per-doc converter routing** via `registries/converter-routing` → Docling (out-of-process CLI; typer conflict forbids in-proc), **routes `CPRS/cprsguium`** — verified end-to-end: bare markers 3,058→0, list items 332→3,230, +559 image refs. EMF/WMF→PNG + the few residual `<!-- image -->` deferred |
| 3 | **discover** | 🥈 DOC | `text@converted` → `reports/patterns` (candidate boilerplate/templates/glossary/structure/converter-routing + disposition) | §8, §9.6 | ✅ | `test_discover_pure`, `test_discover_stage` + real run | recurring-block miner (template RETAIN / phrase DELETE / boilerplate REFERENCE) + acronym glossary (PROMOTE) + **convert-quality probe** (`mine_converter_routing`: flags structureless Pandoc output → Docling ROUTE candidates; real corpus = 45 flagged, 25 CPRS); evidence + grade; **mutates no content** |
| 3 | **enrich** | 🥈 DOC | `text@converted`,`catalog.enriched` → `text@enriched` (identity FM baked) + `index.db:doc_meta_staged` | §8 | ✅ | `test_enrich_doc_pure`, `test_enrich_stage` | joins each bundle to its inventory record (by `<app>/<slug>`, DOCX-preferred), bakes identity FM via the kernel codec; **computed fields (word_count) staged to index.db, never in the body** (§6.3) |
| 3 | **normalize** | 🥈 DOC | `text@enriched`,`raw`,`registries` → `text@normalized` (+ history/tables/refs sidecars; TOC regen) | §8, §6.7, §6.6 | ◐ | `test_normalize_pure`, `test_revision_pure`, `test_normalize_stage` + real 469-doc run | **F-steps**: **heading recovery** from `_Toc` bookmarks (real `or_30_243rn` 0→56 headings); **revision-history → `history.yaml` sidecar** (§6.6; HTML + GFM-pipe dialects; 22 real sidecars, table stripped from body); strip Pandoc artifacts; subtract `registries/phrases`; regenerate `## Contents` TOC (GitHub-slug anchors); stamp `source_sha256`. **Deferred**: tables→csv, boilerplate REFERENCE, template STRIP+STAMP, refs.yaml + back-links + bookmark rewrite, heading-level inference |
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
| 7 | property tests | — | Hypothesis property tests for the pure transforms | §10 | ◐ | `tests/property/*` (text, frontmatter) | extend to enrich/normalize transforms as they land |
| 7 | `--verify` mode | — | upgrade fingerprints to full content hashes for CI/paranoid runs | §7.4 | ◐ | wired in `ArtifactContract.fingerprint(verify=)` | exercise end-to-end |
| 7 | `gc` | — | sweep superseded silver trees | §17.7 | ☐ | | |
| 7 | `docs/stages/` gen | — | per-stage reference generated from contracts | §17.7 | ☐ | | |
| 7 | `push --replay-history` | — | build git commit history from `history.yaml` sidecars + retained prior bodies | §6.6 | ⬚ | | deferred git-native payoff |
| 7 | `refresh` | — | scheduled crawl-diff + incremental re-processing; refresh fidelity/currency verdicts | §7.6 | ☐ | | drift: NEW/SUPERSEDED/CHANGED propagate only |

**Current focus:** **Phase 1 ✅, inventory medallion ✅, the whole document-silver pipeline runs on real
docs** — `convert`/`discover`/`enrich`/`normalize` (v1) all green and verified on a real 469-doc corpus;
pipeline is now **DOCX-only** (§1). `make check` green (251 tests, 100% cov, ruff + mypy clean). **Next:**
finish the deferred `normalize` F-steps (tables→csv, revision-history→history.yaml, boilerplate/templates,
refs.yaml + back-links) **or** start **Phase 4** (`consolidate`→`index`→`relate`→`manifest`). The
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
