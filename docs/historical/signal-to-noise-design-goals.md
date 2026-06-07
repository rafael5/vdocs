# Signal-to-Noise Design Goals

**Status:** Design note (synthesis). **Date:** 2026-06-03.
**Companion to:** [`vdocs-design.md`](vdocs-design.md) (§6.4–§6.7, §9.6–§9.8) and
[`fidelity-framework.md`](fidelity-framework.md) (§4, §5 C2/C5/C7, §10.5).

This note captures, in one place, the *signal-to-noise* thesis of the pipeline: **why** vdocs
subtracts so aggressively, **how** it does so without losing anything, **where** the optimum lies,
and **how** that optimum is enforced rather than assumed. It is a synthesis — the authoritative
mechanisms live in the two documents above; this note is the "why it all points the same way"
explainer. If this note and either source doc disagree, the source doc wins.

---

## 1. The thesis (and the one correction)

**The intuition.** The more repeated, templated, and machine-processable material we safely move out
of the prose — boilerplate to a single shared copy, dead furniture deleted, structured data to
`tables/*.csv`, revision apparatus to `revisions.yaml`, navigation derived from the heading tree —
the more the text that *remains* is the substantive, specific, unique content of that document. That
denser prose makes sharper embeddings, cleaner lexical signal, and better retrieval. It also makes a
more readable human corpus.

**This is a real, stated goal**, not a side effect: the fidelity baseline explicitly *excludes
registered noise* from the source-token denominator (`fidelity-framework.md` §4), and the
search-corpus is deliberately curated — anchor-only, condensed — precisely to maximize retrieval
fidelity (vdocs-design ADR-021).

