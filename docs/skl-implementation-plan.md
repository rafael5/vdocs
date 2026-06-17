# Semantic Knowledge Layer — Implementation Plan & Tracker

> **The *what/why* lives in** [`skl-proposal.md`](skl-proposal.md)
> (the pivot, the data model, the reconciliation with the 2026-06-08 reset, the decision table). This
> document is the *how/status* tracker: detailed S0–S5 steps, per-phase gates, and a per-phase
> changelog/discoveries/risks log. **Update it as work lands** (TDD → `make check` → update tracker →
> commit, per step — the house cadence).

> **Status: S0 signed off + S1 fully landed + S2 landed (2026-06-17).** S0 ratified the model
> and resolved proposal §13 (K1–K7 + Q1–Q6 — see Decisions under S0). S1 (the self-contained casing
> quick win) is **done end-to-end** — facet schema blessed, casing bug fixed at the source, and S1.4
> (the `fileman-docs` repo half) landed: `Brand.yml` deleted, generated `Casing.yml` wired in,
> `make gate` green (`fileman-docs` `f89977d`). **S2 is done**: the `resolve` stage + `knowledge.db`
> are built and proven on the real FileMan (DI) gold — the headline holds (`file #200` ↔ `NEW PERSON`
> ↔ `^VA(200,` → one `fileman_file/200` entity), 21 FileMan files resolved, 111 typed edges, every
> node provenanced + `asserted`. **Next: S3** (re-point the projections; entity-keyed `index.db`;
> the search vocab-mismatch payoff), per the S0 decisions.

## Goal — one outcome

A governed, symbolic **Semantic Knowledge Layer (SKL)** — entities · terms · concepts · relationships,
keyed to VistA's own identifiers — materialized in the gold tier (`knowledge.db`), from which the
termbase, glossary, cross-links, search index, and the docs-as-code gate are all **projected**. Meaning
becomes the gold artifact everything derives from; quality is measured in semantic-fidelity terms.
Deterministic, offline, zero-ML, incremental (proposal §3, §9).

## Inherited — do not redo

The proposal §4 seeds stand and are built *on*, not over:
`registries/entities/entities.yaml` (typed recognizers + canonical ids + lifecycle), `index.db:entities`
(stable `(type, canonical)` ids), `build-termbase` (already a registries→gate projection),
`enrich`/`relate` stages, the medallion lake + content-addressing, the §9.6 `discover` proposal gate.

## Definition of done

1. `knowledge.db` exists in gold as a first-class `ArtifactContract`, with entity/term/concept/
   relationship nodes carrying identity + provenance + lifecycle.
2. **Termbase, glossary, cross-links, and `index.db` are generated from the SKL** — no hand-maintained
   parallel lists. `fileman-docs` `Brand.yml` + `Vale.Terms = NO` are deleted (S1).
3. **Semantic-fidelity gates** (entity-resolution coverage, term canonicalization, relationship
   integrity, provenance completeness) run in CI on the FileMan corpus and fail on regression.
4. The search vocabulary-mismatch failures (KAAJEE, `file #200` ↔ "NEW PERSON") are fixed via
   entity-resolved indexing and **beat the 0.395 lexical baseline** on the golden set.
5. The run is templatized and proven on a second package (Kernel), the catalog growing monotonically.

---

## Phases

Status legend: ✅ done · 🟡 in progress · ⬜ not started. Each phase is an independently shippable
increment with a gate; TDD-first where it touches the pipeline (pure `*_pure.py` cores tested before
thin `stage.py` drivers).

### S0 — Ratify the model ✅ (signed off 2026-06-17)
Settle the proposal §13 decision table and open questions; freeze the SKL node schema and the
`knowledge.db` gold contract as program policy.

| ID | Step | Detail | Gate | Status |
|----|------|--------|------|--------|
| S0.1 | Sign off the data model | Ratify entity/term/concept/relationship + identity/provenance/lifecycle fields (proposal §5) | schema agreed; written into this tracker | ✅ adopted as policy |
| S0.2 | Resolve K2 / Q6 | Confirm "symbolic honors the embedding reset" framing (K2); decide entity seed source (Q6) | decisions recorded with rationale | ✅ see Decisions below |
| S0.3 | Fix the relationship taxonomy | Closed starter edge set vs `discover`-proposed (Q3) | edge-type registry shape agreed | ✅ closed set + gated discover |

#### Decisions (S0 sign-off, 2026-06-17) — proposal §13 resolved

**Decision table K1–K7:** all recommendations **adopted as program policy** (proposal §13). Note on
**K2**: symbolic ≠ statistical — this *honors* the 2026-06-08 embedding reset; embeddings stay **fully
parked**, not even scoped as the "optional grounded top-layer," to avoid scope creep. Revisit only as a
deliberate future decision.

**Open questions Q1–Q6:**

