# VDL Crawler & Inventory-Enrichment — Implementation Plan & Tracker

**Living document.** This is the build plan *and* the running tracker for the **inventory medallion**
(`crawl` → `catalog` → `serve-inventory`) — the control-plane track that produces the gold inventory and
the fetch gate. It implements **[`vdl-crawl-spec.md`](vdl-crawl-spec.md)** within the architecture of
**[`vdocs-design.md`](vdocs-design.md)** (§4 two medallions, §8 stages, ADR-022 fork-ready).

**How to use:** as each stage is implemented, update its **Status** + **Evidence** row in the table,
append a **Change Log** entry, and record any **Lessons Learned**. The table is the single source of
build truth; the spec is the source of *what correct looks like*.

**Status legend:** ☐ todo · ◐ in progress / partial · ✅ done (tests + `make check` green) · ⏸ blocked · ⬚ deferred

**Scope boundary:** this tracker stops at the **gold inventory + fetch gate**. The document medallion
(`fetch` → … → `publish`) is downstream of the gate and tracked separately. `acquisitions` (fetch
status, §5.5) is scaffolded here only as far as the `inventory_status` join needs it.

---

## Phase / stage summary

| ID | Phase | Stage / deliverable | Goal | Spec / design ref | Status | Evidence (tests / artifact) | Notes |
|---|---|---|---|---|---|---|---|
| **A** | Foundations | | shared machinery + vocabularies before any inventory stage | | ✅ | A1+A2+A3 ✅ | |
| A1 | Foundations | `kernel/http` hardening | descriptive User-Agent · retry/backoff on 5xx · 429 backoff · `max_redirects=5` · **return final URL** · config inter-request delay | spec §3.1, §9.1 | ✅ | `test_http` (10 tests, httpx `MockTransport`, no network) | `PoliteClient` (UA/retry/429-backoff/redirect-cap/final-URL/delay); `get_page→Page(text,url,status)`; module `get_text/get_bytes` keep back-compat |
| A2 | Foundations | config + lake layout (inventory medallion) | `inventory/{bronze,silver,gold}` paths; `vdl_base_url`, delay, UA in `Settings` | design §5.3, §4 | ✅ | `test_config` (10 tests; inventory-path + crawl-session assertions) | `catalog_raw`→`inventory/bronze/catalog.raw.json`, `catalog_enriched`→`inventory/silver/catalog.enriched.json`; `crawl_delay`/`user_agent`; contracts repointed (keys `inventory/catalog.*`) |
| A3 | Foundations | `registries/` + vocabularies (verbatim from v1) | port doc-types, packages, doc-labels, typo-corrections, manual-labels, noise-domains, system-types | spec §6, §10; design §9.6 | ✅ | `test_registries` (16 tests) | 9 YAML files **AST-generated** from v1 (no hand-transcription): doc_type_patterns=57, slug_suffix=54, manual_slugs=154, system_type=196 apps, COTS={MD,YS,ROI,CPT,DRG,PREM}, doc_labels=31; loader in `stages/catalog/registries.py` (I/O), pure `parse_*`; `Settings.registries` (repo, env-overridable) |
| **B** | Inv-bronze (`crawl`) | | site-wide raw catalog (metadata only) | | ◐ | B1+B2 ✅; B3 (live) todo | |
| B1 | Inv-bronze | `crawl_pure` parsers (verify vs spec) | index/section/application parsers; relative-href resolution; status/app-code parse | spec §3.2–3.4 | ✅ | `test_crawl_pure` (9 tests; + final-URL-base regression) | verified vs spec; final-URL base confirmed against A1's `Page.url` |
| B2 | Inv-bronze | `CrawlStage` driver | 3-level polite walk → `inventory/bronze/catalog.raw.{json,csv}`; skip non-200 (WARN); dedup | spec §3.5; design §8 | ✅ | `test_crawl_stage` (3) + `test_bronze_dag` + `test_cli` | reworked to `PoliteClient.get_page`; resolves each level vs page **final URL**; non-200 section/app skipped (WARN, `skipped` count) and retained empty; writes inventory-bronze path |
| B3 | Inv-bronze | live-VDL verification | real bounded crawl; section/app/doc counts sane | spec §2, §7 | ☐ | recorded counts vs live site | politeness mandatory (real `.gov`) |
| **C** | Inv-silver (`catalog`) | | the full multi-pass enrichment → conformed inventory | | ✅ | C1–C10 ✅; §7 distributions reproduced **exactly** | |
| C1 | Inv-silver | patch identity (pure) | `PATCH_A/B/FULL`, `MULTI_NS_RE`, `FNAME_VER/PATCH`; pkg_ns/ver/num/patch_id/patch_id_full/multi_ns | spec §4.1, §6.2 | ✅ | `test_enrich_pure` (PATCH_A, multi-NS, PATCH_B + filename patch) | in `enrich_pure.parse_row`; regexes verbatim from v1 §6.2 |
| C2 | Inv-silver | doc-type classification (pure) | `DOC_TYPE_PATTERNS` (title, ordered) → `_SLUG_SUFFIX_MAP`/`_APP_SPECIFIC` (filename); title-first | spec §4.1, §6.3–6.4 | ✅ | ordering traps (`_tg`=TRG, DIBR<IG, UM<UG) | `compile_doc_types`/`classify_doc_type`/`classify_by_filename`; reads `registries/doc-types` |
| C3 | Inv-silver | text fixers | **ftfy** mojibake + NFC + nbsp-strip; typo corrections + `doc_search_aliases` | spec §4.1, §9.3 | ✅ | `test_fix_mojibake_and_typo` | `ftfy` dep added; `fix_mojibake`/`apply_typo_corrections`; NOT `kernel/text` |
| C4 | Inv-silver | pass 1 (per-row) | rename/drop source cols; repair; abbrev extraction; `parse_row`; VBA-form override | spec §4.1 | ✅ | e2e + VBA-override test | `enrich_rows` pass 1 |
| C5 | Inv-silver | pass 2 (corpus-global) | shared-URL **noise**; companion pairing; package-master canon; subject clean; section_code; decommission date; ver split; doc_layer; patch_id; doc_format; **group_key + anchor_key**; doc_slug | spec §4.2, §9.4 | ✅ | e2e (companion, noise, canon, anchor_key, group_key, doc_layer) | `anchor_key=app:pkg:doc_code` (vdocs addition §9.4) |
| C6 | Inv-silver | pass 3 (peer inference) | fill missing doc_code by 100% group_key peer consensus | spec §4.3 | ✅ | `test_enrich_peer_inference_and_manual_override` | |
| C7 | Inv-silver | pass 4 (manual overrides) | `MANUAL_OVERRIDES` / `MANUAL_NOISE` from `registries/manual-labels` | spec §4.4 | ✅ | manual-override + manual-noise-tag tests | |
| C8 | Inv-silver | pass 5 (canonical labels) | canonical `doc_label` + `doc_subtitle`; `doc_labelling` | spec §4.5 | ✅ | e2e (canonical label) | `apply_canonical_label`; reads `registries/doc-labels` |
| C9 | Inv-silver | Stage C (system classification) | `system_type` (196-app map) + `cots_dependent` | spec §4.6, §10.7 | ✅ | e2e + unclassified-fallback test | `classify_system`; reads `registries/system-types` |
| C10 | Inv-silver | `CatalogStage` driver | raw → passes 1–5 + C → `inventory/silver/catalog.enriched.{json,csv}` + schema JSON | spec §4, §5; design §8 | ✅ | `test_catalog_inventory`: §7 gate vs pinned 8,834-row fixture (**exact**) + driver wiring | `enrich_rows` wired; `EnrichedRecord`/`EnrichedInventory` (37 cols incl. `anchor_key`); old thin `catalog_pure`+drift removed; `fetch` reconciled (selects `noise_type==''`, drift → acquisitions later) |
| **D** | Inv-gold (`serve-inventory`) | | curated/queryable gold inventory + the fetch gate | | ✅ | D1–D4 ✅ | |
| D1 | Inv-gold | `serve-inventory` stage | promote silver → `inventory/gold` (`inventory.db` + `inventory.json` + `inventory.csv`); the selection surface | design §8 (serve-inventory row), §4 | ✅ | `test_serve_inventory` (gold json + flat csv + indexed `inventory.db`) | `ServeInventoryStage`; `inventory.json` + published flat `inventory.csv` (doc_id-led) + queryable `inventory.db` (table `inventory`, `doc_id` + 6 selection indexes); built atomically (temp+rename) |
| D2 | Inv-gold | HARD GATE (postflight) | complete vs crawl · enriched · noise-classified · §7 acceptance → blesses gold `ok` = **fetch gate** | design §8, §7.3; spec §7 | ✅ | `test_serve_pure` (9) + gate-pass/fail integration | `deep_gate`→ pure `evaluate_gate` (1:1 vs crawl, noise/system/section/format complete; unclassified = soft WARN); **`fetch` now `requires` GOLD_INVENTORY** so the `ok` literally gates fetch; verified green on the full 8,834-row corpus |
| D3 | Inv-gold | `acquisitions` + `inventory_status` | `state.db:acquisitions` table; `inventory_status` view = enriched ⋈ acquisitions | design §5.5 | ✅ | `test_state_store` (acq round-trip/upsert/all) + `test_serve_pure` (join/summary) + bronze-dag | `Acquisition` model + StateStore methods; `fetch` now **records acquisitions** (fetched/failed, sha256/bytes/timestamps) keyed by `doc_id`; pure `inventory_status` join collapses PDF/DOCX, excludes noise |
| D4 | Inv-gold | CLI | `vdocs crawl` / `catalog` / `serve-inventory`; `vdocs inventory --status`; selection flags | design §8; spec §9.5 | ✅ | `test_cli` (`inventory --status`, bare, no-gold error) | `vdocs serve-inventory` + `vdocs inventory [--status]` (prints the join summary: fetched/pending/failed/not_acquired). Fetch-selection flags = a later enhancement |
| **E** | Publish / validate (independent product) | | the inventory as its own deliverable (ADR-022) | | ⬚ | | |
| E1 | Publish | no-information-loss check vs v1 | enriched ⊇ v1 signals; §7 distributions at/above floor | spec §7 | ☐ | comparison report vs v1 reference CSV | |
| E2 | Publish | browsable inventory site | publish gold inventory (table / GitHub Pages, à la v1 `vistadocs.github.io`) | ADR-022; spec §9.5 | ⬚ | — | deferred until inventory is wanted as a standalone product |

