# Implementation prompt — Code-Review Stage 4 follow-ups (close the MEDIUM deviations + easy wins)

> Paste this whole file as the opening message of a fresh session. It is self-contained except for
> the repo itself — read the files it points at before writing code. This is a **multi-increment**
> task: each numbered increment below is its own TDD cycle and its own commit. Keep `make check`
> green between increments. **Do not** start unbuilt Phase 6+ stages (`embed`/`serve-mcp`) — out of
> scope. Theme 1 of the review (the §9.2 read-only-SQLite / catalog-month-table / `load_mapping`
> kernel-adoption findings) is **already fixed** — do not redo it.

## Context — why this exists

The full code review captured in [`docs/code-review-stage4.md`](../code-review-stage4.md) found the
codebase substantially design-compliant (no CRITICAL/HIGH; 674 tests, 99% cov, ruff+mypy clean) with
findings in **two non-structural themes** plus polish. **Theme 1 is done.** This task closes the
remaining **MEDIUM** findings and the **easy reliability/coherency wins**, each TDD-first.

Read [`docs/code-review-stage4.md`](../code-review-stage4.md) in full first — it has the precise
file:line for every finding and the rationale. This prompt is the execution plan over it.

## Read first (source of truth — read before writing code)

- `CLAUDE.md` — project rules. **Hard TDD**: write the test, confirm it fails, implement, confirm
  green, `make check` (ruff line 100 · mypy · pytest random-order · coverage ≥95%) before each
  commit. Pure logic in `*_pure.py` (zero I/O), thin I/O in `stage.py`; a primitive used by ≥2
  stages lives in `kernel/`; no `print()` (structlog). End commit messages with the required
  `Co-Authored-By` trailer. **Commit per increment; do not push unless asked.**
- `docs/vdocs-design.md` — the architectural source of truth. **If code and the doc disagree, the
  doc is the bug report — but a finding may instead mean the *doc* over-claims; in that case fix the
  doc.** Sections you will need are named per increment below.
- `docs/fidelity-framework.md` — C2 (sidecar completeness / count reconciliation) and C5
  (ref-resolution) for increment 4.
- `docs/vdocs-implementation-tracker.md` — flip status + add a Change Log entry + any Lessons after
  each increment (newest first), as every prior phase did.

**Execution order: 1 → 2 → 3 → 4 → 5 → 6.** 1–2 are doc/tracker-only (cheap, unblock clarity); 3–4
are the substantive MEDIUMs; 5–6 are the easy wins and polish. Each is independent — you may stop
after any increment with `make check` green.

---

### Increment 1 (doc/tracker only) — Theme 2: stop the "built-ahead-of-consumer" surfaces reading as missed wiring

