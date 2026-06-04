# Code Review — Stage 4 (whole-pipeline compliance · quality · reliability · coherency)

**Date:** 2026-06-03 · **Branch reviewed:** `feat/phase-5-sidecar-verification` (tip `8f8cfc3`)
**Scope:** the entire `vdocs` codebase to date — spine + kernel, all 17 stages across the two
medallions, and the cross-cutting concerns. Reviewed against the source of truth
[`docs/vdocs-design.md`](vdocs-design.md), the QA companion
[`docs/fidelity-framework.md`](fidelity-framework.md), the
[`docs/doc-sidecar-design.md`](doc-sidecar-design.md) note, and the running
[`docs/vdocs-implementation-tracker.md`](vdocs-implementation-tracker.md).

**Method:** six parallel reviewers, each grounded in the design doc as authority (when code and the
doc disagree, the doc is the bug report), covering: (1) spine + kernel; (2) inventory medallion +
bronze (crawl·catalog·serve-inventory·fetch); (3) silver text (convert·discover·enrich·normalize);
(4) gold derive (consolidate·index·relate·manifest); (5) the Phase-5 verification slice
(capture.yaml·validate·bundle manifest); (6) a whole-codebase coherency/reliability sweep. The
highest-value findings were independently re-verified before inclusion.

---

## Verdict

**The codebase is in excellent shape and substantially faithful to the design.** No CRITICAL or HIGH
findings. The design-as-source-of-truth discipline is real and visible in the code: one shared
kernel, clean pure/IO split, atomic writes, fail-loud gates wired structurally (not by convention),
no mocks, property tests on every pure transform, and the tracker's documented "lessons" are
demonstrably internalized.

**Objective gate state (verified at review time):** 674 tests pass · ruff clean · mypy clean ·
**99% coverage** (gate ≥95%).

Findings cluster into **two themes, neither structural**, plus polish.

> **Remediation status (this session):** **Theme 1 (the §9.2 kernel-adoption findings) is FIXED**
> — see [§ Remediation log](#remediation-log) at the end. The rest is captured in the companion
> follow-up prompt [`prompts/code-review-stage-4-plan.md`](prompts/code-review-stage-4-plan.md).

---

## Theme 1 — Kernel primitives that exist but weren't uniformly adopted (genuine §9.2 violations) — ✅ FIXED

| Sev | Finding | Sites |
|---|---|---|
| **MEDIUM** | Read-only SQLite URI re-inlined instead of `kernel.db.connect(read_only=True)`. `db.py`'s own docstring says it is "the single place that knows connection pragmas," yet the `file:…?mode=ro` URI was spelled in 3 places — on the hot fingerprint/validate path a future pragma change (busy_timeout, `immutable=1`) would silently miss two of them. Independently flagged by 2 reviewers. | `models/artifact.py:138`, `kernel/fingerprint.py:63` |
| **MEDIUM** | Catalog kept its own `_MONTH` table + `normalize_date()` doing the identical `"DEC 2019"→"2019-12"` mapping that `kernel.text.month_year_iso` already does (and which `revision_pure`/`template_pure` were migrated onto). Unlike `make_doc_slug` (intentionally distinct, documented), this was not a justified local variant. | `stages/catalog/enrich_pure.py:54,98` |
| **LOW** | Inline `yaml.safe_load(read_text()) or {}` re-implemented `kernel.registry.load_mapping` six ways across three stages reading bundle sidecars. A naming/scoping gap (`load_mapping` was charter-scoped to *registries*). | `consolidate/stage.py:183,191`, `index/stage.py:240,251`, `validate/stage.py:192,205` |

A single small cleanup PR closed all three.

---

## Theme 2 — "Built ahead of consumer" surfaces (probably the documented deferral, but currently unreachable)

These read as missed wiring unless explicitly tracked — and the project's own lesson is that *"a
curated registry with no consumer is a silent deviation."* Confirm each is the intended deferral and
add an explicit tracker line so it doesn't become the next silent deviation.

| Sev | Finding | Detail |
|---|---|---|
| **MEDIUM** | `stages/fidelity/` (`compliance_pure.py`, `overstrip_pure.py`) is tested pure logic with **no stage, no contract, no DAG node, no CLI command** importing it (verified: nothing outside `stages/fidelity/` imports it). The tracker says broader-fidelity is the Phase-5 deferral (validate is the built slice), so this is *probably* intentional ahead-of-driver code — `overstrip.gate()` looks ready to be a `validate` input. Confirm it is the deferral, not a missed wiring. |
| **LOW** | `registries/glossary` + `gold/glossary.md`: `discover.mine_glossary` produces *candidates* but no stage consumes a curated glossary to *emit* it. Exact shape of the lesson that already bit `structures`→`normalize`. Likely a legit Phase-6 deferral — wants an explicit tracker line. |

---

## Other notable findings (per-stage)

- **MEDIUM — `merge_history` ordering robustness** — `consolidate/consolidate_pure.py:124-138`.
  Appends new members at the end and flags the *last* as `is_latest`. **Verified.** If a
  previously-*missed older* patch (lower `patch_num`) is acquired in a later run, it is appended
  after the newest and `is_latest` is mis-assigned — and `is_latest` drives the entire anchor-only
  search surface + the git-replay source. Narrow (VDL publishes monotonically) and currently
  **untested** for that case. Fix: re-sort after merge, or document the monotonic-publish
  precondition explicitly and add the late-older-patch test.

- **MEDIUM ×2 — residue re-scans not fully independent** (Phase-5 branch) —
  `normalize/capture_pure.py:116,140` + `normalize/tables_pure.py:128`. The design advertises
  residue predicates "deliberately broader than the detectors." True for revisions/toc (a real
  second signal, with real-corpus false-positive guards). **For `tables` and `refs` the residue
  re-uses the detector's own predicate** (`count_qualifying_tables` shares `_qualifies`; the `refs`
  residue keys on the same headings the anchor map is minted from) — so it is a post-condition, not
  an independent broad re-scan. A *threshold* miss on tables is invisible at the doc grain (the
  corpus-zero reconciliation still backstops whole-detector failure). Either broaden the tables
  residue (count *all* multi-row tables) or soften the design's "broader than the detectors" wording
  to match what the tables/refs residues actually are.