**Current focus:** **the entire inventory medallion (Phases A–D) is ✅** — crawler (A1/A2/B1/B2),
foundations+registries (A3), full enrichment (C1–C10), the gold inventory + HARD GATE (D1/D2), and
acquisitions + `inventory_status` + CLI (D3/D4). `make check` green (208 tests, 100% cov, ruff + mypy
clean); §7 distributions reproduce exactly and the gate passes green on the full 8,834-row corpus.
The fetch gate is live, `fetch` records per-document acquisitions, and `vdocs inventory --status` shows
the enriched ⋈ acquisitions join. **This tracker's scope (gold inventory + fetch gate) is complete.**
Remaining: **B3** (a manual, politeness-gated live VDL smoke crawl) and **E1** (no-information-loss
comparison vs the v1 reference — already proven exact by the §7 fixture gate; E1 would formalize it as a
report). The document medallion (`fetch` → … → `publish`) is downstream of the gate and tracked separately.

**Dependency order:** A1→A2→A3 ⇒ B1→B2→B3 ⇒ C1–C9 (pure, parallelizable) → C10 (driver) ⇒ D1→D2 (gate) → D3→D4 ⇒ E. The gate (D2) is the milestone that unblocks the document medallion's `fetch`.

---

## Lessons Learned

*Append implementation lessons as they accrue (newest first). Spec-level lessons live in `vdl-crawl-spec.md` §8; this section is for things discovered while building.*