The review flagged two surfaces that are *probably* intentional deferrals but currently look like
silent deviations (the project's own lesson: "a curated registry with no consumer is a silent
deviation").

1. **`stages/fidelity/`** (`compliance_pure.py`, `overstrip_pure.py`) — tested pure logic that **no
   stage/contract/DAG node/CLI command imports** (verified: nothing outside `stages/fidelity/`
   imports it). Confirm it is the documented Phase-5 `fidelity` deferral (validate is the built
   slice). Add an explicit line to `docs/vdocs-implementation-tracker.md` (the Phase-5 row and/or
   "Open follow-ups") stating these pure cores are built ahead of the `fidelity` driver, with the
   intended consumer (`overstrip.gate()` looks ready to be a `validate`/`fidelity` input). **No code
   change** unless you decide to wire `overstrip.gate()` into `validate` now — if so, that is
   increment 4's territory, do it there with tests.
2. **`registries/glossary` + `gold/glossary.md`** — `discover.mine_glossary` produces *candidates*
   but no stage consumes a curated glossary to emit it. Confirm it is the Phase-6 deferral and add a
   tracker "Open follow-ups" line so it is explicitly tracked, not implied-done.

**DoD:** the tracker names both surfaces as deferrals with their intended consumer; a future reader
cannot mistake either for missed wiring. `make check` unaffected.

---

### Increment 2 (doc only) — reconcile the "residue broader than the detectors" claim (the other half of increment 4)

This is the *documentation* half of the Phase-5 residue-independence finding; increment 4 is the
*code* half. Do whichever you prefer first, but land both. The design (§6.4, `capture_pure`
docstring) claims residue predicates are "deliberately broader than the detectors." That is true for
revisions/toc but **not** for tables/refs (their residue re-uses the detector's own predicate). If
you choose **not** to broaden the code (increment 4), then here you must soften the design wording to
state honestly that the tables/refs residue is a *post-condition over the detector's predicate*, not
an independent broader signal — and say why that is acceptable (the corpus-zero reconciliation
backstops whole-detector failure). Edit `docs/vdocs-design.md` §6.4 and `docs/fidelity-framework.md`
C2 to match reality. **Pick increment 2 or increment 4, not both contradicting each other.**

---

### Increment 3 (code, MEDIUM) — `merge_history` ordering robustness

**Finding:** `src/vdocs/stages/consolidate/consolidate_pure.py:124-138` (`merge_history`) appends
new members at the end of `existing["members"]` and flags the *last* element `is_latest`. If a
later run acquires a previously-missed **older** patch (lower `patch_num`), it is appended *after*
the current newest and `is_latest` is mis-assigned to the older member. `is_latest` drives the entire
anchor-only search surface (`index._latest_doc_ids`) and is the git-replay source — so a wrong
`is_latest` is corpus-visible.

**Read:** §6.6 (consolidate / `history.yaml` / ordering on `(patch_num, official_date, doc_slug)`),
and the 2026-06-02 Lesson about the stable tiebreak. Note `order_members` already exists in the same
module.

**TDD:** add a unit test in `tests/unit/stages/test_consolidate_pure.py` — build a history whose
existing members are `[patch 3, patch 5]` (5 = latest), then `merge_history` in a `fresh` containing
`patch 1` (an older, previously-missed member). Assert the merged `members` are ordered
`1, 3, 5` (oldest→newest) **and** `is_latest` is on `patch 5`, not on the appended `patch 1`.
Confirm RED. Then fix: after the append-only union, **re-sort the merged members by the same
`order_members` key** before assigning `is_latest = (i == last)`. Append-only (no member dropped, no
recorded fact mutated) must still hold — add/keep a property test asserting the merged `doc_id` set
equals the union and is order-independent. Also add a property/regression test that re-running with
identical membership is a no-op (idempotent) — that invariant must survive the re-sort.

**Alternative if you and the design owner prefer:** keep append-only-append and instead **document a
hard precondition** in §6.6 + the docstring that VDL publishes monotonically (no older patch ever
arrives after a newer one) and gate it — but the re-sort is cheaper and removes the foot-gun, so
prefer the re-sort.

**DoD:** late-older-patch test green; ordering + correct `is_latest` guaranteed regardless of
acquisition order; append-only + idempotency property tests still green. Update the §6.6 note and
add a Lesson.

---

### Increment 4 (code, MEDIUM) — make the tables (and optionally refs) residue a true independent second signal

**Finding:** `src/vdocs/stages/normalize/capture_pure.py:116` calls
`tables_pure.count_qualifying_tables`, which evaluates the **same** `_qualifies` predicate
(`tables_pure.py:55`) the extractor uses — so the residue is a post-condition, not the independent
*broader* re-scan the design advertises (§6.4). A *threshold* miss (a table that should have
qualified but didn't) is invisible at the document grain. The `refs` residue (`capture_pure.py:140`)
has the same shape (keys on the headings the anchor map is minted from).

**Read:** §6.4 typed capture-attempt subsection; `capture_pure` module docstring (the "deliberately
broader than the detectors" contract); `doc-sidecar-design.md` §5.2 (the worked "zero tables
corpus-wide ⇒ extraction broke" example).

**TDD (tables):** add a unit test in `tests/unit/stages/test_capture_pure.py` constructing a body
that contains a genuine multi-row data table the **detector's `_qualifies` rejects** but a broader
"any table with ≥2 rows and ≥2 columns" scan would catch; assert it surfaces as `absent-unexpected`
(or a residue hit) rather than being silently invisible. Confirm RED. Then implement a residue scan
in `capture_pure`/`tables_pure` that counts **all** multi-row pipe tables (the broad signal),
independent of `_qualifies`, and feed that into the `tables` outcome classification. Keep the
existing real-corpus false-positive guards green (do not regress revisions/toc).

**refs (optional, smaller payoff):** if you broaden refs too, the independent signal is "outbound
ref markers present in the body but `anchor_map.rows` under-populated" — a broader scan for
`[…](#…)`/`[[…]]` markers than the anchor pass mints. If you do **not** broaden refs, say so in
increment 2's doc edit.

**DoD:** the tables residue is genuinely independent of the extractor predicate; a threshold miss is
caught at the document grain; design wording (increment 2) matches the code. Property + unit tests
green; add a Lesson.

---

### Increment 5 (code, LOW — easy reliability wins) — three small guards

Each is a self-contained TDD cycle; group into one or two commits.

1. **serve-inventory in-scope floor** — `src/vdocs/stages/serve_inventory/serve_pure.py:67`.
   `evaluate_gate`'s "at least one genuine document survives" floor counts `noise_type==""` rows that
   are out-of-scope (PDF-only). Tighten to require at least one **in-scope** genuine document (read
   §5.6 for the out-of-scope semantics). **Note** `test_gate_fails_on_corrupt_inventory` currently
   relies on the weaker floor (its passing-shape record is `doc_format="pdf"`) — update that fixture
   so the test still asserts the intended failure. TDD: add a test where every genuine row is
   out-of-scope (zero fetchable docx) and assert the gate **fails** (systemic enrichment bug).

2. **`index._latest_doc_ids` fail-loud on malformed `history.yaml`** —
   `src/vdocs/stages/index/stage.py:236`. A corrupt/empty history currently yields empty members →
   that group's anchor silently gets `is_latest=0` (dropped from FTS + entities). Per tenet #7
   (fail-loud), add a reconciliation: every consolidated group should contribute **exactly one**
   latest `doc_id`; if a group's `history.yaml` yields zero latest members, raise/log-loud rather
   than silently dropping. TDD: a malformed history in one group → loud failure (or a counted,
   surfaced WARN that the postflight gate trips on), not a silent corpus hole.

3. **fetch `status==fetched` skip (or spec fix)** — `src/vdocs/stages/fetch/stage.py:63-110`. The
   driver re-GETs every selected target on a broadened selection, contradicting §5.6 ("leaving prior
   `acquisitions` rows untouched"). **Decide with the design:** either (a) skip targets whose
   acquisition `status=='fetched'` unless stale/forced — TDD: a broadened selection re-fetches only
   the *newly included* docs, prior rows untouched, prior bytes not re-downloaded; or (b) if the
   re-fetch is intentional (CAS dedups; cheap), fix the §5.6 wording + the overstated inline
   `CHANGED_IN_PLACE` comment to match. Prefer (a) — it matches the design and the comment.

**DoD:** each guard tested; `make check` green; tracker Change Log + any Lesson updated.

---

### Increment 6 (code, NIT — coherency polish) — the inert/self-imposed cruft

Lowest risk, highest tidiness. One commit.

1. **`# type: ignore[no-untyped-def]` sweep** (~25 sites across the stage drivers — manifest,
   serve_inventory, consolidate, relate, enrich, normalize, catalog, index, validate, convert).
   mypy is `strict = false`, so these are self-imposed and inert. Annotate the obvious params
   (`path: Path`, `conn: sqlite3.Connection`, `cfg: Settings`, etc.) and **delete the ignore
   comments**. Confirm mypy stays clean. Do **not** add `--check-untyped-defs` unless you intend to
   green the whole tree under it.
2. **Inert `# noqa: BLE001`** — `consolidate/stage.py:76` (and ensure convert/normalize match).
   ruff selects only `E,F,I`; `BLE001` is not active. Remove the inert noqa for consistency (the
   per-doc broad `except` is the intended, documented isolation pattern — keep the code, drop the
   misleading suppression).
3. **Deterministic sort tiebreaks** — `discover_pure.py:666` (`-c.xref_wraps` has no secondary key;
   match the file's `(-doc_count, key)` pattern) and add `sort_keys=True` to the `json.dumps` in
   `fetch/stage.py:112` and `catalog/stage.py:50` for byte-stability uniformity.
4. **`load_mapping` soundness** — `kernel/registry.py`: `safe_load(...) or {}` returns a non-dict for
   a truthy non-mapping top level. Add an `isinstance(loaded, dict)` guard (mirror
   `frontmatter.parse`) so the `-> dict` annotation is honest. TDD: a YAML file whose top level is a
   list → returns `{}` (or raises loud — pick and test).
5. **UA string dedup** — `kernel/http.USER_AGENT` vs `config.Settings.user_agent`: one should
   reference the other so they cannot drift. (Also flag, but do **not** silently change, the
   `github.com/rafael5/vdocs` vs design `vistadocs/vdl` discrepancy — confirm the canonical org with
   the owner first.)

**DoD:** ruff + mypy clean with fewer suppressions; no behavior change; tracker Change Log updated.

---

## Global Definition of Done

- Each increment: test-first (RED confirmed), implemented, `make check` green, its own commit with
  the `Co-Authored-By` trailer.
- `docs/vdocs-design.md` updated in the **same commit** as any behavior/wording change (doc-first
  rule); `docs/vdocs-implementation-tracker.md` gets a Change Log entry (newest first) + any Lesson +
  status flips per increment.
- No regression in the 677-test suite; coverage stays ≥95%.
- Do not push unless explicitly asked.
