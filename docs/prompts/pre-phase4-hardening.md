# Implementation prompt — pre-Phase-4 hardening (reliability · non-redundancy · doc reconciliation)

> Paste this whole file as the opening message of a **fresh, clean session**. It is self-contained
> except for the repo itself — **read the files it points at before writing code.** This is a
> **multi-increment** task: each numbered increment is its own TDD cycle and its own commit. Keep
> `make check` green between increments. **Do NOT start Phase 4+ stages** (`consolidate`/`index`/
> `relate`/`embed`/`fidelity`/`manifest`/`publish`/`validate`/`push`/`serve-mcp`) — out of scope.

## Context — why this exists

A comprehensive review of the **built scope** (Phases 1–3: the 8 stages `crawl · catalog ·
serve-inventory · fetch · convert · discover · enrich · normalize` + the spine) against
`docs/vdocs-design.md` found the code **structurally sound and substantially faithful**: §8 contracts
match exactly, the pure/I-O split is clean, the orchestrator derives DAG order from contracts, config
is centralized, `make check` is green (414 tests, 100% line / 99.7% branch). **No P0 correctness
defects; no false ✅ status claims.**

What the review *did* surface are (1) **reliability gaps** that don't show up in single-run unit tests
but bite on real multi-run / large-corpus / incremental use, (2) **§9.2 anti-duplication violations**
(markdown primitives copy-pasted across the `normalize` stage), (3) a few **design-vs-code
reconciliations** (the doc is the source of truth), and (4) the **property-test breadth gap** the
tracker already marks ◐. This task closes all of them, then regenerates the data lake so it reflects
the new pipeline output.

## Sequencing — and why this order

Dependency- and risk-ordered. Do the phases in order; increments within a phase are independent unless
noted.

1. **Phase A — hygiene & naming** first: delete dead code and resolve the latent `history.yaml`
   filename collision *before* later increments reference those names.
2. **Phase B — redundancy consolidation** next: establish the single kernel markdown/slug primitives
   **while tests are green**, so the reliability fixes and new property tests land on a clean
   foundation (this also finishes the `#+` heading-regex unification across all four modules).
3. **Phase C — reliability**: behavioral fixes, each TDD; kernel-level fixes before the stage-level
   ones that may touch them.
4. **Phase D — property tests**: lock in the idempotency/round-trip invariants the consolidation and
   fixes depend on; enable branch coverage in the gate.
5. **Phase E — doc reconciliation**: bring §8 / §6.6 / §6.7 + the tracker into agreement with the
   final code state (doc-first where a decision was made).
6. **Phase F — regenerate & verify**: rebuild the deterministic document plane from bronze so **all
   data in `~/data/vdocs` reflects the current pipeline output** (a standing project requirement).

## Decisions already made (defaults — do not re-litigate; proceed unless you find a hard blocker)

- **D-dec-1 (catalog drift, finding C1):** §8 names `catalog` as the drift detector
  (NEW/SUPERSEDED/CHANGED/UNCHANGED/WITHDRAWN), but drift requires comparing against prior state — a
  *temporal* property — and the deterministic `catalog.enriched` artifact must stay a **pure function
  of one crawl**. **Decision: reword §8 (doc-first) to relocate drift ownership to the §7.6 scheduled/
  incremental layer (Phase 7); do NOT implement drift now.** (Increment E1.)
- **D-dec-2 (`history.yaml` collision, finding C2):** `normalize` emits `history.yaml` = the in-body
  revision *table*; §6.6 has the unbuilt `consolidate` emit `history.yaml` = version-group *lineage*.
  **Decision: rename `normalize`'s sidecar to `revisions.yaml`** and reconcile §6.4/§6.6 so
  `consolidate`'s `history.yaml` is unambiguous. (Increment A2.)
- **D-dec-3 (skip-defeat fix, finding R2):** **Decision: content-skip in `kernel.cas.atomic_write`** —
  when the new bytes hash-match the existing file, do **not** rewrite (preserve mtime), so the cheap
  `size:mtime_ns` fingerprint stays stable across no-op re-runs. (Increment C-rel-1.)
