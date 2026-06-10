# vdocs TUI — Bubble Tea Architecture Sketch (faceted drill-down over index.db)

> **Status:** design sketch, 2026-06-09. Implements the prototype-first recommendation from
> [`incremental-discovery-evidence-based-design.md`](incremental-discovery-evidence-based-design.md):
> live faceted drill-down with count previews + zero-hit suppression (operator persona), then
> fzf-style fuzzy narrowing (developer persona), then split-pane preview. A new **read-only Go
> binary** over the existing `index.db` (SQLite + FTS5). The Python pipeline owns writing the index;
> the TUI only reads.

## The contract: `index.db` (v3 schema)

The TUI binds to these tables/columns — nothing else:

```
documents(doc_key PK, doc_id, app_code, doc_type, section, pkg_ns, version, patch_id,
          anchor_key, group_key, title, doc_label,
          app_user, doc_user, software_class, function_category,   -- v3 facet bake
          word_count, section_count, is_latest, source_sha256, source_url)
doc_sections(section_id PK, doc_key, slug, title, level, section_path, searchable, is_latest)
chunks(chunk_id PK, section_id, doc_key, text)
chunks_fts USING fts5(chunk_id, section_id, doc_key, title, doc_title, section_path, body)
entities(entity_id PK, type, canonical_name, mention_count)        -- 9 types
entity_mentions(entity_id, doc_key, section_id)
INDEX idx_documents_facets(is_latest, doc_type, app_code, pkg_ns)
INDEX idx_documents_persona(is_latest, app_user, doc_user)
```

**Facet inventory the TUI exposes** (each a column on `documents` unless noted):

| Facet axis | Source | Live now? |
|---|---|---|
| `doc_type`, `app_code`, `pkg_ns`, `section` | `documents` (+ index) | ✅ |
| `app_user`, `doc_user`, `software_class`, `function_category` | `documents` (v3) | ⏳ needs enrich-bake + re-index |
| entity (routine/rpc/fileman_file/option/global/hl7_segment/mail_group/build/package_namespace) | `entities` ⋈ `entity_mentions` | ✅ |
| free text | `chunks_fts` (FTS5 MATCH) | ✅ |
| fuzzy (title narrowing) | in-memory over current result list | ✅ |

`is_latest = 1` is an implicit always-on filter (gold = the version anchor; the B1 fix makes that
one row per logical document).

---

## Three-pane layout (the visible motif)

```
┌─ FACETS ────────────┬─ RESULTS  (462) ───────────────┬─ PREVIEW ───────────────┐
│ doc_type            │ ▸ Scheduling User Manual   UM   │ # Scheduling User Manual │
│  [x] UM      (188)  │   Outpatient Pharmacy UM   UM   │                          │
│  [ ] TM      (·71)  │   Lab User Guide           UG   │ ## Make an Appointment   │
│  [ ] UG      (·44)  │   …                             │ To schedule a clinic …   │
│ app_user            │                                 │                          │
│  [x] clinical (210) │  ── fuzzy: ▕appoint▏  (12) ──    │ [entities: SDM, ^SD…]    │
│  [ ] developer(·90) │                                 │                          │
│ entity:option       │                                 │                          │
│  [ ] SDMGR    (·6)  │                                 │                          │
│ …                   │                                 │                          │
└─────────────────────┴────────────── total: 462 → 12 ─┴──────────────────────────┘
   ↑ multi-select toggles      ↑ recognition list, shrinks live    ↑ details-on-demand
```

- **Left** — facet axes, each value with a **live count** in parens; **zero-hit values grayed/hidden**
  (the Flamenco mechanism). `Space`/`Enter` toggles a value; counts + results recompute < 100 ms.
- **Center** — the candidate documents (recognition list). A `/` opens an inline **fuzzy** box that
  narrows the *current* list per keystroke (fzf-style) with its own match count.
- **Right** — selected doc's markdown (details-on-demand), plus its entities.
- **Footer** — running total `462 → N`, so the user knows when the set is small enough to scan.

---

## The data layer (Go) — the queries that power it

A read-only package, `internal/index`, with one `Filter` type and four query shapes.

### Filter → WHERE (AND across axes, OR within an axis — the Flamenco default)

