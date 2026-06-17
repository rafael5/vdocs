# Kickoff — SKL S3: re-point the projections at the SKL (the search vocabulary-mismatch payoff)

**Repo: `vdocs`.** Start a fresh session and `cd ~/projects/vdocs` first (one session ↔ one repo).
Read `CLAUDE.md`, then — in order — `docs/skl-proposal.md` (the *what/why*; esp. §6 the projection
refactor, §8 the search payoff, §5 the data model) and `docs/skl-implementation-plan.md` (the
*how/status* tracker — read the **Decisions (S0 sign-off)** block and the **S2 changelog +
Discoveries**, both of which bind S3). **The tracker is the bug report: if code and plan disagree,
fix the plan first.** Keep new SKL artifacts under the `skl-`/`knowledge` naming where the name is
ours.

## Where we are

- **S0 signed off** (`8d949d0`), **S1 done end-to-end** (`7658fa0` + `fileman-docs f89977d`), and
  **S2 LANDED** (`b0b6100`): the `resolve` stage + `knowledge.db` are real and proven on the live
  FileMan (DI) gold — the headline holds (`file #200` ↔ `NEW PERSON` ↔ `^VA(200,` → one
  `fileman_file/200`), **21 FileMan files resolved, 23 terms, 111 `documented-in` edges, 0 rejected,
  315 propose-only candidates**. `make check` green (1037 tests, 97.76% cov).
- S3 is the **payoff phase**: make every downstream artifact a *view of the SKL* (proposal §6/§8) —
  the termbase, the glossary + cross-links, and an **entity-keyed `index.db`** — and cash in the
  search **vocabulary-mismatch** win the whole program was a precursor for (proposal §8). This is
  still **re-centering, not rewrite**: re-point existing projections at `knowledge.db`; do not
  rebuild the pipeline.

### What S2 built that S3 builds *on* (read the code before changing it)
- `gold/knowledge.db` (= `cfg.knowledge_db`, at `documents/gold/knowledge.db`): tables
  `entities` / `terms` / `relationships` + `meta`. Read it via **`kernel.knowledge_db`**
  (`read_entities` / `read_terms` / `read_relationships`, schema v1.0) — never hand-roll SQL.
- `models/knowledge.py` — the node types. **Entity id is `type/canonical`** (slash), e.g.
  `fileman_file/200`; Term id is `term/<surface>`; a relationship is `(src_id, rel, dst_id)`.
- `stages/resolve/` — the `recognize→resolve→classify→relate→verify` cores (`resolve_pure.py`) +
  the thin driver. Scope is the **DI pilot only** (`PILOT_APP = "DI"`).
- Registries that ARE the curated seed: `entities/dd-seed.di.yaml` (Q6 DD spine),
  `relationships/edge-types.yaml` (Q3 closed set), plus the propose queue at
  `reports/knowledge/proposals.json` (§10).

## The S0 decisions that bind S3 (ratified — do not re-open)