| # | Decision | Rationale / implication for S2+ |
|---|----------|----------------------------------|
| **Q6** Entity seeds | **Live DD spine + corpus-mined synonyms; live system as tiebreaker.** | The live Data Dictionary gives authoritative identity (`file #200 → "NEW PERSON"`) cheaply and un-guessably; the corpus supplies the prose synonyms readers actually use (the S3 vocabulary-mismatch fix). **Dependency:** S2.2 needs a live VistA (vehu/foia-t12 + m-engine) for the DD spine; mind the vdocs shared-lake / don't-race-the-operator rule. |
| **Q2** `verified_on` | **Defer full live verification to S5; schema carries `verification.status` from day one.** | S2 nodes are `asserted` (corpus provenance); a later live check upgrades to `verified` with **no migration**. Decouples S2 throughput from live-system/shared-lake ops (per the Risks "defer if it blocks S2" note). Optional cheap win: a thin file#→name confirmation for the DI files at S2 if the engine is handy. |
| **Q4** `knowledge.db` ↔ `index.db` | **Two DBs in the lake (joined on entity-id); `publish` folds the small knowledge tables into the shipped `index.db`.** | Separate rebuild lifecycles internally (knowledge = small/curated/slow; index = large/regenerated/per-chunk); one portable file at the distribution edge (honors the search-plan one-file DoD). Shapes **S2.1** (`knowledge.db` is its own gold ArtifactContract) and the publish merge step. |
| **Q3** Relationship taxonomy | **Closed starter edge set + `discover`-proposed extensions through the §9.6 gate.** | Fixed types (`synonym-of`, `miscapitalization-of`, `documented-in`, `reads`, `runs-on`, `part-of`/`belongs-to-package`) in a version-controlled `registries/relationships/edge-types.yaml`; `discover` may *propose* new types (human-approved); **unregistered edge types never reach `knowledge.db`.** Closed-by-default, extensible-by-review. Shapes **S2.3**. |
| **Q1** Concept identity | **AI-proposes-clusters → human-curates (§10 loop); Concepts scoped OUT of S2.** | Entities/Terms/Relationships are enumerable + authoritative — S2 builds those. Concepts are the hardest, least-bounded kind; they enter at **S3/S4** when there is corpus-wide signal. Keeps S2 cost bounded (the §13-Q1 cost concern). |
| **Q5** Governance | **Rafael = sole curator/SME of record; governance = registry PRs + the §9.6 discover gate. No committee.** | Hobbyist/single-developer scale: the version-controlled `registries/` + PR review *is* the governance (CODEOWNER = Rafael). Revisit only if this ever feeds a real VA program. |

### S1 — Classify the vocabulary; fix the casing bug at the source ✅ (vdocs + fileman-docs both done)
Self-contained quick win (proposal §12 S1) — the smallest proof that "everything is a projection"
works, and the deletion of the `fileman-docs` workaround. Does **not** require `knowledge.db` yet; it
extends the existing termbase projection.

| ID | Step | Detail | Gate | Status |
|----|------|--------|------|--------|
| S1.1 | Add Term classification facets | Extend the product registry with `class` / `canonical_casing` / `enforce_case` / `expand_on_first_use` (proposal §5); validate on load (fail-loud on wrong type) | facets present + schema-validated; TDD on the loader | ✅ `kernel/products.py` |
| S1.2 | Auto-derive `collides_with_english` | Pure transform: a term collides iff lowercase ∈ the dict **Vale's own speller consults** AND it is not brand-cased (internal-capital). Vendored wordlist from Vale `en_US-web.dic` (proposal §7) | pure-fn unit-tested incl. CAN/SITE/AN/OR/IS + Title-case (Site/Host/Map) + brands; no human collision-guessing | ✅ `kernel/casing_pure.py` |
| S1.3 | `build-termbase` emits selective casing | Project casing enforcement **only** for `enforce_case && !collides_with_english` single-token terms (new `Casing.yml` Vale style); accept.txt still whitelists all spellings | regenerated Vale style enforces brand casing, ignores colliding acronyms — **624 terms enforced**; E2E Vale proof: Vista→VistA bites, ordinary "can/or/site" untouched | ✅ `kernel/termbase.py` |
| S1.4 | Retire the `fileman-docs` workaround | Re-run `build-termbase --out-dir` into `fileman-docs`; **delete `.vale/VistA/Brand.yml`**, wire `Casing.yml` into `make termbase`; `make gate` stays green; the `Vista→VistA` break-test still bites | fileman-docs gate green with zero hand-maintained vocab; casing coverage ≫ 6 terms | ✅ `fileman-docs` `f89977d` (2026-06-17): Brand.yml gone; Casing.yml = 624 terms; gate green 7/7; Vista→VistA + Fileman→FileMan bite, common-word prose clean. `Vale.Terms = NO` **kept** — empirically, accept.txt's English-colliding acronyms (CAN/SITE/OR) make Vale.Terms-ON force-cap prose; Casing.yml is the precise enforcer |

*TDD: `collides_with_english` and the selective-casing projector are pure functions tested first; the
`fileman-docs` re-run (S1.4) is the integration proof (a one-repo-per-session handoff).*

