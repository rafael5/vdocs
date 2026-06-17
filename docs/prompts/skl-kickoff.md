# Kickoff — Semantic Knowledge Layer (SKL): ratify S0, then build S1

**Repo: `vdocs`.** Start a fresh session and `cd ~/projects/vdocs` first (one session ↔ one repo).
Read `CLAUDE.md`, then — in order — `docs/skl-proposal.md` (the *what/why*) and
`docs/skl-implementation-plan.md` (the *how/status* tracker, S0–S5). **The tracker is the bug
report: if code and plan disagree, fix the plan first.**

> **Naming convention (effective now).** All SKL documents, prompts, and artifacts use the **`skl-`**
> prefix going forward. The two program docs were renamed to `docs/skl-proposal.md` and
> `docs/skl-implementation-plan.md`; this prompt is `docs/prompts/skl-kickoff.md`. Keep new SKL
> registries/stages/reports/docs under the same prefix where a name is ours to choose.

## Where we are

The SKL program is **proposed, not started** (commits `3c12cde` proposal, `c96fe57` tracker). It is a
*re-centering, not a rewrite*: meaning becomes the gold artifact everything is projected from
(termbase, glossary, cross-links, index, gate). The seeds already exist —
`registries/entities/entities.yaml` (typed recognizers + canonical ids + lifecycle),
`index.db:entities`, and **`build-termbase` is already a registries→gate projection** (the thing S1
generalizes). Do **not** reintroduce embeddings/vectors — symbolic-and-grounded honors the
2026-06-08 reset (proposal §3, decision K2).

## S0 — ratify the model (a sign-off gate, not code)

S0 settles proposal §13 before S2+ touches the schema. **Surface these to Rafael for sign-off; do not
self-decide them.** The blockers for the deeper phases are **K2** (symbolic ≠ statistical — confirm
the framing) and the open questions, especially:

- **Q6 — entity seed source:** live data dictionary / KIDS / routine source (authoritative) vs.
  corpus-mined-then-curated vs. both with the live system as tiebreaker.
- **Q2 — `verified_on`:** verify DD-facts against a live system (`vehu`/`foia-t12`) now, or defer to S5.
- **Q3 — relationship taxonomy:** fixed closed starter edge set vs. `discover`-proposed.
- **Q4 — `knowledge.db` ↔ `index.db`:** one DB or two with a defined join.
- **Q1 / Q5 — Concept identity & catalog governance** (editorial calls).

Record the decisions (with rationale) into the tracker's S0 rows. **Critically:** the plan states S1
**does not** need full S0 — it can start the moment the **Term-classification facets (proposal §5)
are agreed** (a subset of S0.1). K2/Q6 block S2+, **not** S1. So: get the facet schema blessed, then
build S1 immediately; leave the deeper §13 questions open for a later S2 sign-off.

## S1 — the build increment: classify the vocabulary; fix the casing bug at the source

This is the self-contained quick win and the smallest proof that "everything is a projection" works.
It retires the `fileman-docs` casing workaround **at the source** — no `knowledge.db` yet, just an
extension of the existing termbase projection.

