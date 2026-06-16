# Proposal — Rich reading: tables (gold-for-reading vs gold-for-indexing)

**Status:** proposal / for sign-off. **Date:** 2026-06-15. **Author:** Claude (Opus 4.8) with Rafael.
**Repos:** `vdocs` (pipeline) + `vdocs-web` (consumer).
**Relates to:** [`rich-publication-and-pdf-export-proposal.md`](rich-publication-and-pdf-export-proposal.md)
(figures, already built) — this is the **table** analogue of that work.

> **One-line decision (agreed 2026-06-15):** *treat gold-for-rich-web-reading differently from
> gold-for-indexing/search.* The lean indexed body stays lean; the **reading** consumer augments it
> at render time with the table data — exactly as it already does with figures.

## Table of contents

- [1. Context — what exists today](#1-context--what-exists-today)
- [2. The two bugs (and the one that isn't a bug)](#2-the-two-bugs)
- [3. Blast radius (measured)](#3-blast-radius-measured)
- [4. Decision: reading ≠ indexing](#4-decision-reading--indexing)
- [5. The design](#5-the-design)
- [6. Producer changes (`vdocs`)](#6-producer-changes-vdocs)
- [7. Consumer changes (`vdocs-web`)](#7-consumer-changes-vdocs-web)
- [8. Approaches considered & rejected](#8-approaches-considered--rejected)
- [9. Phased plan](#9-phased-plan)
- [10. Open questions](#10-open-questions)
- [11. Risks](#11-risks)
- [12. Recommendation](#12-recommendation)

---

## 1. Context — what exists today

Grounded in the live lake/code (2026-06-15), `DI/fm22_2dg` (FileMan Developer's Guide) as the worked
example:

- **`convert`** emits complex tables as raw HTML `<table>` (Pandoc) or GFM pipe tables (Docling).
- **`normalize` (`tables_pure.py`, §6.4/§6.5/§9.6)** *deliberately* lifts genuinely large tables —
  `≥ 10` total rows **or** `≥ 8` columns — into a **`tables/table-NN.csv` sidecar bundle** and
  replaces them in the body with a markdown reference link
  `_[Table N (extracted to CSV)](tables/table-NN.csv)_`. The §6.5 "don't-over-decompose" guardrail
  leaves ~75% of tables (the short/narrow ones) inline as GFM/HTML. **This is by design** — it keeps
  the body readable *for the lexical index* and keeps the tabular data queryable as CSV.
- The sidecars are written under `silver/text/03-normalized/<app>/<slug>/tables/*.csv`.
- **`consolidate`** promotes the *latest* member of each anchor group to
  `gold/consolidated/<app>/<slug>/` as a **signed bundle** (`bundle.yaml` carries every part + its
  sha256; the `validate` gate recomputes from disk — tamper-evident).

## 2. The two bugs

### 2a. Images — raw HTML `<img>` not routed (FIXED, `vdocs-web`)
Pandoc emits figures with inline sizing as raw `<img>` HTML, not markdown `![](…)`. The reading
pane's `markdown.ts` only rewrote the markdown form, so raw `<img>` `src` kept its bare
content-addressed name and 404'd. **Fixed** (`vdocs-web` PR #10): a post-render pass routes *every*
`<img>` (markdown- and HTML-emitted) to `/api/asset/<sha>`. Not part of this proposal; noted for
completeness.

### 2b. Tables — sidecars dropped at consolidation (THE BUG)
`consolidate` assembles each gold bundle from an explicit part set — `body.md`, `flags.yaml`,
`toc.yaml`, `capture.yaml`, `history.yaml`, `bundle.yaml` — and then **prunes any file in the anchor
dir not in that set** (`stage.py:128–131`). The `tables/` sidecar dir is **never added to the part
set**, so it never reaches gold. Result: the gold body's `tables/table-NN.csv` links are **dead** —
the table content lives in silver but is invisible to every gold consumer.

### 2c. Not a bug: the CSV extraction itself
Extracting large tables to CSV is the intended §6.4 behavior and is *correct for the index*. The
defect is purely that gold (and thus the reading consumer) loses the sidecar. We are **not** undoing
extraction.

### 2d. Minor data quirk (separate, low priority)
Some HTML `<caption>` labels are misnumbered (e.g. `DI/fm22_2dg` Table 2's `<table>` carries
`<caption>Table 3…</caption>`), and CSV-link labels renumber independently (`table-01.csv` for the
doc's "Table 3"). Cosmetic; tracked but not blocking.

## 3. Blast radius (measured)

Counted over the live lake, 2026-06-15:

| Metric | Count |
|---|---|
| Gold docs total | 615 |
| **Gold docs with ≥1 dead CSV-table link** | **435 (71%)** |
| **Dead table links in gold bodies** | **4,233** |
| Table CSVs that reached gold | **0** |
| Table sidecars sitting in silver (the data) | 6,563 CSVs / 731 docs |
| *(context) raw `<img>` fixed by 2a* | 17,891 imgs / 368 docs |

71% of the reading corpus is missing at least one table. This is the single biggest reading-fidelity
gap after the (now-fixed) image issue.

## 4. Decision: reading ≠ indexing

The gold corpus serves two consumers with **opposite** needs for big tables:

- **Index / search (`index.db`, FTS5):** wants the body *lean* — a 200-row data dictionary inlined
  would bloat the body and dilute FTS relevance. CSV sidecar is right.
- **Rich web reading (`vdocs-web`):** wants the table *visible* — a link to a missing CSV is useless.

**Agreed direction:** keep **one lean `body.md`** (serves the index unchanged) and have the
**reading consumer augment** it at render time with the table data carried as a **sidecar** — the
same shape already proven for figures (figures are sidecar assets the reading pane fetches via
`/api/asset`; tables become sidecar CSVs the reading pane fetches and renders inline). No second
body; no index change; no re-extraction.

## 5. The design

```
normalize ── body.md (lean, links) + tables/*.csv (sidecars)   [unchanged]
     │
consolidate ── gold bundle: body.md + … + tables/*.csv  ← NEW: carry + sign the sidecars
     │
distribution ── rich-publication bundle also ships the doc's tables/*.csv  (mirrors rich-assets)
     │
vdocs-web ── GET /api/table/{docKey}/{name}  → serve a sidecar CSV
            reading pane: replace each `[Table N (extracted to CSV)](tables/table-NN.csv)`
                          link with the CSV rendered inline as an HTML <table>
index.db ── unchanged (body.md still lean; tables still links — search unaffected)
```

The indexed body and the read body are **the same file**; the reading pane *layers tables on top* by
resolving the link to live CSV data, just as it layers figures on top by resolving `<img>` to CAS
bytes. "Treat reading differently" is realized at the **consumer**, not by forking gold.

## 6. Producer changes (`vdocs`)

1. **`consolidate` carries the `tables/` sidecar** (the core fix):
   - When assembling the latest member's bundle, read its `tables/*.csv` (alongside `body.md`) and
     add each as a bundle **part** (e.g. keyed `tables/table-NN.csv`).
   - Fold those parts into **`bundle.yaml`** (sha256 each) so the `validate` gate accepts them and
     the bundle stays tamper-evident.
   - Extend the **expected-part set** so the staleness prune (`stage.py:128–131`) keeps them, and
     prunes a `tables/` entry only when the latest member no longer has it.
   - **Bump `Consolidate.contract_ver`** (currently 1) → re-runs `index` (mechanical; the index
     content is unchanged, but the gold bundle layout changed).
   - **Open:** part-key/dir handling — bundle parts are currently flat filenames; carrying a `tables/`
     subdir means either flattening keys (`tables/table-NN.csv` as a literal key) or teaching the
     bundle writer/manifest about a subdir. Decide in P1.

2. **Distribution** — the rich-publication bundle (`publish-rich-assets` → `rich-assets/`) should
   also ship each curated doc's `tables/*.csv`, so a downloaded-only install gets tables like it gets
   figures. (Or a parallel `rich-tables/` bundle — decide in P2; reuse the assetfetch pattern.)

3. *(Optional, 2d)* caption/number reconciliation — left out of v1.

## 7. Consumer changes (`vdocs-web`)

1. **Serve sidecar CSVs** — `GET /api/table/{docKey}/{name}` returns a doc's `tables/table-NN.csv`
   from the gold bundle (path-safe: `name` a bare `table-NN.csv`; docKey resolved like `/api/preview`).
   Mirror the `/api/asset` safety checks.
2. **Render tables inline** — in the reading-pane pipeline, detect the
   `[Table N (extracted to CSV)](tables/table-NN.csv)` link and replace it with the CSV fetched from
   the new endpoint, parsed to an HTML `<table>` (reuse the existing `.markdown :global(table)`
   styling). Wide data-dictionary tables (8+ cols) get a horizontal-scroll container so the page
   itself never scrolls sideways (consistent with the figure width-cap decision).
   - **Open:** client-side CSV→table (fetch per visible table) vs. producer pre-renders the CSV back
     to an HTML `<table>` string the body already contains. Client-side keeps the body lean and is
     symmetric with figures; pre-render is simpler in the consumer but re-bloats the read body.
     Leaning **client-side**.

## 8. Approaches considered & rejected

- **Inline-expand tables into the single gold `body.md`** — simplest consumer, but **bloats the
  indexed body** (a 200-row DD inlined), directly contradicting §4. Rejected.
- **Second, reading-only gold body** (`body.reading.md` with tables inlined) — honors §4 but
  duplicates every body, doubles consolidate output, and splits "which body is truth." Heavier than
  sidecar-augmentation for no extra benefit. Rejected (sidecar wins).
- **Stop extracting tables in `normalize`** — would fix reading but regress the index design (§2c)
  and re-bloat FTS. Rejected.
- **Download links only** (serve the CSV as a file download, no inline render) — minimal, but the
  user reads in a pane; a download is not "the table displays." Acceptable as a P-zero stopgap only.

## 9. Phased plan

- **P0 — image fix** ✅ (`vdocs-web` PR #10) — independent; shipped.
- **P1 — producer: carry `tables/` into gold.** `consolidate` adds + signs the sidecars; `contract_ver`
  bump; `validate` accepts them; re-consolidate + re-index the corpus. TDD: a consolidate test
  asserting a doc's `tables/*.csv` land in its gold bundle and appear in `bundle.yaml`. **Unblocks
  everything.**
- **P2 — consumer: serve + render.** `/api/table/...` endpoint + reading-pane CSV→`<table>` inline
  render (+ wide-table scroll container). TDD: endpoint path-safety + a `markdown`/render unit test
  that a CSV-link becomes a `<table>`.
- **P3 — distribution.** Ship `tables/*.csv` in the rich-publication bundle (assetfetch-style) so
  downloaded-only installs get tables. Mirrors the figure-bundle consumer.
- **P4 (optional) — caption/number reconciliation** (2d).

## 10. Open questions

1. **Bundle part keys for a subdir** (§6.1) — flatten `tables/table-NN.csv` as a literal part key, or
   teach `bundle.yaml`/the writer about a `tables/` subdir? Affects `validate`.
2. **Client-render vs producer pre-render** the CSV (§7.2) — leaning client-side (lean body, symmetric
   with figures).
3. **Distribution shape** (§6.2) — fold tables into the existing `rich-assets/` bundle, or a parallel
   `rich-tables/`? One manifest vs two.
4. **Scope of the re-run** — full corpus re-consolidate+re-index, or only the 435 affected docs?
   (Consolidate is `SKIP_IF_UNCHANGED`; a `contract_ver` bump invalidates all → full re-index.)
5. **Caption fidelity** — is fixing the misnumbered captions (2d) worth a normalize change, or leave
   as-is?

## 11. Risks

- **Bundle/validate regression** — adding parts touches the signed-manifest + staleness-prune logic;
  a mistake trips the `validate` integrity gate corpus-wide. Mitigate: TDD the consolidate change
  against `validate` on a single doc before the full re-run; baseline first.
- **Re-index cost** — `contract_ver` bump forces a full `index` rebuild (~minutes, mechanical). Run
  on the shared lake per the operator-race rule (check for a live `vdocs run` first).
- **Wide tables in a narrow pane** — 8+ column DDs; mitigated by a scroll container, but readability
  of very wide tables in a reading pane is inherently limited (acceptable: data is visible + scrollable).
- **CSV fidelity** — `kernel/csv` round-trip must preserve cell content (carets, multiline) faithfully
  for the rendered table to match the original. Spot-check during P2.

## 12. Recommendation

Adopt the **sidecar-augmentation** design (§5): one lean body for both consumers, tables carried as
signed gold sidecars and rendered inline by the reading pane at render time — the table analogue of
the shipped figure path. Sequence **P1 (producer carry) → P2 (consumer serve+render) → P3
(distribution)**; P1 is the unblocker and the only piece touching the signed bundle, so do it first,
behind a single-doc TDD check, before the corpus re-run.