- **D-dec-4 (dead `exact_jaccard`, finding D5):** **Decision: KEEP `kernel.discovery.exact_jaccard`**
  but make it earn its place as the **reference oracle** for the new `estimate_jaccard` property test
  (Phase D) and add a one-line docstring saying so; **delete `convert_pure.image_targets`** (truly
  dead) + its test. (Increments A1 / D.)
- **D-dec-5 (serve-inventory "sane distributions", finding C4):** **Decision: add minimal bounded
  distribution assertions** to the gate (it *is* the fetch gate) rather than soften §8. (Increment E1.)

## Read first (source of truth — read before writing code)

- `CLAUDE.md` — project rules. **Hard TDD**: write the test, confirm it fails, implement, confirm
  green, `make check` (ruff line 100 · mypy · pytest random-order · coverage ≥95%) before each commit.
  Pure logic in `*_pure.py` (zero I/O); thin I/O in `stage.py`; **a primitive used by ≥2 stages lives
  in `kernel/`** (§9.2 — copy-paste across stages is a build-breaking review failure); no `print()`
  (structlog). End commit messages with the required `Co-Authored-By` trailer. **Commit per increment;
  do NOT push unless asked.**
- `docs/vdocs-design.md` — architectural source of truth. **If code and doc disagree, the doc is the
  bug report.** Sections by phase (grep for the exact line — these are approximate):
  - **§5.6** fetch selection (~506); **§6.4/§6.5** decomposition + don't-over-decompose (~607/628);
    **§6.6** version lineage / `history.yaml` (~634); **§6.7** TOC derivation (~699).
  - **§7.3** preflight/postflight (~828); **§7.4** atomicity & idempotency (~848); **§7.6**
    scheduled/incremental + drift (~863).
  - **§8** stage/contract table (~904–1006) — the `normalize` row sidecars + the drift notes.
  - **§9.2** shared kernel anti-duplication (~1018); **§9.5** observability & failure (~1059);
    **§9.6** discovery loop (~1069); **§11** repo layout (~1339); **§12** testing strategy (~1402).
- `docs/vdocs-implementation-tracker.md` — Change Log conventions (newest-first); you update it in the
  **same commit** as each increment, and refresh the test-count line at the end.
- The review findings are reproduced in the tables below — each cites the exact `file:line`.

---

# Phase A — hygiene & naming

## A1 — Remove dead code (finding D5)

- **Delete** `convert_pure.image_targets` (`src/vdocs/stages/convert/convert_pure.py:59`) and its test
  in `tests/unit/stages/test_convert_pure.py`. Confirm zero `src/` callers first
  (`grep -rn image_targets src`).
- **Keep** `kernel.discovery.exact_jaccard` (`src/vdocs/kernel/discovery.py:35`); add a one-line
  docstring noting it is the reference oracle for the `estimate_jaccard` property test (added in
  Phase D). It stops being dead once that test lands.
- **TDD:** removing `image_targets` should leave the suite green after deleting its test; no new
  behavior. Commit.

## A2 — Rename `normalize`'s revision sidecar `history.yaml` → `revisions.yaml` (finding C2 / D-dec-2)

- In `src/vdocs/stages/normalize/` (the `revision_pure` sidecar write in `stage.py`), change the
  emitted filename from `history.yaml` to `revisions.yaml`; rename the `history_sidecars` count key to
  `revision_sidecars`.
- Reconcile **§6.4/§6.6** in `docs/vdocs-design.md`: `normalize` → `revisions.yaml` (extracted in-body
  revision table); `consolidate` (Phase 4) → `history.yaml` (version-group lineage). Update the §8
  `normalize` row's sidecar list accordingly.
- **TDD:** update `tests/integration/stages/test_normalize_stage.py` + any unit test asserting the
  `history.yaml` sidecar / count key; confirm the new name is written and the old one is not. Commit
  (code + design doc in the same commit, per CLAUDE.md).

---

# Phase B — non-redundancy (§9.2 consolidation)