- **LOW — serve-inventory gate floor** — `serve_inventory/serve_pure.py:67`. The "at least one
  genuine document survives" floor counts `noise_type==""` rows that are PDF-only/out-of-scope, so
  it is weaker than §5.6 implies. Never trips on the real corpus (3,730 docx). Worth tightening to
  "at least one in-scope genuine document."

- **LOW — fetch re-downloads on a broadened selection** — `fetch/stage.py:63-110`. Reads prior
  acquisition only to accrue attempt counts; re-GETs every selected target. CAS dedups the bytes so
  no corruption, but it contradicts §5.6's "leaving prior `acquisitions` rows untouched," and the
  inline comment overstates `CHANGED_IN_PLACE` (not yet implemented — defensibly Phase-7). Tighten
  the code (skip `status==fetched` unless stale) or the spec wording.

- **LOW — `index._latest_doc_ids` tolerates a malformed `history.yaml` silently** —
  `index/stage.py:236`. A corrupt/truncated history yields empty members → that group's anchor
  silently gets `is_latest=0` corpus-wide (dropped from FTS + entity extraction) with no signal,
  contrary to fail-loud (tenet #7). Low because `validate`'s bundle-integrity gate catches on-disk
  tamper independently; an every-group-contributes-exactly-one-latest reconciliation would be more
  in keeping with the design.

---

## Polish / NITs (non-blocking)

- **~25 `# type: ignore[no-untyped-def]`** on driver helpers whose params are obviously
  `Path`/`sqlite3.Connection`/`Settings`. mypy is `strict = false`, so these suppressions are
  **self-imposed and inert** — annotating removes ~25 ignores and the `Any` they imply. Highest-value
  low-risk cleanup. (Sites across manifest/serve_inventory/consolidate/relate/enrich/normalize/
  catalog/index/validate/convert drivers.)
- **Inert `# noqa: BLE001`** on `consolidate/stage.py:76` (and absent on identical patterns in
  `convert`/`normalize`) — ruff only selects `E,F,I`, so `BLE001` is not active. Pick one
  convention.
- **Unstable sort tiebreak** `discover_pure.py:666` (`-c.xref_wraps` with no secondary key); the
  rest of the file uses `(-doc_count, key)`. Deterministic only because the input dict is.
- **Inconsistent `json.dumps(sort_keys=True)`** — manifest/validate use it; `fetch/stage.py:112`
  and `catalog/stage.py:50` omit it (stable today via ordered iteration, but the convention is not
  uniform).
- **`vectors.db` read as out-of-contract orchestrator state** rather than an `optional=True`
  ArtifactContract (`manifest/stage.py:44`). Functionally fine (no VECTORS contract exists until
  `embed`/Phase-6); align when that lands.
- **UA string duplicated** — `http.USER_AGENT` vs `Settings.user_agent`. Also note the literal is
  `github.com/rafael5/vdocs` vs the design's `vistadocs/vdl` push target.
- `kernel.Cas.link` enumerated in §9.2 but unimplemented (no consumer yet) — not a defect.
- `kernel.registry.load_mapping` annotated `-> dict` but `safe_load(...) or {}` returns a non-dict
  for a truthy non-mapping top level (e.g. a YAML list). Never bites (registries are dicts); an
  `isinstance(..., dict)` guard would make it sound.

---

## What is demonstrably *right* (confidence builders)

- **Gates genuinely gate** — wired via downstream `requires` + fail-loud `deep_gate`/postflight, not
  by convention. `fetch.requires=[GOLD_INVENTORY]`; `validate` blocks on absent-unexpected / severed
  ref / corpus-zero / count-drop / tampered bundle (9 integration tests prove block-on; the no-blind-
  download default holds — empty selection matches nothing).
- **Atomicity** — `cas.atomic_write` (fsync + content-skip + `os.replace`), `db.build_atomic`
  (DELETE-journal temp + WAL-orphan sweep), `replace_table_atomic` (`BEGIN IMMEDIATE`) all correct
  per §7.4, including the R7 WAL hardening.
- **"Signed bundle" is honestly scoped** — "signed = verifiable key-free content digest" stated
  identically in code, design, and tracker; no overclaim (a keyed GPG/cosign signature is explicitly
  a future increment). `bundle.yaml` correctly manifests every other part but not itself, written
  last; the prune keeps the on-disk set `== parts ∪ {bundle.yaml}`.
- **Discovery-is-data (tenet #13)** holds — no entity/boilerplate/TOC/template pattern hard-coded in
  stage code; all from `registries/`. The entity recognizer is genuinely registry-driven.
- **No copy-paste of heading/slug logic** — all five fence-aware heading scans use
  `kernel.markdown.iter_headings`; `anchor_key`/`doc_id` single-sourced in `kernel.ids`; the
  intentional `make_doc_slug` distinction is documented. This is the single biggest win vs. the v1
  duplication the design was written against.
- **Benign vs. silent absence is genuinely distinguished** (the Phase-5 DoD) — `absent-expected`
  (benign) is distinct from `absent-unexpected` (silent detector failure), and the gate fails loudly
  on the latter, at both the per-document and corpus grain. The revisions/toc residues are the real
  independent second signal, with real-corpus false-positive guards.
- **Test discipline** — every one of 22 `*_pure.py` modules has a unit test; pure transforms have
  property tests; **no mock library is used anywhere** (consistent with the no-mocks rule); no
  assert-less/tautological tests; per-doc isolation + rate-gate consistent across
  convert/normalize/consolidate; structlog throughout, no `print()` in library code.

---

## Recommended ordering (the follow-up prompt encodes this)

1. **Theme 1 kernel-adoption PR** — *done this session* (see below).
2. **Theme 2 tracker lines** — explicitly mark `fidelity/` pure code and `registries/glossary` as
   the Phase-5/6 deferral so they don't read as missed wiring.
3. **`merge_history`** — re-sort-after-merge (cheap) or document the monotonic-publish precondition +
   add the late-older-patch test.
4. **Tables/refs residue** — broaden to a true independent signal, or soften the design's "broader
   than the detectors" wording for those two classes.
5. **Easy reliability/coherency wins** — serve-inventory in-scope floor; fetch `status==fetched`
   skip (or spec fix); `index._latest_doc_ids` fail-loud; sort tiebreak + `sort_keys` consistency.
6. **Polish** — the `# type: ignore[no-untyped-def]` sweep (highest value/lowest risk), inert
   `# noqa` cleanup, UA dedup, `load_mapping` `isinstance` guard.

---

## Remediation log

**2026-06-03 — Theme 1 closed (TDD-first), `make check` green (677 tests, 99% cov, ruff+mypy clean).**

- **Read-only SQLite URI single-sourced (§9.2).** `kernel/fingerprint.py` and `models/artifact.py`
  now open read-only stores via `kernel.db.connect(path, read_only=True)`; the local `sqlite3`
  imports are gone. Locked by a new architectural guard test
  (`tests/unit/kernel/test_db.py::test_readonly_uri_is_single_sourced_in_kernel_db`) that asserts the
  `mode=ro` literal appears **only** in `kernel/db.py` (RED before the change: flagged both sites).
- **Catalog month table folded onto the kernel.** `stages/catalog/enrich_pure.py` dropped its private
  `_MONTH` dict; `normalize_date` keeps catalog's strict `MON YYYY` *field* anchoring (`_DATE_RE`)
  but routes the month→number conversion through `kernel.text.month_year_iso`. Behavior preserved
  byte-for-byte (new cross-consistency test asserts `normalize_date == month_year_iso` for the
  anchored case, and that embedded/4+-letter/non-month inputs stay unchanged).
- **`load_mapping` charter widened to any YAML mapping (registry *or* per-bundle sidecar).** Docstring
  updated; the six inline `safe_load … or {}` sidecar reads in `consolidate`/`index`/`validate` now
  call `kregistry.load_mapping(...)` (with `missing_ok=True` + `or None` where the caller distinguishes
  absent/empty from populated). Dead `import yaml` removed from `index` and `validate`. New test pins
  that an absent and an empty sidecar both collapse to `{}` (the property the call sites compose on).
