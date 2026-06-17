# Semantic Knowledge Layer — Implementation Plan & Tracker

> **The *what/why* lives in** [`skl-proposal.md`](skl-proposal.md)
> (the pivot, the data model, the reconciliation with the 2026-06-08 reset, the decision table). This
> document is the *how/status* tracker: detailed S0–S5 steps, per-phase gates, and a per-phase
> changelog/discoveries/risks log. **Update it as work lands** (TDD → `make check` → update tracker →
> commit, per step — the house cadence).

> **Status: S1 landed (2026-06-17); S2+ pending proposal sign-off (proposal §13 open questions, esp.
> K2/Q6).** Do not begin S2+ until S0 ratifies the schema. S1 (the self-contained casing quick win)
> is **done** — facet schema blessed, casing bug fixed at the source. S1.4 (the `fileman-docs` repo
> half) is handed off to a separate session (see `docs/prompts/skl-s1.4-fileman-docs-kickoff.md`).

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

### S0 — Ratify the model ⬜
Settle the proposal §13 decision table and open questions; freeze the SKL node schema and the
`knowledge.db` gold contract as program policy.

| ID | Step | Detail | Gate |
|----|------|--------|------|
| S0.1 | Sign off the data model | Ratify entity/term/concept/relationship + identity/provenance/lifecycle fields (proposal §5) | schema agreed; written into this tracker |
| S0.2 | Resolve K2 / Q6 | Confirm "symbolic honors the embedding reset" framing (K2); decide entity seed source — live DD/KIDS vs corpus-mined vs both (Q6) | decisions recorded with rationale |
| S0.3 | Fix the relationship taxonomy | Closed starter edge set (`reads`/`runs-on`/`documented-in`/`synonym-of`/`miscapitalization-of`/…) vs `discover`-proposed (Q3) | edge-type registry shape agreed |

### S1 — Classify the vocabulary; fix the casing bug at the source 🟡 (vdocs half ✅; S1.4 handoff)
Self-contained quick win (proposal §12 S1) — the smallest proof that "everything is a projection"
works, and the deletion of the `fileman-docs` workaround. Does **not** require `knowledge.db` yet; it
extends the existing termbase projection.

| ID | Step | Detail | Gate | Status |
|----|------|--------|------|--------|
| S1.1 | Add Term classification facets | Extend the product registry with `class` / `canonical_casing` / `enforce_case` / `expand_on_first_use` (proposal §5); validate on load (fail-loud on wrong type) | facets present + schema-validated; TDD on the loader | ✅ `kernel/products.py` |
| S1.2 | Auto-derive `collides_with_english` | Pure transform: a term collides iff lowercase ∈ the dict **Vale's own speller consults** AND it is not brand-cased (internal-capital). Vendored wordlist from Vale `en_US-web.dic` (proposal §7) | pure-fn unit-tested incl. CAN/SITE/AN/OR/IS + Title-case (Site/Host/Map) + brands; no human collision-guessing | ✅ `kernel/casing_pure.py` |
| S1.3 | `build-termbase` emits selective casing | Project casing enforcement **only** for `enforce_case && !collides_with_english` single-token terms (new `Casing.yml` Vale style); accept.txt still whitelists all spellings | regenerated Vale style enforces brand casing, ignores colliding acronyms — **624 terms enforced**; E2E Vale proof: Vista→VistA bites, ordinary "can/or/site" untouched | ✅ `kernel/termbase.py` |
| S1.4 | Retire the `fileman-docs` workaround | Re-run `build-termbase --out-dir` into `fileman-docs`; **delete `.vale/VistA/Brand.yml` + `Vale.Terms = NO`**; `make gate` stays green; the `Vista→VistA` break-test still bites | fileman-docs gate green with zero hand-maintained vocab; casing coverage ≫ 6 terms | ⬜ **handed off** → `docs/prompts/skl-s1.4-fileman-docs-kickoff.md` |

*TDD: `collides_with_english` and the selective-casing projector are pure functions tested first; the
`fileman-docs` re-run (S1.4) is the integration proof (a one-repo-per-session handoff).*

### S2 — Formalize the SKL + the `resolve` stage (FileMan) ⬜
Promote semantic resolution to a named DAG layer producing `knowledge.db` for the `DI` gold (proposal
§6). Re-centering, not rewrite — elevate `enrich`+`entities`+`relate`.

| ID | Step | Detail | Gate |
|----|------|--------|------|
| S2.1 | `knowledge.db` ArtifactContract | Define the gold contract (schema for entity/term/concept/relationship + provenance/lifecycle); decide one-db-vs-join with `index.db` (Q4) | contract + Pydantic boundary types; orchestrator wires it |
| S2.2 | `resolve` stage — recognize → resolve | Lift `entities_pure` recognition; add synonymy resolution to canonical entity ids (`file #200`/"NEW PERSON"/`^VA(200,` → `fileman_file/200`) | pure-fn tests; resolution table data-driven from registries |
| S2.3 | `resolve` stage — classify → relate → verify | Fold S1 term classification in; emit typed relationships; mark DD-checkable facts `verified_on` (Q2: live `vehu`/`foia-t12` now or defer) | `knowledge.db` populated for DI gold; relationships typed + provenanced |
| S2.4 | Seed the catalog (AI-proposed, human-curated) | Candidate entities/synonyms/concepts from registries + AI proposal under the §10 guardrails (propose-only, grounded, adversarial-triaged) | curator-approved seed; every node cites provenance |

*TDD: each `resolve` sub-transform is a pure function tested before the `stage.py` driver; integration
test on a seeded gold slice.*

### S3 — Re-point the projections ⬜
Make every downstream artifact a view of the SKL (proposal §6, §8).

| ID | Step | Detail | Gate |
|----|------|--------|------|
| S3.1 | Termbase ← SKL | `build-termbase` reads Term nodes from the SKL instead of raw registries | termbase regenerates identically-or-better; tenet-13 single-source preserved |
| S3.2 | Glossary + cross-links ← SKL | Generate `gold/glossary.md` and in-corpus cross-links from entities/synonyms/relationships | glossary non-empty + drift-gated; links resolve (lychee/strict-build) |
| S3.3 | Entity-keyed `index.db` | `index` tags chunks with resolved entity ids + synonym-expansion data from the SKL | chunk about file #200 retrievable by `#200`/"NEW PERSON"/`^VA(200,` |
| S3.4 | Search wins (the precursor payoff) | Wire SKL synonym data into `fts_match_query` expansion (replaces empty-glossary L1.3) | KAAJEE nDCG@10 > 0; mean nDCG@10 beats 0.395 baseline; recorded via `baseline_golden.py` |

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
| S0 | Model ratified; `knowledge.db` contract frozen | ⬜ |
| S1 | Vocabulary classified; casing fixed at source; `fileman-docs` Brand.yml deleted | 🟡 vdocs ✅ / S1.4 handoff |
| S2 | `resolve` stage + `knowledge.db` for FileMan | ⬜ |
| S3 | Termbase/glossary/cross-links/index projected from SKL; search vocab-mismatch fixed | ⬜ |
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
