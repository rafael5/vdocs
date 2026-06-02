# Handoff prompt — fix the pre-Phase-4 compliance drifts

**For:** a fresh vdocs session. **Created:** 2026-06-02 (after a code-vs-design audit of everything
built through Phase 3). **Goal:** close the small set of genuine deviations from `docs/vdocs-design.md`
**before Phase 4 (`consolidate`→`index`→`relate`→`manifest`) freezes more consumers onto them.**

---

## Context you need first

Read these before touching code:
- `docs/vdocs-design.md` — the architectural source of truth. Relevant sections cited inline below
  (§7.3 preflight/fingerprints, §8 stage table, §9.2 shared kernel, §11 layout, §5.5/§5.6 inventory).
- `docs/vdocs-implementation-tracker.md` — current status (Phases 1–3 done/partial; `make check`
  green at 266 tests / 100% cov / ruff + mypy clean as of this handoff).
- `CLAUDE.md` — TDD is a hard rule: **write the failing test first, confirm it fails, implement,
  confirm green, `make check` before commit.** Pure logic in `*_pure.py` (no I/O); thin `stage.py`
  drivers. Update `docs/vdocs-design.md` in the *same commit* whenever a stage's inputs/outputs change.

**Baseline:** the spine and contract model are faithful to the design — single preflight/postflight
path, DAG-derived order, fail-loud remediation, atomic writes, pure/I-O split, discovery-is-data,
gate-wired-via-`requires`. These items below are localized wiring/placement fixes, **not** a redesign.
Do not refactor beyond them.

---

## The fixes (do in this order; each is small)

