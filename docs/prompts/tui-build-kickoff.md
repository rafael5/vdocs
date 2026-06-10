# Kickoff — Build the vdocs TUI (faceted visual discovery + fuzzy search)

**For a fresh session.** Goal: build the interactive **Go (Bubble Tea) TUI** over the gold library's
`index.db` — the **"find it when you see it" visual-discovery** client for users who lack the magic
keyword, complemented by **fzf-style fuzzy search** for symbol-anchored lookups.

> **PRECONDITION — GREEN gate.** Do not start until the pipeline session
> (`pipeline-run-and-validate-kickoff.md`) has emitted **`GOLD LIBRARY: GREEN`** — the TUI is built on
> a validated corpus, with the persona columns populated. If the index lacks persona columns or the
> validation report is missing/RED, stop and run that session first.

## Read first (the design is already done — implement it)

- **`docs/vdocs-tui-architecture-sketch.md`** — ⭐ the concrete architecture: 3-pane layout, the
  `index.db` v3 schema contract, the `Filter→WHERE` + `facetCounts` (GROUP BY with axis-relaxation) +
  fuzzy data layer, the Bubble Tea Model/Update/View triad with debounced async DB `Cmd`s, package
  layout, perf notes. **Build this.**
- **`docs/incremental-discovery-evidence-based-design.md`** — *why* (the evidence): faceted navigation
  (Hearst/Flamenco) + dynamic queries with **live count previews + zero-hit suppression**
  (Shneiderman) beat keyword search for low-search-literacy users; recognition over recall.
- **`docs/persona-based-search-strategy.md`** — the searcher personas + which facets each reaches for;
  persona = soft Layer-0 pre-filter; entry at any layer.
- **`docs/doc-classification-filtering-summary.md`** — the facet/field reference (what each tag means).

## What to build (in this order — mirrors the evidence)

1. **Faceted drill-down with live counts + zero-hit suppression (FIRST — highest evidence).**
   Left pane: the facet axes as multi-select toggles, each *value* showing a live
   `COUNT(*) … GROUP BY` against the current filter; **gray/hide zero-hit values**; footer shows the
   running total (`1036 → N`). Center pane: the candidate doc list (the recognition list) that
   shrinks/expands live. Facets to expose (all are `documents` columns or entity joins in v3):
   `app_user` · `doc_user` · `doc_type` · `app_code`/`pkg_ns` · `section` · `function_category` ·
   `software_class` · `vasi_status` · the 9 entity types (routine/rpc/fileman_file/option/global/
   hl7_segment/mail_group/build/package_namespace). Semantics: **AND across axes, OR within an axis**.
   This serves the **operator personas** (no vocabulary needed).
2. **fzf-style incremental fuzzy narrowing.** A `/` text box that re-filters the *current* result
   list per keystroke (in-memory, e.g. `sahilm/fuzzy`) with a live match count — the **developer
   accelerator** for symbol-anchored lookups. Keep it distinct from the SQL FTS path.
3. **Split-pane preview (details-on-demand).** Selecting a result renders its markdown + its entities
   in the right pane.
4. *(Optional)* a full-text FTS5 mode (`chunks_fts MATCH`) layered onto the facet filter, reusing the
   existing ranking so it matches `vdocs ask`.

## Constraints & stack

- **Read-only over `index.db`** (`PRAGMA query_only=1`). The Python pipeline owns writes; the TUI only
  reads. Offline, zero-ML.
- **Sub-100ms** per toggle/keystroke (trivial at ~1,036 docs; debounce facet/FTS queries ~80ms; fuzzy
  stays in-memory). Async DB work off the UI thread via `tea.Cmd`.
- Stack: **Bubble Tea** + **Bubbles** (textinput/viewport/list/table) + **Lip Gloss**; pure-Go SQLite
  (`modernc.org/sqlite` — no cgo, fits the offline ethos); `sahilm/fuzzy`. No library restrictions —
  it can be a rich client.
- New Go module/binary (e.g. `cmd/vdocs-tui`), separate from the Python repo or a sibling under the
  org's Go tooling — your call; the `vista` CLI (Go) is prior art for a Go-over-SQLite reader.

## Acceptance

- A working TUI binary that, over the real gold `index.db`: shows live-counted facets with zero-hit
  suppression, narrows the result list reversibly as facets toggle, supports `/` fuzzy narrowing, and
  previews a selected doc — all sub-100ms.
- The three motifs (faceted drill-down · fuzzy · preview) demonstrably work on the gated corpus.
- Tests for the pure data layer (`Filter→WHERE`, `facetCounts`, `doc_user`/`app_user` resolution).
- A short README: keys, the layered model, and how to point it at a lake's `index.db`.

## Open questions to resolve by prototyping (from the evidence doc)

- **Facet ordering / mental-model fit**: which axes do operator vs developer personas reach for
  first? Instrument facet usage; the literature can't answer it for VistA.
- **Entity-facet × FTS composition** in one live loop.
- **CLI vs full-screen TUI**: how much of the live-count benefit survives outside a full-screen Bubble
  Tea app. Default to full-screen (the evidence is for direct-manipulation).
- Soft-expand: when a persona/facet slice underflows, widen with a note — never a bare empty result.