| # | Finding | Locations | Target |
|---|---------|-----------|--------|
| D1 | `_TAG_RE = <[^>]+>` defined 5× | `kernel/text.py:17`, `kernel/table.py:18`, `normalize/{anchors,normalize,revision}_pure.py` | one `kernel.text.strip_tags` / shared `TAG_RE` |
| D2 | heading/fence parse + fence-aware scan loop 4–5×; `#+` vs `#{1,6}` divergence | `normalize_pure`, `anchors_pure`, `template_pure`, `discover_pure` | new `kernel/markdown.py` |
| D3 | slug generation 3× with divergent regex (`-` vs `_`, fallback) → latent index-join bug | `kernel.text.github_slug_base`, `discover_pure._slug:391`, `catalog/enrich_pure.make_doc_slug:130` | one `kernel.text.slugify(text, *, sep, fallback)` |
| D4 | URL→basename→ext 2–3×; `" ".join(s.lower().split())` 5×; `_MULTI_BLANK`/`_WS_RE` dup | crawl/fetch/catalog; normalize/discover/kernel | kernel URL helper + `kernel.text.collapse_ws_lower` |

## B1 — `kernel/markdown.py`: the single markdown-primitive home (D1, D2)

Create `src/vdocs/kernel/markdown.py` owning the canonical markdown primitives and migrate every
copy onto it:
- `HEADING_RE` (canonical = **`^(#+)\s+(.*?)\s*$`**, i.e. `#+` — the divergence resolution: all callers
  recognize >6-hash headings consistently, matching the `e1e3b44` fix), `FENCE_RE`, `MULTI_BLANK`,
  and a `strip_tags(s)` / shared `TAG_RE`.
- A fence-aware generator `iter_headings(body) -> Iterator[(line_idx, level, text)]` that the five
  call sites consume instead of re-implementing the toggle-`in_fence`-match-heading loop:
  `normalize_pure.infer_heading_levels`, `anchors_pure.parse_headings` + `insert_back_links`,
  `template_pure.strip_template_scaffold`, `discover_pure.parse_scaffold`.
- Migrate `normalize_pure`, `anchors_pure`, `template_pure`, `discover_pure` to import these. **Note
  the behavior delta:** `template_pure` and `discover_pure` move from `#{1,6}` → `#+`, so they now
  recognize oversized headings too — this is the intended unification.
- **TDD:** write `tests/unit/kernel/test_markdown.py` first (HEADING_RE on 1–11 hashes, FENCE_RE,
  `iter_headings` skips fenced code + the generated `## Contents`, `strip_tags`). Add cases proving
  `template_pure`/`discover` now handle a >6-hash heading. Existing normalize/anchors/discover tests
  must stay green. Commit.

## B2 — `kernel.text.slugify`: one slug primitive (D3)

- Add `kernel.text.slugify(text, *, sep="-", fallback="")`; refactor `github_slug_base`,
  `discover_pure._slug`, and `catalog/enrich_pure.make_doc_slug` to call it (catalog keeps `sep="_"`
  for filesystem slugs; discover + anchors use `sep="-"` so a section's slug now **matches** the
  GitHub anchor `normalize` emits — closes the latent `index`-join divergence).
- **TDD:** unit test that `discover`'s section slug for a heading == `anchors`' GitHub slug for the
  same heading; catalog's `_`-separated slug unchanged. Commit.

## B3 — URL/text helper dedup (D4) — *optional, do if time permits*

- Add a kernel URL helper (`url_basename` / `url_ext`) used by crawl/fetch/catalog, and
  `kernel.text.collapse_ws_lower(s)` used by normalize/discover/template/`kernel.discovery`.
- **TDD:** unit tests for each; refactor call sites; existing tests green. Commit. (Skip if it risks
  destabilizing Phase C; it is the lowest-value redundancy item.)

---

# Phase C — reliability

