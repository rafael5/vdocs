# Findings — gold title page, revision history, and legacy TOC are not being cleaned

**Status:** root-caused; design updated (§6.3 / §6.4 / §6.6 / §6.7); remediation not yet
implemented.
**Audit scope:** `~/data/vdocs/documents/gold/consolidated/*/*/body.md` — **290 documents**.
**Machine report (per-document tables + evidence):**
`~/data/vdocs/reports/fidelity/gold-titlepage-revhist-toc-audit.md`.
**Remediation kickoff:** [`prompts/vdocs-remediate-gold-cleanup.md`](prompts/vdocs-remediate-gold-cleanup.md).

---

## 1. The desired end state (per document)

A consolidated gold document should read: frontmatter → modern link-based `## Contents` →
**standardized** title block → Introduction → body. Specifically:

1. **Standardized title-page block** — built from frontmatter, not the raw legacy cover.
2. **No revision history** — no heading, no descriptive boilerplate, no revision tables, and no
   in-body mention. The revision facts live in `revisions.yaml` / `history.yaml` (§6.4 / §6.6).
3. **No legacy text TOC** — the page-numbered `[Title [n](#anchor)](#anchor)` list (and its
   "Table of Contents" header) is gone; only the derived `## Contents` remains (§6.7).

The gold corpus currently fails all three. **Only 30 of 290 docs are clean on all three; 260 need
work.** Co-occurrence: 157 docs have all three problems at once.

---

## 2. What is wrong, with measured corpus numbers

| Problem | Affected docs | Notes |
|---|---:|---|
| **P1 — Legacy title page** (raw cover: "Department of Veterans Affairs" / Month-YYYY date / blank-page furniture in the pre-Introduction region) | **255 / 290** | 9 docs still carry "This page intentionally left blank" |
| **P2 — Revision history present** (heading / table / descriptive boilerplate) | **200 / 290** | 84 carry an HTML revision table; 33 carry the "the following table displays the revision history…" boilerplate |
| **P3 — Legacy text TOC present** | **210 / 290** | 184 have page-numbered double-bracket TOC lines; 180 have a "Table of Contents" header; **11,180 legacy TOC lines** corpus-wide |
| Missing the modern `## Contents` (TOC-integrity gap) | 30 / 290 | these need a derived TOC generated |

---

## 3. Root causes

### P1 — the publication date is captured *nowhere* except the legacy title page

The legacy cover is the **sole source of truth** for the document's publication date, and that date
is not persisted anywhere downstream:

- **Frontmatter has no date field at all** (keys: `title, doc_type, app_code, section, pkg_ns,
  version, source_url, source_sha256, tool_ver, patch_id, template_id`).
- **`history.yaml › official_date`** is non-empty for only **8 / 290** docs. It is *derived* from
  `revisions.yaml › revision_newest`, so it is empty wherever P2's extraction failed.
- **Upstream VDL catalog `file_date`** is populated for only **26 / 8834** crawl rows — not a
  reliable source.

**Consequence:** stripping the title page today would destroy the only copy of the publication date
for ~280 documents. → The title page must not be removed until its date is captured.

### P2 — the revision-table detector matches ≈ 0 real tables

`normalize` → `revision_pure.extract_revision_history()` → `find_revision_table()` gates every
candidate table on `revision_pure._is_revision_header`:

```python
def _is_revision_header(header: str) -> bool:
    return "date" in header and "change" in header and ("version" in header or "patch" in header)
```

It requires a **`change`** column AND a **`version`/`patch`** column. But the real VA revision tables
use **`Description`** (not Change) and **`Revision`** (not Version):

| header columns | docs | matched by current code? |
|---|---:|:--:|
| Date · Revision · Description · Author | 42 | ✗ |
| Date · Version · Description · Author (+ bold variant) | 37 (+13) | ✗ |
| Date · Description · Author | 8 | ✗ |
| Date · Description (Patch # if applic.) · Project Manager · Technical Writer | 5 | ✗ |
| Date · Revision · Description · Contacts | 3 | ✗ |

**Measured detection rate: 0 of 168 revision tables.** Because detection fails the table is never
removed (the body keeps it), `revisions.yaml` is never written, `consolidate` folds nothing →
`history.yaml › revisions: []` and `official_date: ''`. This is the *same* failure that empties P1's
date. The ~10 docs that *did* capture revisions are the rare ones using a `…Change…`/pipe-table
layout. (Note also: the revision-history *heading* detector in `discover_pure.py` line ~49 only
matches `#`-ATX headings, missing the `**bold**` / blockquote / plain forms the corpus uses.)

### P3 — the modern `## Contents` is built blind to the legacy TOC, and the legacy TOC is rarely a heading

`anchors_pure.parse_headings` regenerates `## Contents` purely from the **surviving ATX heading
tree**; it never consults the legacy TOC. The legacy strip in `normalize` removes a TOC only when it
sits under a recognised *heading* (`registries/structures`, CANONICALIZE `toc`) — but in most gold
docs the legacy TOC sits under a plain `Table of Contents` line (not an ATX heading), so the strip
never fires while the modern `## Contents` is still added on top → two TOCs.

Separately, the legacy TOC is the natural **completeness oracle** (it lists *intended* sections, each
with a `(#anchor)`): of 181 docs that have both TOCs, **43 docs / 2,304 legacy entries** have no
counterpart in the derived `## Contents` — a mix of unresolved Word bookmarks (`#_Toc…`/`#_Ref…` =
headings that lost their level/bookmark in conversion) and deeper slugs below the Contents depth cut.
The design already names these the "fidelity oracle" and "heading-recovery" roles (§6.7); the code
does not implement them.

---

## 4. Data-safety gates (non-negotiable)

The remediation must **capture before it strips**. No legacy block leaves a body until the fact it
uniquely carries is persisted:

- **Do not strip the title page** until its publication date is in frontmatter `published`
  (and/or `official_date`).
- **Do not strip the revision history** until it is parsed into `revisions.yaml` (and folded into
  `history.yaml`). A revision-history heading with no parseable table → leave it and **flag** it.
- **Do not drop the legacy TOC** until its entries are correlated to the derived `## Contents`
  (role-1 cross-check); unresolved entries become heading-recovery inputs + fidelity flags.

---

## 5. Design changes already made (`docs/vdocs-design.md`)

- **§6.3** — added `published` (publication date, title-page-sourced) to the identity frontmatter;
  it is the capture-gate for title-page removal.
- **§6.4** — three new contract blocks: the **corrected revision-table detection contract**
  (`date ∧ (description|change)`, optional `version|revision|patch`, markup-stripped, gated on
  proximity to a revision-history heading); **capture-before-strip (fail-safe)**; and
  **title-page publication-date capture** + standardized block.
- **§6.6** — the declutter paragraph now states the revision strip is capture-gated.
- **§6.7** — added the **correlate-before-dropping** gate for the legacy TOC.

The code does not yet honor these; that is the remediation work.
