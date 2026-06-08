# Task: Implement the sidecar fidelity recommendations (doc-first, then code)

## Context — read these first, in order
1. `docs/doc-sidecar-design.md` — the design note this task implements. §4 is the audit
   of the current gap; §5 is the prioritized recommendation list you are implementing; §5.6
   is the priority order. This is your spec.
2. `docs/vdocs-design.md` — the SINGLE SOURCE OF ARCHITECTURAL TRUTH. §5.2 (bundle),
   §6.4/§6.6/§6.7 (sidecar split + lineage), §8 (stage contract table), §9.8 (compliance
   oracle), §17 (phased build plan).
3. `docs/fidelity-framework.md` — the QA companion (C2 structure, C5 TOC, H1/H2
   change-history, §6 provenance hard gate).
4. The current code: `src/vdocs/stages/normalize/stage.py`, `.../consolidate/stage.py`,
   `.../fidelity/compliance_pure.py` (note: NO `fidelity/stage.py` and NO `validate` stage
   exist yet — Phase 5 is TODO in `docs/vdocs-implementation-tracker.md`).

## The core problem (from doc-sidecar-design.md §4)
Sidecars are emitted conditionally (a sidecar is written iff its structure was present AND
captured), which is correct. But NOTHING distinguishes "sidecar absent because there was
nothing to capture" from "sidecar absent because a detector silently failed." The
`flags.yaml` fail-safe only fires when a strip step fires-but-cannot-parse; it does NOT
catch a detector that never fired on a structure that was actually present. No verification
stage consumes the emitted sidecar counts. This is the gap to close.

## HARD RULES (project CLAUDE.md — do not violate)
- **Doc-first.** Do NOT redesign in code. Any change to a stage's inputs/outputs/contract
  or to the sidecar set MUST land as an edit to `docs/vdocs-design.md` (and
  `fidelity-framework.md` where the gates change) FIRST, in the same train of work. If code
  and the design doc disagree, the doc is the bug report.
- **TDD.** Write the test first, confirm it fails, implement, confirm green, `make check`
  before commit. Pure transforms get Hypothesis property tests. No skipping to implementation.
- **Pure/impure split.** Logic goes in `*_pure.py` (zero I/O, plain values in/out); thin
  I/O drivers in `stage.py`. No copy-paste across stages — shared primitives go in `kernel/`.
- Use `.venv/bin/` prefixes; `make test` / `make check`.

## Work plan — follow doc-sidecar-design.md §5.6 priority order

### Step 0 — Design doc edits FIRST (doc-first gate)
Before writing any code, fold the §5 recommendations into `docs/vdocs-design.md`:
- Amend the §6.4/§6.7 sidecar split to specify **typed capture-attempt records** (§5.1):
  every capture attempt records its outcome (`captured` / `absent-expected` /
  `absent-unexpected`/failed), so absence is never ambiguous. Decide and document the
  mechanism — extend `flags.yaml`, or add a small per-bundle `capture.yaml` manifest that
  enumerates each attempted capture and its outcome. Pick one, justify it in the doc.
- Amend §8 (stage contract table) and the Phase 5 rows for `fidelity`/`validate` to specify
  the verification behaviors below.
- Add the count-reconciliation and ref-resolution gates to `fidelity-framework.md`
  (extend C2/C5 and the provenance section).
Then update `docs/vdocs-implementation-tracker.md` to reflect the new Phase 5 scope.

### Step 1 — Typed absence (§5.1, highest value)
At the `normalize` level: record, per bundle, WHY each sidecar is absent, so a verifier can
read `absent-expected` vs `absent-unexpected`. Pure logic (the outcome classification) in a
`*_pure.py`; the driver writes the record. Tests first.

### Step 2 — Count reconciliation (§5.2)
Build the verification step that reads `state.db:stage_runs[counts]` (already emitted by
`normalize/stage.py:202-219`) and trips on implausible aggregates (e.g. zero tables
corpus-wide, or a sidecar count dropping between runs with no matching source change). This
is the `fidelity` (or `validate`) stage's first real consumer of the counts. Decide the
right home and document it in §8.

### Step 3 — Ref resolution in the validate gate (§5.5)
Resolve every outbound reference recorded in each `refs.yaml` against the live anchor set;
fail the gate on any dead anchor (generalize the C5 TOC round-trip to all cross-refs). Pure
resolver + a thin gate driver. This is the DITA "severed conref" lesson — the most common
silent-loss mode.

### Step 4 — Signed bundle manifest + per-stage attestation (§5.3/§5.4)
Make the bundle's complete part list (each part + its hash + capture outcome) a verifiable
manifest, building on `history.yaml`'s existing `source_sha256`/`body_sha256`. This is the
"provable, not asserted" bar from the fidelity framework. Lowest priority — do only after
1–3 are green.

## Scope guidance
- Steps 1–3 are the must-do core. Step 4 is a stretch — confirm with me before starting it.
- Land Step 0 (design edits) as its own reviewable change before the code steps, OR keep
  design + code for each step in one coherent commit — but the design edit always precedes
  the code in each step. Do not let code drift ahead of the doc.
- Stay within the existing kernel/pure/driver architecture. If you find yourself wanting a
  new top-level module or cross-stage import, stop — that's a design question, raise it.

## Definition of done
- `docs/vdocs-design.md` + `fidelity-framework.md` describe the typed-absence,
  count-reconciliation, and ref-resolution behaviors; tracker updated.
- Tests written first and green; `make check` passes (≥95% coverage gate).
- A missing sidecar is no longer ambiguous: the pipeline can tell benign absence from a
  silent detector failure, and the verification step fails loudly on the latter.

Start by reading the four context docs, then propose your design-doc edits for Step 0
before writing them — I want to see the typed-absence mechanism choice (extend flags.yaml
vs new capture.yaml) before you commit to it.