### 1. (A1) Promote `safe_component` into the kernel — §9.2 / §11 violation
A primitive used by ≥2 stages must live in `kernel/`. `safe_component` is the bundle-path slug
sanitizer, defined in a *stage* and imported across stage boundaries (couples `enrich`/`normalize`
into `convert`'s internals — violates tenet #3 self-containment):
- Defined: `src/vdocs/stages/convert/convert_pure.py:40`
- Imported by: `src/vdocs/stages/normalize/stage.py:21`, `src/vdocs/stages/enrich/stage.py:24`,
  and used within `convert/stage.py:23` + `convert_pure.py:47`.

**Do:** move `safe_component` to `kernel/text.py` (or a new `kernel/slug.py` — pick whichever fits the
kernel's existing shape; `kernel/text.py` is the path of least surprise). Update all four import sites
to `from vdocs.kernel.text import safe_component`. Keep behavior byte-identical. Add/keep a unit test
for it under `tests/unit/kernel/`.

### 2. (B2) Register `registries` as an ArtifactContract and add it to `normalize.requires`
§8's normalize row requires `registries`, and the §8 note says: *"treat a registry change like a
contract-version bump for normalize: it invalidates and re-runs the affected scopes (§7.3 fingerprints)."*
Today `normalize` loads `registries/phrases.yaml` locally and declares only
`requires = [TEXT_ENRICHED, RAW_INDEX]` (`src/vdocs/stages/normalize/stage.py:27`).

**Functional bug this causes:** editing a curated registry does **not** change normalize's input
fingerprint, so `SKIP_IF_UNCHANGED` will wrongly skip re-normalization after curation — exactly the
stale-input class of bug §7.3 exists to prevent.

**Do:** add a `REGISTRIES` `ArtifactContract` in `src/vdocs/contracts/registry.py` (it is repo config,
not lake data — model it so its `locate`/`fingerprint` point at the `registries/` dir in the repo;
`produced_by=None` like an external/curated input, analogous to `VDL`). Add it to `normalize.requires`.
Confirm a fingerprint covers the registry files normalize actually consumes. Write a test that a
registry edit changes normalize's `inputs_fp` (so a re-run is *not* skipped).

### 3. (B1) Reconcile `acquisitions` — declared artifact vs. orchestrator state
§8 lists `state.db:acquisitions` in the `requires` of both `serve-inventory` and `fetch`, but it is
**not** an `ArtifactContract`, not in either `requires`, and reached only via
`ctx.state.record_acquisition()`. Consequence: `serve_pure.inventory_status(records, acquisitions)`
(the §5.5 "enriched ⋈ acquisitions" selection surface) is implemented but **never wired into the stage
driver** — dead code today.

This is partly a *design* ambiguity: §5.5 says acquisitions is mutable orchestrator state (deliberately
*out* of the deterministic-artifact contract to keep `catalog` idempotent), while §8 lists it as a
declared require. **Resolve in ONE direction — do not guess:**
- **Option A (wire it):** add an `ACQUISITIONS` contract (STATE-class, `state.db:acquisitions`), add it
  to `serve-inventory`/`fetch` `requires`, and actually call `inventory_status(...)` so the gold
  inventory exposes the join. This matches §8 literally.
- **Option B (amend the doc):** if acquisitions should stay out-of-contract orchestrator state (the
  cleaner story per §5.5's idempotency argument), update §8 + §5.5 to say so explicitly and either
  delete or clearly mark `inventory_status` as a CLI-report helper, not a stage output.

**Recommended:** ask the user which they prefer, or default to Option A only if `inventory_status` is
meant to be part of the gold-inventory artifact (it reads that way in §5.5/§5.6). Whichever you pick,
**code and doc must agree in the same commit.**

### 4. (A2) Collapse to one mojibake fixer in the kernel — §9.2
Two codepaths exist; the canonical kernel one is dead:
- `src/vdocs/kernel/text.py:36 repair_mojibake()` (custom cp1252 round-trip) — **imported by nobody.**
- `src/vdocs/stages/catalog/enrich_pure.py:79` rolls its own via `ftfy.fix_text(...)`.

§9.2 mandates ONE mojibake fixer, in the kernel, used by all. **Do:** decide the canonical impl —
`ftfy` is already a dep and is what's actually exercised on the real corpus, so the low-risk move is to
make `kernel/text.repair_mojibake` wrap `ftfy.fix_text(text, normalization="NFC")` and have
`catalog/enrich_pure.py` import and call the kernel function instead of importing `ftfy` directly.
Keep catalog's behavior identical (verify against the pinned 8,834-row inventory fixture —
`tests/fixtures/vdl_inventory_raw.csv.gz`; the §7 distributions must still reproduce exactly).

---

## Out of scope for this session (do NOT do)
These are correctly-tracked deferrals, not faults — leave them on the Phase plan:
- `fetch` dimension-selection flags (`--app/--section/--doc-type/--group/--select/--all`) and the
  §5.6 "default fetches nothing + prints count" behavior. *(If you have time after the four fixes and
  the user agrees, this is the single most valuable next increment — but it is Phase-2 finishing work,
  not a compliance fix. Note: current `fetch` fetches all genuine in-scope rows unconditionally, which
  contradicts §5.6's "no blind/full download" — flag it to the user, don't silently fix.)*
- `normalize` deferred sidecars: `history.yaml`, `tables/*.csv`, `refs.yaml` + back-links + Word-
  bookmark→GitHub-slug rewrite, template STRIP+stamp, boilerplate REFERENCE.
- `kernel/discovery.py` / `kernel/lineage.py` are unused Phase-1 primitives awaiting consumers — fine
  for now; wire or trim during Phase 4/5, not here.
- Phases 4–7 themselves.

## Definition of done
- All four fixes implemented test-first; `make check` green (ruff line 100 · mypy · pytest random-order
  · coverage ≥95%, currently 100%).
- `docs/vdocs-design.md` and `docs/vdocs-implementation-tracker.md` updated in the same commits where
  behavior/contracts changed (esp. fix 3's doc/code reconciliation; add a Change Log + Lessons Learned
  entry to the tracker).
- No regressions in the real-corpus assertions (the pinned inventory fixture distributions still match).
- One commit per fix (or a tightly-scoped few), each message ending with the Co-Authored-By trailer
  per the repo convention.
