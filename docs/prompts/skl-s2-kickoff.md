# Kickoff — SKL S2: the `resolve` stage + `knowledge.db` for the FileMan (DI) gold

**Repo: `vdocs`.** Start a fresh session and `cd ~/projects/vdocs` first (one session ↔ one repo).
Read `CLAUDE.md`, then — in order — `docs/skl-proposal.md` (the *what/why*; esp. §5 data model, §6
pipeline, §10 AI guardrails) and `docs/skl-implementation-plan.md` (the *how/status* tracker — read the
**Decisions (S0 sign-off)** block under S0; it binds everything below). **The tracker is the bug report:
if code and plan disagree, fix the plan first.** Keep new SKL artifacts under the `skl-`/`knowledge`
naming where the name is ours.

## Where we are

S0 is **signed off** (commit `8d949d0`) and S1 is **done end-to-end** (vdocs `7658fa0` + `fileman-docs`
`f89977d` — the casing bug is fixed at the source; the termbase is a projection). S2 is the first phase
that builds the **Semantic Knowledge Layer itself**: promote semantic resolution to a named DAG layer
that emits `knowledge.db` for the `DI`/FileMan gold. This is a **re-centering, not a rewrite** (proposal
§6): keep the stages, kernel, orchestrator, registries; *elevate* today's scattered entity work
(`stages/index/entities_pure.py` recognition, `stages/enrich`, `stages/relate`) into one governed model.

### The seeds you build *on*, not over (proposal §4)
- `registries/entities/entities.yaml` — typed recognizers already model `fileman_file` (canonical =
  file number), `routine`, `global`, `build`, … with `(type, canonical)` ids + `status` lifecycle.
- `stages/index/entities_pure.py` — the generic recognizer that writes `index.db:entities`.
- `stages/relate`, `stages/enrich` — the natural homes for relationship/mention work.
- S1's Term facets in `kernel/products.py` + `kernel/casing_pure.py` — fold these in as the `classify`
  sub-transform.

## The S0 decisions that bind S2 (do not re-open — they're ratified)

