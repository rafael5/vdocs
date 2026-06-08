# Implementation plan — A1: structure-aware chunking (`index`)

> Paste as the opening message of a fresh session. Self-contained except the repo — read the files it
> points at before writing code. **Multi-increment, TDD-first** (write the test, confirm RED, implement,
> confirm GREEN, `make check` before each commit). Authority: [`vdocs-design.md`](../vdocs-design.md)
> §14.6 (the concrete chunking contract), §5.5; [`fidelity-framework.md`](../fidelity-framework.md)
> §10.5; the reframe [`v1-lessons-and-v2-priorities.md`](../v1-lessons-and-v2-priorities.md) (priority
> A1, tenet #14). This is the **highest-leverage substrate fix** and gates `embed` (D1) and `publish`.

## 0. Why (the measured problem)

`index_pure.shred_sections` (read it — `src/vdocs/stages/index/index_pure.py`, ~30 lines) makes one
chunk per ATX heading, spanning the heading line to the next heading. On the real 1299-doc lake that
yields a search surface that retrieves badly:

- **14.2% of `is_latest` chunks are hollow** (<80-char body) — a *container* heading whose substance
  lives in its subsections indexes as a bare heading + `[↑ Back to Contents]` link. Example:
  `Pre-installation Considerations` → body is just the heading + back-link.
- **40.8% are thin** (<400 chars); a few are **>140 KB** (max 144,908).
- Net: hollow chunks pollute the (future) ANN neighbourhood and waste lexical slots; monster chunks
  bury the relevant passage. Both hurt human navigation and AI recall.

The fix: chunk on **structure + self-sufficiency**, not heading-to-heading byte spans. Target: **≈0%
hollow content chunks**, bounded chunk size, every chunk self-interpretable via metadata.

## 1. The model (what a chunk should be)

Separate two concerns that `shred_sections` currently conflates:

- **Structural section row** — one per heading, the navigation/anchor map. Must stay 1:1 with
  `refs.yaml` (same `section_id = <doc_key>/<slug>`, same skip rules) — it is the join key for the
  published markdown anchors, the graph, and MCP URIs. **Keep all heading rows.**
- **Searchable chunk** — the unit FTS indexes and `embed` will embed. This is where the fix lives:
  a chunk must be a *self-sufficient passage*, never a hollow container.

Classify each heading by its own body (the lines from its heading to its first child heading or next
sibling, minus structural furniture — back-links, the heading line itself):

1. **Container** (a deeper heading follows before any substantive own-body): **not searchable as its
   own chunk.** Emit the structural row (anchor/nav/toc) but `searchable = False`; its title flows into
   its descendants' **section-path** metadata. (Container headings are *expected* to have no own-body —
   §14.6; the defect is indexing them as standalone empty chunks, not their existence.)
2. **Leaf with substantive body**: one searchable chunk. If oversized, **split** (increment 3).
3. **Leaf below the substantive floor with no children** (a genuinely empty section): **hollow** — the
   real over-strip defect. Rare after (1). Mark it so `fidelity`/`overstrip_pure` counts it (FF §10.5).

Every searchable chunk carries, as **metadata not prose** (§14.6): `section_path` (ancestor titles,
e.g. `Pre-installation Considerations > Client Requirements`), `level`, and the existing
`app_code`/`doc_type`/`version` (already on `documents`).

## 2. Increments (each its own TDD cycle + commit)

### Increment 1 — classify container / leaf / hollow (pure, no schema change yet)
- **Tests first** (`tests/unit/stages/test_index_pure.py`): a parent heading with immediate child
  headings and no own prose → classified **container**; a parent with a lead-in paragraph *then*
  children → **leaf** (the lead-in is its body) + children are their own chunks; a leaf with real prose
  → **leaf**; a leaf with only a heading+back-link and no children → **hollow**. Fence-aware (a `#` in a
  code fence is not a child). Use a real fixture mirroring `Pre-installation Considerations`.
- **Implement** in `index_pure`: compute each heading's own-body (to first child/sibling), strip
  structural furniture (reuse `kernel.markdown.heading_furniture_text` / the back-link regex — do **not**
  re-roll), apply a **substantive-token floor** (calibrate to the FF §10.5 `<80 non-structural chars`;
  put the constant in one place, shared with `overstrip_pure` so the gate and the chunker agree).
  `Section` gains `kind: "container" | "leaf" | "hollow"`, `searchable: bool`, `section_path: str`.
