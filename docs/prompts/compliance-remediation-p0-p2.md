# Implementation prompt — compliance remediation P0–P2 (close the built-scope deviations + finish `normalize`)

> Paste this whole file as the opening message of a fresh session. It is self-contained except for
> the repo itself — read the files it points at before writing code. This is a **multi-increment**
> task: each numbered increment below is its own TDD cycle and its own commit. Keep `make check` green
> between increments. Do **not** start Phase 4+ stages (`consolidate`/`index`/…) — that is out of scope.

## Context — why this exists

A compliance audit of vdocs against `docs/vdocs-design.md` and `docs/vdocs-implementation-tracker.md`
found that **the built code (Phases 1–3) is structurally compliant** — §8 contracts match, pure/I-O
split is clean, the orchestrator derives order, `make check` is green (316 tests, 100% cov). The gaps
are (A) unbuilt Phase 4–7 scope — *out of scope here* — and a handful of **genuine deviations inside
built scope**. This task closes those deviations and finishes the one ◐ stage (`normalize`).

The three priority buckets from the audit:

- **P0** — close the deviations that mislead a reader (dead code, wrong layout, over-claiming doc).
- **P1** — finish `normalize` to ✅ (its remaining deferred F-steps).
- **P2** — build the discovery substrate the design promises (and that two P1 steps depend on).

**Execution order is P0 → P2 → P1**, not P0→P1→P2. Reason: two P1 steps (boilerplate REFERENCE,
template STRIP+STAMP) consume curated `registries/boilerplate` and `registries/templates`, which only
exist once the P2 `discover` miners produce candidates and you curate them in. The two *independent*
P1 steps (`tables→csv`, heading-level inference) can be done any time after P0.

## Read first (source of truth — read before writing code)

- `CLAUDE.md` — project rules. **Hard TDD**: write the test, confirm it fails, implement, confirm
  green, `make check` (ruff line 100 · mypy · pytest random-order · coverage ≥95%) before each commit.
  Prefer editing existing files; pure logic in `*_pure.py` (zero I/O), thin I/O in `stage.py`; a
  primitive used by ≥2 stages lives in `kernel/`; no `print()` (structlog). End commit messages with
  the required `Co-Authored-By` trailer. **Commit per increment; do not push unless asked.**
- `docs/vdocs-design.md` — the architectural source of truth. **If code and doc disagree, the doc is
  the bug report.** Sections you will need, by increment:
  - **§8** stage table (~lines 900-919), the `normalize` row — the produces list this task fulfils.
  - **§9.2** the shared kernel (~lines 1006-1028) — `kernel/discovery` must hold the near-dup +
    clustering miners and be *used*, not dead.
  - **§9.6** discovery + the adaptive loop (~lines 1057-1175) — what `discover` must mine and how
    candidates curate into `registries/`.
  - **§9.7** registry index (~lines 1176-1208) and **§9.8** templates as computable structural schemas
    (~lines 1209-1275) + **ADR-018** — the `(doc_type, era)` template model and `template_id` stamping.
  - **§11** repo/package layout (~lines 1307-1366) — the `registries/{boilerplate,templates,phrases,
    glossary,structures,converter-routing}/` **subdirectory** layout.
  - **§6.4/§6.5** decomposition decisions + the "don't over-decompose" guardrail (~lines 607-633) and
    the sidecar table — for `tables/*.csv`.
- `docs/fidelity-framework.md` — table-fidelity and template-compliance expectations (skim the
  relevant axes when building `tables→csv` and template STRIP+STAMP).
- `docs/vdocs-implementation-tracker.md` — the `normalize` row + `discover` row + Change Log
  conventions (newest-first). You update this in the **same commit** as each increment.
- Code you will extend:
  - `src/vdocs/kernel/discovery.py` (shingling/MinHash/Jaccard — **currently unused by any stage**).
  - `src/vdocs/stages/discover/discover_pure.py` + `stage.py` (3 miners today: recurring-blocks,
    glossary, converter-routing — all exact-string, none use `kernel/discovery`).
  - `src/vdocs/stages/normalize/normalize_pure.py`, `anchors_pure.py`, `revision_pure.py`, `stage.py`
    (the F-step pipeline; mirror the existing pure-module split and conditional-sidecar write pattern).
  - `src/vdocs/stages/catalog/registries.py` (the registry **loader** — it reads `registries/*.yaml`;
    you will repoint it at the new subdirectory layout).
  - `registries/` (currently **flat** `*.yaml` files; you will reshape to subdirectories).