- **2026-06-01 — Generate the registries from v1, don't hand-copy them.** The 196-app system
  map, 95 manual overrides, 57 ordered doc-type regexes, etc. were ported by a one-off generator
  that `ast.literal_eval`-extracts the literal constants from the v1 sources (no import side-effects)
  and imports the side-effect-free `classify_vista_type` for the system map, then dumps YAML — then
  the generator was deleted and the YAML committed as the in-repo source of truth (§9.7). Exact-count
  matches (manual_slugs 154, system_type 196, COTS 6, doc_labels 31) verify fidelity; the spec's
  "~47/~90/~55/168" were estimates — the **as-built counts are 57/95/54/193** and are authoritative.

- **2026-06-01 — Final-URL contract threaded end-to-end, not just in the parser.** A1 made the HTTP
  layer return the post-redirect URL (`Page.url`); B2's driver now feeds *that* (not the requested URL)
  as each level's parse base. The fake fetcher in tests returns a `Page` whose `url` differs from the
  requested URL for one app, so a redirect that moved the base is regression-guarded at the driver
  level — the parser-only fixtures couldn't catch a driver that passed the wrong base.
- **2026-06-01 — Skipped pages are retained, not dropped.** A non-200 section/app is logged (WARN) and
  kept in the catalog with empty children rather than omitted: for an *inventory*, "this app exists but
  failed to crawl" is signal worth keeping. The `skipped` count surfaces it without losing the row.