| # | Binds | Decision |
|---|-------|----------|
| **Q4** | S2.1 | `knowledge.db` is its **own** gold `ArtifactContract` (two DBs, joined on entity-id; the merge into the shipped `index.db` is a **later** `publish` concern — not S2). |
| **Q2** | S2.1/S2.3 | `verified_on` is **deferred to S5**, but the schema **carries a `verification` block now** — S2 nodes are `status: asserted` (corpus provenance). No live verification gating in S2 (optional thin file#→name confirmation only, see below). |
| **Q6** | S2.2 | Entity seeds = **live DD spine + corpus-mined synonyms**, live system as tiebreaker. The live DD gives authoritative identity; the corpus gives the prose synonyms readers use. |
| **Q3** | S2.3 | Relationship taxonomy = a **closed starter edge set** in a new `registries/relationships/edge-types.yaml`; `discover` may *propose* new types through the §9.6 gate; **unregistered edge types never reach `knowledge.db`**. Starter set: `synonym-of`, `miscapitalization-of`, `documented-in`, `reads`, `runs-on`, `part-of`/`belongs-to-package`. |
| **Q1** | scope | **Concepts are OUT of S2.** Build Entities/Terms/Relationships only (enumerable + authoritative). Concepts enter at S3/S4. Keeps S2 bounded. |
| **K6/§10** | S2.4 | AI **proposes only**; determinism resolves; you authorize. Every node cites provenance (corpus location) or is `asserted`. No AI-asserted node/edge reaches `knowledge.db` unreviewed. |

## Live-DD availability — VERIFIED 2026-06-17 (and the access rule)

Both target systems are **up and the DD is populated**: `vehu` (VistA-on-YottaDB, healthy) and
`foia-t12` (VistA-on-IRIS, healthy). Confirmed read: `^DIC(200,0)` piece 1 = **`NEW PERSON`**, i.e.
`file #200 → "NEW PERSON"` resolves live. So the Q6 DD spine is a green light.

**Hard rule — the engine-stack guard (`~/scripts/lib/engine-stack-guard.sh`):** all access to the live
M engines **must go through the `m` toolchain** (m-driver-sdk → m-ydb / m-iris) — **never raw
`docker exec ... mumps`**. The canonical seams:
- ad-hoc read: `m vista exec --engine ydb ...` (against `vehu`) / `--engine iris` (against `foia-t12`);
- Go: `mdriver.Client` (m-driver-sdk).

`m` is **not on PATH in this vdocs Python session** — so the DD-seeding step needs a deliberate seam.
**Decide at S2.2 (surface to Rafael):** either (a) `vdocs` shells out to `m vista exec` for a one-shot
**DD export** (file#→name + field/global map for the DI files) written to a curated
`registries/entities/dd-seed.<pkg>.yaml`, or (b) do the DD export from a `vista-cloud-dev` session and
hand the YAML to `vdocs`. Prefer **(a)** if the `m` toolchain can be put on PATH for the export; the
export is read-only and content-addressable, so it caches. **Mind the vdocs shared-lake rule** before
any run on `~/data/vdocs` (check for a live operator run; don't race `state.db`/`index.db`/CAS).

## S2 steps (TDD — pure `*_pure.py` cores first, thin `stage.py` drivers)

| ID | Step | Where / detail | Gate |
|----|------|----------------|------|
| S2.1 | `knowledge.db` ArtifactContract + boundary types | Pydantic v2 models for `entity` / `term` / `relationship` nodes — each with identity (`(type, canonical)`), `synonyms[]`, `status` (`approved\|proposed\|deprecated`), `provenance[]` (`{source_sha256, doc, section}`), and a `verification` block (`status: asserted`, room for `verified_on` later). New gold `ArtifactContract`; orchestrator wires the `resolve` output. **Schema is the S0-ratified §5 model — freeze it here.** | contract + types defined; orchestrator builds an empty-but-valid `knowledge.db`; round-trip unit-tested |
| S2.2 | `resolve` stage — **recognize → resolve** | Lift `entities_pure` recognition (don't fork it — share the pure recognizer). Add a **resolution** pure transform: map every surface (`file #200`, `the NEW PERSON file`, `^VA(200,`) → the canonical entity id `fileman_file/200`, data-driven from the registries + the **DD seed** (Q6). Seed the DI files' authoritative identity from the live DD export. | pure-fn tests; `file #200`/`NEW PERSON`/`^VA(200,` all resolve to one id; resolution table is data, not code |
| S2.3 | `resolve` stage — **classify → relate → verify** | `classify`: fold in S1's Term facets (class/casing/collision). `relate`: emit typed edges using the new `registries/relationships/edge-types.yaml` closed set; reject unregistered types. `verify`: stamp every node `verification.status: asserted` (Q2 — no live check gating S2). | `knowledge.db` populated for DI gold; edges typed + provenanced; every node has provenance + a verification block |
| S2.4 | Seed the catalog (AI-proposed, human-curated) | Generate candidate entities/synonyms/edges from the registries + corpus mentions + AI proposal under §10 (propose-only, grounded, adversarial-triaged into a curator queue). **You approve** before anything merges to the curated seed; every node cites provenance. | curator-approved seed for DI; a reproducible proposal→review artifact; zero unreviewed AI assertions in `knowledge.db` |

*TDD: each `resolve` sub-transform (`recognize`/`resolve`/`classify`/`relate`/`verify`) is a pure
function tested before the `stage.py` driver; an integration test runs the stage on a small seeded DI
gold slice and asserts the `knowledge.db` contents.*

## The `resolve` stage shape (proposal §6)

```
consolidate ─▶ [ resolve ] ─▶ gold/knowledge.db
                  recognize → resolve(synonymy) → classify → relate → verify
   registries/ (entities · relationships/edge-types · products+casing) ─┘  + DD seed (live, Q6)
```
Pure cores in `stages/resolve/*_pure.py`; a thin `stages/resolve/stage.py` driver; an
`ArtifactContract` for `knowledge.db`. Update `docs/vdocs-design.md` (or the §8 stage table) in the
**same commit** whenever the stage's inputs/outputs/CLI change (house rule).

## Acceptance / done (S2)

- `knowledge.db` exists in the DI gold as a first-class `ArtifactContract`; entity/term/relationship
  nodes carry identity + provenance + lifecycle + a `verification` block.
- `file #200` ↔ `NEW PERSON` ↔ `^VA(200,` all **resolve to one canonical entity** (the headline proof).
- Relationships are typed against the registered edge set; unregistered types are rejected (gated).
- Every node is provenanced; AI-proposed nodes were human-curated before merge (§10 honored).
- `make check` green (≥95% cov); TDD throughout. Update the tracker (S2 rows ✅ / changelog / discoveries
  — esp. the DD-seam decision and any synonymy-resolution gotchas). Commit with the `Co-Authored-By`
  trailer; push (house cadence).

## Next after this

S3 — re-point the projections at the SKL (entity-keyed `index.db`; the `publish` step merges
`knowledge.db` tables into the shipped `index.db`, Q4) and land the search vocabulary-mismatch payoff
(KAAJEE / `file #200`↔"NEW PERSON" beat the 0.395 baseline). Then S4 (semantic-fidelity CI gates) and
S5 (templatize → Kernel; live `verified_on`, Q2). See `docs/skl-implementation-plan.md`.
