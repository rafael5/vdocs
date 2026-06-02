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

## Phase / stage summary

| Phase | Stage | Layer | Goal (requires → produces) | Design ref | Status | Evidence | Notes |
|---|---|---|---|---|---|---|---|
| **1 — Spine** | | | the Stage/Artifact abstraction + generic DAG runner, proven by a no-op DAG | §7, §17.1 | ✅ | | the contract-enforcing core everything else fills in |
| 1 | kernel | — | text · frontmatter · fingerprint · cas · lineage · db · discovery · **http** (one each, §9.2) | §9.2 | ✅ | `tests/unit/kernel/*` | `http` hardened this session (PoliteClient: UA/retry/429/redirect/final-URL/delay) |
| 1 | config | — | `Settings` off `DATA_DIR`; all lake paths derived; no module-level path constants | §5.3, §9.1 | ✅ | `test_config` | inventory medallion + gold-inventory + registries paths added |
| 1 | models / contracts | — | Pydantic boundary types; `ArtifactContract` (locate/validate/fingerprint); the registry | §7.1 | ✅ | `test_artifact`, `test_registry` | |
| 1 | orchestrator | — | `Stage` base (generic preflight/postflight), DAG engine, `state.db:stage_runs` | §7.1–7.3 | ✅ | `test_noop_dag`, `test_engine_edges` | one execution path; no stage re-implements gating |
| **2 — Inventory medallion + doc-bronze** | | | gold inventory of the whole site + the fetch gate, then a selected bronze | §4, §17.2 | ✅ | see [`vdl-crawl-tracker.md`](vdl-crawl-tracker.md) | the foundation the document plane stands on |
| 2 | **crawl** | 🥉 INV | `vdl` → `inventory/bronze:catalog.raw` (polite 3-level walk; final-URL base; skip non-200) | §8; spec §3 | ✅ | `test_crawl_pure`, `test_crawl_stage` | live bounded smoke (B3) still manual |
| 2 | **catalog** | 🥈 INV | `catalog.raw` → `catalog.enriched` (5-pass enrichment + system classification, §5 cols) | §8; spec §4 | ✅ | `test_enrich_pure`, `test_catalog_inventory` | **§7 distributions reproduce exactly** vs the pinned 8,834-row fixture |
| 2 | **serve-inventory** | 🥇 INV | `catalog.enriched` → gold `inventory.{json,csv,db}`; **HARD GATE = the fetch gate** | §8, §7.3; spec §7 | ✅ | `test_serve_pure`, `test_serve_inventory` | gate green on the full corpus; `vdocs inventory --status` |
| 2 | **fetch** | 🥉 DOC | gate `ok` + selection + `acquisitions` → `documents/bronze:raw` (CAS) + `index.json` + `acquisitions` | §8, §9.5 | ◐ | `test_fetch_pure`, `test_bronze_dag` | works (CAS, DOCX-pref, index, acquisitions, gate-wired); **explicit selection flags pending** (fetches all `noise==''`) |
| **3 — Silver (document text)** | | | bytes → conformed, normalized markdown bundles; discovery→registry seam first | §17.3 | ☐ | | build discover→registry **before** normalize so no pattern is hard-coded |
| 3 | **convert** | 🥈 DOC | `raw`,`index.json` → `text@converted` + `assets` (Pandoc + Docling; CAS images) | §8 | ☐ | | DOCX/PDF → markdown; image extraction to CAS |
| 3 | **discover** | 🥈 DOC | `text@converted` → `reports/patterns` (candidate boilerplate/templates/glossary/structure + disposition) | §8, §9.6 | ☐ | | inductive, corpus-global; **proposes** `registries/` updates via a curation gate; mutates no content |
| 3 | **enrich** | 🥈 DOC | `text@converted`,`catalog.enriched` → `text@enriched` (identity FM baked) + `index.db:doc_meta_staged` | §8 | ☐ | | joins inventory identity onto each bundle |
| 3 | **normalize** | 🥈 DOC | `text@enriched`,`raw`,`registries` → `text@normalized` (+ history/tables/refs sidecars; TOC regen) | §8, §6.7 | ☐ | | F1–F10; subtracts curated patterns; single-sources boilerplate/glossary; strips version apparatus |
| **4 — Gold derive (machine)** | | | version groups + the queryable index + knowledge graph + manifests | §17.4 | ☐ | | |
| 4 | **consolidate** | 🥇 DOC | `text@normalized`,`assets` → `consolidated` (one anchor per version group; ordered lineage) | §8, §6.6 | ☐ | | `is_latest`; prior bodies as travel-with sidecars |
| 4 | **index** | 🥇 DOC | `text@normalized`,`consolidated` → `index.db` (docs, sections + **FTS5 over is_latest**, entities, quality, **stable IDs**) | §8 | ☐ | | the lexical/structured search surface |
| 4 | **relate** | 🥇 DOC | `index.db` → `index.db:relations` (doc↔entity, doc↔doc xref, entity↔entity) | §8 | ☐ | | the knowledge graph |
| 4 | **manifest** | 🥇 DOC | `consolidated`,`index.db`,`vectors.db`,`state.db` → `corpus-manifest.json` + `discovery.json` | §8, §14 | ☐ | | lineage + machine-discovery descriptor |
| **5 — Gold deliver (humans)** | | | per-doc fidelity verdict → published human tree → hard gate → push | §17.5 | ☐ | | |
| 5 | **fidelity** | 🥇 DOC | `text@normalized`,`raw`,`index.db`,`registries` → `reports/fidelity` (per-doc S→T verdict + corpus report) | §8; [`fidelity-framework.md`](fidelity-framework.md) | ☐ | | content/provenance/history axes + template compliance + TOC integrity |
| 5 | **publish** | 🥇 DOC | manifest, `text@normalized`, `consolidated`, `assets`, `catalog.enriched`, `glossary` → `publish` (md-only tree + INDEX) | §8 | ☐ | | markdown-only; images materialized + gitignored |
| 5 | **validate** | 🥇 DOC | `publish`,`text@normalized`,`index.db`,`vectors.db`,`reports/fidelity` → **HARD GATE** (schema·lineage·anchors·IDs·fidelity verdict) | §8, §7.3 | ☐ | | ALWAYS_RERUN; QUARANTINE blocks; REVIEW needs sign-off |
| 5 | **push** | 🚀 DOC | `publish` (+ validate `ok`) → `git:vistadocs/vdl` (anchor files + lineage sidecars) | §8, §6.6 | ☐ | | FORCE_ONLY; commit-replay deferred behind `--replay-history` |
| 5 | **analyze** | ⬩ DOC | `text@normalized` → `reports/{survey,headings,lexicon}` (off critical path) | §8 | ☐ | | diagnostic only |
| **6 — Machine interface (§14)** | | | embeddings + the MCP server (hybrid search) — the headline machine output | §17.6, §14 | ☐ | | |
| 6 | **embed** | 🥇 DOC | `index.db:doc_sections` (**is_latest only**) → `vectors.db` (per-chunk embeddings + ANN) | §8, §14.6 | ☐ | | prior-version chunks excluded |
| 6 | **serve-mcp** | 🥇 DOC | `index.db`,`vectors.db`,`corpus-manifest`,`discovery.json` → MCP server (semantic+lexical+structured+graph, RRF) | §14 | ☐ | | MCP Python SDK; read-only stores |
| **7 — Harden** | | | property tests · `--verify` · `gc` · generated stage docs · history-replay · `refresh` | §17.7 | ☐ | | filling robustness against a frozen spine |
| 7 | property tests | — | Hypothesis property tests for the pure transforms | §10 | ◐ | `tests/property/*` (text, frontmatter) | extend to enrich/normalize transforms as they land |
| 7 | `--verify` mode | — | upgrade fingerprints to full content hashes for CI/paranoid runs | §7.4 | ◐ | wired in `ArtifactContract.fingerprint(verify=)` | exercise end-to-end |
| 7 | `gc` | — | sweep superseded silver trees | §17.7 | ☐ | | |
| 7 | `docs/stages/` gen | — | per-stage reference generated from contracts | §17.7 | ☐ | | |
| 7 | `push --replay-history` | — | build git commit history from `history.yaml` sidecars + retained prior bodies | §6.6 | ⬚ | | deferred git-native payoff |
| 7 | `refresh` | — | scheduled crawl-diff + incremental re-processing; refresh fidelity/currency verdicts | §7.6 | ☐ | | drift: NEW/SUPERSEDED/CHANGED propagate only |

**Current focus:** **Phases 1–2 are ✅** (the spine + the whole inventory medallion + a gated, selected
document-bronze). `make check` green (208 tests, 100% cov, ruff + mypy clean); the gold inventory is
populated in the real lake and the fetch gate is green. **Next: Phase 3 — the document silver**, and the
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
