# Implementation prompt — `normalize` F-step: `refs.yaml` anchor map + round-trip navigation

> Paste this whole file as the opening message of a fresh session. It is self-contained except for
> the repo itself — read the files it points at before writing code.

## Task

Finish the load-bearing deferred F-step of the `normalize` stage: build the **`refs.yaml` anchor
map**, **rewrite Word-bookmark link targets to GitHub slugs**, and **insert round-trip "↑ Back to
Contents" back-links**. This closes the real Phase-4 prerequisite — `index`/`relate`/`embed`/`serve-mcp`
all hang off a stable anchor substrate, and `refs.yaml` is the single home for it (design §6.7, §5.5).

This is **one coherent increment**. Do **not** also tackle the other deferred normalize steps
(`tables→csv`, boilerplate REFERENCE, template STRIP+STAMP, heading-level inference) — they are
later, separate slices.

## Read first (source of truth)

- `CLAUDE.md` — project rules. **Hard TDD**: write the test, confirm it fails, implement, confirm
  green, `make check` (ruff line 100 · mypy · pytest random-order · coverage ≥95%) before commit.
- `docs/vdocs-design.md` **§6.7** ("Table of contents — derived navigation with validated round-trip")
  — the authoritative spec for everything below. Also skim **§5.5** (anchor map / MCP URIs), the §6.5
  sidecar table (~line 601), and the §18 glossary entries for *Anchor map*, *Round-trip navigation*,
  *Table of contents* (~lines 1683–1690). If code and doc disagree, the doc wins — but this slice
  should need **no design edits**; the design already specifies all of it. You are making code match doc.
- Current code you are extending:
  - `src/vdocs/stages/normalize/normalize_pure.py` — already has `Heading`, `github_slug`,
    `parse_headings`, `recover_headings`, `strip_artifacts`, `subtract_phrases`, `regenerate_toc`,
    `build_toc`, `strip_existing_toc`, `normalize_body`.
  - `src/vdocs/stages/normalize/revision_pure.py` — the existing sibling pure module + its
    `history.yaml` sidecar pattern (mirror it).
  - `src/vdocs/stages/normalize/stage.py` — the thin I/O driver; it already writes the `history.yaml`
    sidecar conditionally. Add the `refs.yaml` write the same way.
  - `tests/unit/stages/test_normalize_pure.py`, `tests/unit/stages/test_normalize_stage.py`,
    `tests/property/` (the existing normalize property test) — match their conventions.

## The gap (root cause)