```go
type Filter struct {
    Sel     map[string][]string // axis -> selected values, e.g. {"doc_type":{"UM"}, "app_user":{"clinical"}}
    Entity  []string            // selected entity_ids (special: joins entity_mentions)
    FTS     string              // optional full-text MATCH (empty = none)
}

// where builds the documents-table predicate for all axes EXCEPT `omit` (used for facet counting:
// to count axis A's values we apply every other axis but relax A — see facetCounts).
func (f Filter) where(omit string) (string, []any) {
    clauses := []string{"is_latest = 1"}
    var args []any
    for axis, vals := range f.Sel {
        if axis == omit || len(vals) == 0 { continue }
        clauses = append(clauses, fmt.Sprintf("%s IN (%s)", axis, ph(len(vals))))
        for _, v := range vals { args = append(args, v) }
    }
    if len(f.Entity) > 0 { // doc must mention any selected entity (OR within the entity axis)
        clauses = append(clauses,
          "doc_key IN (SELECT doc_key FROM entity_mentions WHERE entity_id IN ("+ph(len(f.Entity))+"))")
        for _, e := range f.Entity { args = append(args, e) }
    }
    return strings.Join(clauses, " AND "), args
}
```

### 1. Facet counts (the live-count + zero-hit mechanism — recomputed on every filter change)

For each visible axis, count its values **with every *other* axis applied but the axis itself
relaxed** — so each value shows "how many docs I'd add" (multi-select OR semantics). One `GROUP BY`
per axis; trivial at 462 rows.

```go
func (ix *Index) facetCounts(axis string, f Filter) (map[string]int, error) {
    where, args := f.where(axis) // relax this axis
    rows, _ := ix.db.Query(
        "SELECT "+axis+", COUNT(*) FROM documents WHERE "+where+
        " AND "+axis+" <> '' GROUP BY "+axis, args...)
    // → {"UM":188, "TM":71, ...}; values absent from the map render as count 0 → grayed/hidden
}
// entity-axis counts: SELECT em.entity_id, COUNT(DISTINCT d.doc_key) ... JOIN over the same where.
```

### 2. Candidate documents (the center list)

```go
func (ix *Index) candidates(f Filter) ([]Doc, error) {
    where, args := f.where("")
    if f.FTS != "" { // intersect with FTS hits when a full-text query is active
        where += " AND doc_key IN (SELECT doc_key FROM chunks_fts WHERE chunks_fts MATCH ?)"
        args = append(args, ftsSanitize(f.FTS))
    }
    return ix.query("SELECT doc_key, app_code, doc_type, title FROM documents WHERE "+where+
                    " ORDER BY app_code, doc_type, title", args...)
}
```

### 3. Fuzzy narrowing (developer accelerator — in-memory, instant)

