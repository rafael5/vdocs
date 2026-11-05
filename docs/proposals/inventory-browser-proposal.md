# Inventory browser — the whole VDL catalog in vdocs-web

**Status: PROPOSED · 2026-11-05 · amended 2026-11-05 after adversarial review · all decisions
taken 2026-11-05 · step 0 landed 2026-11-05** — nothing else built.
Producer: vdocs · consumer: vdocs-web · read contract 1.6 → 1.7 (additive). An interactive mockup
over the real 2026-11-05 inventory lives in a private Claude artifact
(<https://claude.ai/artifact/UP9W8LRkwXcyHVwhgTBVn5>); this file is the proposal of record. Every
number in §1, §3 and §4 was measured on the 2026-11-05 lake by `scripts/inventory_measurements.py`;
[`reports/inventory-browser-measurements.md`](../../reports/inventory-browser-measurements.md)
names what it read and gives each figure beside the value printed before step 0.

## Abstract

vdocs holds a 9,080-row inventory of the VA Document Library but shows it only as two CLI totals.
This proposal carries the inventory inside `index.db`, one row per VDL listing with the Library's
facets plus three of its own — whether a record reached gold, its disposition and the reason — and
each document's own last-updated date, so vdocs-web can show the whole catalog beside the Library
without a new file, download or binary. The producer half is small: the index stage gains the gold
inventory as an input and runs two functions it already depends on. The adversarial review of
2026-11-05 found that the join between inventory and gold breaks whenever VA re-files a document
(14 of the 15 "gold only" documents are one such re-filing), that an inventory row has no key,
and that three statements in the first draft did not hold as written. Those are corrected in place,
as are the ten figures step 0 found had moved when it re-measured them. The
calls that remained are recorded in §10 with their options, and all were decided on 2026-11-05 as
recommended. The order is producer first; identity continuity across re-filing lands before the web
mode; and the web mode is a separate go/no-go once the table has been used.

## Contents

1. [Why](#1-why)
2. [What the mockup shows](#2-what-the-mockup-shows)
3. [What a record is, and the facets](#3-what-a-record-is-and-the-facets)
4. [Dates](#4-dates--the-documents-own-last-update-never-its-vdl-posting)
5. [Design](#5-design)
6. [Portability](#6-portability--vdocs-web-stays-self-contained)
7. [Staleness](#7-staleness)
8. [Order of work](#8-order-of-work)
9. [Deliberately not building](#9-deliberately-not-building)
10. [Decisions](#10-decisions)
11. [Fixes this proposal's measurements triggered](#11-fixes-this-proposals-measurements-triggered-all-landed-2026-11-05)
12. [References](#12-references)

## 1. Why

The inventory is only visible as two CLI totals. `vdocs inventory --status` counts 3,834 distinct
documents by fetch status (every non-noise `doc_id`, of any system type; 2,886 of them VistA as
the gate defines it); `vdocs completeness` counts all 9,080 catalog records by disposition.
Neither lists records, neither filters, and neither connects a record to the gold document it
became. Joining the inventory to `index.db` on `doc_id` showed two things neither
command reports:

- **216 records counted as held have no gold document**: 152 archived sole survivors, 52 DOCX the
  policy keeps and 6 PDF-only documents were never fetched; 5 fetches failed and 1 PDF was rejected
  as bad content (largest: SD 39, VBECS 27, CPRS 25, ROR 24, PSO 16). Step 0 first counted 219:
  `classify()` also held three PDFs whose DOCX twins it could not pair, because neither row has an
  anchor key; `722d2c2` pairs them by `doc_id`. The completeness verdict still reads COMPLETE
  because it rules on what is admitted, not what is held (backlogged in `TODO.md`).
- **15 gold documents have a `doc_id` no current inventory record carries.** This is not a
  catalog gap. 14 are the ISS release user guides VA re-filed from ADT to Scheduling: gold still
  knows them as `ADT:iss_release_…`, the inventory now lists the same slugs under SD, and the
  re-filing changed the id because the app code is part of it (the identity audit of 2026-08-05
  measured this: the app code contaminates `doc_id`, `doc_key`, `anchor_key` and `group_key`). The
  fifteenth, a PSS dosing-order-check manual, is a genuine VDL departure. The same 14 SD records
  would count as "held but not in gold" on the other side of the join, so an inventory browser
  built on the raw id reports one re-filing as two anomalies. See decision D1.

## 2. What the mockup shows

vdocs-web's current layout and theme, with an Inventory mode beside Library:

- **Filter pane** (left): the Library's facet controls — collapse all, clear, per-facet count/A–Z
  sort, vocabulary tooltips — over the facets in §3.
- **Results table**: a file icon (PDF, DOCX or legacy DOC — 7 records are `.doc`) linking to the
  record's original on the VDL, then title and `doc_id`, last-updated date, application, doc type,
  disposition and gold status. Columns sort by click; results open newest first.
- **Summary strip**: a disposition bar over the current selection, plus one-click views for
  *held but not in gold*, *in gold but not in the inventory*, and *unreachable + undecided*. The
  second view is a query over gold documents, not a filter over inventory rows (§3, *In gold*).
  Re-filed documents appear in neither, because identity continuity across re-filing lands before
  the web mode (D1).
- **Record panel**: disposition with the reason's full explanation, gold status, the Library facet
  values, the record's fields, how many application pages list the same file (D2), and the VDL
  link. *Open in library* hands a gold document to the
  Library reader by its `doc_key`. The panel is addressed by the row key of §3.
- **Search**: the Name scope only (title, file name, `doc_id`, patch id), plus a month range on the
  last-updated date. Full-text and headings search need a document body, which only gold documents
  have.

## 3. What a record is, and the facets

**A record is one VDL listing**: one link on one application page, as `inventory.json` holds it.
It is not a document. Measured on 2026-11-05:

| Quantity | Count |
|---|---|
| Records (listings) | 9,080 |
| Distinct `doc_id` (app code + slug) | 5,032 |
| Records sharing one `doc_id`, at most | 6 |
| Records of the 9 links listed on 148 application pages each (8 benefits forms, a VA strategic plan) | 1,332 |
| Records with a gold match on `doc_id` | 2,120 |

Neither `doc_id` nor the VDL URL is unique, so a row needs its own key. The inventory record carries
no `doc_id` field; the id is derived by `kernel.ids.doc_id` (app code and slug), and the proposed
rows derive it through that one function, never a second format string. No combination of fields
distinguishes every row: (application page URL, section, file URL, patch id) separates 9,073 of
the 9,080. The 7 surplus rows come from 5 links listed more than once on one page: three files
listed twice with every field identical, and one manual (`DVBA_UM`, DOCX and PDF) listed three
times under three different titles and two doc codes. The app *code* cannot stand in for the page
URL: 171 app codes appear on more than one application page (LR on 12). The row key is therefore a hash
of those four fields plus an ordinal among the rows that share them, assigned by sorting those rows
on their full canonical content (§5), so it is stable under VA reordering a page and changes only
when the listing itself does; over the 2026-11-05 inventory it gives 9,080 distinct keys. The
1,332 records of the 9 repeated links stay as rows, each with its disposition (*not-vista:vba-form*
for the 8 forms, *not-vista:va-reference* for the plan); they are not collapsed (D2).

| Facet | Group | Where the value comes from |
|---|---|---|
| Year updated | Date | The document's own last update (§4), plus *Undated* |
| Domain | Library | Application → functional domain, through the same `profile_tags()` that tags gold documents |
| Audience | Library | Doc type → reader persona, or the application's operators (`doc-user.yaml` maps the omitted types too) |
| Type | Library | The Library's three families plus Other, each opening into its doc-type codes; families move from the Svelte page into the vocab table (§5) |
| App user | Library | Application → primary persona |
| Namespace | Library | The record's package namespace; full name from the PACKAGE file (#9.4), else the same-code application, flagged as such (D4). Code/Name toggle |
| In gold | Inventory | Current, earlier version, or not in gold — a join on `doc_id`. *Gold only* is not a facet value: those are gold documents, not inventory rows, so the Library's counting rule (each facet counted with its own selection relaxed) cannot cover them; the summary strip queries them |
| Disposition | Inventory | The six completeness outcomes from `classify()` |
| Reason | Inventory | The reason `classify()` records; hovering shows its full explanation |
| Application | More | Code and full name. Code/Name toggle |
| VDL section, Format, Lifecycle | More | The inventory record itself |

For the 2,120 record-to-gold matches, the computed Domain, Audience, App user and Type agree with
`index.db` every time; Namespace differs on 2 documents where the pipeline corrected it after the
inventory (`CPRS:cprslmtm`, CPRS in the inventory and OR in gold; `POC:lab_poc_iug`, POC and LA).
2,305 records have no application profile — 2,298 of them are not VistA — and show as
*(no profile)* so every facet's counts add up.

**Namespace names.** The PACKAGE file (#9.4), via vista-meta's measured export
(`package-namespace.tsv`, vista-meta `f1e9d33`), names 102 of the 161 inventory namespaces (6,710
records); 56 more (1,717 records) are really application codes — mostly web and commercial products
such as WEBP and VBECS — and would take the application's name, flagged as such; 3 (XUSC, PREC,
PREN — 92 records) have no name anywhere; 561 records have no namespace. 94 namespaces are named
both by the PACKAGE file and by a same-code application, and the two names are equal after folding
case and punctuation for 37 of them; most of the other 57 differ by an abbreviation or a
"Pharmacy:"-style prefix (the report lists every pair). Applied to the Library this would name all
96 namespaces instead of 92, name DG, USR, BPS and PSGW for the first time, and change 46 names. A
reading of that list in the report — a reading, not a measurement — finds 7 changed in substance
(FH, GMRV, LA, MMRS, OR, QAC, SPN) and 39 reworded. The Library keeps its current names in this
change; those renames are their own small change (D4). The names registry's header records the
vista-meta release and commit it was copied from.

## 4. Dates — the document's own last update, never its VDL posting

**The rule.** A record's date is the newest dated entry in its document's Revision History table;
when there is none, the title-page date. Both come from the document's own text, at month precision
(`YYYY-MM`, the shape every `history.yaml` member carries). This is `official_date`, which
`consolidate` already computes and writes to each anchor's `history.yaml` — a file the index stage
already walks for every gold document — but the read contract does not publish: `index.db` carries
only the title-page date. The VDL posting date is never used: the crawl records one for only 28 of
9,080 links, and it says when the file moved, not when the content changed.

**Why the title page is not enough.** For 332 gold documents the newest revision is later than the
title page — a median of 14 years later. The RPC Broker TCP/IP Supplement (`xwb1_1p44um`) has a
2005-01 title page and a 2022-08 newest revision.

**Coverage.** 990 of the 1,040 gold documents are dated (856 from Revision History, 134 from the
title page), which dates 2,018 inventory records through `doc_id`, PDF twins included. The other
7,062 records are *Undated*: they sort last and drop out while a month range is set. Of those,
3,228 are not VistA and 3,834 are VistA records. The first draft called all 3,834 "never fetched";
that is not so. 102 are records of the 50 gold documents that carry no date at all. The other
3,732 records (1,861 distinct `doc_id`s) have no gold document: 1,860 are copies covered by another
format, 1,656 have a doc type the policy omits, and 216 are the held records of §1. Of the 3,732,
3,721 were never fetched, 10 belong to fetches that failed and 1 to the PDF rejected as bad
content. (The `inventory --status` total is also 3,834; it counts a different thing, distinct
non-noise documents of any system type, and the two must not be read as one number. Step 0
measured the undated figure directly rather than by subtraction: the match is a coincidence.)

The consequence is plain: the date facet covers about 22 % of rows. It is a gold-document attribute
projected onto the inventory, and the Inventory mode says so where the facet sits. Dating the
never-fetched documents is out of scope (D6).

**Fixed before this proposal (vdocs `9f9df51`, applied to the lake 2026-11-05):** a null revision
date no longer becomes the date `"None"` (67 documents had skipped their title-page fallback, and one
version group served VS GUI Technical Manual release 1.7.31.2 instead of 1.7.56.1); a revision dated
after the run month is ignored (GMRC `consum` records `3018-03`); and the measured revision-date
shapes (`07/24`, `12-22-2004`, `September 26, 2008`, …) now normalize — the newest date changed for 82
of 858 documents. The remaining gaps are backlogged in `TODO.md`.

**Inherited, not fixed here.** Version ordering ranks unpatched members below patched ones
regardless of date, so 11 version groups serve an old document as latest (memory, PXRM refresh
2026-11-05); those will show as *Current* in the In-gold facet until that is fixed.

## 5. Design

```
inventory/gold/inventory.json + registries ─▶ vdocs index ─▶ index.db ─▶ release bundle ─▶ vdocs-web
                                               (classify()  (one more    (ships it       (Inventory
                                                + profile_   view + vocab   whole)          mode)
                                                tags())      + meta hash)
```

**Producer — vdocs.**

- The index stage gains the gold inventory as an input. It is stage 2's artifact
  (`GOLD_INVENTORY`, produced by `serve-inventory`), so the edge is one more entry in `requires`.
  The index has required the registries since `a5b4363`, so the gate policy (`scope-policy.yaml`,
  `doctype-policy.yaml`) and the profile maps are already covered; `sole_survivors()` and the DOCX
  anchor set are pure over the records and the policy. In the same atomic build that writes
  everything else the stage runs the existing `classify()` and `profile_tags()` over every record
  and writes one row per record.
- Each row carries the row key (§3), `doc_id` from `kernel.ids.doc_id`, application code and name,
  VDL section, doc type, title, file name, format, patch id, lifecycle label, system type, VDL URL,
  the four profile tags, the namespace, and the disposition with its reason.
- `classify()` composes its reason strings inline (`doctype-omitted:RN`,
  `not-vista:system-type=Web client`, `format:pdf-duplicate`, …). The reason explanations are
  **not** regenerated from the four policy registries — that would be a second copy of the grammar.
  `classify()` returns the reason as a structured kind plus value alongside the string, the vocab
  rows are the distinct kinds the function actually emits over the inventory, and each kind's
  explanation is one sentence keyed by kind, worded from the registry that produces it.
- The read contract gains one projection view over that table and a capability that says it is
  populated — additive, so 1.6 → 1.7 and every 1.x consumer keeps working. Note what a capability
  is: a name in `contracts/read/v1.json`, not a stamp in the database. `meta` carries only
  `read_schema_version`, so a consumer learns a view exists by the MINOR version, not by asking the
  database (see the consumer bullet on the missing-view path).
- v_documents gains the corrected last-updated date and its source (Revision History or title page),
  in the same bump, read from the `history.yaml` members the stage already loads. Inventory records
  get it through the `doc_id` join; the Library can use it too.
- The vocab table gains: the six disposition definitions, the reason-kind explanations above,
  namespace full names (read by the Inventory mode only, D4), and the doc-type families. The families are today a hardcoded list in
  vdocs-web's Svelte page (`TYPE_FAMILIES`, with the comment "could move to a registry later"); the
  Inventory mode makes a second consumer of that taxonomy, and the bump is being made anyway, so
  they move into the producer now — one taxonomy, two consumers, one source.
- `meta` gains the inventory's record count and content hash. The hash is order-independent,
  computed the way the crawl snapshot's `canonical_hash` is — sorted canonical rows — over the
  enriched records, because `inventory.json` keeps the order VA's pages happened to list and the
  enrichment changes with the registries, not only with the crawl.

**Gold status is not stored.** vdocs-web derives it by joining `doc_id` to v_documents, and finds
gold-only documents with the reverse join; storing it would copy a fact the contract already
publishes. (The profile tags *are* stored, although they are recomputed from the same function the
gold documents use: a tag is a property of the record, gold status is a relation between two
tables.)

**Consumer — vdocs-web.**

- Reads the new view, v_documents and v_vocab: no new files, no new download, no access to
  `~/data/vdocs`.
- New read-only API routes for inventory facets, rows and a single record by row key, with the
  Library's facet rules (OR within a facet, AND across, each facet counted with its own selection
  relaxed) and its own fixed facet list. Go tests against a fixture `index.db`.
- Inventory mode beside Library; the facet pane is reused and the reading pane becomes the results
  table and record panel. Type families come from v_vocab in both modes; the Library's namespace
  names are unchanged (D4).
- An `index.db` without the view gets an explicit message naming the cause and the fix (re-run
  `vdocs index`), never an empty list. Today `Open()` refuses only a different MAJOR; a 1.7 build
  opens a 1.6 database cleanly and would fail on the first inventory query. The Inventory routes
  therefore compare the stamped MINOR against the vendored contract before querying, and say which
  version they need.
- The vendored contract copy in `internal/index/contract/v1.json` is updated by hand; vdocs-web has
  no drift check against the producer (the `make contract-check` target existed in vdocs-tui, not
  here), so the bump is a two-repo commit pair and the §8 order makes the producer land first.

## 6. Portability — vdocs-web stays self-contained

The binary does not change in kind: static, CGO-free, front-end embedded, built for Linux, macOS and
Windows by `make dist`. The data travels inside `index.db`, which the release bundle already ships
whole and vdocs-web already auto-downloads. Measured cost: the 9,080 rows with their facet columns
take 3.1 MB as a scratch SQLite table before indexes, against a 374 MB `index.db`.

## 7. Staleness

The browser shows the inventory as of the last `vdocs index`, not live state. Because the inventory
becomes an index input, the orchestrator's input fingerprint already re-runs index — and merge,
relate, manifest and doctor after it — whenever the inventory changes; a stale table can only come
from a partial run that stops before index. `vdocs doctor` compares the stamped canonical hash with
the current `inventory.json` and reports **WARN** when they differ, naming the fix; the check is
proved by planting a mismatched hash. WARN, not RED: the gold library is sound either way, and the
one case the check catches is already visible as a pending stage in the next run (decision D3).

## 8. Order of work

0. **Commit the measurements — landed 2026-11-05.** The numbers in §1, §3 and §4 had come from
   ad-hoc scripts. `scripts/inventory_measurements.py` re-derived every one of them through the
   pipeline's own definitions and wrote
   [`reports/inventory-browser-measurements.md`](../../reports/inventory-browser-measurements.md)
   and its `.json`, which name what they read: the sha256 and record count of `inventory.json`,
   `index.db`'s schema version and corpus hash, and the vdocs and vista-meta commits. Ten figures
   moved and were corrected in place: the VistA share of the status total; the repeated links, their
   records and the number of form files among them; the namespace count, the name agreement and the
   namespaces the registries leave unnamed; the Library renames; the never-fetched count; and D6's
   Word versions. It also found that `classify()` could not pair a PDF with its DOCX twin when
   neither has an anchor key — fixed in `722d2c2`, which moved §1's 219 to 216 — and that
   `inventory --status` labels a PDF-only document *out_of_scope* whatever its fetch did, which is
   backlogged in `TODO.md`. The report was re-run at `722d2c2`. (The project's own lesson from the
   August audit: a measurement that cannot name what it read is not evidence.)
1. **vdocs, the producer.** Tests first: a pure function from (records, policy, profile maps) to rows
   whose disposition counts equal `completeness_report` on the same input, and whose profile tags
   equal the gold documents' for records in gold; the row key is unique over the 2026-11-05
   inventory fixture; the contract bump is checked by calling `lint_bump` with the committed 1.6
   spec as the previous version — `lint_latest`, the `make contract-lint` gate, compares the two
   highest *major* files and is a no-op while only `v1.json` exists, so on its own it cannot red on
   a 1.6 → 1.7 edit; the doctor staleness check warns on a planted mismatch. Then implement,
   `make check`, and re-run index on the shared lake only after confirming no operator run is live.
   Measured cost of the rebuild this adds after every crawl: index 48.7 s, merge 31.6 s, relate,
   manifest and doctor under 4 s together — about a minute and a half.
2. **Use the table.** With step 1 landed the operator has the whole §1 case through `sqlite3` on
   the new view. The go/no-go on the web mode (D5) is taken here, not before.
3. **Identity continuity across re-filing (D1).** Its own short proposal, which does not exist yet:
   keep the id a document already had when VA moves it to another application page. It must land
   before step 4. If the producer half lands first, the new view carries D1's stopgap (option C),
   and the stopgap's exception list carries a testable expiry: a test that reds once the listed ids
   resolve through the continuity mechanism.
4. **vdocs-web, the consumer.** Update the vendored contract copy; tests for the MINOR check, the
   facet counts, routes and the missing-view path; then the Svelte mode with its unit tests;
   `make check`.
5. **Docs last, in the past tense**: the read-contract changelog entry and both READMEs.

## 9. Deliberately not building

- **Full-text or headings search over records not in gold** — they have no body.
- **Showing a VDL original inside vdocs-web.** va.gov answers with `X-Frame-Options: SAMEORIGIN`
  (checked 2026-11-05), so another origin cannot frame it; showing it would mean downloading and, for
  Word, converting each file at view time. The file icon opens the original in a new tab instead.
- **Fetch status in `index.db`** — it lives in `state.db`, mutable state outside the read contract;
  `vdocs inventory --status` stays the place to see why a fetch failed.
- **Dating the never-fetched documents by partial download** — a separate proposal if ever; the
  measurements are kept under D6 so they are not lost.
- **A second reason grammar** generated from the policy registries (§5).
- **A `gold only` facet value** (§3).
- **Collapsing repeated listings** of one file into one row (D2).
- **Library namespace renames** — their own small change (D4).
- Any live read of `~/data/vdocs` from vdocs-web; editing rulings or registries from the browser;
  charts beyond the one disposition bar; a separate inventory service or binary.

## 10. Decisions

Each decision names the options, their cost, and a recommendation. All six open decisions were
taken on 2026-11-05, each as recommended; the options stay as the record of why. D7 was closed by
measurement.

### D1 — The join across a VA re-filing

**The problem.** `doc_id` is app code plus slug, so when VA moves a document to another
application page the inventory's id changes and gold's does not. Today that is 14 documents; every
future re-file adds to it, and the browser would show each one twice, as *gold only* and as *held
but not in gold*.

| Option | For | Against |
|---|---|---|
| **A. Prerequisite: land "identity continuity across re-filing" first** (keep the id a document already had when VA moves it; the small survivor of the August audit, precedent `anchor-aliases.yaml`) | Fixes the cause once, for every consumer; the browser then needs nothing special | Blocks this proposal on a change that still needs its own short proposal |
| **B. An alias table in the inventory rows** (old id → current id, built from slug matches across app codes) | Unblocks the browser | A second identity mechanism beside the anchor aliases; cross-app slug shadowing is a known risk, so a slug match alone can be wrong |
| **C. Label it** (the two summary views carry a note; the 14 are listed in a fixed exception file) | Smallest; honest | The list rots with every crawl; the facet counts stay wrong |

**Decided 2026-11-05: A**, as recommended, with C as the stopgap only if the producer half of this
proposal lands first and the continuity change is not yet written; the stopgap's exception list
then carries a testable expiry (§8 step 3). B is not worth a second mechanism.

### D2 — Repeated listings of the same file

**The problem.** 1,332 of 9,080 rows are the same 9 links repeated on 148 application pages
each: 8 benefits forms and a VA strategic plan. They are honest records of what the VDL lists, and
they dominate the *not-vista* bucket.

| Option | For | Against |
|---|---|---|
| **A. Keep every row** | A record is a listing; the counts match `vdocs completeness` exactly | The not-vista facet reads as 1,184 forms when it is 8 files |
| **B. Collapse repeated URLs to one row with a listing count** | Cleaner table | A row is no longer a listing; the counts stop matching the CLI, and the facet-count invariant in step 1 needs a second definition |

**Decided 2026-11-05: A**, as recommended. The record panel shows a *listed on N pages* count
instead (§2).

### D3 — Stale inventory: WARN, RED, or no doctor check

| Option | For | Against |
|---|---|---|
| **A. WARN** | Visible in the one verdict the operator reads; never blocks a sound gold library | A warning can be ignored |
| **B. RED** | Cannot be ignored | Turns GOLD LIBRARY RED for a condition that is not about the gold library, after any partial run |
| **C. No check** | The stage fingerprint already re-runs index; nothing to build | Standalone `vdocs doctor` would not mention it |

**Decided 2026-11-05: A**, as recommended (written into §7).

### D4 — Namespace names in the Library

**The problem.** The inventory needs namespace names (161 namespaces, 64 of them with no
same-code application name in the registries today). Applying the same source to the Library
changes 46 shipped names — by a reading of the list, 7 in substance and 39 in wording — and the
source is a one-time copy of vista-meta's PACKAGE-file export.

| Option | For | Against |
|---|---|---|
| **A. Ship the names in this bump, both modes** | One vocabulary, one registry, no second step | A change to a shipped surface rides inside an inventory proposal; nobody has seen the 7 |
| **B. Inventory only now; Library in its own small change** | The 7 are reviewed on their own; this proposal stays about the inventory | Two modes with two namespace labels for a while |

**Decided 2026-11-05: B**, as recommended. The registry file's header records the vista-meta release and
commit it was copied from (the Track D precedent is mutual pinning, not a bare copy), so the copy
can be re-derived and its drift measured.

### D5 — Build the web mode now, or after using the table

| Option | For | Against |
|---|---|---|
| **A. Producer and consumer in one workstream** | The mockup exists; momentum | The consumer is the larger half (Go routes, Svelte mode, tests) and its value is unmeasured |
| **B. Producer first; use the view from `sqlite3`; decide the web mode after** | Everything §1 asks for is answered by step 1 alone; the web half is a separate go/no-go | The mockup waits |

**Decided 2026-11-05: B**, as recommended (written into §8). The question to answer at step 2,
before step 4: in a month of use, how often was the table opened, and for what.

### D6 — Dating the never-fetched documents

**The problem.** 1,911 VistA documents (distinct `doc_id`s) have no date: 1,861 with no gold
document, nearly all never fetched, and the 50 gold documents whose text carries none. Dating them
all would cover about 64 % of the inventory instead of 22 %.

*Measured:* va.gov ignores HTTP range requests (a 1 KB range returns the whole file), so nothing
can be fetched by page. A Word file can still be cut short by closing the connection: its text is
one ZIP entry ahead of the images, ending at a median 29 % of the file — 219 MB instead of
1,863 MB across the 1,035 Word files vdocs holds. 1,882 of the 1,911 documents have a Word version,
so the projected download is about 400 MB instead of about 3.4 GB (projected when the count read
1,903). Word's own created/last-saved
metadata sits at the end of the file and records saving, not content change, so it is not worth
the full download.

| Option | For | Against |
|---|---|---|
| **A. Not in this proposal** | The Undated bucket is honest; nothing new to maintain | 78 % of rows stay undated |
| **B. A separate proposal for a partial fetch** | Three times the dated coverage | Changes the rule that omitted doc types are never fetched; a truncated ZIP has to be rebuilt before Pandoc can read it; invents a state "dated but not held" that the completeness vocabulary does not have |

**Decided 2026-11-05: A**, as recommended; B only ever as its own proposal with its own
measurements.

### D7 — Closed by measurement: rebuild cost

The first draft asked whether making the inventory an index input would make inventory-only
changes slow. Measured on 2026-11-05: index 48.7 s, merge 31.6 s, relate 1.5 s, manifest 1.6 s,
doctor 0.5 s. A crawl-triggered rebuild costs about a minute and a half. Closed; the rows stay in
the index stage.

## 11. Fixes this proposal's measurements triggered (all landed 2026-11-05)

- `9c90213`, `5fbc388` — Surgery (SR) carried MailMan's name in `package-master.yaml`,
  `app-profiles.yaml` and `product-names.yaml`.
- `526c6d0` — nine `doctype-policy.yaml` reasons were cut at an unquoted comma.
- `9f9df51` — the three document-date bugs in §4.
- `a5b4363` — `index` did not re-run when the registries it reads change.
- `722d2c2` — `classify()` held three PDFs as the only format beside a DOCX with the same `doc_id`,
  because neither row has an anchor key (found by step 0).

## 12. References

- `scripts/inventory_measurements.py` and
  [`reports/inventory-browser-measurements.md`](../../reports/inventory-browser-measurements.md)
  (+ `.json`) — every figure in §1, §3 and §4, what it read, and the value printed before step 0.
- [ADR-0001 — Read contract and drift prevention](../adr/0001-read-contract-and-drift-prevention.md);
  [read-contract changelog](../../contracts/read/CHANGELOG.md) (1.6 is the current version);
  `src/vdocs/kernel/read_contract.py` (`lint_bump`, `lint_latest`).
- [VO identity and classification audit, 2026-08-05](vdocs-quality-vdl-observatory/vo-identity-and-classification-audit.md)
  — the app code in every key; "identity continuity across re-filing" as the surviving fix;
  [its tracker](vdocs-quality-vdl-observatory/vdocs-quality-vdl-observatory-tracker.md).
- `src/vdocs/stages/serve_inventory/completeness_pure.py` — `classify()`, `completeness_report()`,
  the closed reason vocabulary; `src/vdocs/stages/fetch/fetch_pure.py` — `GatePolicy`,
  `sole_survivors()`.
- `src/vdocs/kernel/personas.py` — `profile_tags()`; `src/vdocs/kernel/ids.py` — `doc_id()`.
- `src/vdocs/stages/consolidate/consolidate_pure.py` — `official_date()`; the per-anchor
  `history.yaml` under `documents/gold/consolidated/`.
- `src/vdocs/stages/index/stage.py` — inputs, `_latest_bundle_paths()` (the history walk),
  the atomic build; `src/vdocs/contracts/registry.py` — `GOLD_INVENTORY`.
- `src/vdocs/stages/crawl/snapshot_pure.py` — `canonical_hash()`.
- vdocs-web: `internal/index/contract.go` (`CheckSchemaVersion`, MAJOR-only),
  `internal/index/index.go` (`Open()`, namespace naming), `web/src/routes/+page.svelte`
  (`TYPE_FAMILIES`).
- `TODO.md` — the admitted-but-not-held verdict gap; the unnormalized revision dates.
- Memory: `docs/memory/pxrm-refresh-2026-11-05.md` (version-ordering defect);
  `docs/memory/search-quality-programme.md` (the observatory findings behind §1).
- Lake run log `~/data/vdocs/reports/run-index-registries-2026-11-05.log` — the stage timings in
  D7.
- Mockup: <https://claude.ai/artifact/UP9W8LRkwXcyHVwhgTBVn5> (private).