The Word bookmark id is currently **thrown away**. `recover_headings` strips `<span id="_Toc…">`
spans and `parse_headings` ignores them, so:
1. in-body cross-references like `[Intro](#_Toc1234)` (Pandoc/v1's measured reality) can never be
   rewritten to `#introduction` → they stay **dead on GitHub**;
2. there is no `(stable_section_id ↔ github_slug ↔ original_bookmark)` record for downstream stages;
3. there are no "↑ Back to Contents" back-links → round-trip integrity (a `validate` hard-gate axis) is unmet.

## What to build

Add a new pure module **`src/vdocs/stages/normalize/anchors_pure.py`** (keep `normalize_pure` focused;
mirror the `revision_pure` split). Plus a small `Heading` change and the stage sidecar write.

### (a) Extend `Heading` to carry its bookmark + stable id
```python
@dataclass(frozen=True)
class Heading:
    level: int
    text: str
    slug: str
    bookmark: str | None   # the _Toc…/_Ref… id Pandoc attached to this heading, if any
    stable_id: str         # see Decision 1
```
`parse_headings` (and `recover_headings`) must **capture** the `_Toc…`/`_Ref…` id on, or on the line
immediately above, a heading — for both late-gen docs (span sits on the real `##` line) and old-gen
docs (span is the recovery seed) — instead of silently dropping it.

### (b) `build_anchor_map(headings, doc_id, toc_depth) -> AnchorMap`
The pure record that serializes to `refs.yaml`. One row per heading:
`(stable_section_id, github_slug, original_bookmark, level, title, toc_level)` where `toc_level` marks
whether the heading is in-TOC at the chosen depth. Also carries the doc's chosen `toc_depth` and the
outbound link map (below).

### (c) `rewrite_link_targets(body, bookmark_to_slug) -> (body, outbound_map)`
Rewrite every `](#_Toc…)` / `](#_Ref…)` target to `](#slug)`. Targets with no mapping are recorded as
`UNRESOLVED` in the outbound map (a fidelity signal — **do not crash**, leave them untouched in the
body). Then drop the now-redundant `<span id="_Toc…">` anchors (GitHub mints slug anchors from heading
text automatically).

### (d) `insert_back_links(body, headings, toc_depth)`
Under each TOC-targeted heading insert `[↑ Back to Contents](#contents)`. **Idempotent**: strip any
existing back-link first (same approach as `strip_existing_toc`). Out-of-depth headings (e.g. H4+ under
the default) get no back-link.

### (e) New F-step order in `normalize_body` (order matters for idempotency)
```
recover_headings → strip_artifacts → subtract_phrases
  → [parse heading tree once, with bookmarks]
  → rewrite_link_targets        # uses bookmark→slug from the tree
  → regenerate_toc              # uses the same slugs (keep TOC + map consistent)
  → insert_back_links
```
Change `normalize_body` to **return `(body, anchor_map)`** so the stage can write `refs.yaml`. Update
all existing callers/tests accordingly.

### (f) Stage write (`stage.py`)
Write `refs.yaml` next to `body.md` exactly like `history.yaml` is written today — **conditionally**
(only when there are headings/anchors), via `cas.atomic_write` + `yaml.safe_dump(..., sort_keys=False,
allow_unicode=True)`. Add a `refs_sidecars` count to `RunResult.counts`.

## Two decisions (pinned — proceed with these)

1. **`stable_section_id = "<doc_id>/<slug>"`.** Human-readable, stable while the heading text is
   stable, and the same identity MCP URIs will use. It churns on retitle — record that tradeoff in a
   code comment and let the future `index` stage own ID *persistence* across runs. (If you find a
   strong reason to prefer position ids `sec-0001`, raise it before coding rather than switching silently.)
2. **TOC depth = H2–H3 fallback.** §6.7 wants template-governed `toc_level`, but `registries/templates`
   isn't built yet. Ship the **H2–H3 fallback** and record `toc_depth: [2, 3]` in `refs.yaml`; leave a
   clearly-marked seam where the template hook wires in when the template F-step lands. H1 is the doc
   title, never a TOC entry.

## TDD test list (write first, confirm red, then implement)

`tests/unit/stages/test_anchors_pure.py`:
1. `test_parse_headings_captures_toc_bookmark` — a `##` heading with an inline `<span id="_Toc1234">`
   yields `Heading.bookmark == "_Toc1234"`; a heading without one yields `None`.
2. `test_rewrite_link_targets_maps_bookmark_to_slug` — `[Intro](#_Toc1234)` → `[Intro](#introduction)`.
3. `test_rewrite_link_targets_records_unresolved` — `](#_Toc9999)` with no heading lands in the
   outbound map as `UNRESOLVED` and is left untouched in the body (no crash).
4. `test_rewrite_drops_redundant_bookmark_spans` — `<span id="_Toc…">` anchors are gone from the output.
5. `test_build_anchor_map_rows` — one row per heading with `(stable_id, slug, bookmark, level, title,
   toc_level)`; duplicate titles get `-1`/`-2` slugs matching the TOC.
6. `test_insert_back_links_under_toc_headings` — each in-TOC heading is followed by
   `[↑ Back to Contents](#contents)`; out-of-depth headings are not.
7. `test_back_links_idempotent` — running twice inserts exactly one back-link.
8. `test_normalize_body_roundtrip_idempotent` — `normalize_body(normalize_body(x)) == normalize_body(x)`
   for body **and** anchor map (extend the existing idempotency assertion).
9. `test_anchor_map_every_toc_entry_resolves` — §6.7 hard-gate invariant at unit level: zero TOC
   entries point at a slug absent from the anchor map.

`tests/unit/stages/test_normalize_stage.py` (extend):
10. `test_normalize_writes_refs_yaml_sidecar` — a bundle with cross-refs produces a parseable
    `refs.yaml` next to `body.md`, with the anchor map + `toc_depth`.
11. `test_no_refs_yaml_when_no_headings` — a heading-less bundle writes no `refs.yaml`;
    `counts["refs_sidecars"]` reflects it.

`tests/property/` (extend the existing normalize property test):
12. "no anchor points nowhere" (design §13, ~line 1374): for any generated heading tree, every
    rewritten link target resolves into the anchor map.

## Contract / doc / tracker touch-ups (same commit, per CLAUDE.md)

- `TEXT_NORMALIZED` is `Kind.TREE_TEXT` and validates the whole bundle tree, so `refs.yaml` needs
  **no new contract** — but note it as a recognized sidecar in the `stage.py` / module docstrings
  (as `history.yaml` is).
- **No `docs/vdocs-design.md` changes expected** (design already specifies this). If you discover a
  genuine mismatch, fix the doc first and say so.
- `docs/vdocs-implementation-tracker.md`: in the `normalize` row, move `refs.yaml + back-links +
  bookmark rewrite` from **Deferred** to shipped; keep `tables→csv`, boilerplate REFERENCE, template
  STRIP+STAMP, heading-level inference deferred (the next slices, in that order). Add a **Change Log**
  entry (newest first) and any **Lessons Learned** if real behavior surprises you. Update the test
  count + coverage line.

## Definition of done

- All 12 tests above green; `make check` green (ruff · mypy · pytest random-order · coverage ≥95%).
- `normalize_body` returns `(body, anchor_map)`; stage writes `refs.yaml` conditionally with a count.
- In-body `_Toc`/`_Ref` cross-refs resolve to GitHub slugs; every in-TOC heading has a back-link;
  every TOC entry resolves to a real anchor.
- Tracker updated, Change Log appended. Commit (do not push unless asked); end the commit message with
  the required `Co-Authored-By` trailer.

## Optional verification on the real corpus

If the seeded 469-doc corpus is present in `~/data/vdocs` (`scripts/seed_from_v1.py` reproduces it),
run `normalize` over it and spot-check a doc known to have `_Toc` cross-refs (e.g. a CPRS RN) to
confirm dead `#_Toc…` links became live `#slug` links and `refs.yaml` is sane. Report counts.