The `/` box does **not** hit the DB: it fuzzy-matches `sahilm/fuzzy` over the already-loaded
candidate titles (+ optionally entity names), re-ranking per keystroke. (Full-text body search is the
separate FTS path in #2.) This is the fzf motif: zero latency, ranked, with a live match count.

### 4. Preview (details-on-demand)

```go
// load the selected doc's body for the right pane (chunks joined in section order, or read body.md)
func (ix *Index) preview(docKey string) (string, []Entity, error) { ... }
```

---

## Bubble Tea model (Elm architecture)

```go
type pane int; const (facetsPane pane = iota; resultsPane; previewPane)

type Model struct {
    ix      *index.Index
    filter  index.Filter
    facets  []FacetAxis      // [{name, []FacetValue{val,count,selected}}], rebuilt from facetCounts
    results []index.Doc      // current candidates (post-filter)
    shown   []index.Doc      // results after fuzzy narrowing
    fuzzy   textinput.Model  // the '/' narrowing box
    preview viewport.Model   // right pane (Bubbles viewport, scrollable)
    focus   pane
    cursor  int
    total   int              // running result count for the footer
    w, h    int
}
```

`Init` loads the full facet catalog + the unfiltered candidate list (462 docs) once.

### Messages & Update (async DB work off the UI thread, debounced)

Every facet toggle / FTS change spawns a `tea.Cmd` that runs the queries on a goroutine and returns a
`refreshedMsg`; the UI stays responsive. Rapid toggles are **debounced** (~80 ms) so a burst of
key-presses runs one query, not ten.

```go
type refreshedMsg struct{ facets []FacetAxis; results []index.Doc }

func (m Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
    switch msg := msg.(type) {
    case tea.KeyMsg:
        switch {
        case msg.String() == "tab":          m.focus = (m.focus+1)%3
        case msg.String() == " " && m.focus == facetsPane:
            m.toggleFacetUnderCursor()        // mutate m.filter.Sel
            return m, m.refresh()             // → debounced query Cmd
        case msg.String() == "/":             m.fuzzy.Focus(); m.focus = resultsPane
        case msg.String() == "esc":           m.fuzzy.Reset(); m.applyFuzzy()
        }
        if m.focus == resultsPane && m.fuzzy.Focused() {
            m.fuzzy, cmd = m.fuzzy.Update(msg)
            m.applyFuzzy()                     // in-memory re-filter of m.results → m.shown
        }
    case refreshedMsg:
        m.facets, m.results = msg.facets, msg.results
        m.applyFuzzy(); m.total = len(m.results)
        m.loadPreviewForCursor()
    case tea.WindowSizeMsg: m.w, m.h = msg.Width, msg.Height; m.relayout()
    }
    return m, cmd
}

// refresh runs facetCounts(all axes) + candidates(filter) in one Cmd (goroutine), debounced.
func (m Model) refresh() tea.Cmd { return debounce(80*time.Millisecond, func() tea.Msg {
    return refreshedMsg{ facets: m.ix.AllFacetCounts(m.filter), results: m.ix.Candidates(m.filter) }
})}
```

### View (Lip Gloss panes)

`View` composes three `lipgloss` columns sized from `m.w/m.h`: `facetsView` (axes + counted, zero-hit
values dimmed via `Faint(true)`), `resultsView` (the `shown` list + the fuzzy box + match count), and
`preview.View()`. A footer renders `total: 462 → len(shown)`.

---

## Package layout

```
cmd/vdocs-tui/main.go          # open index.db read-only, tea.NewProgram(model).Run()
internal/index/
  index.go                     # Open(roDB), AllFacetCounts, Candidates, Preview, Entities
  filter.go                    # Filter type + where() builder + ftsSanitize
internal/tui/
  model.go  update.go  view.go # the Elm triad
  facets.go results.go preview.go  # pane components (Bubbles: list/textinput/viewport)
```

Stack: **Bubble Tea** (runtime) · **Bubbles** (`textinput`, `viewport`, `list`, `table`) · **Lip
Gloss** (layout/style) · `mattn/go-sqlite3` or `modernc.org/sqlite` (pure-Go, no cgo — fits the
offline/portable ethos) · `sahilm/fuzzy` (in-memory narrowing).

---

## Performance & correctness notes

- **Sub-100 ms is trivial at 462 docs.** Every facet refresh is `(#axes) GROUP BYs + 1 candidate
  SELECT`, all index-backed (`idx_documents_facets`, `idx_documents_persona`). Keep the connection
  open; `PRAGMA query_only=1`.
- **Debounce** facet/FTS queries (~80 ms); fuzzy stays in-memory (no debounce needed).
- **Zero-hit suppression** falls out of the count map: a value absent from `facetCounts` → 0 → dim or
  hide. This is the single most-praised Flamenco detail; get it right.
- **Multi-select OR-within / AND-across** via the `where(omit)` relaxation is the standard faceted
  semantic; document it so counts read as "docs this value would add."
- **Open dependency (for the persona facets):** `app_user`/`doc_user`/`software_class`/
  `function_category` are v3 columns but **not yet baked into gold frontmatter** → empty in today's
  index. The TUI should **render only the axes that have non-empty counts** (graceful: it shows
  `doc_type`/`app_code`/`pkg_ns`/`section`/entity now, and the persona axes appear automatically once
  enrich bakes them + re-index). No TUI change needed when they light up.

---

## Build order (mirrors the evidence doc)

1. **Facet pane + live counts + zero-hit suppression + results list** over the live axes
   (`doc_type`/`app_code`/`pkg_ns`/`section` + entity). This is the operator-persona core and the
   highest-evidence motif — ship it first, instrument facet usage (open question #3).
2. **Fuzzy `/` narrowing** on the result list (developer accelerator).
3. **Preview pane** (details-on-demand) + entity chips.
4. Light up **persona/function/class facets** once the enrich-bake (open item #1) populates them — no
   TUI change, they just appear.
```
