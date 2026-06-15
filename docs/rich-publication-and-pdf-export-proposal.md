# Proposal — Rich publication (images in vdocs-web) + gold→PDF export

**Status:** proposal / for sign-off (no code yet). **Date:** 2026-06-15.
**Author:** Claude (Opus 4.8) with Rafael. **Repos touched:** `vdocs` (pipeline) + `vdocs-web` (consumer).

> **Why this doc:** two requested capabilities — (1) a **rich vdocs-web display that shows figures**
> for a curated high-value subset (CPRS GUI, FileMan, …), and (2) an **export of the cleaned gold
> documents back out to PDF** with a working linked TOC and all figures. Both are feasible and share
> one substrate (resolving the asset store + a curated-subset registry). This lays out the
> approaches, trade-offs, a rapid-review decision table, and open questions before any code.

## Table of contents

- [1. Context & what already exists](#1-context--what-already-exists)
- [2. Goals & non-goals](#2-goals--non-goals)
- [3. The shared substrate](#3-the-shared-substrate)
- [4. Feature A — images in vdocs-web (curated subset)](#4-feature-a--images-in-vdocs-web-curated-subset)
- [5. Feature B — gold → PDF export](#5-feature-b--gold--pdf-export)
- [6. PDF engine comparison](#6-pdf-engine-comparison)
- [7. Rapid-review decision table](#7-rapid-review-decision-table)
- [8. Open questions](#8-open-questions)
- [9. Phased plan](#9-phased-plan)
- [10. Risks & mitigations](#10-risks--mitigations)
- [11. Recommendation](#11-recommendation)

---

## 1. Context & what already exists

Grounded in the current lake/code (2026-06-15):

- **Figures are captured.** `convert` extracts every inline image to a content-addressed store —
  **15,705 assets / 1.2 GB** at `~/data/vdocs/documents/assets/<sha256>.<ext>` — and rewrites body
  refs to `![](<sha>.png)`. **Content figures survive `normalize`** (only title-page logos are
  stripped). So the gold bodies already point at real images.
- **TOC + anchors exist.** Each `gold/consolidated/<app>/<slug>/body.md` carries a regenerated
  `## Contents` with nested `- [Title](#github-slug)` links over `##`/`###` headings; Pandoc's GFM
  auto-identifiers reproduce the same GitHub slugs, so those intra-doc links resolve in HTML/PDF.
- **The high-value docs are present in gold:** `CPRS/cprsguitm`, `CPRS/cprsguium` (CPRS GUI TM/UM),
  `DI/fm22_2tm`, `DI/fm22_2um1/2`, `DI/fm22_tutorial`, … (FileMan 22.2).
- **Pandoc 3.1.3 is installed** (already the `convert` dependency).
- **`index.db` is text-only.** It carries the image *refs* in chunk text but **not the image bytes**
  — and it's the ~294 MB artifact vdocs-web ships/downloads. Images therefore need a separate path.
- **`publish` is a planned-but-unbuilt slot** (lexical plan L3.1 ⬜ "markdown-only tree + INDEX").
  This proposal extends that slot rather than inventing a new one.
- **vdocs-web today** renders the reading pane as **plain pre-wrapped text** — `## Heading` and
  `![](…)` show literally; it serves no images.

**Implication:** the bytes exist; both features are about (a) getting a *curated subset* of image
bytes to where they're needed and (b) rendering them. The "selected subset" instinct is right —
bundling all 1.2 GB is a non-starter; CPRS GUI + FileMan + a few peers is tens of MB.

## 2. Goals & non-goals

**Goals**
- A reader can view a high-value doc **with its figures** in vdocs-web (curated subset).
- An operator can **export any gold doc to a self-contained PDF** with a clickable TOC and all
  figures embedded.
- Curation is **data, not code** (a registry), per tenet #13.
- No regression to the lexical-first, offline, zero-AI-operable posture.

**Non-goals**
- Not images for *all* ~615 docs in vdocs-web (payload/UX); curated subset only.
- Not re-architecting `index.db` into a blob store (kept text-only/lexical).
- Not editorial re-layout — we publish the *cleaned* gold body as-is, just rendered.

## 3. The shared substrate

Both features need the same two pieces; build once.

1. **Curated-subset registry** — `registries/rich-publication.yaml`: an allowlist of doc keys (or
   anchor keys) that get the rich treatment. Data-not-code; reviewed like the other registries.
2. **Asset-resolution helper** (kernel) — given a gold `body.md` + the asset CAS, produce either:
   - (for PDF/HTML) the body with `<sha>.png` refs rewritten to real file paths **plus** the set of
     referenced asset files; or
   - (for serving) the referenced image bytes for a doc.
   Pure-ish (CAS lookups), unit-testable, reused by both features.

## 4. Feature A — images in vdocs-web (curated subset)

Two gaps today: vdocs-web (a) serves no image bytes and (b) renders the body as plain text, not
markdown. Three candidate approaches:

### A1 — client-side markdown render + image route *(recommended)*
Add a markdown renderer to the Svelte SPA; add a Go route `GET /api/asset/{sha}` backed by a bundled
subset of images; the reading pane renders the body so `![](<sha>.png)` resolves to the route.
- **Pros:** keeps the single-binary model; renders *every* doc's text properly (headings/lists/tables
  — a universal reading-pane upgrade), with figures for the curated subset; the image refs are
  already in the chunk text, so no `index.db` change; subset image bundle is small/optional.
- **Cons:** adds a JS markdown lib (build-time only, embedded); needs a second artifact (the subset
  image bundle) shipped/downloaded alongside `index.db`; rendering corpus markdown as HTML is an XSS
  surface (mitigated: trusted corpus, localhost-only, sanitizer).

### A2 — server-side render to HTML with images inlined as data URIs
A pre-build (or server) step renders the subset's bodies to HTML with images base64-inlined; vdocs-web
serves rich HTML for subset docs, plain text otherwise.
- **Pros:** no client JS lib; fully self-contained HTML (no image route); clean rich/lexical split.
- **Cons:** base64 inflates ~33%; needs a Go (or build-time) markdown→HTML renderer; two UI rendering
  paths to maintain; non-subset docs still unrendered.

### A3 — pre-rendered standalone HTML mini-site for the subset
A `publish` step emits a portable static HTML site (rendered HTML + co-located images) for the subset;
vdocs-web links out to it (or it's a separate deliverable).
- **Pros:** fully self-contained & portable; works offline with no server; doubles as the L3 human
  corpus deliverable.
- **Cons:** a *separate* browse surface, not integrated into the faceted navigator; partial overlap
  with the reading pane; another thing to host.

**Lean:** **A1** for integration (and it upgrades the reading pane for all docs), optionally feeding
**A3** later as the standalone "human corpus" deliverable from the same rendered output.

## 5. Feature B — gold → PDF export

A `publish`/`export` step (the L3 slot) renders a selected gold body to PDF. Pipeline per doc:

1. **Resolve assets** (shared substrate): rewrite `<sha>.png` → real asset paths; collect the files.
2. **Pre-process the body** (decisions in §8): optionally **re-inline relocated `tables/*.csv`** as
   markdown tables (else the PDF has dead "see table" links); optionally **strip the
   `[↑ Back to Contents]` nav links** (or keep — they're useful clickable PDF nav).
3. **Pandoc → PDF** with `--toc` (native clickable bookmarks; the body's `## Contents` `#slug` links
   also resolve) and a `--resource-path` so figures embed.
4. Emit `gold/publish/pdf/<app>/<slug>.pdf` (+ optionally a combined "book" per app/subset).

The gold body is *already* the cleaned/normalized artifact, so this is mostly engine + asset
resolution. The **one new dependency** is a PDF engine (§6).

**Approaches differ only by engine** (§6) and by *scope*: per-doc PDFs (simple) vs. a combined book
(needs heading-level shifting + a master TOC). Recommend per-doc first.

## 6. PDF engine comparison

All drive through Pandoc (`--pdf-engine=…`); the gold input is GFM markdown that is image- and
table-heavy.

| Engine | Install / fit | Fidelity | TOC + bookmarks | Airgap | Verdict |
|---|---|---|---|---|---|
| **weasyprint** (HTML/CSS→PDF, Python) | `uv add` — fits the Python/uv toolchain; pulls system pango/cairo | High for doc-style content; CSS control; graceful with wide tables/images | Yes (clickable + outline) | pip wheels cache; system libs needed | **Recommended primary** — best toolchain fit, no TeX, handles VistA's tables/figures |
| **tectonic** (LaTeX, single binary) | one self-contained binary; no TeX Live | Highest typographic quality | Excellent | **Best** (one vendored binary, fetches packages once) | **Recommended high-fidelity alternative** — pick if print-perfect output matters |
| **xelatex / TeX Live** | heavy system install (GBs) | Highest | Excellent | Hard (huge) | Not recommended — install + airgap cost too high |
| **typst** (`--pdf-engine=typst`, pandoc 3.x) | one fast modern binary | Good, improving | Yes | Good (single binary) | **Spike candidate** — promising; pandoc's typst writer still maturing |
| **wkhtmltopdf** (HTML→PDF, QtWebKit) | system pkg | OK | Limited | OK | Rejected — unmaintained/archived; bad for takeover |

**Lean:** **weasyprint** (toolchain fit, no TeX, table/image-friendly) as primary; **tectonic** if
LaTeX-quality is required; **typst** worth a short spike. Decide via a one-doc spike on `cprsguitm`
(figure-heavy) + `fm22_2tm` (table-heavy).

## 7. Rapid-review decision table

| # | Decision | Options | Recommendation | Why / trade-off |
|---|---|---|---|---|
| D1 | vdocs-web rich display | A1 client-render+route · A2 server HTML+data-URI · A3 static site | **A1** (+ A3 later) | Integrates into the navigator, upgrades all docs' rendering; A3 is the standalone deliverable |
| D2 | PDF engine | weasyprint · tectonic · xelatex · typst · wkhtmltopdf | **weasyprint** primary; tectonic alt | Fits uv/Python, no TeX, handles tables/figures; tectonic for print-perfect/airgap |
| D3 | Curated subset source | hardcode · `registries/rich-publication.yaml` | **registry (YAML)** | Data-not-code (tenet #13); reviewed like other registries |
| D4 | Image bytes for vdocs-web | inline in index.db (BLOB) · separate sidecar bundle | **separate bundle** | Keeps index.db text-only/lexical + the 294 MB download lean; subset bundle is tens of MB |
| D5 | Relocated table CSVs in PDF | re-inline as tables · keep as links | **re-inline** | A standalone PDF shouldn't have dead "see CSV" links |
| D6 | Back-to-Contents nav links in PDF | keep · strip | **keep** (clickable) | Useful PDF navigation; revisit if noisy |
| D7 | PDF scope | per-doc · combined book | **per-doc first** | Simpler; book needs heading-shift + master TOC (later) |
| D8 | Where it lives | new `publish`/`export` stage vs CLI-only | **stage (L3 slot)** | Fits the DAG/contract model + the planned L3; CLI `export` wraps it |

## 8. Open questions

1. **PDF engine** (D2): weasyprint (fit) vs tectonic (fidelity/airgap) vs typst (modern spike)? —
   resolve with the two-doc spike.
2. **vdocs-web rendering** (D1): A1 vs A2 vs A3 — confirm A1 + a markdown-render lib is acceptable
   in the SvelteKit app (it's a build-time dep; one justified addition like Vite was).
3. **Subset scope**: beyond CPRS GUI + FileMan, what's in? Curation criteria (figure-density?
   importance?) and a **payload budget** for the vdocs-web image bundle.
4. **Distribution**: where do the subset image bundle + PDFs live — alongside `index.db` in the
   (future) publish manifest / auto-download? A separate release artifact?
5. **Reproducibility / gate**: do we gate PDF output (engine version + font pinning) for determinism,
   or treat PDFs as non-reproducible build outputs? (Affects CI + the `fidelity` retention ethos.)
6. **CSV re-inline fidelity** (D5): some `tables/*.csv` are wide/complex — acceptable in PDF, or cap
   columns / landscape pages?
7. **Alt-text/captions**: convert preserves alt-text; do we render `figure`+caption in PDF/HTML, or
   bare images? (Affects accessibility + readability.)
8. **vdocs-web markdown XSS posture**: trusted corpus + localhost makes this low-risk, but confirm a
   sanitizer (and whether raw HTML `<img>` in bodies is allowed through).
9. **System deps for CI**: weasyprint needs pango/cairo; tectonic needs the binary. Which to install
   in CI for a PDF smoke test (mirrors the pandoc smoke test just added)?

## 9. Phased plan

- **P0 — substrate + spike (proof):** `registries/rich-publication.yaml`; the kernel asset-resolution
  helper (TDD); a throwaway one-doc PDF spike on `cprsguitm` + `fm22_2tm` across weasyprint/tectonic
  (resolve D2). *Exit:* a real PDF of each with figures + a working TOC; engine chosen.
- **P1 — PDF export (Feature B):** the `publish`/`export` stage producing per-doc PDFs for the subset
  (then optionally all gold); CLI `vdocs export`; CI PDF smoke test (mirrors the pandoc one);
  preflight checks the chosen engine.
- **P2 — rich vdocs-web (Feature A):** the subset image bundle artifact + `/api/asset/{sha}` route;
  markdown rendering in the reading pane (A1); render figures for subset docs.
- **P3 (optional) — standalone HTML site (A3)** as the L3 human-corpus deliverable from the same
  rendered output; wire into `publish`/`push`.

Each phase is independently shippable, TDD-first, gated, and (per the increment protocol)
proposal-before-code where it changes a contract.

## 10. Risks & mitigations

- **PDF engine fragility on real-world docs** (huge tables, exotic chars) → the two-doc spike on the
  hardest docs (CPRS GUI figures, FileMan tables) *before* committing; HTML-based engine (weasyprint)
  degrades more gracefully than LaTeX.
- **Payload bloat** (images) → curated subset + a *separate* bundle keeps `index.db` lean (D4).
- **New system deps vs airgap/zero-AI** → favor self-contained (tectonic binary / vendored wheels);
  `vdocs preflight` + a CI smoke test catch a missing engine with a clear message, not a traceback.
- **Determinism** (PDF/gate) → pin engine + fonts, or explicitly treat PDFs as non-reproducible
  outputs (decide D5/Q5) so the corpus-characterization gate isn't destabilized.
- **Maintainer surface** → both features extend existing slots (L3 `publish`; vdocs-web reading pane)
  rather than new subsystems, and curation stays in `registries/`.

## 11. Recommendation

Proceed in the phase order above, starting with the **P0 substrate + a two-doc PDF spike** to settle
the engine (D2) — the only decision with real unknowns. Default leans: **A1** for vdocs-web,
**weasyprint** for PDF (tectonic if print-perfect/airgap wins the spike), a **`registries/
rich-publication.yaml`** curated subset, and a **separate image bundle** so `index.db` stays
text-only. Treat the gold→PDF export as the long-planned **L3 `publish`** capability, finally built —
and the rich vdocs-web display as the interactive companion over the same resolved assets.