**The bug it kills:** `build-termbase`'s `accept.txt` does two jobs from one flat list — accept a term
*as a spelling* **and** enforce its *exact casing* everywhere. Acronyms that collide with English
(`CAN`, `SITE`, `AN`, `OR`, `IS`) make Vale demand "use `CAN`" on every "can". `fileman-docs` retreated
to `Vale.Terms = NO` + a hand-maintained `.vale/VistA/Brand.yml` (~6 terms) — exactly the
hand-curated parallel list (tenet #13 violation) this program exists to kill.

### Steps (TDD — pure cores tested first)

| ID | Step | Where |
|----|------|-------|
| S1.1 | Add Term-classification facets — `class` / `canonical_casing` / `enforce_case` / `expand_on_first_use` — to the product/term registries; schema-validate them (TDD on the loader) | `registries/inventory/product-names.yaml` (+ `registries/glossary/expansions.yaml`); loaders `kernel/products.py`, `kernel/termbase.py` |
| S1.2 | **Auto-derive `collides_with_english`** — pure transform: lowercase each surface; if it's a real word in the **same Hunspell dict Vale spell-checks against**, set `true` → never case-enforced. No human guessing which acronyms collide. | new pure fn, e.g. `kernel/casing_pure.py` |
| S1.3 | `build-termbase` emits selective casing — project casing enforcement **only** for `enforce_case && !collides_with_english`; `accept.txt` still whitelists **all** spellings | `kernel/termbase.py:build_artifacts` |
| S1.4 | Retire the workaround (the **fileman-docs** half — see handoff below) | `~/projects/fileman-docs` |

**S1.2 grounding to confirm, don't assume:** Vale's spelling uses an `en_US` Hunspell dictionary
(`/usr/share/hunspell/en_US.{dic,aff}` exists on this box; Vale may also bundle its own under the
synced `Google`/Vale package). Confirm which dictionary the live gate actually consults and derive the
collision check from *that* exact word list — the invariant is "force-case only what Vale's own
speller would not already accept as an English word." Unit-test the pure fn explicitly on
`CAN`/`SITE`/`AN`/`OR`/`IS` (collide → not enforced) vs. `VistA`/`FileMan`/`KIDS` (brand → enforced).

**Facet schema notes:** `build_artifacts` is a pure transform over `products`/`corrections`/
`expansions` — extend it without breaking the existing `accept.txt`/`VistA.yml`/`typos-extend.toml`
contract. Casing enforcement is a **new** generated Vale style (substitution: wrong-case→canonical),
replacing what `Brand.yml` did by hand — generated, never hand-edited. Heads-up: there are untracked
`docs/product-names.draft.yaml` / `docs/product-abbreviations.draft.yaml` mining drafts — read them for
candidate surfaces, but the facets land in the **real** `registries/inventory/product-names.yaml`.

### TDD (hard rule)

Write the test first (red), implement, `make check` (lint + mypy + coverage ≥95%) before commit.
`collides_with_english` and the selective-casing projector are **pure functions** — test them directly
against synthetic registry dicts; the `fileman-docs` re-run (S1.4) is the integration proof. Line
length ≤100 (ruff E501 bites docstrings; the format hook won't fix those).

## S1 acceptance / done

- **vdocs session:** facets present + schema-validated; `collides_with_english` pure fn unit-tested
  (incl. the colliding/brand pairs above); `build-termbase` emits casing enforcement only for the safe
  set; `make check` green. Update the tracker (S1.1–S1.4 rows ✅ / changelog / discoveries). Commit
  with the `Co-Authored-By` trailer; push (finished, self-contained, approved work — house cadence).
- **Then hand off to a `fileman-docs` session** (one session ↔ one repo) for S1.4's repo half:
  re-run `vdocs build-termbase --out-dir ~/projects/fileman-docs/<vocab-path>`, **delete
  `.vale/VistA/Brand.yml` and the `Vale.Terms = NO` line in `.vale.ini`**, confirm `make gate` stays
  green and the `Vista→VistA` break-test still bites, and that casing coverage now spans the full safe
  set (≫ 6 terms). Either leave that tree dirty for the next session or write a short
  `skl-s1.4-fileman-docs-kickoff.md`.

## Next after this

S2 — formalize the SKL + the `resolve` stage on FileMan (`recognize→resolve→classify→relate→verify`
→ `knowledge.db`), **gated on S0 sign-off of K2/Q6/Q2/Q3/Q4**. Then S3 (re-point projections →
entity-keyed `index.db`; the KAAJEE/`file #200` search payoff), S4 (semantic-fidelity CI gates), S5
(templatize + walk to Kernel). See `docs/skl-implementation-plan.md`.
