# vdocs — As-Is State of the Pipeline (2026-06-08)

> **What this is.** A comprehensive, ground-truth snapshot of the vdocs pipeline as it actually
> exists on 2026-06-08 — verified against the live code (`src/vdocs/`), the two data lakes
> (`~/data/vdocs` prod, `~/data/vdocs-dev` dev), and the test suite, **not** asserted from design
> docs. It is written to be read cold by someone picking the project up, and to mark the hand-off
> point from the (now-closed) build-out spike to the new **offline lexical search** direction.
>
> **Companion documents** — read in this order for the full arc:
> 1. [`historical/vdocs-design.md`](historical/vdocs-design.md) — the **original master plan**
>    (founding greenfield design, 2026-06-01).
> 2. [`vdocs-remediation-plan.md`](vdocs-remediation-plan.md) — the 2026-06-06 audit + closure plan
>    (with a 2026-06-08 direction-reset banner).
> 3. [`vdocs-implementation-plan.md`](vdocs-implementation-plan.md) — the **frozen** spike execution
>    record (see its 🏁 Closure section for the decisive finding).
> 4. **This document** — the as-is state at the moment of the pivot.
> 5. [`offline-lexical-search-plan.md`](offline-lexical-search-plan.md) — the **active** go-forward
>    plan.

## Table of contents