- **DoD**: `section_id`s unchanged for existing headings (the `_unique`/`github_slug` path is
  untouched); idempotent; the property test for id-stability still green.

### Increment 2 — section-path metadata + carry the structural tree
- **Tests**: a 3-level doc → each chunk's `section_path` is its ancestor-title chain; a container's
  title appears in its descendants' paths; H1 (doc title) handling matches `effective_toc_depth`
  conventions (don't fabricate an ancestor where `normalize` wouldn't).
- **Implement**: track the ancestor stack during the scan (mirror `normalize_pure.infer_heading_levels`'s
  stack discipline so levels/paths agree across stages). No new I/O.

### Increment 3 — bound oversized leaf chunks (windowed split)
- **Tests**: a leaf body > the split threshold splits into N parts on blank-line/paragraph boundaries
  (never mid-fence, never mid-table — reuse `kernel.markdown` fence awareness); part 1 keeps the bare
  `section_id` (stability), parts 2..N get a deterministic suffix (`<section_id>#p2`…); small overlap
  (calibration target) so a passage spanning a boundary isn't lost; re-joining parts reproduces the
  body (no content dropped — assert it).
- **Implement**: a pure `split_oversized(text, *, target, overlap)` in `index_pure`; thresholds are
  **calibration targets** (start ~6–8 KB split / ~3–4 KB window / ~10% overlap), recorded and tunable
  like the FF floors — B3 confirms them. Keep them named constants, not literals.
- **DoD**: no chunk exceeds the cap; oversized count → 0; total body bytes preserved across the split.

### Increment 4 — wire into the `index` stage + schema + FTS (the ripple)
- Read `src/vdocs/stages/index/stage.py` first. The schema (`doc_sections`: `section_id, doc_key, slug,
  title, level, toc_level, is_latest`; FTS5 `doc_sections_fts(section_id, doc_key, title, body)`).
- **Decision to confirm before coding (the one genuinely open call):** how to persist the
  section/chunk split. **Recommended:** add `kind`, `searchable`, `section_path` columns to
  `doc_sections` (keep one row per heading for the anchor map) and **build FTS over `searchable=1 AND
  is_latest=1` only** (today it's `is_latest` only). Oversized split-parts become additional searchable
  rows keyed by the `#pN` suffix with `is_latest` inherited. This keeps the anchor contract intact while
  the *search surface* drops hollow containers. (Alternative — a separate `chunks` table — is cleaner
  long-term but a bigger schema change; not recommended for A1.)
- **Tests** (`tests/integration/stages/test_index_stage.py`): container rows present but **absent from
  FTS**; no hollow rows in FTS; split parts present and searchable; `section_id`s still match
  `refs.yaml`; forced-rebuild stable; counts (`sections`, `fts_sections`) reflect the new surface.
- Update `manifest`'s `sections_searchable` count source if needed (it reads FTS rows — verify).

## 3. Verification on the real lake (the DoD that matters — tenet #14 / "smoke every gold stage")
- `vdocs run --from index --to manifest --force` on `~/data/vdocs` (do **not** re-fetch/convert; check
  no live `vdocs run` first — `pgrep -af "vdocs run"`, the shared-lake hazard).
- Re-measure the surface (the queries in the 2026-06-04 audit): **hollow rate ≈ 0** (was 14.2%), **0
  chunks over the cap** (was 346 >10 KB), and `fts_sections` now excludes containers. Record before/after.
- This is also the input precondition for **D1 `embed`** (never embed hollow chunks) and the baseline
  for the **B3** retrieval harness (run B3 before *and* after to quantify the lift, not assert it).

## 4. Guardrails / non-goals
- **Do not change `normalize`'s slugs or `refs.yaml`.** A1 is an `index`-side chunking change; section
  ids stay byte-identical (regression-test it). Heading *recovery* (more headings) is **A2**, separate.
- **Do not embed yet** (that's D1) — A1 only reshapes `doc_sections`/FTS.
- Reuse `kernel.markdown` fence/heading/furniture helpers and `overstrip_pure`'s floor — no copy-paste
  (tenet #4); if a primitive is missing, add it to the kernel.
- `make check` green each increment (ruff line 100, mypy, pytest random-order, coverage ≥95%).
- Update `vdocs-design.md` §5.5/§14.6 + the tracker A1 row in the same commit as the schema change.
