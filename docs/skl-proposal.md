# Proposal — Meaning-first: the VistA Semantic Knowledge Layer as the spine of corpus quality

**Status:** proposal / for sign-off. **Date:** 2026-06-16. **Author:** Claude (Opus 4.8) with Rafael.
**Scope:** a program-wide pivot in *what `vdocs` produces and gates* — from a clean string corpus to a
**governed model of meaning** from which the corpus, its quality gates, and its search index are all
*projected*. Touches the pipeline DAG, the registries, the termbase, the search index, and the
docs-as-code gate.
**Sits under:** [`vdl-content-quality-and-ia-strategy.md`](vdl-content-quality-and-ia-strategy.md)
(the editorial standard — this deepens its §6 controlled-vocabulary and §9 gate into a semantic layer).
**Relates to:** [`offline-lexical-search-plan.md`](offline-lexical-search-plan.md) (this is the
*precursor* that fixes its #1 quality failure — vocabulary mismatch),
[`docs-as-code-master-publication-proposal.md`](docs-as-code-master-publication-proposal.md) (the
delivery machine this feeds), and the `fileman-docs` repo (whose `Brand.yml`/`Vale.Terms = NO`
workaround is the leaf symptom that motivated this — see §1).

> **The thesis in one line.** The corpus is currently modeled as **strings**; quality, consistency,
> and meaningful search are impossible to enforce on strings at the scale of the whole VDL (thousands
> of documents, millions of words). The pivot is to make **meaning a first-class, governed,
> single-sourced data layer** — a symbolic VistA knowledge model, grounded in the system's own
> authoritative identifiers — and to **derive every artifact from it**: the termbase, the glossary,
> the cross-references, the search index, and the docs-as-code gate. *Fix meaning at the source;
> generate everything downstream.* This is the centerpiece of quality and the substrate every later
> capability (search, indexing, ranking) stands on.

## Table of contents

- [1. The trigger — a casing bug that is really a category error](#1-the-trigger--a-casing-bug-that-is-really-a-category-error)
- [2. The reframe — quality is a property of meaning, not of strings](#2-the-reframe--quality-is-a-property-of-meaning-not-of-strings)
- [3. Why symbolic-and-grounded — and why this *respects* the 2026-06-08 reset](#3-why-symbolic-and-grounded--and-why-this-respects-the-2026-06-08-reset)
- [4. We are already ~20% there — the existing seeds](#4-we-are-already-20-there--the-existing-seeds)
- [5. The data model — the VistA knowledge graph](#5-the-data-model--the-vista-knowledge-graph)
- [6. The pipeline refactor — a semantic-resolution layer in the lake](#6-the-pipeline-refactor--a-semantic-resolution-layer-in-the-lake)
- [7. Quality, redefined — semantic-fidelity invariants the gate enforces](#7-quality-redefined--semantic-fidelity-invariants-the-gate-enforces)
- [8. The payoff for search & indexing — meaning closes the vocabulary-mismatch gap](#8-the-payoff-for-search--indexing--meaning-closes-the-vocabulary-mismatch-gap)
- [9. Scale & cost — why this holds at millions of words](#9-scale--cost--why-this-holds-at-millions-of-words)
- [10. AI's role, safely — extend the §10 layering to meaning](#10-ais-role-safely--extend-the-10-layering-to-meaning)
- [11. How it composes with the existing program](#11-how-it-composes-with-the-existing-program)
- [12. Phased plan — no big bang](#12-phased-plan--no-big-bang)
- [13. Decision table & open questions](#13-decision-table--open-questions)
- [14. Sources & cross-references](#14-sources--cross-references)

---

## 1. The trigger — a casing bug that is really a category error

Standing up the `fileman-docs` quality gate (impl-plan L0b) surfaced a small failure with a large
cause. `vdocs build-termbase` compiles the curated registries into Vale config; its `accept.txt`
correctly whitelists ~1,117 approved VistA terms. But Vale's vocabulary mechanism does two jobs from
one flat list: it accepts those terms *as spellings* **and** enforces their *exact capitalization*
everywhere. The term list contains acronyms that collide with ordinary English words — `CAN`, `SITE`,
`AN`, `OR`, `IS` — so the gate began demanding "use `CAN`" every time a sentence contained the word
"can." On the placeholder page this was noise; across millions of words it makes the prose gate
**unusable**.

The leaf fix in `fileman-docs` was a retreat: disable the blanket case-enforcement (`Vale.Terms = NO`,
keeping only spelling acceptance) and re-add casing for a handful of brand terms via a *hand-maintained*
`.vale/VistA/Brand.yml`. That works, but it is exactly the anti-pattern this program exists to kill: a
**hand-curated parallel list** that violates single-sourcing (tenet #13), enforces casing for ~6 terms
instead of the full safe set, and silently drifts from the registries.

The root cause is not Vale and not the casing rule. **It is that the vocabulary is modeled as a flat
list of strings with no notion of what each string *means*.** `accept.txt` cannot tell a brand
(`VistA` — capitalization is load-bearing) from an English-colliding acronym (`CAN` — capitalization is
meaningless) because the data carries no such distinction. Every downstream tool inherits that
poverty. The casing bug is the first visible crack in a foundation that treats meaning as absent.

## 2. The reframe — quality is a property of meaning, not of strings

The strategy doc already won the argument that VDL modernization is a **content-quality** program, not
a format migration (its 80/20 thesis), and it named the cure for terminology drift: a controlled
vocabulary compiled into gate rules (§6/§9). This proposal takes the next, larger step the casing bug
forces into the open:

> A controlled vocabulary is not a list of approved strings. It is the **surface of a model of the
> domain.** "VistA," "FileMan file #200," "the NEW PERSON file," "`^VA(200,`," and "`$$GET1^DIQ`" are
> not strings to be spell-checked — they are **references to entities** with identity, canonical names,
> synonyms, relationships, and provenance. Quality means those references *resolve* and stay
> *consistent*; meaningful search means a query *resolves to the same entities*; meaningful indexing
> means the index is keyed to *entities and relationships*, not bytes.

Almost every quality defect the strategy doc catalogs is, at root, a **meaning** defect that no
string-level transform can fix:

| Strategy-doc defect | What it actually is, in meaning terms |
|---|---|
| **D-1 redundancy/overlap** | the *same concept* described in many places — a meaning identity the strings don't carry |
| **D-3 terminology drift** | one *entity/concept* named many ways across two decades — unresolved synonymy |
| broken cross-references | a *relationship* between two entities that the link text fails to encode |
| the search "vocabulary mismatch" failure (§8) | the query names an *entity* by a word the matching doc never spells |

You cannot gate, dedupe, link, or search *meaning* you have not *modeled*. So the program needs a
first-class, governed, single-sourced **Semantic Knowledge Layer (SKL)** — a model of VistA's entities,
terms, concepts, and relationships — sitting in the gold tier of the lake, **and every other artifact
becomes a projection of it**: the Vale/typos termbase, the rendered glossary, the in-corpus
cross-links, the search index, the front-matter, the coverage dashboard. One model of meaning; many
generated views. That is the same "discovery is data, not code" philosophy (tenet #13) raised from
*patterns* to *meaning*, and the same "fix at the source, generate downstream" principle that makes any
of this maintainable at VDL scale.

## 3. Why symbolic-and-grounded — and why this *respects* the 2026-06-08 reset

The instinctive reading of "semantics is the centerpiece" is "bring back embeddings/vectors." **It is
not, and this proposal is careful not to reverse the direction reset.** The reset (2026-06-08) parked
the embedding/vector + MCP path after a spike proved it *not worth its cost on this corpus*: OOM via
ONNX fan-out, a full re-embed on every doc change, opaque relevance, all-or-nothing. That finding
stands. Crucially, it is an argument *for* the path proposed here, not against it.

There are two ways to get "meaning" into a system, and they are not the same thing:

| | **Statistical / induced** (the parked path) | **Symbolic / grounded** (this proposal) |
|---|---|---|
| How meaning is obtained | *induce* it from text via embeddings — a model guesses latent similarity | *assert* it as governed data, keyed to real identifiers |
| Fit for an **upstream-uncontrolled** corpus | poor — re-embed on every change; drift is invisible | strong — the model is *ours*, versioned, diffable |
| Auditability for a **VA-authoritative** source | low — relevance is a black box | high — every node cites where it was asserted/verified |
| Cost at millions of words | high, recurring (re-embed) | low, incremental (resolve-on-change) |
| Determinism / offline / zero-ML | no | **yes** — pure lookups; matches the house posture |

The decisive fact is that **VistA is not an unstructured domain.** Unlike generic prose, its meaning is
*enumerable and authoritative*: packages and namespaces, FileMan files (by number), fields, globals
(`^DD`, `^DIC`, `^VA`), routines, RPCs, options, security keys, HL7 segments, KIDS builds, DBIA
agreements. These are **real entities with real identity and real relationships**, documented in the
very corpus we process and derivable from the live system (the data dictionary, the routine source).
The right way to model meaning here is therefore **explicit, symbolic, and grounded in the system's own
identifiers** — a controlled knowledge base — not a statistical approximation of it. This is cheaper,
auditable, incremental, deterministic, and it cannot *hallucinate* meaning into an authoritative VA
source (the §10 hazard).

Embeddings are not forbidden forever; they are *relegated to their correct place* — an **optional, late,
grounded top-layer** that could one day add fuzzy recall *on top of* a resolved entity index, never the
foundation and never a dependency. The foundation is symbolic. (This also keeps the search deliverable
zero-ML and portable, per the active search plan's definition of done.)

## 4. We are already ~20% there — the existing seeds

This is a pivot in *emphasis and elevation*, not a green-field build. The mechanical 20% the strategy
doc credits the pipeline with includes the **embryo of the SKL**, already shaped correctly:

- **`registries/entities/entities.yaml`** already models typed VistA entities — `build`, `global`,
  `fileman_file`, `routine`, … — each with a recognizer (regex/literal), a **canonical-id rule**, a
  `status` lifecycle (`approved`/proposed), and provenance notes. It is already keyed the way an entity
  catalog should be: `(type, canonical-name)`.
- **`index.db:entities`** already exists — the `index` stage's generic `entities_pure` recognizer
  writes entity rows keyed by that stable id (§5.5). A symbolic entity catalog is *already being built*;
  it is just under-modeled (no relationships, no synonymy, no per-term classification) and
  under-exploited (it doesn't drive the termbase, the glossary, the gate, or ranking).
- **`build-termbase`** is **already a projection** — it compiles `product-names` + `typo-corrections` +
  `glossary/expansions` into gate config with "a registry edit re-flows with no copy-paste (tenet
  #13)." The architecture this proposal wants (termbase = thin view over the knowledge layer) is
  already true *in miniature*; we generalize it.
- **`relate` and `enrich` stages** already exist as the natural homes for relationship and
  entity-mention work.
- **The glossary registry is empty** and the search plan's L1.3 (synonym/acronym expansion) has *no
  data to run on* — a gap the SKL fills systematically rather than by hand-seeding "known cases."

So the pivot is: **elevate these seeds from scattered helpers into one governed model**, give it a real
schema (relationships, synonymy, classification, provenance, lifecycle), make it the gold-tier spine,
and re-point the projections (termbase, glossary, cross-links, index, gate) at it.

## 5. The data model — the VistA knowledge graph

The SKL is a small, typed, versioned graph. Four node kinds, every node carrying **identity,
provenance, and lifecycle** (the non-negotiables for an authoritative corpus):

1. **Entity** — a thing in VistA with stable identity. `id = (type, canonical)` (e.g.
   `fileman_file/200`, `routine/DIQ`, `package/XU`, `global/^DIC`, `option/XUMAINT`, `rpc/ORWU GET`).
   Carries: `canonical_name` (the human name, e.g. file #200 → "NEW PERSON"), `synonyms[]` (resolved
   aliases), `type`, `status` (`approved|proposed|deprecated`), `provenance[]` (where asserted; and for
   facts checkable against the live system, `verified_on`).
2. **Term** — a *naming* of an entity or concept as it appears in prose, with the **classification
   facets** the casing bug demanded: `class` (`brand|acronym|file-name|command|common-collision|…`),
   `canonical_casing`, `enforce_case` (bool), `collides_with_english` (bool, *auto-derived* — see §7),
   `expand_on_first_use`. The termbase is a projection of Term nodes; the casing fix is *one facet of
   one node kind*.
3. **Concept** — an explanation-level idea that is not a system object ("file access security," "the
   ScreenMan form/block/field model"). Concepts own the single-sourced `concepts/` topics and are what
   D-1 dedupe resolves against ("these five passages are the same Concept").
4. **Relationship** — a typed, directed, **provenanced** edge: `routine/DIQ —reads→ fileman_file/200`,
   `option/XUMAINT —runs-on→ package/XU`, `concept/file-security —documented-in→ topic/use/...`,
   `term "Vista" —miscapitalization-of→ term "VistA"`. Relationships are the cross-references, the
   crosswalk (old→new), and the search graph — all the same edges, viewed differently.

```yaml
# Illustrative SKL node (gold/knowledge/…), single-sourced; projections are generated from it.
- kind: entity
  id: fileman_file/200
  type: fileman_file
  canonical_name: "NEW PERSON"
  synonyms: ["NEW PERSON file", "file #200", "^VA(200,", "the 200 file"]
  status: approved
  provenance:
    - {source_sha256: "…", doc: "fm22_2tm", section: "global-map"}
  verified_on: {system: "vehu", date: "2026-06-15"}     # checkable against the live DD
- kind: term
  id: term/VistA
  surface: "VistA"
  class: brand
  enforce_case: true          # → emitted as a Vale casing substitution
  collides_with_english: false
- kind: term
  id: term/CAN
  surface: "CAN"
  class: acronym
  enforce_case: false         # English-colliding → spelling-accept only; NEVER force-cased
  collides_with_english: true # auto-derived against the Hunspell dictionary (§7)
```

Storage follows the house grain: human-curated **seeds and overrides** stay in version-controlled
`registries/` (diffable, CODEOWNER-routed); the **resolved, corpus-wide graph** materializes in the
gold tier as `knowledge.db` (SQLite, the same portable contract as `index.db`) plus a human-readable
`gold/knowledge/*.yaml` projection for review. The registry is the *intent*; `knowledge.db` is the
*resolved truth*; `discover` proposes additions through the existing §9.6 gate (tenet #13, now applied
to meaning).

## 6. The pipeline refactor — a semantic-resolution layer in the lake

Today entity work is a side-effect smeared across `enrich`, `index/entities_pure`, and `relate`. The
pivot makes **semantic resolution a named layer** of the medallion DAG, producing a first-class gold
artifact that the rest of the pipeline consumes:

```
 bronze ─ silver(convert·enrich·normalize) ─ consolidate ──▶  [ RESOLVE ]  ──▶ gold
                                                                  │              ├─ knowledge.db  (the SKL: entities·terms·concepts·relationships)
   recognize → resolve(synonymy) → classify → relate → verify    │              ├─ consolidated/  (entity-tagged, cross-linked topics)
                                                                  ▼              └─ glossary.md   (projection)
                                          registries/ (curated seed + override) ─┘     │
                                                                                       ▼  derived, never hand-maintained:
                                          termbase (Vale/typos) · cross-links · index.db (entity-keyed) · front-matter · coverage dashboard
```

Concretely, this reshapes the DAG without abandoning the spine discipline (§17 phased build; pure
`*_pure.py` cores; thin `stage.py` drivers; `ArtifactContract`s):

- **Promote a `resolve` stage** (consolidating/elevating today's `enrich`+`entities`+`relate`) that
  runs after `consolidate` and emits `knowledge.db`. Its pure sub-transforms: **recognize** entity
  mentions (today's `entities_pure`), **resolve** them to canonical entities including synonymy,
  **classify** terms (the casing/collision facets), **relate** (typed edges), **verify** (mark facts
  checkable against the live DD/source as `verified_on`).
- **Re-point `index` at the SKL** — `index.db` gains entity tags, synonym-expansion data, and
  relationship facets per chunk (§8), instead of re-recognizing entities in isolation.
- **Re-point `build-termbase`, the glossary, and the crosswalk** to *read from the SKL* rather than
  raw registries — `build-termbase` becomes a thin projection of Term nodes (and now emits casing
  enforcement *only* for `enforce_case` terms, deleting `Brand.yml` and `Vale.Terms = NO`).
- **`consolidate`/`publish`** consume resolved entities to insert cross-links and single-source by
  Concept identity (the structural cure for D-1).

"Complete refactoring of the pipeline" is acceptable per the user's mandate, but the honest scope is
**re-centering, not rewrite**: the stages, kernel, orchestrator, and registries stay; what changes is
that meaning stops being a scattered side-effect and becomes the gold artifact everything derives from.
Per house rule, propose it by editing the plan first — this doc — then build TDD-first against the new
`ArtifactContract` for `knowledge.db`.

## 7. Quality, redefined — semantic-fidelity invariants the gate enforces

Today's gate (strategy §9) checks that strings are *well-formed*: spelling, casing, links, headings,
a11y. The SKL lets the gate check that meaning is *coherent* — corpus-wide invariants that scale to
thousands of documents because they are checks against a model, not a reviewer's memory:

| New gate dimension | Invariant it enforces | Why it scales |
|---|---|---|
| **Entity-resolution coverage** | every recognized mention resolves to a known entity (no orphan `file #9999`) | a join against `knowledge.db`, O(mentions) |
| **Term canonicalization** | every Term used in its `canonical_casing`; forbidden synonyms flagged | projection → Vale substitutions, generated |
| **Casing classification correctness** | `collides_with_english` is **auto-derived** (lowercase the surface; if it's a real word in the same Hunspell dict Vale ships, it cannot be force-cased) — no human guesses which acronyms collide | mechanical; self-maintaining as the catalog grows |
| **Relationship integrity** | every cross-reference is a real edge between real entities; no dangling | graph validation, deterministic |
| **Provenance completeness** | every asserted fact cites a source; `verified_on` present where required by `status`/`doc_type` | front-matter + node schema check |
| **Concept single-sourcing** | no Concept defined in two places (D-1); duplicate passages flagged to a curator | similarity against Concept nodes |
| **Ambiguity / contradiction flags** | a surface resolving to two entities, or two nodes asserting conflicting facts → curator queue (advisory, never auto-decided, §10) | candidate generation at scale; human decides |

This is the precise upgrade the casing bug asked for: **the gate stops enforcing strings it doesn't
understand and starts enforcing meaning it does.** "Quality" becomes falsifiable in semantic terms —
*"FileMan: 100% of entity mentions resolved, 0 unknown entities, 0 forbidden synonyms, 142/142
relationships valid, 318/318 DD-facts verified on vehu"* — a stronger claim than "0 Vale errors."

## 8. The payoff for search & indexing — meaning closes the vocabulary-mismatch gap

The user's framing — the semantic layer is "a precursor for any meaningful search or indexing" — is
exactly right, and the active search plan already names the symptom it cures. That plan's headline
failure is **vocabulary mismatch**: the KAAJEE query scores **nDCG@10 = 0.0** because the
doc-defining token lives in the title, not the body; its L1.3 lever (synonym/acronym expansion) is
"data-driven from `registries/glossary`" which is **empty**. These are not three small bugs; they are
one fact: **lexical FTS matches strings, but readers and queries refer to *entities*.**

A query for "file 200" must find a page that only ever says "the NEW PERSON file." A query for "KAAJEE"
must find the install procedure whose body never repeats the acronym. The link between those surfaces
is a *synonym relationship in the SKL* — it does not exist in the text. With the SKL:

- **Entity-resolved indexing** — `index.db` chunks carry resolved entity tags, so a chunk *about* file
  #200 is retrievable by `#200`, `NEW PERSON`, or `^VA(200,` regardless of which it spells. This is the
  principled fix for vocabulary mismatch, where L1.2/L1.3 are stopgaps.
- **Generated synonym expansion** — the search plan's expansion table is *generated from Term
  synonyms*, not hand-seeded; it grows with the catalog and stays consistent with the gate's
  terminology rules (one source, both consumers).
- **Faceted / relationship retrieval** — "options that run on XU," "routines that read file #200"
  become answerable because the edges exist. This is the difference between *finding pages* and
  *answering questions* — and it is the substrate any future ranking (or that optional, grounded
  embedding top-layer, §3) would stand on.

All of it stays **deterministic, offline, and zero-ML**, honoring the search plan's definition of done
and the direction reset. Meaning makes lexical search *better*, on its own terms, without a model.

## 9. Scale & cost — why this holds at millions of words

The embedding path failed on cost: re-embed the world on every change. The SKL is built for the
opposite cost curve, which is the whole reason it scales to the full VDL:

- **Incremental by construction.** The entity/term/concept catalog grows **monotonically** and is
  governed; adding or changing one document re-resolves *only that document* against a stable catalog
  (a lookup), not a global recompute. Content-addressing (already in the lake) means unchanged docs are
  untouched.
- **Linear, cacheable extraction.** Recognition is regex/literal matching (already in `entities_pure`);
  resolution is a dictionary lookup; classification is a Hunspell check. No quadratic similarity, no
  GPU, no OOM fan-out.
- **The model is small even when the corpus is huge.** VistA's entity space is bounded (a few hundred
  packages, a few thousand files/routines/options of interest) even though the prose is millions of
  words. The expensive thing (meaning) is *small and reusable*; the cheap thing (matching) is what
  scales with text.
- **Diffable and reviewable.** Because the SKL is versioned data, a 50-package expansion is a series of
  reviewable PRs against `registries/` + regenerated `knowledge.db`, not an opaque re-index. This is
  what lets a risk-averse VA trust it.

## 10. AI's role, safely — extend the §10 layering to meaning

The SKL is where AI earns its keep *and* where it is most dangerous, so the strategy's §10 layering
(machine → AI-advisory-human-gated → human-authority) applies verbatim, now to meaning:

- **AI proposes, determinism resolves, humans authorize.** AI is excellent at *candidate generation* at
  scale — "these 40 surfaces look like synonyms of file #200," "this passage asserts a routine→file
  relationship," "these two sections define the same Concept." It is **never** allowed to *assert* a
  node or edge into `knowledge.db` unreviewed — that would launder a hallucinated relationship into an
  authoritative VA source, the §10 hazard at its worst.
- **Grounding beats fluency.** Every AI-proposed fact must cite a corpus location (provenance) or be
  checkable against the live system (`verified_on`); ungrounded assertions are rejected, not merged.
- **Adversarial verification is triage, not authority.** A second agent refutes each proposed edge to
  rank the curator's queue; LLM-as-judge filters, it never closes the loop (one token can fool it).
- **The deterministic gates (§7) run on AI output too** before any human sees it.

AI does the *scale* (no human reads millions of words to find every synonym); determinism does the
*resolution*; humans own the *authority*. The SKL makes that division enforceable because every node
records *who/what asserted it and on what evidence*.

## 11. How it composes with the existing program

This proposal does not compete with the four existing docs; it supplies the layer they all assumed but
none owns:

- **Under the content-quality strategy.** It is the concrete realization of strategy §6 (controlled
  vocabulary) and §9 (gates), deepened from "approved strings" to "a model of meaning." It does not
  change the Diátaxis IA, the topic-based chunking, or the GitHub-legible-subset rules — it makes them
  *enforceable on meaning*.
- **Feeds the master-publication machine.** `publish` consumes resolved entities to insert cross-links
  and single-source by Concept; the crosswalk (old→new) becomes a *view of Relationship edges*.
- **Fixes the `fileman-docs` leak.** `Brand.yml` and `Vale.Terms = NO` are deleted the moment
  `build-termbase` projects from classified Term nodes (§12 S1). The docs-as-code gate inherits the
  semantic-fidelity dimensions (§7).
- **Is the precursor the search plan needs.** It supplies the entity tags and synonym data that fix
  vocabulary mismatch (§8) — turning L1.2/L1.3 stopgaps into a principled capability — while keeping
  the deliverable zero-ML and offline.

## 12. Phased plan — no big bang

Additive, TDD-first, each phase independently shippable, mirroring the Diátaxis/medallion "continuously
shippable" cadence. The early phases pay for themselves immediately (they unblock `fileman-docs` and
the search plan) before the corpus-wide work.

- **S0 — ratify the model (this doc).** Settle §13. Adopt the SKL node schema (entity/term/concept/
  relationship + identity/provenance/lifecycle) and the `knowledge.db` gold contract as program policy.
- **S1 — classify the vocabulary; fix the casing bug at the source.** Add the Term classification facets
  to the product/term registries; auto-derive `collides_with_english` against the Hunspell dict; make
  `build-termbase` emit casing enforcement only for `enforce_case` terms. **Deliverable:** delete
  `fileman-docs` `Brand.yml` + `Vale.Terms = NO`; casing coverage jumps from ~6 terms to the full safe
  set. *This is the smallest possible proof that "everything is a projection" works.*
- **S2 — formalize the SKL + `resolve` stage on FileMan.** Promote `resolve` (recognize→resolve→
  classify→relate→verify) producing `knowledge.db` for the `DI` gold; seed entities/synonyms/concepts
  from the existing registries + AI-proposed-human-curated candidates (§10).
- **S3 — re-point the projections.** Generate the termbase, glossary, cross-links, and an
  **entity-keyed `index.db`** from the SKL. **Deliverable:** the KAAJEE/`file #200` vocabulary-mismatch
  queries beat the 0.395 baseline via entity resolution (search plan L1, done right).
- **S4 — semantic-fidelity gates.** Turn the §7 invariants into CI gates (entity-resolution coverage,
  term canonicalization, relationship integrity, provenance completeness) on the FileMan corpus; ship
  the meaning-aware coverage dashboard.
- **S5 — generalize across the VDL.** Extract the FileMan run into a reusable kit and walk the
  dependency graph (Kernel → MailMan → clinical), the catalog growing monotonically — proving the model
  holds at thousands of documents and millions of words.

## 13. Decision table & open questions

| # | Decision | Recommendation | Why |
|---|---|---|---|
| K1 | Meaning model | **Symbolic, grounded knowledge layer** keyed to VistA identifiers | Auditable, deterministic, incremental, zero-ML; fits an authoritative, upstream-uncontrolled corpus (§3) |
| K2 | Relation to the 2026-06-08 reset | **Honors it** — symbolic ≠ statistical; embeddings stay parked as an optional grounded top-layer only | The reset rejected induced/embedding meaning; this is asserted/symbolic meaning (§3) |
| K3 | Storage | **`registries/` = curated seed/override; `knowledge.db` (gold) = resolved truth**; YAML projection for review | Matches the lake grain + tenet #13; portable like `index.db` |
| K4 | Pipeline shape | **Promote a `resolve` stage** (elevate enrich/entities/relate); re-point index/termbase/glossary/crosswalk as projections | Re-centering, not rewrite; keeps the spine discipline |
| K5 | Casing/collision | **Auto-derive `collides_with_english`** against Hunspell; enforce case only when safe | Mechanical + self-maintaining; deletes the hand-curated `Brand.yml` |
| K6 | AI's role | **Propose-only, grounded, human-gated, deterministic-gate-passing** (extends strategy §10) | Prevents laundering hallucinated meaning into a VA source |
| K7 | Quality definition | **Semantic-fidelity invariants** (resolution coverage, canonicalization, relationship integrity, provenance) | Corpus-wide, model-checkable, scales past human review |

**Open questions:**

1. **Concept identity** — how is "same Concept" decided for D-1 dedupe: human-curated Concept nodes
   only, or AI-proposed-clustered-then-curated? (Affects S2 cost.)
2. **`verified_on` source** — verify DD-facts against the live system (`vehu`/`foia-t12`, strongest
   fidelity, ties into the FileMan POC's `verify-docs`) now, or defer live verification to S5?
3. **Relationship taxonomy scope** — fix a small closed set of edge types (`reads`/`runs-on`/
   `documented-in`/`synonym-of`/…) for the pilot, or let `discover` propose new types through the gate?
4. **`knowledge.db` ↔ `index.db`** — one database with a knowledge schema, or two with a defined join?
   (Distribution: the search deliverable wants one portable file.)
5. **Catalog governance at VDL scale** — who is the SME of record for entity/synonym/relationship
   approval as the catalog crosses package boundaries (an editorial/clinical call, not engineering)?
6. **Seed source for entities** — bootstrap the entity catalog from the **live data dictionary / KIDS /
   routine source** (authoritative, generated) vs. corpus-mined-then-curated — or both, with the live
   system as the tiebreaker?

## 14. Sources & cross-references

- **Within this program:** [`vdl-content-quality-and-ia-strategy.md`](vdl-content-quality-and-ia-strategy.md)
  §6 (controlled vocabulary), §9 (gate stack), §10 (AI guardrails);
  [`offline-lexical-search-plan.md`](offline-lexical-search-plan.md) (vocabulary-mismatch failure,
  empty glossary, zero-ML/offline DoD); the direction-reset note in
  [`CLAUDE.md`](../CLAUDE.md) and [`historical/vdocs-implementation-plan.md`](historical/vdocs-implementation-plan.md)
  closure (why embeddings were parked); `registries/entities/`, `src/vdocs/kernel/termbase.py`,
  `src/vdocs/stages/{enrich,relate,index}` (the existing seeds); the `fileman-docs` `HANDOFF.md` L0b
  note (the casing-bug trigger).
- **Frameworks:** controlled vocabulary / terminology management (ISO 30042 TBX; ASD-STE100 "one word =
  one meaning"; Google/Microsoft A–Z word lists); knowledge-graph / ontology grounding for technical
  domains (entity resolution, synonymy, typed relations); the strategy doc's single-sourcing and
  "generate reference, hand-write the rest" (Microsoft Learn model) — here applied to *meaning* as the
  generated substrate.

> This proposal is the *what/why* of the pivot. The *how/status* tracker is
> [`skl-implementation-plan.md`](skl-implementation-plan.md)
> (S0–S5 steps/gates, mirroring the lexical-search plan/tracker split) — **not started, pending
> sign-off of §13**. The affected `ArtifactContract`s + stage docs update in the same commits as the code.