**The correction — one word.** The verb is **relocate**, not **remove**. Almost nothing is destroyed.
Each kind of content moves to the representation where its retrieval modality is strongest, and the
knowledge base as a whole loses nothing. Saying "remove" invites two errors this note exists to
prevent: (a) thinking condensation trades fidelity for density (it doesn't — §3), and (b) thinking
*more* subtraction is *always* better (it isn't — §4).

---

## 2. Route by disposition, not by "is it noise?"

The enabling idea is that repetition is not one undifferentiated pile. It falls into distinct kinds,
each with its own registry, key, and **disposition** — and the disposition is what decides whether a
match is referenced, stripped, deleted, promoted, canonicalized, extracted, or routed. The whole
detect/filter/extract question collapses once content is classified by *what it is*:

| Kind | Detection technique | Disposition | Lands in |
|---|---|---|---|
| **Boilerplate** — meaningful but duplicated blocks | MinHash/Jaccard near-duplicate clustering (`kernel/discovery`) — drift in spelling clusters into one candidate | **REFERENCE** — one canonical copy, body links to it | `gold/_shared/boilerplate/<id>.md` + `registries/boilerplate` |
| **Template / scaffold** — the section skeleton each manual was poured into | structural scaffold clustering bucketed by `(doc_type, era)` | **STRIP + stamp `template_id` + RETAIN schema** | `registries/templates` (computable §9.8 schema, queryable) |
| **Dead phrases** — paper-era residue, zero meaning | frequency of short recurring strings | **DELETE** — no copy, no reference | `registries/phrases` (rules only) |
| **Structural conventions** — callouts, legacy TOC, rev-table shape | convention/shape detection | **CANONICALIZE** to one GFM form | `registries/structures` |
| **Per-doc unique facts** — revision table, big data tables, publication date | shape detector + heading-proximity guard | **EXTRACT to sidecar** | `revisions.yaml`, `tables/*.csv`, `published` FM field |
| **Domain entities** — namespaces, file numbers, RPCs, … | curated + corpus-frequency candidates | **EXTRACT to index** | `index.db:entities` |

Three of these are *subtractive*, and they are deliberately different because they preserve different
things: **boilerplate is referenced** (the content matters, it just shouldn't be copied N times),
**a template is stripped with a provenance stamp** (the skeleton is structural noise but *which*
template is an audit fact, and its schema is a reusable asset), and **a dead phrase is simply
deleted** (pure residue, nothing worth keeping). "Sidecar vs registry" falls right out: a **registry**
holds a *rule* that applies across many docs; a **sidecar** holds a *unique fact* this one document
carried.

---

## 3. Why this raises search quality (the mechanisms)

Condensation helps retrieval through several distinct, measurable mechanisms — not one vague "less
noise" effect:

1. **De-duplication / ranking diversity (often the biggest win).** When the same boilerplate
   paragraph appears in dozens of documents, those chunks cluster at nearly the same point in
   embedding space. At query time the retriever surfaces arbitrary near-duplicates and crowds the
   genuinely unique answer out of the top-k. Collapsing them to one referenced copy improves
   *ranking diversity* — measured as `redundancy@k` (target ≈ 0; `fidelity-framework.md` §10.5).
2. **Per-chunk semantic density.** A chunk that is 80% boilerplate embeds toward the boilerplate
   centroid; removing it sharpens the vector toward the chunk's actual topic.
3. **Right modality for structured data.** A data-dictionary table embeds *terribly* as prose.
   Moving it to `tables/*.csv` routes it to the **structured** leg of the hybrid search (semantic +
   lexical + **structured** + graph) — upgrading it from a fuzzy vector match on a mangled table to
   an exact field query. The data is not hidden; it is better indexed.
4. **Latest-only correctness.** Anchor-only indexing keeps stale prior-version chunks out of the ANN
   neighborhood entirely, so hits are `is_latest` by construction (measured as version-correctness).

**Fidelity is not traded away.** Search corpus ≠ evidence corpus (vdocs-design §14.6): the
index/embeddings are curated and anchor-only; bronze + full history stay complete and immutable. The
framework measures *both halves* — migration fidelity (`S`→`T`, §5–§7) **and** retrieval quality
(§10.5) — so the central bet (whole-source fidelity *and* condensed discoverability) is proven on its
machine half, not just asserted.

---

## 4. The optimum: more subtraction is not monotonically better

This is the load-bearing correction to the naïve thesis. Signal-to-noise is **maximized, not
minimized-token-count.** A retrieved chunk must be **self-explaining in isolation**: strip away the
surrounding context that disambiguates the unique prose and the chunk embeds as an unanchored
fragment, and the retriever can no longer tell what it is *about*. Recall falls even though density
rose. **The curve peaks, then falls.**

The guardrail (vdocs-design §6.5): *can a contributor still open one thing, read it, change it, and
see a sensible diff?* The same test protects the embedding — a chunk needs enough context to stand
alone. So the goal is to ride the rising side of the curve, not to chase maximal removal.

---

## 5. How the optimum is held (capture-before-strip + over-strip check)

Two disciplines keep condensation on the productive side of the curve:

**Capture-before-strip (the inviolable rule, §6.4).** No legacy block leaves the body until the
unique fact it carries is persisted. The revision table → `revisions.yaml` *before* the apparatus is
removed; the cover's publication date → the `published` identity field *before* the title page is
replaced. A revision-history heading with no parseable table is **retained and flagged**, never
deleted blind. Every deletion is attributable to an *approved* registry entry — no free-form
stripping. Bronze immutability keeps the untouched original as proof.

**The over-strip check (the retrieval-side guardrail, NEW — `fidelity-framework.md` §10.5).** The
§6.5 optimum is now *enforced*, not assumed. The `fidelity` stage scores an **over-strip rate** over
each section-chunk of the normalized body:

- a chunk is **hollow** when it is a content heading whose retained body is below a substantive-token
  floor **and** carries no resolvable referent (no `_shared/` boilerplate link, `tables/*.csv` stub,
  or asset reference) — i.e. stripped to a bare heading;
- a chunk reduced to a **referent** (content *relocated*, recoverable, dereferenced before scoring
  per §4) is **not** penalized — that is by-design decomposition;
- **container** headings (substance lives in subsections) are excluded.

`over_strip_rate = hollow ÷ content chunks`; any hollow content chunk drops the document below PASS
(never silently faithful); a mostly-hollow body QUARANTINEs. It is a pure, deterministic, **T-only**
check (no source needed — a hollow content section is self-evidently a defect), implemented in
`src/vdocs/stages/fidelity/overstrip_pure.py`, mirroring `compliance_pure.py`.

---

## 6. The adaptive loop that makes it safe to be aggressive

Aggressive subtraction is only safe because the *rules* are reviewable data, not buried code
(tenet #13, §9.6). Discovery (corpus-global, statistical, adaptive) is kept strictly apart from
application (per-document, pure, deterministic), connected by one version-controlled seam:

```
discover (mine) ─► candidates+evidence ─► CURATE (gate, a PR) ─► registries/ ─► normalize subtracts & references
  reports/patterns/                                               (the seam)        pure fn of (doc × registry)
        ▲                                                                                  │
        └──────────────────────── re-discover on drift / new era ◄─────────────────────────┘
```

Because the deterministic stages are pure functions of `(document, registry)`, a newly-found pattern
extends the pipeline by gaining a *registry entry*, never a code edit — and every subtraction is
auditable, diffable, and reversible.

---

## 7. The goals, stated as targets

1. **Maximize the substantive-prose share** of every anchor document by relocating repeated,
   templated, and machine-processable material to its best-indexed home — *losing nothing*.
2. **Measure the retrieval lift, don't assert it** — `precision@k` / `recall@k` / `nDCG` / `MRR`,
   plus `redundancy@k ≈ 0`, version-correctness ~100%, and `over_strip_rate ≈ 0`, with a with-vs-without
   condensation ablation quantifying the causal lift (`fidelity-framework.md` §10.5).
3. **Hold the §6.5 optimum** — never strip a chunk past self-sufficiency; the over-strip check is the
   standing enforcement.
4. **Never trade fidelity for density** — search corpus ≠ evidence corpus; both halves are scored and
   gated independently (§5–§7 vs §10.5; vdocs-design §14.6 / ADR-021).
5. **Keep the rules as reviewable data** — disposition-typed registries curated by PR; no hard-coded
   pattern in any stage (tenet #13).
6. **Capture before you strip** — every unique fact persisted to a sidecar/field before its legacy
   carrier is removed; unparseable apparatus retained and flagged (§6.4).

---

## 8. Pointers

- Registry family, dispositions, the induction→curate→apply→re-discover loop — vdocs-design §9.6–§9.7.
- Templates as computable structural schemas (the retained asset, not just stripped scaffold) — §9.8.
- TOC as derived-not-extracted navigation, with correlate-before-drop — §6.7.
- Capture-before-strip and the revision/title-page contracts — §6.4.
- Don't-over-decompose guardrail (human + retrieval edges) — §6.5.
- Retrieval-quality measurement, `redundancy@k`, and the over-strip rate — fidelity-framework §10.5.
- The over-strip pure kernel — `src/vdocs/stages/fidelity/overstrip_pure.py` (+ tests
  `tests/unit/stages/test_overstrip_pure.py`, `tests/property/test_overstrip_props.py`).
