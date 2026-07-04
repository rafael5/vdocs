# Proposal — vdocs gold → docs-as-code **master** (the source-of-truth inversion)

**Status:** proposal / for sign-off. **Date:** 2026-06-16. **Author:** Claude (Opus 4.8) with Rafael.
**Repos:** `vdocs` (pipeline — owns the new `publish`/L3 stage) + a new published-docs repo.
**Builds on:** `rich-publication-and-pdf-export-proposal.md` (reuses its `kernel/figures.py`
asset-resolution substrate). **Distinct from it:** that proposal is about *viewing/exporting* the
gold; this one is about making a **published GitHub repo the authoritative master** and **retiring
the VA Word/VDL source**.

> **The thesis (the inversion).** Today the master is VA MS-Word on the VDL; vdocs *ingests* it
> (`crawl→…→consolidate`) into an internal gold corpus, and `index.db` is derived from gold. The
> goal is to **flip the arrow**: a published docs-as-code GitHub repo becomes the master that VA
> edits directly; Word/VDL is frozen as a one-time import; and `index.db`, rich viewing, and PDF
> export all become **derived build outputs of the published master** — exactly the relationship
> Microsoft Learn has with the MicrosoftDocs repos.

## Table of contents

- [1. Why the current gold is not yet a publishable master](#1-why-the-current-gold-is-not-yet-a-publishable-master)
- [2. What "mirror Microsoft" actually means on disk](#2-what-mirror-microsoft-actually-means-on-disk)
- [3. Target format — the published master](#3-target-format--the-published-master)
- [4. The narrative-vs-reference table classifier](#4-the-narrative-vs-reference-table-classifier)
- [5. Front-matter schema](#5-front-matter-schema)
- [6. The `publish` (L3) stage — transforms](#6-the-publish-l3-stage--transforms)
- [7. Fidelity gate](#7-fidelity-gate)
- [8. The inversion — editing model & what git replaces](#8-the-inversion--editing-model--what-git-replaces)
- [9. Decision table](#9-decision-table)
- [10. Phased plan](#10-phased-plan)
- [11. Open questions](#11-open-questions)

---

## 1. Why the current gold is not yet a publishable master

Grounded in the lake (2026-06-16). The internal gold at
`gold/consolidated/<APP>/<slug>/body.md` is optimized for the **pipeline** (CAS dedup, version
collapse, sidecar extraction) — and three of those optimizations **break a raw github.com view**,
which is the bar a master must clear:

| Element | Current gold form | Renders on github.com? | Why it breaks |
|---|---|---|---|
| **Tables** | `_[Table 1 (extracted to CSV)](tables/table-01.csv)_` + `tables/table-01.csv` | ❌ | Shows a hyperlink to a CSV, not a table. The CSV is a *sidecar* only the vdocs-web runtime hydrates (`markTableLinks` → `/api/table/...`). |
| **Images** | `![](ef30a2…jpeg)` → `documents/assets/<sha256>.<ext>` (15,705 assets / 1.2 GB, **shared** store) | ❌ | Bare content-addressed filename; the bytes live in a *non-adjacent* shared CAS, not beside the `.md`. GitHub shows a broken image. vdocs-web only works because `/api/asset/{sha}` proxies the CAS. |
| **Boilerplate** | `_[… — shared boilerplate](_shared/boilerplate/bp-<hash>.md)_` | ❌ | Single-sourced as a link; the prose isn't inline. |
| Front matter | Rich YAML already present (title, doc_type, app_code, section, pkg_ns, version, published, app_user, doc_user, software_class, function_category, source_url, source_sha256, tool_ver) | ✅ (ignored, harmless) | — |
| Headings/TOC | Regenerated `## Contents` with `#github-slug` links | ✅ | Already github-native. |

**So the published master is a _materialized, self-contained derivative_ of the internal gold** —
not the internal gold itself. The internal gold stays as-is (it's the right shape for the pipeline);
the `publish` stage produces the master. The three breakers above are exactly the "re-incorporate
the images / CSV / yaml" work you flagged.

## 2. What "mirror Microsoft" actually means on disk

The MicrosoftDocs / Learn source format, reduced to the parts that matter here:

1. **One self-contained `.md` per article**, GFM, renders natively in the GitHub UI.
2. **YAML front matter** carrying metadata.
3. **Images committed as real files** in an adjacent `media/` folder, **relative-path** refs.
4. **Tables inline** — GFM pipe tables, dropping to **raw HTML `<table>`** only when GFM can't
   express the structure. (HTML is the fidelity escape hatch.)
5. **Conceptual vs structured-reference split** — narrative is Markdown; *reference data* (API
   tables, field lists) is **YAML with a schema**, rendered to a page at build time.
6. **Includes** for reusable blocks (`[!INCLUDE [x](../includes/x.md)]`) — the exact analog of our
   single-sourced boilerplate.
7. **`toc.yml`** navigation + a build config (`docfx.json` / openpublishing).

Mapping is almost one-to-one — our front matter is *already richer than theirs*, and our boilerplate
single-sourcing is *already an includes model*. The gaps are tables, images, and the build/repo
layout.

## 3. Target format — the published master

Per-document folder (Microsoft's "article + media folder" pattern), keyed by the existing
`app_code`/`slug`:

```
docs/                                   # the published master repo
  PXRM/
    pxrm_um/
      index.md                          # GFM + front matter — the editable master
      media/
        fig-01.jpeg                     # materialized from the CAS, relative ref
        fig-02.png
      data/
        table-01.csv                    # reference-data tables kept as data files (schema'd)
    toc.yml
  _includes/
    bp-<hash>.md                        # boilerplate as shared includes
  mkdocs.yml                            # build/publish config
```

Format decisions for `index.md`:

- **GFM-first on disk** so it renders in the raw GitHub UI (the whole point of the flip). Use only
  GitHub-native extensions (alerts `> [!NOTE]`, footnotes). No DocFX `:::triple-colon:::` in the
  committed file — those don't render on github.com.
- **Tables materialized** per the classifier (§4): narrative → inline GFM/HTML; reference → rendered
  table in the page **plus** a `data/*.csv` source file.
- **Images materialized**: copy the referenced CAS asset into the doc's `media/`, rewrite
  `![](<sha>.ext)` → `![<alt>](media/fig-NN.ext)`. Sequential `fig-NN` names (we rarely have good
  captions; alt-text backfill is a quality follow-up, not a blocker).
- **Boilerplate** → `_includes/` rendered at build (MkDocs `pymdownx.snippets`), or inlined if we
  decide the master shouldn't depend on a build step to read correctly (see Q3).

## 4. The narrative-vs-reference table classifier

The pipeline already extracts **every** table above a size threshold to `tables/table-NN.csv`. The
classifier runs at `publish` time over those CSVs and routes each:

**Signals (cheap, deterministic — no AI):**
- **Row count** — `≥ ~12` data rows leans reference.
- **Column homogeneity** — consistent arity across rows, header row of short field-like labels.
- **Header pattern** — matches known VistA reference shapes (`File #`, `Field`, `Global`, `Routine`,
  `RPC`, `Option`, `Error`, …).
- **Host doc_type / section** — a Technical Manual data-dictionary/file-listing section leans
  reference; a numbered prose step in a User Manual leans narrative.

**Routing:**
- **Narrative / presentational** → **materialize inline.** GFM pipe table when rectangular with
  simple cells (cells may carry inline markdown like `**EN^DIK**` — vdocs-web already proves inline
  markdown in cells works via `renderInline`). HTML `<table>` when cells hold block content or the
  layout is irregular.
- **Reference data** → emit `data/table-NN.csv` (or `.yml`) as the **authoritative** data file **and**
  materialize a rendered table into the page so github.com shows it. The data file is the source; the
  in-page table is generated and **drift-gated** against it. This is the MS "structured reference
  content" split — keeps big field/routine tables diffable and machine-queryable instead of buried in
  a 500-row markdown blob.

**Quality flags this surfaces (real, from the lake):** the current CSVs carry placeholder headers
(e.g. `GEC,Referral Categories,col_3`) and some flatten multi-column layouts into interleaved
numbering (`1,ADDITIONAL INFO,2` / `3,COGNITIVE STATUS,4`). Reference-table publication needs a
header/shape cleanup pass — tracked as a fidelity follow-up, not silently shipped.

## 5. Front-matter schema

Start from the front matter gold **already has** (don't reinvent), add the docs-as-code essentials,
and freeze the import provenance:

```yaml
---
# --- identity (exists today) ---
title: PXRM*2*38 Symptom Assessment System (VSAS) Template User Manual
doc_type: UM                       # ms.topic analog (UM/TM/DG/IG/SG/RN…)
app_code: PXRM
pkg_ns: PXRM
section: CLI
version: '2'
# --- audience/classification facets (exists today) ---
app_user: clinical
doc_user: clinical
software_class: I
function_category: Clinical care
# --- provenance, FROZEN at import (exists today; becomes "imported-from") ---
source_url: https://www.va.gov/vdl/documents/Clinical/...
source_sha256: eb1aa724…          # the retired Word doc this was imported from
imported_by: vdocs 0.1.0
imported_date: '2026-06-16'
# --- docs-as-code lifecycle (NEW — git-owned after the flip) ---
last_reviewed: '2026-06-16'        # ms.date analog; staleness signal
status: imported                   # imported | reviewed | maintained | deprecated
owner: pxrm-maintainers            # CODEOWNERS routing
---
```

Key shift: pre-flip, `source_*` is a *live* link to the master (Word). **Post-flip it is a frozen
"this page was imported from …" record** — the master is now this file. `last_reviewed`/`status`
become the live freshness signals, owned by git history.

## 6. The `publish` (L3) stage — transforms

A new `vdocs publish` stage (the planned-but-unbuilt L3 slot) reads `gold/consolidated/**` and emits
the master tree in §3. Pure-ish, deterministic, gated. Per document:

1. **Resolve assets** — reuse `kernel/figures.py` (already built for rich-publication) to map each
   `![](<sha>.ext)` to CAS bytes; copy into `media/fig-NN.ext`; rewrite the ref to the relative path.
2. **Materialize tables** — classify each `tables/*.csv` (§4); inline narrative tables; for reference
   tables write `data/*.csv` + a rendered table; drop the `_[Table N](…)_` placeholder.
3. **Resolve boilerplate** — rewrite `_shared/boilerplate/bp-<hash>.md` links to `_includes/` (build
   transclusion) or inline (Q3).
4. **Rewrite front matter** — freeze provenance, add lifecycle fields (§5).
5. **Emit nav + config** — generate `toc.yml` from the existing `anchor_key`/section structure;
   `mkdocs.yml`.
6. **Latest-only** — publish `is_latest=1` members (git replaces `_shared/history` — §8).

`index.db`, rich viewing, and PDF export are then rebuilt **from this master**, not from the internal
gold — closing the inversion.

## 7. Fidelity gate

"100% fidelity" needs to be *enforced*, not asserted (and it's exactly the class of bug the
`web-fix-csv-table-nesting` branch has been hand-fixing: table nesting, orphaned figures, captions).
The gate (red-gates the `publish` output):

- **No dangling refs** — every image ref resolves to a committed `media/` file; every reference-table
  page matches its `data/` source (drift check); no leftover `_[Table N]`/boilerplate placeholders.
- **Table integrity** — every materialized table parses to a well-formed table (no collapsed
  `<tr>/<td>`, the exact DOM-nesting failure vdocs-web hit); row/col counts match the source CSV.
- **Render-diff** — render source-gold vs published-master and diff structural content (headings,
  table cell text, figure count). Mismatch = red.
- **Schema-valid front matter** — required fields present; `doc_type`/`status` in controlled vocab.

This is the org's `source-tag → generate → registry → red-gate` discipline applied to docs.

## 8. The inversion — editing model & what git replaces

Once the published repo is the master, several pipeline mechanisms that assumed a Word upstream get
**replaced by git**, and this must be deliberate:

- **History** — `_shared/history/<sha>.md` CAS and `history.yaml` lineage are replaced by **git
  history**. The import is the initial commit; subsequent edits are commits/PRs.
- **Version collapse** — `anchor_key`/`is_latest` was about collapsing VDL version churn. Post-flip,
  versions are **git branches/tags** (or per-version doc folders if VA publishes parallel versions).
  Decide explicitly (Q1).
- **Provenance** — `source_url`/`source_sha256` stop being live ingestion keys and become the frozen
  "imported-from" stamp (§5).
- **Pipeline direction** — `crawl→fetch→convert→…→consolidate` runs **once** as the migration that
  seeds the master. Thereafter the pipeline's input is the **git repo**, and only the *derive* tail
  (`index`, publish-rich-assets, PDF) keeps running, now sourced from the master.
- **Contribution loop** — "Edit this page" + issue-per-page now target the master repo (real edits),
  not just conversion-defect reports. CODEOWNERS routes by `owner`/package.

## 9. Decision table

| # | Decision | Options | Recommendation | Why |
|---|---|---|---|---|
| D1 | Master on-disk flavor | GFM-pure · DocFX-flavored | **GFM-pure (+ GH alerts)** | Renders in the raw GitHub UI — the point of the flip; DocFX `:::` doesn't |
| D2 | Static-site generator | DocFX · **MkDocs-Material** · Docusaurus | **MkDocs-Material** | Python (matches vdocs + house stack); GFM superset; snippets=includes; `.md` stays github-native |
| D3 | Narrative tables | inline GFM/HTML · keep sidecar | **inline** | Sidecar can't render on github.com; master must be self-contained |
| D4 | Reference tables | inline only · **data file + rendered** | **data file + rendered (drift-gated)** | MS structured-reference split; diffable + queryable + visible |
| D5 | Images | shared CAS + proxy · **per-doc `media/`** | **per-doc `media/`, relative** | github.com needs adjacent files; drop the `/api/asset` dependency for the master |
| D6 | Boilerplate | inline · **includes** | **includes (revisit Q3)** | Preserves single-sourcing; MkDocs snippets render it |
| D7 | Versions/history | CAS+anchor_key · **git** | **git history + tags** | docs-as-code native; retires `_shared/history` |

## 10. Phased plan

- **P0 — spec sign-off (this doc).** Settle D1–D7 + Q1–Q5.
- **P1 — `publish` stage core (vdocs):** asset materialization (reuse `kernel/figures.py`) + image
  rewrite + narrative-table inlining + front-matter rewrite → master tree for one package. TDD;
  fidelity gate (§7) from day one.
- **P2 — reference-table classifier + data files:** §4 classifier, `data/*.csv` emission + rendered
  tables + drift gate. Header/shape cleanup pass.
- **P3 — boilerplate includes + nav + `mkdocs.yml`:** whole-corpus `toc.yml`, buildable site,
  github-UI render check.
- **P4 — derive-from-master:** re-point `index` (and rich-assets/PDF) to read the published master
  instead of internal gold — the actual inversion. Seed the master repo as the import commit.
- **P5 — contribution surface:** CODEOWNERS, edit-this-page, issue templates; VA editing workflow.

Each phase independently shippable, TDD-first, gated; the pipeline keeps working throughout (the
master is additive until P4 flips the source).

## 11. Open questions

1. **Versioning model post-flip** — git tags for VistA patch versions, parallel version folders, or
   branches? (VA may ship multiple supported versions simultaneously.)
2. **Reference-table source format** — `data/*.csv` (simplest, matches what exists) or `data/*.yml`
   with a schema (closer to MS structured reference, better for the index)?
3. **Boilerplate: includes vs inline** — includes preserve single-sourcing but make the raw `.md`
   depend on a build step to read whole; inlining makes each file fully self-contained on github.com.
   Which wins for "the master *is* the GitHub docs"?
4. **Who owns the master repo / governance** — is this a VA-facing repo (VA edits) or a vista-cloud-dev
   staging mirror first? Determines CODEOWNERS and the contribution workflow.
5. **Image alt-text/caption backfill** — `![]()` is mostly empty alt today; is sequential `fig-NN`
   acceptable for v1, with caption backfill as a follow-up, or is alt-text a fidelity requirement?