1. [Introduction](#1-introduction)
2. [Document lineage — how we got here](#2-document-lineage--how-we-got-here)
3. [As-is pipeline at a glance](#3-as-is-pipeline-at-a-glance)
4. [Current state by subsystem](#4-current-state-by-subsystem)
5. [The data lakes — verified counts](#5-the-data-lakes--verified-counts)
6. [Registries & gold corpus](#6-registries--gold-corpus)
7. [Search & serving surface](#7-search--serving-surface)
8. [The vdocs spike & the discoveries it produced](#8-the-vdocs-spike--the-discoveries-it-produced)
9. [As-is gaps & loose ends](#9-as-is-gaps--loose-ends)
10. [Transitioning to the new plan (offline lexical search)](#10-transitioning-to-the-new-plan-offline-lexical-search)
11. [Verified-facts appendix](#11-verified-facts-appendix)

---

## 1. Introduction

vdocs is the greenfield v2 rewrite of the `vista-docs` pipeline: it ingests the VA VistA Document
Library (VDL) — DOCX/PDF manuals — and turns them into (a) a clean, latest-only, structure-aware
corpus and (b) a queryable index. The architecture is a **medallion lake** (bronze → silver → gold)
driven by a generic orchestrator over a DAG of contract-bound `Stage`s, with pure transforms in
`*_pure.py` and thin I/O drivers in `stage.py`.

As of 2026-06-08 the pipeline is **built and working end-to-end through lexical retrieval** on a real
~1,450-document corpus. What changed this week is not the machinery but the *direction*: a focused
spike to turn on semantic/vector search produced a decisive negative result (§8), and the project has
pivoted to **offline, human, no-AI lexical search distributed to developers** as its near-term goal.
This document records exactly where the code and data stand at that pivot.

**Method.** Every figure in §5/§11 was read live from `index.db`, the filesystem, and `pytest`
collection on 2026-06-08. Where this disagrees with older trackers, **this document is current.**

## 2. Document lineage — how we got here

| # | Document | Date | Role now |
|---|----------|------|----------|
| 1 | `historical/vdocs-design.md` | 2026-06-01 | **Original master plan** — the founding architectural source of truth (medallion lake, stage DAG, ADRs, two co-equal consumers: human corpus + AI/MCP knowledge base). Now historical reference. |
| 2 | `historical/vdocs-implementation-tracker.md` | through 2026-06-04 | Original whole-pipeline build tracker (spine-before-stages). Superseded by the remediation/implementation plans. |
| 3 | `vdocs-remediation-plan.md` | 2026-06-06 | Greenfield audit + 6-phase closure plan (0, A–E). Reset-bannered 2026-06-08. |
| 4 | `vdocs-implementation-plan.md` | 2026-06-06 → frozen 2026-06-08 | Spike execution tracker. **Frozen**; its 🏁 Closure section holds the embed-vs-lexical decision. |
| 5 | **this document** | 2026-06-08 | As-is state snapshot at the pivot. |
| 6 | `offline-lexical-search-plan.md` | 2026-06-08 | **Active** go-forward plan. |

The original master plan named **two co-equal consumers** — a human markdown corpus *and* an AI/MCP
knowledge base with hybrid (semantic + lexical + structured + graph) search. The spike tested the
costliest half of that vision (semantic/vector) and found it not worth its price on this corpus (§8),
which collapses the near-term goal to the human/lexical half. §10 covers the transition.

## 3. As-is pipeline at a glance

**14 stages are wired into the default DAG** (`cli/app.py:build_stages`), in order:

```
INVENTORY medallion (control plane)        DOCUMENT medallion (data plane)
crawl → catalog → serve-inventory  ──▶  fetch → convert → discover → enrich → normalize
                                          → consolidate → index → relate → embed → manifest → validate
```

| Stage | Status | Notes (as-is) |
|-------|--------|---------------|
| crawl · catalog · serve-inventory | ✅ live | inventory medallion; hard gate on fetch |
| fetch · convert | ✅ live | content-addressed DOCX; routed Pandoc/Docling → markdown + assets |
| discover · enrich · normalize | ✅ live | pattern mining + identity FM + F-step denoise; **registries now well-populated** (§6) |
| consolidate | ✅ live | version groups → 1 anchor + signed `bundle.yaml` + `history.yaml` lineage |
| index | ✅ live | `documents`/`doc_sections`/`chunks`+FTS5/`entities`; structure-aware chunking (A1) |
| relate | ⚠️ built, **output not present in current prod index.db** | wiped by the index rebuild; not re-run since (§9) |
| **embed** | ⛔ **parked / failed** | OOM-killed mid-run; `vectors.db` is a **0-byte zombie** (§8) |
| manifest | ✅ live | `ai-manifest.json` + `corpus-manifest.json` + `CORPUS.md` + `discovery.json` |
| validate | 🟡 slice | sidecar-verification slice live; full fidelity gate deferred |
| fidelity | ❌ unwired | directory exists, not in the DAG |
| publish · push | ❌ not built | **human deliverable absent** |
| analyze · refresh | ❌ not built | off critical path |
| MCP server | ⛔ descoped | never built; now out of scope (no-agent goal) |

## 4. Current state by subsystem

**Ingestion (crawl → fetch) — solid.** The inventory medallion cleanly separates "know every doc"
from "fetch a chosen subset"; `serve-inventory` is a hard gate and `fetch` is content-addressed with
full version lineage. Nothing pressing.

**Conversion + denoising (convert, discover, enrich, normalize) — solid and now *realized*.** The
F-step chain (recover headings → strip artifacts → drop dead phrases → reference boilerplate → strip
legacy TOC after capture → fix levels → GitHub-slug anchors → regenerate TOC → backlinks) is
capture-before-strip safe. Unlike the 2026-06-06 audit, the registries that drive it are no longer
thin (§6): boilerplate 37→**106**, phrases 7→**14**, and a **268 KB `gold/glossary.md` is
materialized**. Denoising has been applied to prod.

**Derivation (consolidate, index, manifest) — solid.** Version-group consolidation with a signed
bundle is a genuine strength (search corpus = latest only; evidence corpus = all versions, in CAS).
`index` builds a clean latest-only, structure-aware chunk surface with stable IDs
(`doc_key` · `section_id = doc_key/slug` · `chunk_id = section_id[#pN]`). `manifest` produces the AI
orientation card. **One regression:** the knowledge graph (`relate` → `relations`) is **absent from
the current prod `index.db`** because `index` rebuilds the DB wholesale and `relate` was not re-run
after this week's embed-prep index rebuilds (§9).

**Search/serving — lexical only, and that is now the intended surface (§7).**

**Tests — green and substantial:** **774 tests collected**; the project gate is `make check`
(ruff line 100 · mypy · pytest random-order · coverage ≥95%).

## 5. The data lakes — verified counts

Two medallion lakes, switched by `DATA_DIR`. Both read live on 2026-06-08.

| Metric | **prod** `~/data/vdocs` | **dev** `~/data/vdocs-dev` |
|---|---|---|
| `index.db` size | 167 MB | 56 MB |
| documents | 1,449 (462 `is_latest`) | 451 (69 `is_latest`) |
| doc_sections | 89,811 | 33,407 |
| — searchable `is_latest` | 21,847 | 6,308 |
| — kinds (`is_latest`) | container 7,098 · hollow 1,746 · ok 21,517 · stub 330 | container 2,049 · hollow 545 · ok 6,260 · stub 48 |
| chunks (= `chunks_fts`) | 26,923 | 8,036 |
| entities | 4,792 | 1,824 |
| entity_mentions | 60,832 | 22,342 |
| `relations` table | **absent** | absent |
| `vectors.db` | **0 bytes (zombie)** | absent |

The dev lake is the stratified golden subset (≈70 `is_latest` docs) used to prove the stack fast and
to host the retrieval-quality harness.

## 6. Registries & gold corpus

**Registries** (`registries/`, version-controlled in the repo) — materially richer than the
2026-06-06 audit:

| Registry | Entries (2026-06-08) | vs audit (06-06) |
|---|---|---|
| boilerplate | 106 | 37 |
| phrases | 14 | 7 |
| structures | 18 | 7 |
| templates | 130 | 129 |
| entities | 30 | 10 |
| glossary | (no YAML — README only) | 0 |

Note the glossary registry directory still holds only a README, **yet `gold/glossary.md` (268 KB) is
materialized** — the glossary was promoted into the gold corpus directly from `discover`'s candidates,
not via a curated registry YAML. (This matters for L1.3 query expansion in the new plan, which wants a
*structured* term map — see §10.)

**Gold corpus** (`~/data/vdocs/documents/gold/`): `consolidated/`, `_shared/`, `glossary.md`,
`corpus-manifest.json`, `ai-manifest.json`, `CORPUS.md`, `discovery.json` — all present. **`publish/`
is empty** (the human markdown tree is not built).

## 7. Search & serving surface

**Live today:** `server/search.py` + `server/search_pure.py` + `server/ids.py`, exposed as
`vdocs ask`. Lexical FTS5 + BM25 over `chunks_fts`, joined to `documents`/`doc_sections` for
pre-cited hits (stable `section_id`, snippet, score, resolved gold `body_path`). Structured
pre-filters: `app_code`, `doc_type`.

**The FTS schema:** `chunks_fts(chunk_id, section_id, doc_key, title, section_path, body)` —
`section_path` (breadcrumb) is indexed, but the **document title is not** (it is joined only at query
time). Ranking is `bm25(chunks_fts)` with **no field weighting**, and the MATCH string is a plain
OR-of-quoted-tokens (`fts_match_query`). These two facts are the entire near-term lexical-quality
opportunity (new plan L1).

**Baseline quality (dev lake, golden set, 2026-06-07):** mean **nDCG@10 = 0.395**, MRR = 0.517,
recall@10 = 0.50, redundancy@10 = 0.017 (5 labeled of 6 queries). The canonical failure is
`kaajee-install-procedure` at **nDCG@10 = 0.0** — a vocabulary-mismatch case where the doc-defining
token ("KAAJEE") lives in the *document title* (not in FTS) while the section bodies are terse and
generically titled. Harness: `scripts/baseline_golden.py` + `registries/golden-queries.yaml`.

**Not present:** no MCP server, no semantic/ANN, no RRF fusion, graph not exposed (and the graph
table is not even materialized in prod right now).

## 8. The vdocs spike & the discoveries it produced

The week of 2026-06-06 → 08 was, in effect, a **spike**: prove (or disprove) the costly half of the
original master plan — turn on semantic/vector search and fuse it with lexical (remediation Phases
A→C). A spike's deliverable is a *decision*, and this one delivered.

**What the spike built and proved (kept):**
- A **stratified golden dev set** + a separate dev lake, with the full DAG running end-to-end on it.
- A **retrieval-quality harness** and the lexical **baseline (nDCG@10 = 0.395)**.
- **Denoising driven to prod** (registries populated, glossary materialized, tables re-introduced as
  searchable chunks) — all of which sharpen *lexical* hits too.
- **Structure-aware chunking with a no-truncation budget gate** (A1), which caught and forced fixes
  for two unsplittable oversized-chunk classes before any vectors were written (`d5a6169`, `d91e34d`).

**The decisive discoveries (why semantic/vector was parked):**

1. **A per-batch OOM — found and fixed (`b1c5c2c`).** A fixed 256-item batch made ONNX pad to the
   longest member, so transient memory scaled with `items × longest_seq` (~20–25 GB spikes).
   `token_batched` (bound the *padded* footprint) + streaming writes brought a single worker's peak
   to ~5.3 GB. **This fix is correct and stays in-tree.**

2. **A process-fan-out OOM that killed the whole machine — the show-stopper.** On 2026-06-08 at
   **01:44:31** the kernel OOM-killer fired during the live prod embed run. Root cause is **not**
   per-batch padding (fixed) but **fastembed/ONNX-Runtime process fan-out**: a single OOM dump shows
   **19 `python` worker processes** (≈ one per core on the 16-core box), **each independently resident
   at ~1.78 GB** (model + ONNX runtime loaded per process), summing to **~24.6 GB** against **27 GiB
   RAM + ~2 GiB swap**. The OOM-killer fired **9 times**, SIGKILLed **14 processes**, and cascaded
   *beyond* embed into the user session (`systemd`/`sd-pam`/VS Code) — so the run died and
   **`vectors.db` was never written** (it survives only as a 0-byte file). The per-batch fix bounds
   *one* worker; nothing bounded *N* workers each loading the model.

3. **`embed` has no incrementality — every corpus change forces a full rebuild.** `EmbedStage.run`
   re-embeds **all** latest non-stub chunks and rebuilds `vectors.db` from scratch; its SKIP/run
   decision is the cheap input fingerprint of `index.db:chunks`, which is **just the row count**.
   So: fetch one new VDL doc, or make any silver change that adds/removes/splits chunks → **re-embed
   all ~26k chunks** (the heavy, OOM-prone job above). Same-count text edits *silently* skip (stale
   vectors). The VDL is a **large upstream corpus we do not control**, so this cost is **recurring**,
   and it **throttles iteration** on the cheaper lexical/structural work (every chunking tweak
   invalidates the whole `vectors.db`).

**The decision.** Against the reframed goal — *high-quality offline, human, no-AI search distributed
to developers with no agent to plug in* — the embedding/vector path's cost (fan-out OOM risk +
full-corpus rebuild on every upstream change + iteration drag) is **not justified**. Lexical (SQLite
+ FTS5) is lighter, more portable, faster to rebuild/iterate, and — for an expert/exact-token corpus
— good enough, with its residual gap closable cheaply at query time. **Portability is the headline:**
a self-contained `index.db` opened anywhere with stock `sqlite3` (zero ML deps) is the right
deliverable for a no-agent audience; a 500 MB-model surface is not. Full numbers: the implementation
plan's 🏁 Closure section + Phase C Discoveries (2026-06-08).

## 9. As-is gaps & loose ends

- **`vectors.db` 0-byte zombie** in prod (`~/data/vdocs/vectors.db`, created 01:27 by the killed run).
  Harmless but should be removed so nothing mistakes it for a built index.
- **Knowledge graph absent from prod `index.db`.** `relate` output (`relations`) was wiped by this
  week's `index` rebuilds and not regenerated. Not needed for the lexical pivot, but if anything
  (e.g. `manifest`, future structured search) expects it, **re-run `relate`**. The wipe-on-rebuild
  ordering (`index` must precede `relate`, and `index` clears prior `relations`) is itself a sharp
  edge worth a guard.
- **Human deliverable unbuilt** (`publish`/`push` empty) — this is now the *primary* go-forward work,
  not a side gap (§10).
- **Lexical ranking is un-tuned:** unweighted `bm25`, doc title not in FTS — the known cause of the
  KAAJEE 0.0 (§7).
- **Golden set is small** (6 queries) — must grow before weight-tuning is trustworthy.
- **`fidelity` unwired; full `validate` gate deferred** — quality is asserted, not gated.

## 10. Transitioning to the new plan (offline lexical search)

The transition is **subtractive, not a rewrite** — most of the pipeline is kept; only the
semantic/agent ambition is dropped. Mapping the original master plan's surface onto the new direction:

**Keep (already built, still load-bearing):** the whole ingestion → denoise → consolidate → index
path; the lexical search engine; the denoising registries + materialized glossary; the golden-query
harness. These *are* the substrate the new plan optimizes.

**Drop / park:** `embed`/`vectors.db` (parked), the MCP/agent server (descoped). The original
master plan's "co-equal AI/MCP consumer" framing is set aside; the human/lexical consumer is primary.

**Inert-but-retained:** A1 chunk-sizing-to-the-embedder and A2a contextual headers were embedding
concerns; under lexical-only they neither help nor hurt (A2a has zero lexical effect by construction).
Leave them; don't treat them as load-bearing.

**The clean hand-off steps** (detailed in [`offline-lexical-search-plan.md`](offline-lexical-search-plan.md)):
1. **L1 — close the lexical quality gap** (cheap, mostly query-time): field-weighted `bm25`, index
   the **doc title** (+ keep breadcrumb) in `chunks_fts`, and **query expansion**. *Transition note:*
   expansion wants a structured term map — promote the materialized `gold/glossary.md` (or
   `discover`'s candidates) into the empty `registries/glossary` so L1.3 has data (§6).
2. **L2 — the distributable tool**: a **Go** search CLI (`modernc.org/sqlite`, FTS5 compiled in) over
   `index.db`, single static cross-compiled binary, zero ML deps; `vdocs` (Python) stays the index
   builder; a golden-set parity gate keeps the Go ranker in sync with the Python one.
3. **L3 — the human corpus**: build `publish`/`push` (the original master plan's human half — now the
   headline deliverable, not a co-equal).
4. **L4 — gate quality**: run the golden-query metrics in CI; grow the query set; publish the claim.

**Housekeeping to do as part of the transition:** delete the 0-byte `vectors.db`; decide whether to
re-run `relate` (and add the ordering guard) or formally shelve the graph; keep `embed`/A1/`b1c5c2c`
in-tree (parking is a cost decision, not a defect) so the path can be un-parked later **only** behind
(a) a worker/thread cap and (b) content-hash delta-embedding.

**Net:** the as-is pipeline is a strong lexical-search substrate with one parked stage, one
un-materialized graph, and an unbuilt human deliverable. The new plan finishes the *human/lexical*
half of the original vision and ships it as a portable, offline, zero-dependency tool.

## 11. Verified-facts appendix

All read live on 2026-06-08.

**Wired stages (14, `cli/app.py:build_stages`):** crawl, catalog, serve-inventory, fetch, convert,
discover, enrich, normalize, consolidate, index, relate, embed, manifest, validate.
**Not built:** publish, push, analyze, refresh, MCP server. **Unwired:** fidelity.

**Prod `index.db` tables present:** documents, doc_sections, chunks, chunks_fts(+shadow tables),
entities, entity_mentions, doc_meta_staged, quality (view). **Absent:** relations.

**Prod counts:** documents 1,449 (462 latest) · doc_sections 89,811 (latest: container 7,098, hollow
1,746, ok 21,517, stub 330; searchable 21,847) · chunks 26,923 · entities 4,792 · entity_mentions
60,832. **Dev counts:** documents 451 (69 latest) · doc_sections 33,407 · chunks 8,036 · entities
1,824 · entity_mentions 22,342.

**Registries:** boilerplate 106 · phrases 14 · structures 18 · templates 130 · entities 30 · glossary
0 (README only). **Gold:** `glossary.md` 268 KB present; `publish/` empty.

**Serving:** `server/{search.py, search_pure.py, ids.py}` + `vdocs ask`; lexical FTS5+BM25, unweighted,
app/doc-type filter; doc title not in FTS. No MCP, no vectors, graph not exposed.

**Quality:** baseline nDCG@10 = 0.395 / MRR 0.517 / recall@10 0.50 / redundancy@10 0.017 (dev lake,
5 labeled / 6 golden queries). **Tests:** 774 collected; gate `make check` (ruff · mypy · pytest ·
coverage ≥95%).

**Spike OOM (2026-06-08 01:44:31):** 19 python workers × ~1.78 GB ≈ 24.6 GB on 16-core / 27 GiB +
~2 GiB swap; OOM-killer fired 9×, 14 processes SIGKILLed; `vectors.db` 0 bytes.