- **2026-06-01 — Real fetch > fixtures for the URL contract.** The relative-href resolution bug (doc links
  resolve against the application page's *final* URL, not the host root) was invisible to unit fixtures
  that used absolute hrefs; only a real bounded fetch against live VDL exposed it (fixed in `209361a`,
  regression-guarded). Implication for B-phase: every parser/driver stage gets at least one real-VDL
  smoke check, not just synthetic fixtures.

---

## Change Log

*Newest first. One entry per meaningful tracker/implementation change.*

- **2026-06-01** — **Acquisitions + inventory_status + CLI (D3/D4 → ✅; Phase D complete).** `state.db`
  gains the `acquisitions` table (per-document fetch status, keyed by `doc_id`) with an `Acquisition`
  model + StateStore round-trip/upsert/all methods; `fetch` now **records an acquisition per target**
  (fetched → status/sha256/bytes/timestamps, failed → status/error). The pure `inventory_status` join
  (enriched ⋈ acquisitions) collapses PDF/DOCX to one logical doc, excludes noise, and defaults to
  `not_acquired`; `status_summary` powers `vdocs inventory --status` (fetched/pending/failed/not_acquired).
  Added the `vdocs serve-inventory` and `vdocs inventory [--status]` commands. 208 tests, 100% cov.
  **The whole inventory medallion (A–D) is now green — the tracker's scope is complete.**
- **2026-06-01** — **Gold inventory + the fetch gate live (D1/D2 → ✅).** `ServeInventoryStage` promotes
  `catalog.enriched` → `inventory/gold/inventory.{json,db}` (a portable JSON view + a queryable SQLite
  `inventory` table with the stable `doc_id` join key and 6 selection indexes, built atomically). Its
  postflight `deep_gate` delegates to the pure `evaluate_gate` — the HARD GATE: complete vs. the crawl
  (1:1), every row noise-/system-/section-/format-classified; unclassified apps are a soft WARN, not a
  block. **`fetch` now `requires` the GOLD_INVENTORY artifact**, so serve-inventory's blessed `ok` is
  literally the fetch gate (the generic consumer-preflight refuses fetch until green). Verified green on
  the full 8,834-row corpus (0 unclassified). 203 tests, 100% cov.
- **2026-06-01** — **Catalog enrichment wired + §7 gate green (C10 → ✅; Phase C complete).** `CatalogStage`
  now flattens `catalog.raw` → raw rows → `enrich_rows` (loading `registries/`) → the inv-silver
  `catalog.enriched.{json,csv}` + schema. New `EnrichedRecord`/`EnrichedInventory` (37 cols incl.
  `anchor_key`) replace the thin drift-focused `EnrichedDocument`; the old `catalog_pure.py` + its
  drift logic are removed (drift is a `fetch`/`acquisitions` concern, §7.6). `fetch` reconciled to
  select `noise_type==''` rows off the new model. **Fidelity proven against the full 8,834-row v1
  corpus** (pinned, gzipped under `tests/fixtures/`): every §7 distribution matches *exactly* — noise
  7491/1192/149/2, layer 3466/3584/1784, format 5097/3730/7, labelling 8526/308, section CLI=5790…,
  patch_id 6902, companion 7422, doc-code leaders RN=1598…VDD=145, 0 unclassified. 189 tests, 100% cov.
- **2026-06-01** — **Pure enrichment engine implemented (C1–C9 → ✅).** `stages/catalog/enrich_pure.py`
  is a faithful, pure port of v1's `enrich_inventory.py` + `classify_vista_type.py`: patch identity
  (PATCH_A/B/FULL, multi-NS, filename ver/patch), title+filename doc-type classification, ftfy text
  fixers + typo aliases, and the full 5-pass + system-classification pipeline (`enrich_rows`) over
  row-dicts + the loaded `Registries`. Adds the vdocs-native `anchor_key` (`app:pkg:doc_code`, §9.4).
  19 tests incl. an end-to-end corpus exercising companion pairing, shared-URL noise, peer inference,
  manual overrides, canonical-label collapse, and system classification. `ftfy` added as a dep.
  `make check` green: 203 tests, 99.5% cov. **C10 (driver + 36-col model + fetch reconciliation +
  §7 fixture validation) is the next, more invasive step** — kept separate so the model/fetch rework
  gets its own focused pass with the pinned 8,834-row fixture for distribution assertions.
- **2026-06-01** — **Crawler implemented (A1, A2, B1, B2 → ✅).** A1: `kernel/http.PoliteClient` —
  descriptive UA, 5xx retry + exponential backoff, 429 escalating backoff, `max_redirects=5`, exposes
  the post-redirect final URL via `Page`, configurable inter-request delay; `get_page`/`get_bytes`
  injectable transport + sleep, 10 `MockTransport` tests (no network). A2: `Settings` gains the
  inventory medallion (`inventory/{bronze,silver,gold}`), `catalog_raw`/`catalog_enriched` repointed
  onto it, `crawl_delay` + `user_agent`; `ArtifactContract` keys/relpaths repointed to
  `inventory/catalog.*`. B1: `crawl_pure` parsers verified vs spec §3.2–3.4 + final-URL-base
  regression. B2: `CrawlStage` driven by the polite client, resolves each level against the page's
  final URL, skips non-200 with a WARN (`skipped` count), writes `inventory/bronze/catalog.raw.{json,csv}`.
  `make check` green: 168 tests, 100% coverage, ruff + mypy clean. **Scope:** the *crawler* half;
  A3 vocabularies + Phase C enrichment (the *inventory-enrichment* half) remain todo.
- **2026-06-01** — Tracker created. Phases A–E and stages A1–E2 enumerated from `vdl-crawl-spec.md` §9
  build order + the corrected two-medallion design (`vdocs-design.md` §4/§8, ADR-022). Pre-existing
  Phase-2 artifacts marked partial: `crawl_pure` parsers + `CrawlStage` (B1/B2 ◐, at the old flat
  `bronze/catalog/*` path), thin `catalog_pure` (precursor to C1–C10), basic `kernel/http` (A1 ◐). No
  inventory-medallion stage is `done` yet — implementation begins at A1.