### S2 — Formalize the SKL + the `resolve` stage (FileMan) ✅ (landed 2026-06-17)
Promote semantic resolution to a named DAG layer producing `knowledge.db` for the `DI` gold (proposal
§6). Re-centering, not rewrite — elevate `enrich`+`entities`+`relate`. **Kickoff (next session):**
`docs/prompts/skl-s2-kickoff.md`. **Live-DD verified available** 2026-06-17 (`vehu`/`foia-t12` up; DD
populated — `file #200 → "NEW PERSON"` confirmed); access **must** go via the `m` toolchain
(m-driver-sdk → m-ydb/m-iris), never raw `docker exec` (engine-stack guard). **`m vista exec`/`status`
docker→engine binding is NOW WIRED** (fixed 2026-06-17, m-cli + m-ydb) — **option (a) is unblocked**.
Working invocation (copy verbatim into S2.2):

```
m vista exec --engine ydb  --transport docker --container vehu     'W $P($G(^DIC(200,0)),"^",1)'   # → NEW PERSON
m vista exec --engine iris --transport docker --container foia-t12 --namespace VISTA 'W $P($G(^DIC(200,0)),"^",1)'   # → NEW PERSON
```

Targeting is explicit flags: `--container` (both engines) + `--namespace` (IRIS only); `m vista status
--engine ydb --transport docker --container vehu` → `running:true healthy:true version:r2.02`. Two
fixes landed: m-cli `vista_cmd.go` now passes the target via the SDK Client `ConnArgs` (still the seam —
no raw `docker exec`), and the m-ydb docker transport now runs through a login shell so the container's
own `gtmgbldir`/`gtmroutines` load. Seed corpus-first + backfill (options b/c) remains available but is
no longer necessary for the DD spine.

| ID | Step | Detail | Gate | Status |
|----|------|--------|------|--------|
| S2.1 | `knowledge.db` ArtifactContract | Gold contract (schema for entity/term/relationship + provenance/lifecycle + verification block); two-DBs-joined (Q4) | contract + Pydantic boundary types; orchestrator wires it | ✅ `models/knowledge.py`, `kernel/knowledge_db.py`, 3 `KNOWLEDGE_*` contracts |
| S2.2 | `resolve` stage — recognize → resolve | Share `entities_pure`; data-driven synonymy resolution to canonical ids (`file #200`/`NEW PERSON`/`^VA(200,` → `fileman_file/200`) | pure-fn tests; resolution table data-driven from registries + DD seed | ✅ `resolve_pure.resolution_index/resolve`; live-DD seed `dd-seed.di.yaml` |
| S2.3 | `resolve` stage — classify → relate → verify | Fold S1 term facets; typed edges from the closed `edge-types.yaml` set (reject unregistered); stamp every node `asserted` (Q2) | `knowledge.db` populated for DI gold; edges typed + provenanced | ✅ `classify_terms`/`partition_edges`/`all_asserted`; `documented-in` edges |
| S2.4 | Seed the catalog (AI-proposed, human-curated) | Curated seed = `dd-seed.di.yaml` + `edge-types.yaml` (status `approved`); unresolved mentions → a propose-only curator queue (§10) | curator-approved seed; every node cites provenance; zero unreviewed assertions | ✅ `build_proposals` → `reports/knowledge/proposals.json` (4954 candidates, none asserted) |

*TDD: each `resolve` sub-transform is a pure function tested before the `stage.py` driver
(`tests/unit/stages/test_resolve_pure.py`); the integration test runs the stage on a seeded DI gold
slice (`tests/integration/stages/test_resolve_stage.py`) and asserts the headline + `knowledge.db`.*

**Stage seam (design):** `resolve` runs after `consolidate`, reads the DI gold bodies + the
registries (`entities/entities.yaml`, `entities/dd-seed.di.yaml`, `relationships/edge-types.yaml`,
`inventory/product-names.yaml`, `glossary/english-words.txt`) and produces the three
`knowledge.db:{entities,terms,relationships}` SQLITE_TABLE contracts at
`documents/gold/knowledge.db` (its own gold DB, Q4). CLI: `vdocs resolve`. The orchestrator derives
its order from `requires`/`produces` — no hand-maintained list (the `vdocs-design.md` §8 table is
frozen/historical; this tracker + the proposal §6 are the live design surface for the SKL).

### S3 — Re-point the projections 🟡 (S3.3 + S3.4 + S3.1 landed 2026-06-17; S3.2 next)
Make every downstream artifact a view of the SKL (proposal §6, §8).

