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
| **A** | Foundations | | shared machinery + vocabularies before any inventory stage | | ◐ | A1+A2 ✅; A3 todo | |
| A1 | Foundations | `kernel/http` hardening | descriptive User-Agent · retry/backoff on 5xx · 429 backoff · `max_redirects=5` · **return final URL** · config inter-request delay | spec §3.1, §9.1 | ✅ | `test_http` (10 tests, httpx `MockTransport`, no network) | `PoliteClient` (UA/retry/429-backoff/redirect-cap/final-URL/delay); `get_page→Page(text,url,status)`; module `get_text/get_bytes` keep back-compat |
| A2 | Foundations | config + lake layout (inventory medallion) | `inventory/{bronze,silver,gold}` paths; `vdl_base_url`, delay, UA in `Settings` | design §5.3, §4 | ✅ | `test_config` (10 tests; inventory-path + crawl-session assertions) | `catalog_raw`→`inventory/bronze/catalog.raw.json`, `catalog_enriched`→`inventory/silver/catalog.enriched.json`; `crawl_delay`/`user_agent`; contracts repointed (keys `inventory/catalog.*`) |
| A3 | Foundations | `registries/` + vocabularies (verbatim from v1) | port doc-types, packages, doc-labels, typo-corrections, manual-labels, noise-domains, system-types | spec §6, §10; design §9.6 | ☐ | load/parse tests per registry | discovery-is-data: data, not inline code — feeds `catalog` (Phase C), not the crawler |
| **B** | Inv-bronze (`crawl`) | | site-wide raw catalog (metadata only) | | ◐ | B1+B2 ✅; B3 (live) todo | |
| B1 | Inv-bronze | `crawl_pure` parsers (verify vs spec) | index/section/application parsers; relative-href resolution; status/app-code parse | spec §3.2–3.4 | ✅ | `test_crawl_pure` (9 tests; + final-URL-base regression) | verified vs spec; final-URL base confirmed against A1's `Page.url` |
| B2 | Inv-bronze | `CrawlStage` driver | 3-level polite walk → `inventory/bronze/catalog.raw.{json,csv}`; skip non-200 (WARN); dedup | spec §3.5; design §8 | ✅ | `test_crawl_stage` (3) + `test_bronze_dag` + `test_cli` | reworked to `PoliteClient.get_page`; resolves each level vs page **final URL**; non-200 section/app skipped (WARN, `skipped` count) and retained empty; writes inventory-bronze path |
| B3 | Inv-bronze | live-VDL verification | real bounded crawl; section/app/doc counts sane | spec §2, §7 | ☐ | recorded counts vs live site | politeness mandatory (real `.gov`) |
| **C** | Inv-silver (`catalog`) | | the full multi-pass enrichment → conformed inventory | | ☐ | | |
| C1 | Inv-silver | patch identity (pure) | `PATCH_A/B/FULL`, `MULTI_NS_RE`, `FNAME_VER/PATCH`; pkg_ns/ver/num/patch_id/patch_id_full/multi_ns | spec §4.1, §6.2 | ☐ | unit + property tests | thin version exists in Phase-2 `catalog_pure` |
| C2 | Inv-silver | doc-type classification (pure) | `DOC_TYPE_PATTERNS` (title, ordered) → `_SLUG_SUFFIX_MAP`/`_APP_SPECIFIC` (filename); title-first | spec §4.1, §6.3–6.4 | ☐ | unit tests incl. ordering traps (`_tg`=TRG, DIBR-before-IG) | reads `registries/doc-types` |
| C3 | Inv-silver | text fixers | **ftfy** mojibake + NFC + nbsp-strip; typo corrections + `doc_search_aliases` | spec §4.1, §9.3 | ☐ | unit tests | add `ftfy` dep; NOT `kernel/text` custom repair |
| C4 | Inv-silver | pass 1 (per-row) | rename/drop source cols; repair; abbrev extraction; `parse_row`; VBA-form override | spec §4.1 | ☐ | unit tests | |
| C5 | Inv-silver | pass 2 (corpus-global) | shared-URL **noise**; companion pairing; package-master canon; subject clean; section_code; decommission date; ver split; doc_layer; patch_id; doc_format; **group_key + anchor_key**; doc_slug | spec §4.2, §9.4 | ☐ | unit tests + distribution checks | `anchor_key` = vdocs addition (§9.4) |
| C6 | Inv-silver | pass 3 (peer inference) | fill missing doc_code by 100% group_key peer consensus | spec §4.3 | ☐ | unit tests | |
| C7 | Inv-silver | pass 4 (manual overrides) | `MANUAL_OVERRIDES` / `MANUAL_NOISE` from `registries/manual-labels` | spec §4.4 | ☐ | unit tests | |
| C8 | Inv-silver | pass 5 (canonical labels) | canonical `doc_label` + `doc_subtitle`; `doc_labelling` | spec §4.5 | ☐ | unit tests | reads `registries/doc-labels` |
| C9 | Inv-silver | Stage C (system classification) | `system_type` (196-app map) + `cots_dependent` | spec §4.6, §10.7 | ☐ | unit tests | reads `registries/system-types` |
| C10 | Inv-silver | `CatalogStage` driver | raw → passes 1–5 + C → `inventory/silver/catalog.enriched.{json,csv}` + schema JSON | spec §4, §5; design §8 | ☐ | integration test vs **pinned raw-inventory fixture**, asserting §7 distributions | supersedes the thin Phase-2 catalog |
| **D** | Inv-gold (`serve-inventory`) | | curated/queryable gold inventory + the fetch gate | | ☐ | | |
| D1 | Inv-gold | `serve-inventory` stage | promote silver → `inventory/gold` (`inventory.db` + `inventory.json`); the selection surface | design §8 (serve-inventory row), §4 | ☐ | integration test | |
| D2 | Inv-gold | HARD GATE (postflight) | complete vs crawl · enriched · noise-classified · §7 acceptance → blesses gold `ok` = **fetch gate** | design §8, §7.3; spec §7 | ☐ | gate-pass + gate-fail tests | consumer-preflight makes fetch wait automatically |
| D3 | Inv-gold | `acquisitions` + `inventory_status` | `state.db:acquisitions` table; `inventory_status` view = enriched ⋈ acquisitions | design §5.5 | ☐ | StateStore tests | acquisitions written by `fetch` (downstream); table+view scaffolded here |
| D4 | Inv-gold | CLI | `vdocs crawl` / `catalog` / `serve-inventory`; `vdocs inventory --status`; selection flags | design §8; spec §9.5 | ☐ | CLI integration tests | extends the Phase-2 Typer app |
| **E** | Publish / validate (independent product) | | the inventory as its own deliverable (ADR-022) | | ⬚ | | |
| E1 | Publish | no-information-loss check vs v1 | enriched ⊇ v1 signals; §7 distributions at/above floor | spec §7 | ☐ | comparison report vs v1 reference CSV | |
| E2 | Publish | browsable inventory site | publish gold inventory (table / GitHub Pages, à la v1 `vistadocs.github.io`) | ADR-022; spec §9.5 | ⬚ | — | deferred until inventory is wanted as a standalone product |

**Current focus:** the **crawler** (A1, A2, B1, B2) is ✅ green (`make check`: 168 tests, 100% cov,
ruff + mypy clean). Next: **A3** (port v1 vocabularies into `registries/`) → **Phase C** the
`catalog` enrichment — the *inventory-enrichment* half. **B3** (live bounded VDL crawl) is a manual,
politeness-gated smoke check, intentionally not run in CI.

**Dependency order:** A1→A2→A3 ⇒ B1→B2→B3 ⇒ C1–C9 (pure, parallelizable) → C10 (driver) ⇒ D1→D2 (gate) → D3→D4 ⇒ E. The gate (D2) is the milestone that unblocks the document medallion's `fetch`.

---

## Lessons Learned

*Append implementation lessons as they accrue (newest first). Spec-level lessons live in `vdl-crawl-spec.md` §8; this section is for things discovered while building.*

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