| # | Binds | Decision |
|---|-------|----------|
| **Q4** | S3.3 | **Two DBs in the lake, joined on entity-id; the `publish` step folds the small knowledge tables into the *shipped* `index.db`.** S3 owns that merge — the search deliverable wants **one portable file** (the active search plan's DoD). |
| **K4/§6** | all | **Re-point, don't rewrite.** `build-termbase`, the glossary, the crosswalk, and `index` become *projections of the SKL*; the stages/kernel/orchestrator stay. |
| **tenet #13** | S3.1/S3.2 | **Single-source.** Every generated artifact flows from the SKL with no hand-maintained parallel list — the same principle S1 proved (Brand.yml deleted). |
| **K2** | S3.4 | **Deterministic, offline, zero-ML.** The search win is *entity resolution + generated synonym expansion*, not embeddings. Honors the 2026-06-08 reset and the search plan's zero-ML DoD. |

## The real technical frictions to resolve at S3 (surface these to Rafael; decide before building)

These are the non-obvious facts the new session must reckon with — found while reading the live code,
not assumed:

1. **Entity-id reconciliation (the join, Q4).** `index.db` keys entities **colon-style**
   (`stages/index/stage.py`: `eid = f"{etype}:{canon}"` → `fileman_file:200`) from its *own*
   recognition pass; `knowledge.db` keys them **slash-style** (`fileman_file/200`). The Q4 join needs
   one canonical id on both sides. **Decide:** normalize index.db to the SKL id at the merge, or carry
   a mapping column. Recommended: the SKL id (`type/canonical`) is the canonical one — the merge
   rewrites/augments index.db entity rows to it (and `manifest`'s ID-scheme advertises it).

2. **DAG placement of the merge.** Today `index` runs **before** `resolve` (both only depend on
   `consolidate`; the topo tie breaks by name, and `resolve` doesn't depend on `index`). So `index`
   *cannot* read `knowledge.db` — it doesn't exist yet when `index` runs. The entity-keying/merge
   (S3.3) must therefore live in a step that runs **after `resolve`**. **Decide the home:** (a) a new
   thin **`publish`/`merge` stage** that augments `index.db` from `knowledge.db` (cleanest; matches
   Q4's "publish merges"); or (b) make `index` `require` `knowledge.db` (forces resolve→index order,
   but couples whole-corpus `index` to the DI-only `resolve`). **(a) is recommended** — keep `index`
   the generic builder, add a post-resolve SKL-merge that tags chunks + writes the synonym table.

3. **`resolve` is DI-only; the corpus is whole.** `index` covers every package; `knowledge.db`
   covers DI. The merge must **augment where SKL data exists and no-op elsewhere** (a non-DI chunk
   simply gets no SKL entity tags yet) — never drop or regress non-DI coverage. Generalizing `resolve`
   past DI is **S5**, not S3.

4. **Termbase coverage must not regress (S3.1 trap).** `build-termbase` today projects the **full
   controlled vocabulary (624 terms)** from `registries/inventory/product-names.yaml`. The SKL's Term
   nodes are only the **~23 that appear in DI gold**. Naively "termbase ← SKL Term nodes" would crater
   coverage 624→23. **Decide:** either `classify` emits a Term node for **every** registry term
   (status `approved`, provenance only where it appears) so the SKL is the term *superset*; or the
   termbase projection unions the SKL term catalog with the registry. The proposal's intent is the
   former — the SKL becomes the single source the 624-term termbase projects from.

5. **The search golden set vs KAAJEE.** The tracker names *both* `file #200`↔`NEW PERSON` **and**
   KAAJEE. The `file #200`↔`NEW PERSON` mismatch is **resolvable from the DI SKL now** (it's the
   headline). **KAAJEE is a Kernel (XU) doc, not FileMan** — its win waits for S5 (Kernel resolution),
   unless its doc is pulled into scope. So S3.4 proves the **class** of fix on a **DI-resolvable**
   mismatch query: ensure `registries/golden-queries.yaml` contains a file#↔name query (add one if
   absent — the search plan already flags "expand the golden set before trusting expansion tuning"),
   take it from nDCG@10 = 0 → positive, and show the **mean beats the 0.395 baseline**. Record KAAJEE
   as the S5 generalization proof.

## S3 steps (TDD — pure `*_pure.py` cores first, thin drivers)

| ID | Step | Where / detail | Gate |
|----|------|----------------|------|
| S3.1 | **Termbase ← SKL** | Make `kernel/termbase.py` (and `build-termbase`) project from the SKL Term catalog instead of raw registries — **without** regressing the 624-term coverage (friction #4: SKL must carry the full term superset). The casing facets already live on Term nodes. | termbase regenerates **identically-or-better** (≥624 terms, same Vale behavior); tenet-#13 single-source preserved; S1's `Vista→VistA`/`Fileman→FileMan` break-tests still bite |
| S3.2 | **Glossary + cross-links ← SKL** | Generate `gold/glossary.md` (= `cfg.glossary`, currently empty) from entity `canonical_name` + `synonyms`; generate in-corpus cross-links from `documented-in` (and later `synonym-of`) edges. | glossary non-empty + drift-gated; generated links resolve (strict-build / lychee); no hand-maintained glossary |
| S3.3 | **Entity-keyed `index.db` (the Q4 merge)** | New post-`resolve` merge (friction #2 home decision): reconcile entity ids (friction #1), tag `chunks`/`doc_sections` with resolved SKL entity ids, and write a generated **synonym/expansion table** into `index.db` so the shipped one file carries the SKL surface. | a chunk *about* file #200 is retrievable by `#200` / `NEW PERSON` / `^VA(200,`; non-DI coverage unchanged; `index.db` read-contract version bumped |
| S3.4 | **Search wins (the precursor payoff)** | Wire the **SKL-generated** synonym/expansion data into `server/search_pure.fts_match_query` (replaces the hand-seeded, off-by-default `registries/glossary/expansions.yaml` — L1.3). Re-run `scripts/baseline_golden.py`. | a DI file#↔name golden query goes nDCG@10 0 → >0; **mean nDCG@10 beats the 0.395 baseline**, recorded via `baseline_golden.py`; still zero-ML/offline |

*TDD: each projection/merge transform is a pure function tested before its thin driver; an
integration test runs the merge on a seeded index.db + knowledge.db slice and asserts the
entity-keyed retrieval; the search win is recorded by the existing golden harness.*

## The projection shape (proposal §6)

```
                                   registries/ (curated seed + override)
                                          │
 consolidate ─▶ resolve ─▶ knowledge.db ──┼─▶ [ S3 projections / merge ]
                            (entities·     │      ├─ build-termbase  (Vale Casing.yml)   ← S3.1
                             terms·        │      ├─ gold/glossary.md + cross-links       ← S3.2
                             relationships)│      ├─ index.db (entity-keyed + synonym tbl) ← S3.3
                                           │      └─ search expansion (fts_match_query)    ← S3.4
                index.db (generic builder, runs before resolve) ─────────┘  (merge augments it)
```

Pure cores in the relevant `*_pure.py`; thin drivers; reuse `kernel.knowledge_db` for all reads (no
hand-rolled SQL, §9.2). Update the tracker (and the read-contract spec under `contracts/read/` if
`index.db`'s shape changes) in the **same commit** as the code (house rule).

## Acceptance / done (S3)

- `build-termbase` projects from the SKL with **no coverage regression** (≥624 terms) and zero
  hand-maintained vocab; S1 invariants still hold.
- `gold/glossary.md` and in-corpus cross-links are **generated from the SKL** (non-empty,
  drift-gated, links resolve).
- `index.db` is **entity-keyed**: a chunk about file #200 is retrievable by `#200` / `NEW PERSON` /
  `^VA(200,`; the entity-id scheme is reconciled (Q4); non-DI coverage is unchanged; the read
  contract version is bumped.
- The search **vocabulary-mismatch payoff lands**: a DI file#↔name golden query beats 0 and the mean
  nDCG@10 **beats the 0.395 baseline**, recorded by `scripts/baseline_golden.py`; deterministic,
  offline, zero-ML throughout.
- `make check` green (≥95% cov); TDD throughout. Update the tracker (S3 rows ✅ / changelog /
  discoveries — esp. the entity-id reconciliation + merge-placement decisions and any expansion-tuning
  gotchas). Commit with the `Co-Authored-By` trailer; push (house cadence).

## Suggested order & starting point

Start with **S3.3's two design decisions** (entity-id reconciliation + merge placement, frictions #1
and #2) since they shape everything downstream — propose them by **editing
`docs/skl-implementation-plan.md` first** (house rule), get Rafael's nod, then build. A sensible build
order is **S3.3 → S3.4** (the headline search payoff, the reason S3 exists) then **S3.1 → S3.2** (the
termbase/glossary projections, lower-risk and gated by the no-regression rule). Mind the **vdocs
shared-lake rule** before any run on `~/data/vdocs` (check for a live operator run; don't race
`state.db`/`index.db`/CAS — `resolve` + the new merge both write `index.db`/`knowledge.db`).

## Next after this

- **S4** — turn the proposal §7 invariants into CI gates (entity-resolution coverage, term
  canonicalization, relationship integrity, provenance completeness) on the FileMan corpus + the
  meaning-aware coverage dashboard.
- **S5** — templatize the FileMan run into a reusable kit and walk the dependency graph (**Kernel** →
  MailMan → clinical), the catalog growing monotonically; **KAAJEE** becomes resolvable here; land
  live `verified_on` (Q2). See `docs/skl-implementation-plan.md`.