| ID | Step | Detail | Gate | Status |
|----|------|--------|------|--------|
| S3.1 | Termbase ← SKL | `build-termbase` reads Term nodes from the SKL instead of raw registries | termbase regenerates identically-or-better; tenet-13 single-source preserved | ✅ classify emits the 483-surface Term superset; `build-termbase` projects from `knowledge.db` (registry fallback); **byte-identical** to the registry path (identity test + real-lake diff); accept.txt 1117 terms (no regression) |
| S3.2 | Glossary + cross-links ← SKL | Generate `gold/glossary.md` and in-corpus cross-links from entities/synonyms/relationships | glossary non-empty + drift-gated; links resolve (lychee/strict-build) | ⬜ |
| S3.3 | Entity-keyed `index.db` | New post-`resolve` **`merge`** stage augments `index.db` from `knowledge.db` (D-S3.3a/b below) | chunk about file #200 retrievable by `#200`/"NEW PERSON"/`^VA(200,`; non-DI coverage unchanged; read-contract version bumped (additive) | ✅ `bcd4bd0` (merge stage; read contract v1.5; real lake: 6 entities reconciled, 56 synonyms, 5786 chunk tags) |
| S3.4 | Search wins (the precursor payoff) | Wire SKL synonym data into `fts_match_query` expansion (replaces empty-glossary L1.3) | a DI file#↔name golden query nDCG@10 0 → >0; mean nDCG@10 beats the lexical-only baseline; recorded via `baseline_golden.py` | ✅ DI query **0.131 → 0.406** (recall 0.5→1.0); mean (19-query, main lake) **0.313 → 0.328**; the delta is *only* that query (no regression) |

#### Decisions (S3.3 design, 2026-06-17) — frictions #1/#2 resolved (Rafael)

The two S3.3 decisions that shape everything downstream (kickoff §"real technical frictions"). Surfaced
from the live code, decided with Rafael before building.

