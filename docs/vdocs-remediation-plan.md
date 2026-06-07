# vdocs Pipeline — Comprehensive Greenfield Review & Remediation Plan

> **Status:** **Forward source of truth for the project's direction** (greenfield reset, 2026-06-06).
> All prior design / spec / tracker documents have been moved to [`historical/`](historical/) and are
> retained **for reference only — not to be implemented**. Section references like "§14.6" and
> "fidelity-framework.md §10.5" throughout this report point into those historical docs
> ([`historical/vdocs-design.md`](historical/vdocs-design.md),
> [`historical/fidelity-framework.md`](historical/fidelity-framework.md)) as *background*, not as
> active commitments. This plan supersedes them as the implementation direction.
>
> **Date:** 2026-06-06 · **Scope:** entire pipeline, all stages/phases · **Method:** read-only audit
> of the live code + the real ~1,450-doc data lake at `~/data/vdocs` (figures verified against
> `index.db`, not asserted from design). · **Lens:** greenfield — beholden to no legacy approach.
>
> **Goal of the plan:** bring the pipeline to closure on three outcomes — **best human search**,
> **best AI search**, and **best signal-to-noise** (optimal chunking + optimal denoising for the
> richest, most substantive searchable text).

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [The Goal & What "Best" Means](#2-the-goal--what-best-means)
3. [As-Is Pipeline — Tabular Summary](#3-as-is-pipeline--tabular-summary)
4. [As-Is Pipeline — ASCII Art](#4-as-is-pipeline--ascii-art)
5. [As-Is Pipeline — Mermaid Diagram](#5-as-is-pipeline--mermaid-diagram)
6. [Stage-by-Stage Purpose & Effectiveness](#6-stage-by-stage-purpose--effectiveness)
7. [Effectiveness Analysis vs. the Goal](#7-effectiveness-analysis-vs-the-goal)
8. [Signal-to-Noise Optimization](#8-signal-to-noise-optimization)
9. [Optimal Chunking Strategy (greenfield)](#9-optimal-chunking-strategy-greenfield)
10. [Structured-Data / Sidecar Assessment](#10-structured-data--sidecar-assessment)
11. [Recommendations — Advanced AI (MCP) & Robust Human Search](#11-recommendations--advanced-ai-mcp--robust-human-search)
12. [The Closure Plan](#12-the-closure-plan)
13. [Verified Facts Appendix](#13-verified-facts-appendix)

---

## 1. Executive Summary

vdocs is a **well-architected medallion pipeline** that is **~70% built**. The spine (orchestrator,
contracts, medallion lake), the full ingestion → denoise → derive path (14 wired stages),
structure-aware chunking (A1), the knowledge graph, the AI corpus card, and lexical search
(`vdocs ask`) are **live and verified on a real ~1,450-doc corpus**.

The gap to the stated goal — *best-in-class human + AI search* — is concentrated in three places:

1. **Semantic search is off.** `embed` is scaffolded but unrun (no `fastembed`); `vectors.db` is
   empty; there is no ANN query, no RRF fusion, and **no MCP server** (`server/mcp.py` doesn't
   exist). Today's retrieval is lexical-only (BM25 over FTS5).
2. **Denoising is under-realized.** The discover → curate → apply machinery is built, but the curated
   registries are thin (phrases: 7, glossary: 0), so the corpus carries more redundancy/boilerplate
   than the design intends. Signal-to-noise is not yet measured (`fidelity §10.5` retrieval metrics
   unrun).
3. **A latent chunking/embedding mismatch.** The current chunk target (4,000 chars, hard split at
   8,000) **exceeds the 512-token limit of the planned embedder (`bge-small`)** — chunks would be
   silently truncated at embed time. This must be fixed *before* semantic goes live.

The architecture is sound and largely unbiased-by-legacy already. The recommendations here are
**evolutionary, not a rewrite**: right-size chunks to the embedder, add contextual headers, finish
denoising via the existing registry loop, promote structured sidecars into the queryable index, and
ship the MCP endpoint with hybrid (semantic + lexical + structured + graph) RRF.

---

## 2. The Goal & What "Best" Means

The design names **two co-equal consumers**:

- **Human** — a clean, browsable markdown corpus on GitHub (docs-as-code).
- **AI/machine** — a maximally discoverable knowledge base over **MCP**, with structured + lexical +
  semantic + graph search.

"Best" therefore decomposes into measurable targets (the corpus already specifies them in
`fidelity-framework.md §10.5`, just doesn't measure them yet):

- **Retrieval quality:** precision@k, recall@k, nDCG, MRR per mode.
- **Redundancy@k ≈ 0** (no near-duplicate hits) — the payoff of denoising + single-sourcing.
- **Over-strip / hollow rate ≈ 0** (no empty chunks diluting the index).
- **Version-correctness ≈ 100%** (only `is_latest` retrieved).
- **Citability** — every answer resolves to a stable `section_id` + on-disk `body.md`.

Every recommendation below is in service of moving those numbers.

---

## 3. As-Is Pipeline — Tabular Summary

**Medallion phases:** `INV` = inventory medallion (control plane, metadata only); `DOC` = document
medallion (data plane). Status: ✅ built & wired · 🟡 partial/scaffolded · ❌ not built.

| # | Stage | Phase | Purpose | In → Out | Idempotency | Status | Effectiveness |
|---|-------|-------|---------|----------|-------------|--------|---------------|
| 1 | **crawl** | INV·bronze | Scrape VDL site catalog | VDL site → `catalog.raw` | FORCE_ONLY | ✅ | Strong; immutable evidence |
| 2 | **catalog** | INV·silver | Enrich/classify/group/noise-tag (8,834 recs) | `catalog.raw` → `catalog.enriched` | SKIP_UNCH | ✅ | Strong; 57-pattern doc-type, version groups |
| 3 | **serve-inventory** | INV·gold | Curated selection surface + **HARD GATE** | `catalog.enriched` → `inventory.{json,db}` | SKIP_UNCH | ✅ | Strong; gates fetch |
| 4 | **fetch** | DOC·bronze | Download selected DOCX (CAS) | inventory + selection → `raw/<sha>.docx` | SKIP_UNCH | ✅ | Strong; explicit selection, no blind pull |
| 5 | **convert** | DOC·silver | DOCX→md (Pandoc/Docling, routed) | `raw` → `text@converted` + assets | SKIP_UNCH | ✅ | Strong; discovery-routed converter |
| 6 | **discover** | DOC·silver | Mine boilerplate/phrases/templates/glossary/structures | `text@converted` → `reports/patterns` | SKIP_UNCH | ✅ | Mechanism strong; **curation under-run** |
| 7 | **enrich** | DOC·silver | Bake identity frontmatter | `text@converted` → `text@enriched` | SKIP_UNCH | ✅ | Strong |
| 8 | **normalize** | DOC·silver | F-step denoise + sidecars (refs/toc/revisions/tables/capture/flags) | `text@enriched`+registries → `text@normalized` | SKIP_UNCH | ✅ | Strong machinery; **denoise limited by thin registries** |
| 9 | **consolidate** | DOC·gold | Version-group → 1 anchor + `history.yaml` + signed `bundle.yaml` | `text@normalized` → `consolidated/` | SKIP_UNCH | ✅ | Strong; tamper-evident, lineage captured |
| 10 | **index** | DOC·gold | documents/sections/**chunks+FTS5**/entities | `consolidated`+`normalized` → `index.db` | SKIP_UNCH | ✅ | Strong; **A1 chunking live** |
| 11 | **relate** | DOC·gold | Graph edges (mentions/cooccurs/xref) | `index.db` → `relations` (110k) | SKIP_UNCH | ✅ | Built; not yet served |
| 12 | **embed** | DOC·gold | chunks → `vectors.db` (bge-small 384-d) | `chunks` → `vectors.db` | SKIP_UNCH | 🟡 | **Skips (no fastembed); never run** |
| 13 | **manifest** | DOC·gold | corpus-manifest/discovery/**ai-manifest/CORPUS.md** | derived → `gold/*.json,md` | SKIP_UNCH | ✅ | Strong; the AI card |
| 14 | **validate** | DOC·gold | Sidecar-verification HARD GATE (slice) | sidecars → `reports/validation` | ALWAYS | 🟡 | Slice live; full fidelity gate deferred |
| — | **fidelity** | DOC·gold | Per-doc S→T verdicts + retrieval metrics | normalized+raw → `reports/fidelity` | — | 🟡 | Dir exists, **not wired into DAG** |
| — | **publish** | DOC·gold | Human markdown tree for GitHub | consolidated → `publish/` | — | ❌ | Not built — **human deliverable absent** |
| — | **push** | delivery | Commit to `vistadocs/vdl` | publish → git | — | ❌ | Not built |
| — | **analyze** | reports | Survey/headings/lexicon diagnostics | normalized → `reports/` | — | ❌ | Not built (off critical path) |
| — | **refresh** | currency | Scheduled crawl-diff re-process | — | — | ❌ | Not built |
| — | **MCP server** | serving | Resources/Tools/Prompts + hybrid RRF | index/vectors → MCP | — | ❌ | **Designed only — the key AI gap** |

**Serving layer today:** `server/search.py` (lexical FTS5 + BM25, structured app/doc-type pre-filter)
+ `server/ids.py` (stable IDs/URIs) + `vdocs ask` CLI. Semantic, graph-traversal tools, and the MCP
protocol are **not** built.

---

## 4. As-Is Pipeline — ASCII Art

```
                          ┌───────────────────────── INVENTORY MEDALLION (control plane) ─────────────────────────┐
   VDL site ──crawl──▶ catalog.raw ──catalog──▶ catalog.enriched ──serve-inventory──▶ inventory.{json,db}  [HARD GATE]
                          └──────────────────────────────────────────────────────────────────────┬───────────────┘
                                                                                    selection │ (gate green)
                                                                                              ▼
   ┌──────────────────────────────────────── DOCUMENT MEDALLION (data plane) ──────────────────────────────────────┐
   │  🥉 BRONZE        🥈 SILVER (immutable snapshots)                       🥇 GOLD (derived, computable)           │
   │                                                                                                                 │
   │  fetch ─▶ raw/<sha>.docx                                                                                        │
   │            │                                                                                                    │
   │         convert ─▶ text@converted ─┬─▶ discover ─▶ reports/patterns ┄┄(curate PR)┄┄▶ registries/  (boilerplate, │
   │            │ +assets               │                                                  phrases, templates, …)    │
   │            │                       └─▶ enrich ─▶ text@enriched ─▶ normalize ─▶ text@normalized + SIDECARS       │
   │            │                                       (F-recover→strip→phrases→boilerplate→toc→levels→anchors→     │
   │            │                                        toc-regen→backlinks)   (refs/toc/revisions/tables/          │
   │            │                                                                capture/flags .yaml + tables/*.csv) │
   │            │                                                                          │                         │
   │     consolidate ◀──────────────────────────────────────────────────────────────────┘                         │
   │        │  version groups → 1 anchor + history.yaml(lineage) + bundle.yaml(signed) + _shared/history/<sha>.md     │
   │        ▼                                                                                                         │
   │     index ─▶ index.db {documents · doc_sections(anchors) · chunks+FTS5(search) · entities}                      │
   │        │        ▲ A1 chunking: container+hollow EXCLUDED · oversized SPLIT (#pN) · is_latest only               │
   │        ├──▶ relate ─▶ index.db:relations  (mentions · cooccurs · xref = 110k edges)                             │
   │        ├──▶ embed ─▶ vectors.db   ✗ SKIPPED (no fastembed) → semantic OFF                                        │
   │        └──▶ manifest ─▶ gold/{corpus-manifest, discovery, ai-manifest}.json + CORPUS.md                          │
   │                 │                                                                                                │
   │              validate (sidecar slice: typed-absence · refs · bundle-digest)  [full fidelity gate deferred]      │
   └─────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
                          │                                                            │
              SERVING ─── │ vdocs ask  ──▶ server/search.py (FTS5+BM25, structured filter) ──▶ ranked, pre-cited hits
              (today)     │ ✗ no MCP server · ✗ no semantic/ANN · ✗ no RRF · ✗ graph tools unexposed
                          ▼
          ❌ publish (human GitHub tree)   ❌ push   ❌ refresh (currency)   🟡 fidelity (unwired)
```

---

## 5. As-Is Pipeline — Mermaid Diagram

```mermaid
flowchart TD
    VDL([VDL website]) -->|crawl| CR[catalog.raw]
    CR -->|catalog| CE[catalog.enriched]
    CE -->|serve-inventory| GI{{gold inventory\nHARD GATE}}

    GI -->|fetch selection| RAW[raw/&lt;sha&gt;.docx]
    RAW -->|convert| TC[text@converted]
    TC -->|discover| PAT[reports/patterns]
    PAT -.curate PR.-> REG[(registries/\nboilerplate·phrases·\ntemplates·structures)]
    TC -->|enrich| TE[text@enriched]
    REG -.consumed by.-> NORM
    TE -->|normalize| TN[text@normalized\n+ sidecars]
    TN -->|consolidate| CON[consolidated/\nanchor + history.yaml\n+ signed bundle.yaml]

    CON -->|index| IDX[(index.db\ndocuments·sections·\nchunks+FTS5·entities)]
    IDX -->|relate| REL[(relations\n110k edges)]
    IDX -->|embed| VEC[(vectors.db)]:::off
    CON -->|manifest| MAN[ai-manifest.json\nCORPUS.md\ndiscovery.json]
    TN -->|validate slice| VAL{{sidecar gate}}

    IDX --> ASK[vdocs ask\nFTS5 + BM25]
    ASK --> HITS[ranked pre-cited hits]

    MAN -.orients.-> AGENT([AI agent / Claude])
    HITS --> AGENT

    VEC -.->|NOT built| MCP[MCP server\nhybrid RRF]:::missing
    REL -.->|NOT exposed| MCP
    IDX -.-> MCP
    CON -.->|NOT built| PUB[publish to GitHub]:::missing

    NORM[normalize]:::hidden

    classDef off fill:#fee,stroke:#c33,stroke-dasharray:4;
    classDef missing fill:#eee,stroke:#999,stroke-dasharray:5,color:#666;
    classDef hidden fill:none,stroke:none,color:none;
```

*(Red dashed = built but inactive `vectors.db`/embed; grey dashed = designed, not built: MCP server,
publish.)*

---

## 6. Stage-by-Stage Purpose & Effectiveness

**Ingestion (crawl → fetch) — Effectiveness: high.** The inventory medallion cleanly separates "know
about every doc" from "fetch a chosen subset." `serve-inventory`'s hard gate and `fetch`'s
explicit-selection rule (no blind downloads, full version lineage acquired) are disciplined and
working. Little to improve.

**Conversion (convert) — high.** Pandoc-default with a *discovered* Docling allowlist (for VA DOCX
that explode into bare cross-ref markers) is a genuinely good pattern: the routing is data
(registry), not code. CAS image store is correct.

**Discovery + denoising (discover, normalize) — strong machinery, under-realized output.** This is the
heart of signal-to-noise and the biggest lever. The F-step chain (recover headings → strip artifacts
→ delete dead phrases → reference boilerplate → strip legacy TOC after capture → fix heading levels →
rewrite anchors to GitHub slugs → regenerate clean TOC → insert back-links) is comprehensive and
*capture-before-strip safe* (nothing deleted without a typed `capture.yaml` record). **But** the
curated registries are thin (phrases: 7 entries, boilerplate: 37, glossary: 0), and
`gold/_shared/boilerplate/` is empty — so in practice most boilerplate/phrase redundancy is **not yet
subtracted**, and there is **no corpus glossary**. The loop is built; it just hasn't been *run to
saturation*.

**Consolidation (consolidate) — high.** Version-group → single anchor with append-only `history.yaml`
lineage, retained prior bodies in CAS, and a **signed `bundle.yaml`** (per-part sha256 +
`bundle_digest`) is excellent: tamper-evident, replay-ready, and it keeps the *search corpus* (latest
only) separate from the *evidence corpus* (all versions). A design strength.

**Indexing + chunking (index) — strong, now A1-correct.** Verified live: of 30,664 `is_latest`
sections, containers (7,094) and hollow (1,739) are correctly **excluded** from search; 21,831
searchable sections expand to 24,320 chunks (2,489 oversized splits). Stable IDs (`doc_key`,
`section_id = doc_key/slug`, `chunk_id = section_id[#pN]`) are the contract across FTS, graph,
citations, and (future) MCP URIs. The one concern is the **chunk-size vs. embedder mismatch** (§9).

**Graph (relate) — built, not served.** 110k edges (mentions/cooccurs/xref) exist but no tool exposes
traversal. Latent value.

**Embedding (embed) — scaffolded, never run.** Clean injected-backend design; now skips gracefully
without `fastembed`. `vectors.db` is empty → **semantic capability is off**.

**Manifest + AI card (manifest) — strong.** `ai-manifest.json` + `CORPUS.md` give an agent the full
catalog, entity index, citation scheme, query recipe, and an `index.db` fingerprint for staleness —
exactly the orientation layer that prevents re-discovery and hallucination.

**Validation/fidelity — partial.** The sidecar-verification slice (typed-absence, ref-resolution,
bundle-digest) is live and good. The **per-document fidelity verdict and the retrieval-quality
measurement (§10.5) are not running** — so corpus quality is asserted, not measured.

**Human deliverable (publish/push) — absent.** There is **no human-browsable GitHub tree yet**. Half
the stated goal (the human consumer) is currently unserved end-to-end.

---

## 7. Effectiveness Analysis vs. the Goal

| Capability | Target | Today | Verdict |
|---|---|---|---|
| **Lexical search** | BM25 over clean latest-only corpus | ✅ live (`vdocs ask`) | **Good** |
| **Structured search** | filter app/doc-type/is_latest/entity/date | 🟡 app+doc-type only | Partial |
| **Semantic search** | ANN over per-chunk embeddings | ❌ off (no vectors) | **Missing** |
| **Hybrid (RRF)** | fuse semantic+lexical, structured pre-filter | ❌ not built | **Missing** |
| **Graph search** | traverse entities/xrefs/versions | 🟡 edges built, no tool | Latent |
| **MCP endpoint** | Resources/Tools/Prompts for agents | ❌ not built | **Missing** |
| **AI orientation** | corpus card, citations, no-guess rule | ✅ ai-manifest + CORPUS.md | **Good** |
| **Human corpus** | browsable GitHub markdown tree | ❌ publish/push absent | **Missing** |
| **Signal-to-noise** | boilerplate/phrase removed, glossary promoted | 🟡 machinery built, registries thin | Under-realized |
| **Quality measurement** | nDCG, redundancy@k, version-correctness | ❌ unrun | **Missing** |

**Net:** the *substrate* (clean latest-only structure-aware chunks, stable IDs, graph, lineage) is
genuinely strong and the foundation for excellent search. The *retrieval surface* is currently
lexical-only and CLI-only, the *human deliverable* is unbuilt, and *denoising + quality* are not yet
driven to target. The path to "best" is well-defined and short.

---

## 8. Signal-to-Noise Optimization

Signal-to-noise directly governs both semantic and structured search quality (noisy chunks → blurry
embeddings, crowded neighborhoods, false matches). Current state and concrete moves:

1. **Saturate the denoising loop (highest leverage, lowest risk).** The mechanism exists; the
   registries are thin. Run `discover` at corpus scale, then curate aggressively:
   - **Phrases (7 → the long tail):** delete paper-era furniture ("This page intentionally left
     blank", "Continued on next page", revision-table filler).
   - **Boilerplate (37 → materialize):** populate `gold/_shared/boilerplate/` and replace duplicated
     legal/header/footer blocks with references. The single biggest redundancy@k win.
   - **Glossary (0 → materialize `gold/glossary.md`):** promote acronyms once, drop per-doc copies.
2. **De-weight ubiquitous low-signal entities.** Globals dominate (2,355 of 4,792 entities) and are
   noise for ranking. Already excluded from `xref` edges; also **exclude/down-weight globals from
   semantic boost and from the entity-index headline**, keeping them queryable but not
   ranking-dominant.
3. **Reconsider `stub` chunks (299).** These are <8-token sections that exist only to point at a
   referent (boilerplate/CSV/asset). They're currently searchable; for **semantic** they should
   likely be excluded (a pointer embeds to nothing useful) while remaining lexically findable. Make
   searchability mode-specific.
4. **Index extracted tables as data.** `tables/*.csv` are lifted out of prose for fidelity but become
   **invisible to search**. Re-introduce them as a distinct structured chunk (caption + headers +
   rows) so data-dictionary lookups work — otherwise prose S/N improved at the cost of table recall.
5. **Measure it.** Implement `fidelity §10.5`: a golden query set + redundancy@k + over-strip +
   version-correctness, run as a gate. You cannot optimize S/N you don't measure; this also produces
   the published quality claim.

**Expected effect:** redundancy@k → near 0, sharper embedding neighborhoods, and a defensible "hybrid
nDCG@10 = X" number.

---

## 9. Optimal Chunking Strategy (greenfield)

The current design — **chunk on structure, exclude hollow/container, split oversized with overlap,
carry context as metadata** — is the right philosophy. Three greenfield refinements, one urgent:

### 9a. URGENT: right-size chunks to the embedding model
`CHUNK_TARGET_CHARS = 4000`, `OVERSIZED_CHUNK_CHARS = 8000`. But the planned embedder,
**`BAAI/bge-small-en-v1.5`, has a 512-token limit (~2,000 chars)**. A 4,000-char chunk (~1,000
tokens) is **silently truncated to its first half at embed time** — the back of every large chunk
would never be embedded. Options:

- **(A) Right-size to the model:** target ~**1,800 chars / ~450 tokens**, hard split ~**2,400 chars**,
  keep one-block overlap. Safe with bge-small.
- **(B) Switch to a long-context embedder** — **`bge-m3`, `nomic-embed-text-v1.5`, or
  `jina-embeddings-v3` (8,192 tokens)** — and keep ~2,000–3,000-char chunks. *Recommended:* bge-m3 is
  multilingual, strong, and supports long context + sparse+dense (helps hybrid).

Whichever model, **align `CHUNK_TARGET_CHARS` to its real token budget** and assert it at embed time.

### 9b. Add contextual chunk headers ("small-to-big" / contextual retrieval)
A leaf chunk like "Select Installation Option: 1" is ambiguous in isolation. Prepend a compact
**context header** to the *embedded* text (not the displayed body):
`«{doc_title} › {section_path}»\n\n{chunk}`. Cheap, dramatically improves semantic recall on terse
VistA sections, and the metadata is already computed (`section_path`, `title`). Keep the
displayed/cited body clean.

### 9c. Right-size the unit of knowledge by merging tiny adjacent leaves
40%+ of sections are thin (<400 chars). Pure structure-chunking leaves many sub-target fragments. Add
a **merge pass**: coalesce consecutive small leaf sections *under the same parent* up to the target
size, so a chunk is a coherent unit of knowledge rather than a one-line fragment — while still
splitting big leaves. This raises mean chunk substance without crossing semantic boundaries.

**Recommended chunking contract (v2):**
```
unit        = leaf section (container/hollow excluded — already correct)
merge       = adjacent small leaves under same parent → up to TARGET
split       = leaf > HARD → paragraph windows of ~TARGET, 1-block overlap (already correct)
embed text  = "«doc_title › section_path»\n\n" + chunk_body   (new: context header)
TARGET/HARD = aligned to the chosen embedder's token budget (FIX from 4000/8000)
stub chunks = lexical-only, excluded from semantic (new)
```

---

## 10. Structured-Data / Sidecar Assessment

**Current approach (sound foundation):** lifecycle-split is correct — *identity* frontmatter baked
into `body.md`; *computed* data only in `index.db`; *heavy structured* data in travel-with YAML
sidecars (`refs.yaml`, `revisions.yaml`, `toc.yaml`, `flags.yaml`, `capture.yaml`), `tables/*.csv`,
plus the **signed `bundle.yaml`** and cross-version `history.yaml`. Boilerplate is single-sourced by
reference. This keeps prose clean, diffs sane, and the bundle tamper-evident. **Keep all of this.**

**The gap (greenfield):** the sidecars are **YAML-on-disk, not queryable by the serving layer.**
`relate`/`entities` made it into `index.db`, but `revisions`, `toc`, `refs` (cross-references), and
extracted `tables` live only as YAML/CSV. So an MCP `list_versions()`, `cross_references()`, or "show
me the data dictionary table for file #2" cannot be answered from the DB — the serving layer would
have to parse YAML per request. Recommendations:

1. **Promote machine-facing sidecars into `index.db` at index time.** Add tables:
   `revisions(doc_key, date, version, change)`, `cross_refs(section_id, target_section_id, kind)`,
   `toc(doc_key, title, level, anchor)`, `doc_tables(table_id, doc_key, section_id, caption, columns,
   csv_path)`. Sidecars remain the human/fidelity artifact; the DB becomes the single queryable
   surface for MCP. (Tenet stays intact: DB is *derived*, rebuildable from sidecars.)
2. **Index table content for retrieval** (§8.4) so extracted tables are findable.
3. **Dereference discipline at serve time:** when a hit's body contains a boilerplate reference, the
   MCP `get_section`/`get_document` should optionally inline the canonical
   `_shared/boilerplate/<id>.md` so an agent never receives a bare "[see boilerplate]" as an answer.
4. **Keep `bundle.yaml` signing** — a genuine strength; extend `validate` to verify it corpus-wide as
   a release gate.

Net: **structured-data *capture* is excellent; structured-data *serving* is the missing half.** Move
the machine-facing slices into the index.

---

## 11. Recommendations — Advanced AI (MCP) & Robust Human Search

**A. Ship the MCP endpoint (the headline AI capability).** Build `src/vdocs/server/mcp.py` on the MCP
Python SDK, reusing `server/search.py`/`ids.py`:

- **Tools:** `search(query, mode=hybrid, filters, k)`, `get_section`, `get_document`, `find_entity`,
  `cross_references`, `list_versions`, `get_lineage`.
- **Resources:** `vdocs://doc/{id}`, `vdocs://section/{id}`, `vdocs://entity/{type}/{name}`
  (read-only, mode=ro).
- **Prompts:** "answer-with-citations over vdocs", "trace a routine across the corpus".
- Versioned against `index.db` `contract_ver`; refuses incompatible stores.

**B. Turn on semantic + hybrid RRF.** `uv add fastembed` (or the chosen long-context model), fix chunk
sizing (§9a), run `embed`, then implement vector ANN over `vectors.db:vec_chunks` and **RRF fusion**
(semantic ⊕ lexical, structured pre-filter as a WHERE clause). This flips `capabilities.semantic` on
and delivers the "best human + AI semantic search" the goal asks for.

**C. Expose graph + structured.** Wire `relations` into `cross_references`/`find_entity` tools;
complete structured filters (date, has-entity, section, FileMan file #).

**D. Build the human deliverable.** Implement `publish` (markdown-only tree + INDEX + materialized
glossary) and `push` to `vistadocs/vdl`. Without this, the human consumer is unserved.

**E. Measure and gate.** Stand up `fidelity §10.5` (golden queries + redundancy@k + over-strip +
version-correctness) as a release gate; run the with/without-condensation ablation to prove the
denoising lift.

---

## 12. The Closure Plan

A sequenced, dependency-ordered plan to reach the three goals (best human search · best AI search ·
best signal-to-noise). Each step is a shippable increment with a gate.

### Phase A — Fix the substrate before embedding (prereq for everything semantic)
- **A1. Right-size chunking to the embedder** (§9a): pick the model (recommend **bge-m3, 8k-context**),
  set `CHUNK_TARGET/HARD` to its token budget, assert no-truncation at embed time. *Gate: no chunk
  exceeds the model limit.*
- **A2. Contextual chunk headers + small-leaf merge** (§9b–c). *Gate: mean chunk substance ↑, hollow
  stays 0.*
- **A3. Stub chunks → lexical-only** (§8.3).

### Phase B — Drive signal-to-noise to target (the denoising loop)
- **B1.** Run `discover` at scale; curate **phrases** + **boilerplate** registries; **materialize
  `gold/_shared/boilerplate/`**.
- **B2.** Materialize **`gold/glossary.md`** (PROMOTE).
- **B3.** De-weight globals; index extracted tables as data (§8.4).
- *Gate: redundancy@k → ~0 on the golden set; ablation shows lift.*

### Phase C — Semantic + hybrid retrieval
- **C1.** `uv add fastembed`/model; run `embed`; `vectors.db` populated; `manifest` flips semantic on.
- **C2.** Implement ANN query + **RRF fusion** + full structured pre-filter in `server/search.py`.
- *Gate: hybrid nDCG@10 measured and ≥ lexical baseline.*

### Phase D — MCP endpoint (the AI deliverable)
- **D1.** `server/mcp.py` + `vdocs serve-mcp`: Tools/Resources/Prompts over the hybrid engine.
- **D2.** Promote machine-facing sidecars into `index.db` (§10.1) so `list_versions`/
  `cross_references`/table lookups are DB-served.
- *Gate: an agent answers "based on vdocs gold corpus…" via MCP with citations, semantically.*

### Phase E — Human deliverable + quality gate
- **E1.** Build `publish` (markdown tree + INDEX + glossary) and `push` to GitHub.
- **E2.** Wire `fidelity` into the DAG; stand up the `§10.5` retrieval-quality gate; finish the full
  `validate` gate (schema + fidelity verdict).
- *Gate: per-doc PASS/REVIEW/QUARANTINE verdicts + a published retrieval-quality claim; human corpus
  live on GitHub.*

**Critical path:** A → C → D (semantic AI search). **Parallelizable:** B (denoising) and E1 (publish)
can proceed alongside. **Do A1 first** — running `embed` before fixing chunk size would bake in
truncated vectors.

---

## 13. Verified Facts Appendix

All figures below were read from the live system on 2026-06-06 (not asserted from design docs).

**Stage directories present** (`src/vdocs/stages/`): catalog, consolidate, convert, crawl, discover,
embed, enrich, fetch, **fidelity**, index, manifest, normalize, relate, serve_inventory, validate.
**Wired into the default DAG** (`cli/app.py:build_stages`, 14): crawl, catalog, serve-inventory, fetch,
convert, discover, enrich, normalize, consolidate, index, relate, embed, manifest, validate.
`fidelity` exists but is **not wired**; `publish`/`push`/`analyze` directories **do not exist**.

**Chunking constants:** `MIN_SUBSTANTIVE_TOKENS = 8` (`kernel/markdown.py:107`),
`OVERSIZED_CHUNK_CHARS = 8000`, `CHUNK_TARGET_CHARS = 4000`, `DEFAULT_TOC_DEPTH = (2,3)`
(`stages/index/index_pure.py`).

**Live `index.db`:** doc_sections total 89,800; `is_latest` 30,664 — by kind: container 7,094,
hollow 1,739, ok 21,532, stub 299. Searchable `is_latest` sections 21,831 → chunks 24,320 (split
parts `#pN`: 2,489). **A1 hollow/container exclusion + oversized split confirmed live.**

**Entities (9 types):** build, fileman_file, global, hl7_segment, mail_group, option,
package_namespace, routine, rpc. Total 4,792 (globals 2,355 — the dominant, low-signal type).
**Relations:** 110,390 edges (mentions/cooccurs/xref).

**Registries populated (list entries):** templates 129, boilerplate 37, phrases 7, structures 7,
entities 10, **glossary 0**. `gold/_shared/boilerplate/` and `gold/glossary.md` **not materialized**.

**Embedder mismatch:** planned `BAAI/bge-small-en-v1.5` max sequence = 512 tokens (~2,000 chars) vs.
`CHUNK_TARGET_CHARS = 4000` / `OVERSIZED = 8000` → truncation risk if embed runs unchanged.

**Serving:** `server/{search.py, search_pure.py, ids.py}` + `vdocs ask` (lexical/BM25 + app/doc-type
filter). `server/mcp.py` **absent**; `vectors.db` empty; no RRF; graph edges unexposed.
