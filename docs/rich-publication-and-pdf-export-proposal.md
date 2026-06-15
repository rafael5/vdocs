# Proposal — Rich web viewing in VS Code (in scope) + gold→PDF export (deferred)

**Status:** proposal / for sign-off. **Date:** 2026-06-15. **Author:** Claude (Opus 4.8) with Rafael.
**Repos:** `vdocs` (pipeline) + `vdocs-web` (consumer, incl. its `extension/` VS Code integration).

> **Scope split (this revision):**
> - **IN SCOPE — Part I:** *rich web viewing in VS Code* — show **figures** for a curated high-value
>   subset (CPRS GUI, FileMan, …) in the `vdocs-web` reading pane, which is already viewable inside
>   an editor tab via the **vdocs-vscode** extension. This is the active project.
> - **DEFERRED — Part II (separate project):** *gold→PDF export* (cleaned docs → PDF with a linked
>   TOC + all figures). Analysis retained below; **not** in current scope — it graduates to its own
>   proposal/effort when scheduled (new system dependency, its own phases).
>
> Both share one substrate (§3); building it for Part I means Part II is mostly "add an engine"
> later.

## Table of contents

- [1. Context & what already exists](#1-context--what-already-exists)
- [2. Goals & non-goals](#2-goals--non-goals)
- [3. The shared substrate](#3-the-shared-substrate)
- **Part I — IN SCOPE: rich web viewing in VS Code**
  - [4. The viewing surface (vdocs-vscode + the reading pane)](#4-the-viewing-surface)
  - [5. Approaches & pros/cons](#5-approaches--proscons)
  - [6. In-scope decision table](#6-in-scope-decision-table)
  - [7. In-scope phased plan](#7-in-scope-phased-plan)
  - [8. In-scope open questions](#8-in-scope-open-questions)
- **Part II — DEFERRED (separate project): gold→PDF export**
  - [9. Sketch & why deferred](#9-sketch--why-deferred)
  - [10. PDF engine comparison (retained analysis)](#10-pdf-engine-comparison-retained-analysis)
  - [11. Deferred decisions & open questions](#11-deferred-decisions--open-questions)
- [12. Risks & mitigations](#12-risks--mitigations)
- [13. Recommendation](#13-recommendation)

---

## 1. Context & what already exists

Grounded in the current lake/code (2026-06-15):

- **Figures are captured.** `convert` extracts every inline image to a content-addressed store —
  **15,705 assets / 1.2 GB** at `~/data/vdocs/documents/assets/<sha256>.<ext>` — and rewrites body
  refs to `![](<sha>.png)`. **Content figures survive `normalize`** (only title-page logos are
  stripped). The gold bodies already point at real images.
- **TOC + anchors exist.** Each `gold/consolidated/<app>/<slug>/body.md` carries a regenerated
  `## Contents` with nested `- [Title](#github-slug)` links over `##`/`###` headings.
- **High-value docs present in gold:** `CPRS/cprsguitm`, `CPRS/cprsguium` (CPRS GUI TM/UM),
  `DI/fm22_2tm`, `DI/fm22_2um1/2`, `DI/fm22_tutorial`, … (FileMan 22.2).
- **`index.db` is text-only.** It carries the image *refs* in chunk text but **not the image bytes**
  — and it's the ~294 MB artifact vdocs-web ships/downloads. Images need a separate path.
- **The VS Code viewing surface already exists.** `vdocs-vscode` (Level-1, implemented 2026-06-14,
  in `vdocs-web/extension/`) spawns the `vdocs-web` Go binary and frames its SvelteKit navigator in
  a **WebviewPanel** — so "view the navigator in an editor tab" is a solved, shipped flow. Rich
  viewing rides on top of it with **no extension change** (the extension is glue; the navigator is
  what gains figures).
- **vdocs-web reading pane today** renders the body as **plain pre-wrapped text** — `## Heading` and
  `![](…)` show literally; it serves no images. (So even text isn't rendered as markdown yet.)
- **`publish` is the planned-but-unbuilt L3 slot** (markdown tree); the deferred PDF export is the
  richer realization of it.

**Implication:** the bytes exist; the in-scope work is (a) getting a *curated subset* of image bytes
to vdocs-web and (b) rendering the body (markdown + figures) in the reading pane that VS Code already
frames. The curated subset keeps the payload bounded (CPRS GUI + FileMan + peers ≈ tens of MB, not
1.2 GB).

## 2. Goals & non-goals

**Goals**
- A reader viewing a high-value doc in the vdocs-web navigator **inside VS Code** sees its **figures**
  and properly-rendered markdown (curated subset).
- Curation is **data, not code** (a registry), per tenet #13.
- No regression to lexical-first, offline, zero-AI-operable, or the single read-contract (ADR-0001).

**Non-goals**
- Not images for *all* ~615 docs (payload/UX); curated subset only.
- Not re-architecting `index.db` into a blob store (kept text-only/lexical).
- Not the PDF export — that's Part II (deferred).
- Not changing the vdocs-vscode extension — it frames whatever vdocs-web serves.

## 3. The shared substrate

Both parts need the same two pieces; **build it in Part I**, reuse in Part II.

1. **Curated-subset registry** — `registries/rich-publication.yaml`: an allowlist of doc keys (or
   anchor keys) that get the rich treatment. Data-not-code; reviewed like the other registries.
2. **Asset-resolution helper** (kernel) — given a gold `body.md` + the asset CAS, produce either the
   referenced image **bytes** (for serving — Part I) or the body with `<sha>.png` refs rewritten to
   real **paths** + the asset file set (for an engine — Part II). Pure-ish (CAS lookups), unit-tested.

---

# Part I — IN SCOPE: rich web viewing in VS Code

## 4. The viewing surface

No new viewer is needed: the **vdocs-vscode** extension already runs `vdocs-web` and frames the
SvelteKit reading pane in an editor Webview (locally + over Remote-SSH via `portMapping`). Rich
viewing is entirely a **vdocs-web** change — add figure serving + markdown rendering to the reading
pane — and it shows up in the VS Code tab automatically (and in a plain browser, unchanged). Two gaps
to close in vdocs-web: it serves no image bytes, and it renders the body as plain text.

## 5. Approaches & pros/cons

### A1 — client-side markdown render + image route *(recommended)*
Add a markdown renderer to the Svelte SPA; add `GET /api/asset/{sha}` on the Go server backed by a
bundled subset of images; the reading pane renders the body so `![](<sha>.png)` resolves to the route.
- **Pros:** keeps the single-binary model the vdocs-vscode extension bundles; renders *every* doc's
  text properly (headings/lists/tables — a universal reading-pane upgrade), with figures for the
  curated subset; image refs are already in the chunk text, so **no `index.db` change**; subset image
  bundle is small/optional.
- **Cons:** adds a JS markdown lib (build-time only, embedded — like Vite, a justified app dep); needs
  a second artifact (the subset image bundle) alongside `index.db`; rendering corpus markdown as HTML
  is an XSS surface (mitigated: trusted corpus, localhost/Webview, sanitizer).

### A2 — server-side render to HTML with images inlined as data URIs
A pre-build/server step renders the subset's bodies to HTML with images base64-inlined; vdocs-web
serves rich HTML for subset docs, plain text otherwise.
- **Pros:** no client JS lib; self-contained HTML (no image route); clean rich/lexical split.
- **Cons:** base64 inflates ~33%; needs a Go (or build-time) markdown→HTML renderer; two UI paths;
  non-subset docs stay unrendered.

### A3 — pre-rendered standalone HTML mini-site for the subset
A `publish` step emits a portable static HTML site (rendered HTML + co-located images) for the subset.
- **Pros:** fully self-contained & portable; works with no server; doubles as the L3 human-corpus
  deliverable.
- **Cons:** a *separate* browse surface, not the integrated navigator the VS Code tab frames; partial
  overlap with the reading pane.

**Lean:** **A1** — it upgrades the reading pane for all docs and lands figures for the subset inside
the existing VS Code viewing flow. A3 can follow later as the standalone deliverable from the same
rendered output.

## 6. In-scope decision table

| # | Decision | Options | Recommendation | Why / trade-off |
|---|---|---|---|---|
| D1 | Rich display approach | A1 client-render+route · A2 server HTML+data-URI · A3 static site | **A1** | Integrates into the navigator the VS Code tab frames; upgrades all docs' rendering; no index.db change |
| D2 | Curated subset source | hardcode · `registries/rich-publication.yaml` | **registry (YAML)** | Data-not-code (tenet #13); reviewed like other registries |
| D3 | Image bytes delivery | inline in index.db (BLOB) · separate sidecar bundle | **separate bundle** | Keeps index.db text-only/lexical + the 294 MB download lean; subset is tens of MB |
| D4 | Markdown renderer | a small embedded JS lib · hand-rolled | **vetted JS lib + sanitizer** | Correct GFM rendering; sanitizer covers the (low, trusted/localhost) XSS surface |
| D5 | Non-subset docs | render text only (no images) · hide image refs | **render text; drop/alt-text the refs** | The reading-pane upgrade benefits every doc; only the subset ships bytes |

## 7. In-scope phased plan

- **P1 — substrate (vdocs):** `registries/rich-publication.yaml` + the kernel asset-resolution helper
  (TDD) + a build step that emits the **subset image bundle** (just the curated docs' assets).
- **P2 — vdocs-web serving + rendering:** `GET /api/asset/{sha}` over the bundle; markdown rendering
  in the reading pane (A1) with a sanitizer; figures render for subset docs. Gate: httptest the
  route + svelte-check; verify in the VS Code Webview (the vdocs-vscode smoke flow).
- **P3 — polish:** captions/alt-text, broken-ref fallback for non-subset docs, distribution wiring
  (where the image bundle rides alongside `index.db`).

Each phase is independently shippable, TDD-first, gated; cross-repo (vdocs substrate → vdocs-web
consumer), leaf-first.

## 8. In-scope open questions

1. **Subset scope/budget:** beyond CPRS GUI + FileMan, what's in? Curation criteria (figure density?
   importance?) and a payload budget for the image bundle.
2. **Markdown lib:** which renderer in the SvelteKit app (must be offline/embeddable; pairs with a
   sanitizer)? Confirm it's an acceptable app dep (like Vite).
3. **Distribution:** where does the subset image bundle live — alongside `index.db` in the (future)
   publish manifest / auto-download, or a separate release artifact?
4. **Raw HTML in bodies:** some gold bodies carry `<img …>` (Pandoc HTML) — allow through the
   sanitizer, or normalize to markdown first?
5. **Non-subset UX:** for docs *not* in the subset, show alt-text, a "figure omitted" note, or
   nothing where an image ref sits?

---

# Part II — DEFERRED (separate project): gold→PDF export

> **Deferred.** Not in current scope. Captured here so the analysis isn't lost and so Part I's
> substrate is built with reuse in mind. Graduates to its own proposal/effort when scheduled.

## 9. Sketch & why deferred

Export a selected gold doc to a self-contained PDF with a clickable TOC + embedded figures — the
richer realization of the L3 `publish` slot. Per-doc pipeline: resolve assets (shared substrate) →
pre-process (re-inline relocated `tables/*.csv`; decide back-nav links) → Pandoc → PDF with `--toc`
(clickable bookmarks; the body's `## Contents` `#slug` links resolve, since Pandoc's GFM
auto-identifiers reproduce the same GitHub slugs) → `gold/publish/pdf/<app>/<slug>.pdf`.

**Why deferred (not in scope now):** it introduces a **new system dependency** (a PDF engine) with
real unknowns (fidelity on figure-/table-heavy docs), it's a heavier, independently-scheduled effort,
and the in-scope rich web viewing delivers the "see the figures" value first against the surface the
operator already uses (VS Code). The shared substrate built in Part I removes most of Part II's risk
later.

## 10. PDF engine comparison (retained analysis)

All drive through Pandoc (`--pdf-engine=…`); the gold input is GFM markdown, image- and table-heavy.

| Engine | Install / fit | Fidelity | TOC + bookmarks | Airgap | Verdict |
|---|---|---|---|---|---|
| **weasyprint** (HTML/CSS→PDF, Python) | `uv add`; pulls system pango/cairo | High for doc content; CSS control; graceful with wide tables/images | Yes (clickable + outline) | wheels cache; system libs | **Likely primary** — best toolchain fit, no TeX |
| **tectonic** (LaTeX, single binary) | one self-contained binary; no TeX Live | Highest | Excellent | **Best** (one vendored binary) | **High-fidelity alternative** if print-perfect matters |
| **xelatex / TeX Live** | heavy (GBs) | Highest | Excellent | Hard | Rejected — install + airgap cost |
| **typst** (`--pdf-engine=typst`) | one fast modern binary | Good, improving | Yes | Good | **Spike candidate** — pandoc's typst writer still maturing |
| **wkhtmltopdf** (QtWebKit) | system pkg | OK | Limited | OK | Rejected — unmaintained/archived |

**When picked up:** a two-doc spike on `cprsguitm` (figure-heavy) + `fm22_2tm` (table-heavy) settles
the engine before committing.

## 11. Deferred decisions & open questions

| # | Decision | Options | Lean (to revisit) |
|---|---|---|---|
| E1 | PDF engine | weasyprint · tectonic · typst · xelatex · wkhtmltopdf | weasyprint primary; tectonic for fidelity/airgap; typst spike |
| E2 | Relocated table CSVs | re-inline as tables · keep as links | re-inline (no dead links in a standalone PDF) |
| E3 | Back-to-Contents nav links | keep (clickable) · strip | keep |
| E4 | Scope | per-doc · combined book | per-doc first |
| E5 | Home | `publish`/`export` stage · CLI-only | stage (the L3 slot) + a CLI `export` wrapper |

Deferred open questions: PDF determinism/gating (engine + font pinning vs treat-as-non-reproducible),
CI engine install for a PDF smoke test, captions/landscape for wide tables, combined-book heading
shifting + master TOC.

## 12. Risks & mitigations

- **Payload bloat (images)** → curated subset + a *separate* bundle keeps `index.db` lean (D3).
- **Markdown XSS in the Webview** → trusted corpus + localhost/Webview; a sanitizer; decide raw-HTML
  policy (Q4).
- **Renderer dep in the SPA** → embedded/build-time only (like Vite); pinned + offline.
- **(Deferred) engine fragility / new sys dep** → handled when Part II is scheduled (spike first;
  `vdocs preflight` + a CI smoke test would catch a missing engine cleanly).
- **Maintainer surface** → both parts extend existing slots (the vdocs-web reading pane + the L3
  `publish`); curation stays in `registries/`; the vdocs-vscode extension is untouched.

## 13. Recommendation

Proceed with **Part I (rich web viewing in VS Code)** now: build the **shared substrate** + the
**curated-subset registry**, then add **figure serving + markdown rendering** to the vdocs-web reading
pane (**A1**) so figures appear in the VS Code tab the operator already uses. Keep the image bytes in
a **separate subset bundle** so `index.db` stays text-only. **Defer the gold→PDF export** as its own
project (Part II) — its analysis is retained above, and Part I's substrate makes it mostly "add an
engine" when it's scheduled.