**D-S3.3a — Merge placement = a new post-`resolve` `merge` stage (friction #2, option a).** A thin new
stage `merge` `requires [INDEX_*, KNOWLEDGE_*]` and runs after both — the orchestrator topo becomes
`consolidate → {index, resolve} → merge` (Kahn ties break by name; `merge` is forced last by its
requires). It **augments** `index.db` from `knowledge.db`; `index` stays a **generic whole-corpus
builder with zero SKL knowledge**. CLI: `vdocs merge`. *Rejected option (b)* (make `index` require
`knowledge.db`) because it couples the corpus-wide builder to the **DI-only** `resolve` — every index
run would wait on resolve, any SKL edit would invalidate the whole corpus index, and DI-specificity
would leak into the generic stage (against tenet #13). The new stage is independently re-runnable and is
the natural home for the Q4 fold (and later the publish-into-one-file step).

**D-S3.3b — Entity-id reconciliation = additive, keep the colon ids (friction #1, option B).** `index.db`
keeps its colon `entity_id` (`type:canonical`, e.g. `fileman_file:200`) **untouched**; the read-contract
bump is **additive** (no breaking change for vdocs-tui / vdocs-web). The `merge` stage writes — **only
where SKL data exists** — (i) an `skl_node_id` column on `entities` (slash `type/canonical`, NULL for
non-DI/unresolved rows), (ii) a generated **synonym/expansion** table, and (iii) **chunk→entity tags**.
The Q4 join is via `skl_node_id`. *Rejected option (a)* (normalize index.db to slash corpus-wide)
because it is a **breaking** contract change that churns the id on the thousands of non-DI rows the SKL
never touches, forces a coordinated two-consumer release, and still doesn't deliver the search win on its
own (the win is the synonym table + chunk tags, which both options need). Additive keeps non-DI coverage
**literally unchanged** (friction #3) and is reversible.

> **Note (lowers the stakes on D-S3.3b):** the S3.4 search payoff is delivered by the **chunk→entity
> tags + synonym/expansion table**, *not* by the id-separator choice. Id reconciliation only ensures a
> chunk tag points at a stable entity row. There is also a **set mismatch** the merge must bridge
> regardless of separator: `index` recognizes `fileman_file:200` and a *separate* bare `global:^VA`,
> whereas the SKL folds the number, the name "NEW PERSON", and `^VA(200,` into one `fileman_file/200`
> node (others as synonyms) — so the merge links index's per-surface mentions to the SKL's per-entity
> node, then tags the chunks.

**Decided (friction #4, termbase superset, 2026-06-17 — Rafael): `classify` emits a Term node for
*every* registry term** (status `approved`; corpus provenance where it appears, a `registry:` provenance
marker where it does not), so `knowledge.db` becomes the term **superset** and `build-termbase` projects
purely from the SKL — true single-source (tenet #13). *Rejected* the union-of-SKL+registry path
(termbase reads two sources, weaker single-source).

**S3.1 build shape (no-regression is exacting).** `accept.txt` = abbr + full + match aliases +
expansion keys; `Casing.yml` derives its `no_enforce` set from per-entry `enforce_case`. So `classify`
emits a Term node per **distinct surface** (abbr, full, each match alias), carrying the entry's facets
(a multi-word `full` is auto-skipped by the single-token casing projector). `build-termbase` projects
the accept/casing/typos artifacts from the SKL Term catalog; `VistA.yml` (typo corrections) stays a
registry read (corrections are forbidden→preferred maps, not Term nodes). To avoid coupling the
repo-only termbase build (and the cross-repo `fileman-docs` `make termbase`) to a lake, the projection
**falls back to the registries when `knowledge.db` is absent**, and an **identity test proves
SKL-projection ≡ registry-projection** (the no-regression guarantee). The `fileman-docs` opt-in to the
lake-backed path is a later one-repo session (as S1.4 was).

**Build shape (S3.3 — refinements found while reading the live code/data).** The `merge` stage mirrors
`relate` (a post-`index` stage that augments `index.db` via `kernel.db.replace_table_atomic`, never
rebuilding it). It materializes three **merge-owned, consumer-facing** tables, reconciling on
`(type, canonical)` since index keys `fileman_file:200` and the SKL keys `fileman_file/200`:
- `entity_skl(entity_id PK, node_id, type, canonical, canonical_name)` — the colon↔slash join map +
  SKL identity, only for entities present in **both** DBs (view `v_entity_skl`).
- `entity_synonyms(node_id, surface, kind)` — every surface (canonical_name + synonyms) per SKL entity
  (view `v_entity_synonyms`).
- `chunk_entities(chunk_id, node_id)` — chunk→entity tags (view `v_chunk_entities`).

To keep `meta.read_schema_version` consistent and the views always present (no drift if a run stops
before `merge`), **`index` owns the empty table shells + the new views** (it is the `index.db` schema
owner); `merge` only *populates* them. This preserves D-S3.3a's decoupling — `index` gains **no**
dependency on `knowledge.db` and is **not** reordered after `resolve`; the shells are inert DDL.
Read contract → **v1.5** (additive: three new views + a `skl_entity_keying` capability); `index`
`contract_ver` bumps.

**Distinctive-surface safety (found in the real SKL):** common-word canonical names exist
(`fileman_file/1` = "FILE", `/19` = "OPTION", `/2` = "PATIENT"). Tagging/expanding on a bare common
word would be catastrophic noise. So both chunk-tagging and the S3.4 expansion use **distinctive
surfaces only** — file numbers (≥3 chars), globals (`^…`), and multi-word names — never a bare
single common word. The S3.4 expansion (`number → canonical_name` phrase) is naturally guarded twice:
`fts_match_query` already skips query tokens `<3` chars and expansion phrases of `<2` words, so
`1→"FILE"` is dropped while `200→"NEW PERSON"` survives.

### S4 — Semantic-fidelity gates ⬜
Turn the proposal §7 invariants into CI gates on the FileMan corpus.

| ID | Step | Detail | Gate |
|----|------|--------|------|
| S4.1 | Resolution + canonicalization gates | Fail on unresolved entity mentions, non-canonical term usage, forbidden synonyms | gates run in CI; FileMan corpus green |
| S4.2 | Relationship + provenance gates | Fail on dangling edges / missing provenance / missing `verified_on` where required by status/doc_type | deterministic graph + schema checks |
| S4.3 | Ambiguity/contradiction triage (advisory) | Surface ambiguous resolutions + conflicting facts to a curator queue — never auto-decided (§10) | candidate queue produced; human-gated |
| S4.4 | Meaning-aware coverage dashboard | Extend the strategy coverage dashboard with semantic metrics (% mentions resolved, edges valid, DD-facts verified) | dashboard line reproducible from committed harness |

### S5 — Generalize across the VDL ⬜
Prove the model holds at thousands of documents / millions of words.

| ID | Step | Detail | Gate |
|----|------|--------|------|
| S5.1 | Templatize the FileMan run | Extract the SKL kit (schema, resolve config, seed workflow, gates) | reusable kit documented |
| S5.2 | Walk the dependency graph | Point the kit at **Kernel** (then MailMan → clinical); catalog grows monotonically | Kernel SKL built; cross-package entities resolve; incremental cost confirmed (no global recompute) |

---

## Master tracker

| Phase | Outcome | Status |
|---|---|---|
| S0 | Model ratified; `knowledge.db` contract frozen | ✅ signed off 2026-06-17 (K1–K7 + Q1–Q6) |
| S1 | Vocabulary classified; casing fixed at source; `fileman-docs` Brand.yml deleted | ✅ done (vdocs + S1.4) |
| S2 | `resolve` stage + `knowledge.db` for FileMan | ✅ landed 2026-06-17 (21 entities, 23 terms, 111 edges, headline proven) |
| S3 | Termbase/glossary/cross-links/index projected from SKL; search vocab-mismatch fixed | 🟡 S3.3+S3.4+S3.1 done (entity-keyed index.db + search payoff + termbase ← SKL); S3.2 (glossary) next |
| S4 | Semantic-fidelity CI gates + meaning-aware dashboard | ⬜ |
| S5 | Templatized; proven on Kernel | ⬜ |

**Suggested order:** S0 → **S1 first** (quick win; unblocks `fileman-docs` and validates the projection
principle) → S2 → S3 (the search payoff) → S4 → S5.

---

## Risks

- **Scope creep into a rewrite.** The proposal is explicit that this is *re-centering*, not a green-field
  rebuild. *Mitigation:* keep the stages/kernel/orchestrator; only promote `resolve` and re-point
  projections. Edit this plan before changing code (house rule: "the plan is the bug report").
- **Catalog governance lag.** Human curation of entities/synonyms/relationships can become the
  bottleneck at VDL scale (Q5). *Mitigation:* AI proposes at scale under §10 guardrails; start with the
  live DD as an authoritative auto-seed (Q6) to minimize hand-curation.
- **Over-fitting synonymy to the golden set.** *Mitigation:* same as the search plan — expand the golden
  set before trusting expansion tuning; favor changes that help the *class* of vocabulary-mismatch
  query, not individual labels.
- **`verified_on` cost.** Live-system verification (Q2) ties into the FileMan POC `verify-docs` and the
  shared-lake/engine rule. *Mitigation:* defer live verification to S5 if it blocks S2 throughput; mark
  facts `unverified` rather than dropping them.

## Discoveries

- **(S3.3) D-S3.3b realized as merge-OWNED tables, not a column on `entities`.** The decision said
  "an `skl_node_id` column on `entities`", but the live `relate` precedent (a post-`index` stage that
  adds its OWN table via `replace_table_atomic` and *never* rewrites index's tables) is cleaner and
  more faithful to "additive": `merge` writes `entity_skl`/`entity_synonyms`/`chunk_entities` and
  leaves `entities` untouched. Same join power, zero risk to the existing `entities`/`v_entities`
  contract. `index` owns the empty shells + views so `meta.read_schema_version` is consistent even on
  an index-only run — and `index` takes **no** `knowledge.db` dependency (D-S3.3a preserved).
- **(S3.3) Only 6 of 21 SKL entities reconcile into `index.db` today.** `index`'s recognizer only
  emits a `fileman_file:<n>` when "file #<n>"-style context appears in gold; the SKL also seeds files
  the corpus names only by prose (e.g. `.11 INDEX`, `.402 INPUT TEMPLATE`). The merge augments where
  *both* DBs agree and no-ops otherwise (friction #3), so this is expected, not a bug — widening
  index recognition (or reconciling by name) is a later refinement, not S3.
- **(S3.4) The expansion is a *precision* lever that touches only number-vocabulary queries.** SKL
  expansion fires solely when a query token is a live file number (`200`). Natural-language queries
  almost never contain one, so it is a **no-op on the rest of the golden set** — the OFF→ON mean
  delta (0.313→0.328) is *entirely* the one DI query (0.131→0.406); nothing else moves. This is the
  opposite of the L1.3 hand-seeded glossary, which expanded acronyms to common words and regressed
  broadly. Decimal file numbers (`1.2`, `3.8`) are dropped from the map — FTS splits tokens on `.`,
  so they could never match (a dead, confusing entry otherwise).
- **(S3.4) The "0.395 baseline" is stale and not directly comparable — suspect the metric.** The
  recorded 0.3947 (`reports/baseline-phase0.json`) is the **dev lake** with the **5-query** starter
  set; the golden set was later grown to **19** (`925aefd`) without re-baselining. The valid,
  controlled measure is OFF vs ON on the *same* lake + set: lexical-only **0.313**, SKL expansion
  **0.328** (evidence: `reports/search-skl-s3.4-{off,on}.{md,json}` on `~/data/vdocs`). The gate is
  met on its own terms (the vocab-mismatch query lands, mean improves, no regression); the cross-set
  0.395 figure is recorded here as background, not as the comparison.
- **(S2.2) DD-seam decision: option (a), but cached as committed registry data — not a run-time live
  call.** The kickoff offered (a) live DD export, (b) hand-off YAML, (c) corpus-first. Taken: **(a)**
  — the live YDB-VistA DD (`vehu`) was exported read-only via `m vista exec` (the engine-stack-guard
  seam; the docker→engine binding verified working this session), but the export is **frozen into a
  committed, content-addressable registry** (`registries/entities/dd-seed.di.yaml`), so the `resolve`
  stage stays deterministic/offline at run time. The live system is the *seed source*, never a
  pipeline dependency (honors Q2/Q6 and decouples S2 throughput from shared-lake/live-engine ops).
  All 21 seeded FileMan files (file#→name→global) came straight from the authoritative DD — zero
  guessed identities.
- **(S2.2) Synonymy resolution needs two surface channels, not one.** The generic `entities_pure`
  recognizer extracts a `fileman_file` *number* (`file #200` → `200`) and a *bare* global (`^VA`),
  but the headline also needs the **prose name** (`the NEW PERSON file`) and the **full global root**
  (`^VA(200,`). So `resolve` layers a literal-surface scanner (an alternation over the seed's
  names/globals/synonyms) on top of the recognizer: numbers resolve via the recognizer's file-context
  (so a bare "200" never false-matches), names/globals/synonyms via the literal scan. The headline
  (`file #200` ↔ `NEW PERSON` ↔ `^VA(200,` → one id) needs *both* channels.
- **(S2.2) Boundary guards must be per-surface, applied only at alphanumeric edges.** A blanket
  `(?<![A-Za-z0-9])…(?![A-Za-z0-9])` around the surface alternation broke globals: the seed surface
  `^VA(200,` ends in a comma deliberately followed by subscripts, so a trailing alnum guard rejected
  `^VA(200,0)`. Fix: add the left guard only when the surface *starts* with an alnum and the right
  guard only when it *ends* with one (`_bounded`). Longest-first ordering makes the most specific
  surface win (`NEW PERSON file` over `NEW PERSON`).
- **(S2.4) Propose-only is enforced structurally, not by discipline.** The DI run recognizes ~5k
  mentions the seed can't resolve (bare globals like `^DIC`, routines, options). These are written to
  `reports/knowledge/proposals.json` as `status: proposed` candidates and **never** touch
  `knowledge.db` — the write path simply has no route from the queue to the store. A human curates
  them into the registry seed (status `approved`) before they can be asserted (§10 / Q5).
- **(S1.2) Vale grounds against its *own* embedded dict, not the system Hunspell.** `Vale.Spelling`
  uses `en_US-web.dic` bundled in the binary (`internal/spell/data/`, v3.15.1), **not**
  `/usr/share/hunspell/en_US.dic`. The two differ in ways that matter, so the wordlist is **vendored
  into the repo** (`registries/glossary/english-words.txt`, ~78k lowercased base forms) with a
  provenance header — committed, offline, diffable, no dependency on a go-module-cache layout
  (Rafael's call, 2026-06-17). The pure fn takes the word set as a param (stays pure); the loader
  reads the vendored file. **Refresh** by re-extracting from the installed Vale's `en_US-web.dic`.
- **(S1.2) The naive "lowercase ∈ dict → collides" rule is wrong in *both* directions.** `vista` and
  `mumps` *are* dictionary words, so the naive rule would veto `VistA` and break the headline
  Vista→VistA gate. The fix is a **brand-cased guard**: a term collides only if its lowercase is a
  dict word **and** it is not internal-capital typography (`surface != surface.capitalize()`).
  - Internal-capital brands (`VistA`, `FileMan`) → never collide → **enforced**.
  - All-caps acronyms whose lowercase is a word (`CAN`, `SITE`, `OR`, `IS`, `MUMPS`) → collide → spelling-accept only.
  - **Title-case common words** (`Site`, `Host`, `Map`, `Recall`) → collide too (caught only via the
    end-to-end Vale run — the first heuristic wrongly enforced `Site` and flagged ordinary "site").
- **(S1.2) Lowercasing folds in proper nouns — accepted as a conservative under-enforcement.** e.g.
  Vale's dict has `Tiu` (a deity); lowercased it vetoes the acronym `TIU`. The lowercase-only-base
  alternative *drops* `is`/`or` (stored capitalized but lowercase-accepted via affix flags) and would
  **reintroduce** the bug for `IS`. So the wordlist keeps **all** alphabetic base forms lowercased:
  conservative (a few acronyms like `TIU` go unenforced) but it **never** force-cases a real word.
- **(S1) Behavior change vs the hand-maintained `Brand.yml`:** `MUMPS` is no longer force-cased
  (`mumps` is a real medical word) — confirmed acceptable (Rafael, 2026-06-17). Net casing coverage:
  **6 hand-curated terms → 624 generated terms.**

## Changelog

- 2026-06-17 — **S3.1 landed — the termbase projects from the SKL.** `classify` (`resolve_pure`) now
  emits a Term node for **every** curated surface (abbr + full + each match alias) — the **483-surface
  superset** (was the ~23 seen in DI gold) — status `approved`, corpus provenance where seen else a
  `registry:` marker. `kernel/termbase.build_artifacts_from_terms` projects accept/Casing/typos from
  the SKL Term catalog; `termbase_artifacts(reg, knowledge_db=…)` reads `knowledge.db` when present,
  else the registries (the two are **byte-identical** — proven by an identity test that round-trips
  classify → knowledge.db → project, and confirmed on the real lake with `diff`). `build-termbase`
  passes `cfg.knowledge_db`; `resolve` `contract_ver` 1→2 (the population change forces a re-run).
  accept.txt = **1117 terms** (no regression). Cleaned two whitespace-junk registry aliases (`"AP "`,
  `"FM "`) so the data-as-source is clean (the "or-better" the gate allows). `make check` green (1051
  tests, 97.71%). **`fileman-docs` opt-in to the lake-backed termbase is a later one-repo session.**
- 2026-06-17 — **S3.3 + S3.4 landed — the SKL is folded into `index.db` and the search
  vocabulary-mismatch payoff is cashed.** S3.3 (`bcd4bd0`): a new post-`resolve` **`merge`** stage
  (D-S3.3a) augments `index.db` from `knowledge.db` **additively** (D-S3.3b) — `entity_skl` (the
  colon↔slash reconciliation on `(type, canonical)`), `entity_synonyms` (the surface catalog), and
  `chunk_entities` (chunk→entity tags), each written via `replace_table_atomic` (the `relate`
  pattern; index's own tables untouched). `index` owns the empty shells + the `v_*` views (read
  contract → **v1.5**, additive; `index` `contract_ver` 11→12) so the version is consistent before
  `merge` runs — `index` gains no `knowledge.db` dependency. On the real DI lake: **6 entities
  reconciled, 56 synonyms, 5786 chunk tags**. S3.4: `server/search` now derives query expansion from
  the SKL (`skl_expansions` ← `entity_skl`, on by default; the hand-seeded `glossary/expansions.yaml`
  path retired), so `200 → "NEW PERSON"`. Added a DI file#↔name golden query; on the 19-query set +
  main lake it goes **nDCG@10 0.131 → 0.406** (recall 0.5→1.0) and lifts the **mean 0.313 → 0.328** —
  deterministic, offline, zero-ML. See Discoveries for the additive-tables refinement, the
  distinctive-surface safety, and the baseline-provenance honesty note. `make check` green (1049
  tests, 97.76%).
- 2026-06-17 — **S2 landed — the `resolve` stage + `knowledge.db` are real.** TDD-first: the SKL node
  boundary types (`models/knowledge.py`: entity/term/relationship with identity + `provenance[]` +
  lifecycle + a `verification` block), the gold store I/O boundary (`kernel/knowledge_db.py`, schema
  v1.0, lossless round-trip), three `KNOWLEDGE_*` ArtifactContracts at `documents/gold/knowledge.db`
  (its own gold DB, Q4), and the `resolve` stage (`stages/resolve/`, pure cores in `resolve_pure.py`,
  thin `stage.py`, `vdocs resolve`). Recognize **shares** `index.entities_pure` (no fork); resolve is
  **data-driven** from the live-DD seed `registries/entities/dd-seed.di.yaml` (Q6, option (a) frozen
  to committed data); classify folds the S1 term facets (`kernel.products` + `kernel.casing_pure`);
  relate emits only the closed registered edge set (`registries/relationships/edge-types.yaml`, Q3);
  verify stamps every node `asserted` (Q2). **Proven on the real DI gold:** the headline holds
  (`file #200` ↔ `NEW PERSON` ↔ `^VA(200,` → one `fileman_file/200`), 21 FileMan files resolved,
  23 terms classified, 111 `documented-in` edges, 0 rejected edges, 4954 propose-only candidates
  (none asserted). `make check` green (1035 tests, 97.78% cov). See Discoveries for the DD-seam
  decision + the two-channel synonymy / boundary-guard gotchas.
- 2026-06-17 — **S0 signed off — model ratified; S2 unblocked.** Resolved proposal §13: K1–K7
  recommendations adopted (K2: embeddings stay fully parked); Q1–Q6 decided with rationale (see
  Decisions under S0). Headlines: entity seeds = **live DD spine + corpus synonyms** (Q6); `verified_on`
  **deferred to S5, schema-ready** (Q2); **two DBs joined, merged into `index.db` at publish** (Q4);
  relationship taxonomy = **closed starter set + gated `discover`** (Q3); Concepts scoped **out of S2**
  (Q1); Rafael = sole curator (Q5). The SKL node schema + `knowledge.db` gold contract are now policy.
- 2026-06-17 — **S1.4 landed — S1 done end-to-end.** `fileman-docs` `f89977d`: deleted the
  hand-maintained `.vale/VistA/Brand.yml`, wired the generated `Casing.yml` (624 case-safe terms) into
  `make termbase`, refreshed the four artifacts. `make gate` green (7/7). Invariants proven via Vale:
  `Vista→VistA` + `Fileman→FileMan` still bite, common-word prose ("can run it on or off site; it is an
  option") = zero casing errors, coverage spans `PIMS`/`CPRS`/`KIDS`, `Mumps→MUMPS` deliberately not
  enforced. `Vale.Terms = NO` **kept** (justified empirically — accept.txt's English-colliding acronyms
  force-cap prose when Vale.Terms is on; `Casing.yml` is the precise enforcer). Zero hand-maintained
  vocab remains in `fileman-docs`.
- 2026-06-17 — **S1 (vdocs half) landed.** TDD-first: `kernel/casing_pure.py`
  (`collides_with_english` + `selective_casing_swap`, pure, 100% cov), Term-classification facets +
  fail-loud validation in `kernel/products.py`, new `Casing.yml` projection in `kernel/termbase.py`,
  vendored `registries/glossary/english-words.txt`. `make check` green (1006 tests, 97.9% cov). End-to-end
  Vale proof against the real generated artifacts: Vista/Fileman miscasings flagged, ordinary
  can/or/site/option/item untouched. S1.4 (fileman-docs `Brand.yml`/`Vale.Terms = NO` deletion) handed
  off to a separate one-repo session. Grounding open questions validated — see Discoveries.
- 2026-06-16 — **Tracker opened.** Mirrors the proposal's S0–S5. Status: not started, pending sign-off
  of the proposal §13 open questions. S1 flagged as the self-contained quick win that retires the
  `fileman-docs` casing workaround at the source.