---

# P0 — close the misleading deviations (small, do these first)

Four independent fixes. Each is its own commit (or group the doc-only ones into one commit).

## P0.1 — Reshape `registries/` to the §11 subdirectory layout

**Deviation:** §11 specifies `registries/{boilerplate,templates,phrases,glossary,structures,
converter-routing}/` as **directories**; the repo has flat files (`phrases.yaml`,
`converter-routing.yaml`, plus the inventory-track config `package-master.yaml`, `doc-types.yaml`, …
all mixed at `registries/` root).

**Do:** Decide the layout with the design as arbiter, then make code match doc:
- Move the **pattern registries** into the §11 subdirs: `phrases.yaml → phrases/`,
  `converter-routing.yaml → converter-routing/`, and create the empty-but-present
  `boilerplate/`, `templates/`, `glossary/`, `structures/` dirs (with a `.gitkeep` or a
  `README.md` stub each so they're tracked) — these get populated in P2/P1.
- The **inventory-track** config (`package-master.yaml`, `doc-types.yaml`, `manual-labels.yaml`,
  `system-types.yaml`, `section-codes.yaml`, `doc-labels.yaml`, `noise-domains.yaml`,
  `abbrev-fallback.yaml`, `typo-corrections.yaml`) is *not* a §9.6 pattern registry. §9.7 is the
  canonical catalog — **read it** and place these where it says. If §9.7 is silent on them, the
  cleanest move is a `registries/inventory/` (or `registries/catalog/`) subdir; **if you choose a
  path the design doesn't name, amend §9.7 to record it (doc-first).**
- Repoint every loader/consumer: `src/vdocs/stages/catalog/registries.py`, the `normalize` phrases
  loader, the `convert` converter-routing loader, and the `REGISTRIES` contract's `root`/tree
  fingerprint (`src/vdocs/contracts/registry.py` + `config.py` `registries` path). The `REGISTRIES`
  tree fingerprint must still cover the curated pattern registries (so a curation edit invalidates
  `normalize`); confirm the reshaped tree still produces a stable fingerprint.
- **TDD:** the existing registry-loader tests (`tests/unit/stages/test_registries.py`) and the
  normalize/convert integration tests must stay green after repointing; add a test asserting the
  new subdir layout loads. Verify byte-identical loaded values (the reshape is a move, not a content
  change) — same exact-count fidelity the registries were ported under.

## P0.2 — Decide `kernel/discovery`'s fate (stop the silent dead code)

**Deviation:** `kernel/discovery.py` implements shingling/MinHash/Jaccard but **no production code
imports it** (only its own unit test + an aspirational comment in `discover_pure.py:8`). §9.2 says a
kernel primitive exists because a stage uses it.

**Do (P0 part):** This is *resolved for real* in **P2** (wire MinHash into the `discover` boilerplate
miner). For P0, just make the state honest and tracked so it isn't latent dead code in the interim:
add a one-line module docstring note in `kernel/discovery.py` that it is the substrate for the P2
`discover` near-dup miner, and add a tracker note (P0.4) flagging it. **Do not delete it** — P2 uses it.
(If you reach P2 in the same session, this becomes moot — the import lands and the note can say "used by
discover".)

## P0.3 — Reconcile §8 `normalize.produces` with reality (doc-first)

**Deviation:** the §8 `normalize` row reads as if `tables/*.csv`, boilerplate-referenced,
template-stripped+`template_id`-stamped, and glossary-single-sourced are **done**; they are the
deferred F-steps (the tracker's `normalize ◐` is the only place that records the gap).

**Do:** Until P1/P2 land the steps, annotate the §8 cell (and/or a §8 note) to mark those clauses as
**forward-looking / in-progress**, matching the tracker. As each P1 step lands, flip the corresponding
clause to plain (done) in the **same commit** as that step. Net: §8 never over-claims relative to code.

## P0.4 — Tracker notes for the deviations

Add a short **Lessons Learned** / Change-Log note (newest-first) in
`docs/vdocs-implementation-tracker.md` recording the audit findings being remediated: registries
layout (P0.1), kernel/discovery currently unused → wired in P2 (P0.2), §8 normalize over-claim
reconciled (P0.3). This is the audit trail; keep it terse.

---

# P2 — build the discovery substrate the design promises (do before P1's curated steps)

§9.2/§9.6/§11 promise more than the current `discover` delivers. Two gaps, two increments. **Each is
test-first; `discover` still mutates no content (proposals only) — §8/§9.6.**

## P2.1 — Use `kernel/discovery` for near-duplicate boilerplate detection

**Gap:** `discover`'s recurring-block miner uses **exact normalized-string equality**
(`discover_pure.py` `block_key`); §9.6 step 1 specifies **shingling/MinHash near-duplicate** detection
so near-identical (not byte-identical) boilerplate clusters together.

**Do:** Extend the boilerplate path of `mine_recurring_blocks` to cluster blocks by MinHash/Jaccard
similarity (threshold a constant, justified in a comment) using `kernel/discovery`'s `shingles`,
`minhash_signature`, `estimate_jaccard`. Keep exact-match as the cheap pre-bucket; promote near-dup
clustering on top. If `kernel/discovery` lacks a banding/LSH or candidate-pair helper you need, **add
it to `kernel/discovery` first** (test-first) — it's the shared home (§9.2), not stage-local code.
**TDD:** unit tests in `tests/unit/stages/test_discover_pure.py` for "near-identical blocks (one word
differs) cluster as one boilerplate candidate"; extend/keep `tests/unit/kernel/test_discovery.py` for
any new kernel helper. This retires the P0.2 dead-code finding — `kernel/discovery` is now used.

## P2.2 — Structural-fingerprint + clustering miners → `(doc_type, era)` templates and structures

**Gap:** §9.2/§11 promise `kernel/discovery` holds **structural-fingerprint/clustering miners**, and
§9.6/§9.8/ADR-018 require `discover` to induce **per-`(doc_type, era)` templates** (heading-scaffold +
standard-page fingerprints, date-bucketed) with a `template_id` + computable structural schema, plus
**structural-convention** detection (revision-table / TOC / callout shapes) → `registries/structures`.
Today `discover`'s `templates` bucket is single normalized heading lines — no `doc_type`, no `era`, no
`template_id`, no schema — and `registries/structures` has no feeder.

**Do (read §9.8 + ADR-018 carefully first — they define the template model):**
- Add structural-fingerprint + clustering primitives to `kernel/discovery` (heading-scaffold
  fingerprint; standard-page fingerprint; a clustering routine). Test-first in the kernel.
- In `discover` (`discover_pure.py` + `stage.py`): mine `(doc_type, era)` template candidates — cluster
  bodies by structural fingerprint, bucket by publication date/era (the date comes from the inventory /
  enriched metadata — wire whatever join `discover` already has, or note the seam if it requires a new
  input and raise it before coding rather than silently adding a `requires`), emit a `template_id` +
  structural schema + RETAIN/STRIP disposition per §9.8. Also mine structural conventions
  (revision-table/TOC/callout) → `structures` candidates. Write them into the existing `PatternReport`
  / `reports/patterns` (no new contract unless §8 needs one — if it does, declare it and update §8).
- **Curate** a high-confidence starter set into `registries/templates/` and `registries/structures/`
  (the §9.6 curation gate; same "generate from real corpus, commit the YAML as source of truth" pattern
  the inventory registries used). This is what P1's template/structures steps will consume.
- **TDD:** unit tests for the structural fingerprint (two docs with the same heading scaffold →
  same/near fingerprint; different scaffold → different), the era bucketing, and the template/structures
  candidate emission. Keep `discover` mutating no content.

> If `(doc_type, era)` template induction proves larger than one clean increment (it may), split it:
> land the kernel structural primitives + the `structures` miner first, then the `(doc_type, era)`
> template miner. Each split is its own green commit. Note any split in the tracker.

---

# P1 — finish `normalize` to ✅ (its remaining deferred F-steps)

Four F-steps, in the tracker's stated order. **Independent ones (a, d) need no P2 output; curated ones
(b, c) need P2.2's registries.** Each is a separate TDD increment + commit; each flips its §8 clause
(P0.3) from forward-looking to done in the same commit. Mirror the existing F-step conventions in
`normalize_pure.py`/`anchors_pure.py`/`revision_pure.py` and the conditional-sidecar write in `stage.py`
(as `history.yaml`/`refs.yaml` are written). Update `normalize_body`'s fixed F-step order deliberately —
order matters for idempotency; add each step where it belongs and keep
`normalize_body(normalize_body(x)) == normalize_body(x)`.

## P1.a — `tables/*.csv` sidecars (independent — can start right after P0)

Complex tables (data-dictionary, etc.) come through `convert` as raw HTML `<table>` (the revision-history
table is already handled by `revision_pure` → `history.yaml`). Per §6.4/§8: extract qualifying tables to
`tables/*.csv` bundle sidecars and replace them in the body with a reference/link. **Reuse `kernel/csv`**
(the promoted flat-table serialiser) — do not roll a new CSV writer (§9.2). Respect the §6.5
"don't over-decompose" guardrail: only extract tables that meet the criteria the design names; leave
small inline tables as GFM. New pure module (e.g. `tables_pure.py`) mirroring `revision_pure`; conditional
sidecar write + a `tables_sidecars` count. **TDD:** HTML-table → CSV extraction (both Pandoc HTML and
Docling GFM-pipe dialects, as `revision_pure` handles), body gets a reference, idempotent, small tables
left alone.

## P1.d — heading-level inference (independent)

Some docs carry inconsistent/under-leveled headings. Infer corrected heading levels from the document's
structure so the regenerated TOC (§6.7) is sane. Pure function over the heading tree; integrates into
`normalize_body` before TOC regen. **TDD:** under-leveled headings get promoted/demoted to a consistent
tree; idempotent; doesn't break the existing `_Toc` recovery / anchor-map path.

## P1.b — boilerplate REFERENCE (needs `registries/boilerplate` from P2.1 curation)

Curate P2.1's boilerplate candidates into `registries/boilerplate/` (canonical copy destined for
`gold/_shared/`), then have `normalize` **subtract** matching blocks from bodies and replace them with a
reference to the canonical copy (§9.6: REFERENCE, not DELETE — distinct from `phrases` which DELETE).
Pure function `(document, registry) → document`. **TDD:** a body containing a registered boilerplate block
gets it replaced by a reference; non-matching blocks untouched; idempotent.

## P1.c — template STRIP + `template_id` stamp (needs `registries/templates` from P2.2 curation)

Using P2.2's curated `registries/templates/`: detect a body's `(doc_type, era)` template, **strip the
template scaffold**, and **stamp `template_id`** (per §9.8/ADR-018 — note: identity/computed-field
placement follows §6.3; `template_id` is identity-ish, decide its home with §6.3 as arbiter and record
the decision). Pure function over `(document, template registry)`. **TDD:** a body matching a registered
template has its scaffold stripped and `template_id` recorded; a non-matching body is untouched;
idempotent. This is the step that flips the last `normalize` deferral — after it lands, update the
tracker `normalize` row to **✅** and the Overall-status rollup.

---

## Definition of done (whole task)

- **P0:** `registries/` matches the §11 subdir layout (or §9.7 amended to bless the chosen layout);
  loaders repointed, all existing tests green; §8 `normalize` no longer over-claims; tracker notes added.
- **P2:** `kernel/discovery` is **used** by `discover` (near-dup boilerplate) — no dead code;
  `discover` emits `(doc_type, era)` template + `structures` candidates with evidence; curated starter
  `registries/templates` + `registries/structures` committed. `discover` still mutates no content.
- **P1:** all four F-steps shipped; `normalize` row flips to **✅**; §8 clauses all plain (done).
- Every increment: TDD (red → green), `make check` green (ruff · mypy · pytest random-order · cov ≥95%),
  its own commit with the `Co-Authored-By` trailer, tracker Change-Log entry (newest-first) + test-count
  / coverage line updated. **Do not push unless asked.**
- **No Phase 4+ work.** If any increment reveals a genuine design gap, **fix the design doc first**
  (doc-first) and say so in the commit.

## Real-corpus verification (after the relevant increments)

If the seeded 469-doc corpus is present in `~/data/vdocs` (`scripts/seed_from_v1.py` reproduces it
offline), run the affected stage over it and report counts:
- after P2: how many boilerplate clusters / `(doc_type, era)` templates / structures candidates flagged.
- after P1: tables extracted, boilerplate blocks referenced, templates stripped+stamped, on real docs.
Spot-check one doc per step to confirm the transform did the right thing (and stayed idempotent).