| # | Sev | Finding | Location |
|---|-----|---------|----------|
| R1 | High | `fetch` overwrites `raw/index.json` with only the current selection — selective re-fetch drops prior docs; `convert` then skips them | `fetch/stage.py:55,107` |
| R2 | High | mtime `size:mtime_ns` fingerprint + unconditional rewrites defeat `SKIP_IF_UNCHANGED` | `fingerprint.py:46`; all `stage.py` writes |
| R3 | High | uncaught `httpx.TransportError` aborts the whole crawl/fetch (retries only on 429/5xx) | `http.py:94-114` |
| R4 | Med | no tree-level atomicity — §7.4 wants `OUT.tmp/`→rename; only per-file atomic writes exist | silver-tree producers; `cas.py:16` |
| R5 | Med | no stale-output pruning — WITHDRAWN/renamed doc leaves a ghost bundle read as live (§7.6) | all silver-tree producers |
| R6 | Med | no per-document error isolation — one bad doc aborts the batch (after partial writes) | `convert/stage.py:52-72`, `normalize/stage.py:66-116` |
| R7 | Med | `build_atomic` builds in WAL mode but renames only the main DB file — orphans `.tmp-wal`/`.tmp-shm` | `db.py:50,61` |
| R8 | Low | malformed frontmatter (`yaml.safe_load`) crashes the run | `frontmatter.py:44` |
| R9 | Low | `sqlite_fingerprint` strong mode hashes `repr(row)` ordered `BY 1` (undefined tie order) | `fingerprint.py:69-71` |

Do kernel-level fixes (C-rel-1,2,3,4,5) before stage-level (6,7), since the stage fixes may rely on
them. Each is its own TDD commit.

## C-rel-1 — R2: content-skip in `atomic_write` (D-dec-3)

Make `kernel.cas.atomic_write(path, data)` a no-op when `path` exists and `sha256(existing) ==
sha256(data)` (don't rewrite, preserve mtime). Keep the temp+fsync+`os.replace` path for the
write-needed case. **TDD:** writing identical bytes twice leaves `st_mtime_ns` unchanged; writing
changed bytes updates it; assert via a real temp file. This is what makes the default cheap
fingerprint honest about `SKIP_IF_UNCHANGED`.

## C-rel-2 — R7: `build_atomic` WAL hardening

Build the temp DB so no WAL siblings survive the rename: either open the temp connection in
`journal_mode=DELETE` (add a flag to `kernel.db.connect`, used only for the atomic-build temp), or
`PRAGMA wal_checkpoint(TRUNCATE)` + `journal_mode=DELETE` before `close()`. On both success and
failure paths, unlink any `.<name>.tmp-wal` / `.<name>.tmp-shm`. **TDD:** after `build_atomic`, no
`-wal`/`-shm`/`.tmp*` files remain beside the built DB and it reads back the written rows.

## C-rel-3 — R9: deterministic strong sqlite fingerprint

`sqlite_fingerprint` strong mode: `ORDER BY rowid` (or the table's full PK), and hash typed cell
values (e.g. join `str(v)` over `row` cells) instead of `repr(row)`. **TDD:** two byte-identical DBs
built in different insert orders produce the same strong fingerprint; a one-cell change differs.

## C-rel-4 — R3: retry crawl/fetch on transport errors

In `kernel.http._request`, wrap the `self._client.get(url)` so `httpx.TransportError` (connect/read
timeouts, protocol errors) is retried in the same backoff loop as 429/5xx; on exhaustion return the
same error/`None` the driver already treats as a skippable WARN (matching the module's "skip a bad
page, never abort" docstring + §3.6). **TDD:** a fake transport that raises `ReadTimeout` N-1 times
then succeeds returns the body; raising every time returns the skip sentinel, not an exception.

## C-rel-5 — R8: guard malformed frontmatter

In `kernel.frontmatter.parse`, wrap `yaml.safe_load` in try/except `yaml.YAMLError` → log a WARN
(structlog) and treat the document as having no frontmatter (isolate the one bad doc rather than
aborting `normalize`/`enrich`). **TDD:** a body whose `---` block is malformed YAML parses to
"no frontmatter" + the body intact, no exception.

## C-rel-6 — R1: `fetch` merges `raw/index.json`

`fetch` must read the existing `raw/index.json` (if present), merge this run's `{sha: entry}` into it
(new keys + updated entries), and write the union — never an overwrite that drops previously-fetched
docs. **TDD:** fetch selection #1 (e.g. one app) then selection #2 (a different app); the final
`raw/index.json` contains **both** apps' entries; `select_fetch_targets` ordering stays deterministic.

## C-rel-7 — R6: per-document error isolation in `convert` + `normalize`

Wrap each per-document iteration in `convert/stage.py` and `normalize/stage.py` in try/except: on a
single-doc failure, log a WARN with the doc id, increment an `errors` count, and `continue` (don't
abandon the batch). Surface `errors` in the `RunResult.counts`; have postflight **fail the stage** only
if the error rate exceeds an explicit threshold (a named constant — not a silent swallow; §9.5).
**TDD:** a batch where one doc raises still processes the rest and reports `errors=1`; an all-fail
batch fails the stage.

## C-rel-8 — R4 + R5: tree-level atomicity + stale-output pruning (LARGEST — may split)

> This is the biggest change and **may become its own follow-up PR** if it balloons; if you split it,
> land R5 (pruning) first (simpler) and note the split in the tracker.

§7.4 specifies each tree-producing stage writes to `OUT.tmp/` and atomic-renames to `OUT/`. Implement
this for the silver-tree producers (`convert`/`enrich`/`normalize`/`discover` outputs) in a way that
**preserves the C-rel-1 content-skip**: build the new tree by hardlinking unchanged bundles from the
current `OUT/` and writing only changed/new ones into `OUT.tmp/`, then atomic-rename. This gives both
crash-atomicity (R4) and stale-output pruning (R5: a bundle whose input vanished is simply absent from
the new tree). **TDD:** (a) a simulated mid-stage crash leaves the prior `OUT/` intact (no partial
tree visible); (b) a doc removed from the input set leaves no ghost bundle in the new `OUT/`;
(c) an unchanged doc's bundle keeps its mtime (content-skip preserved). If the orchestrator's
tree-fingerprint/preflight needs to learn about the tmp-dir convention, update it (it owns the
artifact-usable check, `artifact.py`).

---

# Phase D — property tests (finding: §12 / toolchain mandate; tracker ◐)

Add Hypothesis `@given` property tests for the pure transforms whose idempotency/round-trip/invariants
are currently asserted only as fixed examples. Put them under `tests/property/`. **TDD spirit applies:
expect the CSV one to actually find a bug** (current examples never feed cells with commas/quotes/
newlines). Priority order:

1. `kernel.csv.to_csv` round-trip with adversarial cells (commas, embedded quotes, newlines) — fix any
   escaping bug it surfaces.
2. `normalize_pure.normalize_body` idempotency over generated heading trees (§12's literal example).
3. `anchors_pure.github_slug` determinism + uniqueness + monotonic `-N` suffix.
4. `tables_pure.extract_tables` idempotency over randomly-shaped tables.
5. `revision_pure` HTML↔pipe dialect equivalence + `_norm_date` idempotency.
6. `kernel.fingerprint.tree_fingerprint` order-independence + single-byte sensitivity.
7. `kernel.discovery.estimate_jaccard` ≈ `exact_jaccard` within tolerance (this is what makes
   `exact_jaccard` a live reference oracle — closes A1's note).

Also: enable `--cov-branch` in the `make check` coverage gate and register a Hypothesis profile
(`max_examples`, deadline) in `tests/conftest.py` (`pyproject.toml:41-46` is where coverage config
lives). Commit (can be one commit for the property suite + config, or split per transform).

---

# Phase E — doc reconciliation & tracker

One commit (or a few) of doc-only changes bringing the design + tracker into agreement with the final
code:

- **C1 / D-dec-1:** reword §8's drift notes so drift ownership sits in the §7.6 scheduled/incremental
  layer (Phase 7), not `catalog`. State that `catalog.enriched` is a pure function of one crawl.
- **C3:** amend §6.7 to note `strip_legacy_toc` also recognizes >6-hash (invalid-GFM, upstream-
  artifact) legacy-TOC headings, and add the missing Change Log entry for commit `e1e3b44`.
- **C4 / D-dec-5:** (code) add bounded distribution assertions to `serve_pure.evaluate_gate` (e.g.
  genuine ≥ a sane floor, each `doc_format`/`section_code` bucket non-empty) so the §8 "sane
  distributions (crawl-spec §7)" clause is actually enforced — with a unit test. (This one carries a
  test, so it's really a small code+doc increment; place it here or fold into Phase C if you prefer.)
- **C5:** refresh the tracker test-count line and the stale "origin tip" SHA / merge framing.
- **Tracker Change Log (newest-first):** one entry summarizing this whole hardening pass (reliability
  R1–R9, redundancy D1–D5, the property suite, the `revisions.yaml` rename, the drift-doc
  reconciliation). Bump the test-count + coverage line.

---

# Phase F — regenerate the data lake & verify (standing requirement)

Several fixes change pipeline output (R1 index merge, R6 isolation, the B1 `#+` unification affecting
`discover`/`normalize`, the A2 `revisions.yaml` rename). After the code is green, regenerate the
**deterministic document plane from the immutable bronze evidence** so all data in `~/data/vdocs`
reflects current code. The lake is already in the canonical `documents/{bronze,assets,silver}` +
`inventory/{bronze,silver,gold}` layout.

**Do NOT re-crawl or re-fetch** — `crawl`/`fetch` are network stages; their outputs
(`inventory/bronze/catalog.raw.json`, `documents/bronze/raw/` = 469 docx, `state.db` acquisitions) are
immutable inputs. Preserve them. Regenerate everything computable from them, in DAG order:

```bash
.venv/bin/vdocs catalog --force
.venv/bin/vdocs serve-inventory --force
.venv/bin/vdocs convert --force        # pandoc over 469 docx (~4–5 min)
.venv/bin/vdocs discover --force
.venv/bin/vdocs enrich --force
.venv/bin/vdocs normalize --force
```

**Verify (report counts):**
- `documents/silver/text/03-normalized/CPRS/cprsguium/body.md`: 0 legacy `heading<TAB>page` lines,
  0 `########### Table of Contents`, exactly one `## Contents`.
- corpus-wide: 0 / 469 bundles with any `^#{7,} ` heading or tab+page-number TOC line.
- each normalized bundle now carries `revisions.yaml` (not `history.yaml`).
- 469 normalized bundles; spot-check one doc per changed transform for correctness + idempotency.

---

## Definition of done (whole task)

- **Phase A:** `image_targets` gone; `exact_jaccard` documented as the oracle; `normalize` emits
  `revisions.yaml`; §6.4/§6.6/§8 reconciled.
- **Phase B:** one `kernel/markdown.py` + one `kernel.text.slugify`; no markdown/slug primitive defined
  in ≥2 places; `#+` heading recognition uniform across all four modules; discover's section slug
  matches the GitHub anchor.
- **Phase C:** R1–R9 closed, each with a regression test; `SKIP_IF_UNCHANGED` actually skips on no-op
  re-runs; crawl/fetch survive transport flakiness; one bad doc no longer aborts a stage; tree writes
  are crash-atomic and prune orphans (or R4/R5 split out with a tracker note).
- **Phase D:** the 7 property tests added; `--cov-branch` in the gate; Hypothesis profile registered.
- **Phase E:** §8 drift reworded; §6.7 oversized-heading note + the `e1e3b44` Change Log entry; the
  gate enforces bounded distributions; tracker counts/tip refreshed; one Change Log entry for the pass.
- **Phase F:** data lake regenerated from bronze (no re-fetch); verification counts reported.
- Every increment: TDD (red → green), `make check` green (ruff · mypy · pytest random-order · cov
  ≥95%), its own commit with the `Co-Authored-By` trailer + tracker Change-Log entry. **Do NOT push
  unless asked.**
- **No Phase 4+ work.** Where a fix and the design disagree, **fix the design doc first** (doc-first)
  and say so in the commit.
