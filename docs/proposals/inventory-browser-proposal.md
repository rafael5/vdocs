# Inventory browser — the whole VDL catalog in vdocs-web

**Status: PROPOSED · 2026-11-05** — not built. Producer: vdocs · consumer: vdocs-web · read
contract 1.6 → 1.7 (additive). An interactive mockup over the real 2026-11-05 inventory lives in
a private Claude artifact (<https://claude.ai/artifact/UP9W8LRkwXcyHVwhgTBVn5>); this file is the
proposal of record. Every number below was measured on the 2026-11-05 lake.

An Inventory mode in vdocs-web for the whole VDL catalog: all 9,080 original records, searchable by
name, sortable and filterable by each document's own last-updated date, and filterable by the same
facets as the Library plus three of its own — whether a record reached gold, its disposition, and
the reason. The data travels inside `index.db`, so vdocs-web stays one portable binary.

## 1. Why

The inventory is only visible as two CLI totals. `vdocs inventory --status` counts 3,834 distinct
VistA documents by fetch status; `vdocs completeness` counts all 9,080 catalog records by
disposition. Neither lists records, neither filters, and neither connects a record to the gold
document it became. Joining the inventory to `index.db` on `doc_id` showed two things neither
command reports:

- **219 records counted as held have no gold document**: 152 archived sole survivors, 52 DOCX the
  policy keeps and 9 PDF-only documents were never fetched; 5 fetches failed and 1 was rejected as
  bad content (largest: SD 40, VBECS 27, CPRS 25, ROR 24, PSO 17). The completeness verdict still
  reads COMPLETE because it rules on what is admitted, not what is held (backlogged in `TODO.md`).
- **15 gold documents have a `doc_id` no current inventory record carries** — 14 archived ADT ISS
  release user guides and one PSS dosing-order-check manual.

## 2. What the mockup shows

vdocs-web's current layout and theme, with an Inventory mode beside Library:

- **Filter pane** (left): the Library's facet controls — collapse all, clear, per-facet count/A–Z
  sort, vocabulary tooltips — over the facets in §3.
- **Results table**: a file icon (PDF or DOC) linking to the record's original on the VDL, then
  title and `doc_id`, last-updated date, application, doc type, disposition and gold status. Columns
  sort by click; results open newest first.
- **Summary strip**: a disposition bar over the current selection, plus one-click views for
  *held but not in gold*, *in gold but not in the inventory*, and *unreachable + undecided*.
- **Record panel**: disposition with the reason's full explanation, gold status, the Library facet
  values, the record's fields, and the VDL link. *Open in library* hands a gold document to the
  Library reader.
- **Search**: the Name scope only (title, file name, `doc_id`, patch id), plus a month range on the
  last-updated date. Full-text and headings search need a document body, which only gold documents
  have.

## 3. Facets

| Facet | Group | Where the value comes from |
|---|---|---|
| Year updated | Date | The document's own last update (§4), plus *Undated* |
| Domain | Library | Application → functional domain, through the same `profile_tags()` that tags gold documents |
| Audience | Library | Doc type → reader persona, or the application's operators |
| Type | Library | The Library's three families plus Other, each opening into its doc-type codes |
| App user | Library | Application → primary persona |
| Namespace | Library | The record's package namespace; full name from the VistA PACKAGE file (#9.4), else the same-code application. Code/Name toggle |
| In gold | Inventory | Current, earlier version, not in gold, or gold only — a join on `doc_id` |
| Disposition | Inventory | The six completeness outcomes from `classify()` |
| Reason | Inventory | The reason `classify()` records; hovering shows its full explanation, worded from the registry that produces it |
| Application | More | Code and full name. Code/Name toggle |
| VDL section, Format, Lifecycle | More | The inventory record itself |

For the 2,120 record-to-gold matches, the computed Domain, Audience, App user and Type agree with
`index.db` every time; Namespace differs on 2 documents where the pipeline corrected it after the
inventory. About 2,300 records have no profile — 2,298 of them are not VistA — and show as
*(no profile)* so every facet's counts add up.

**Namespace names (decided 2026-11-05): PACKAGE file first, same-code application as fallback**, in
both Inventory and Library modes. The PACKAGE file names 102 of the 162 inventory namespaces (6,710
records); 56 more (1,717 records) are really application codes — mostly web and commercial products
such as WEBP and VBECS — and take the application's name, flagged as such; 3 (XUSC, PREC, PREN — 92
records) have no name anywhere; 561 records have no namespace. Where both sources name a namespace
they agree on 73 of 94. In the Library this names all 96 namespaces instead of 92, names DG, USR, BPS
and PSGW for the first time, changes 15 names in substance and rewords 32. Names come from
vista-meta's measured PACKAGE-file export, copied once into a committed vdocs registry, so vdocs gains
no runtime dependency on vista-meta.

## 4. Dates — the document's own last update, never its VDL posting

**The rule.** A record's date is the newest dated entry in its document's Revision History table;
when there is none, the title-page date. Both come from the document's own text, at month precision.
This is `official_date`, which `consolidate` already computes but the read contract does not publish
— `index.db` carries only the title-page date. The VDL posting date is never used: the crawl records
one for only 28 of 9,080 links, and it says when the file moved, not when the content changed.

**Why the title page is not enough.** For 332 gold documents the newest revision is later than the
title page — a median of 14 years later. The RPC Broker TCP/IP Supplement (`xwb1_1p44um`) has a
2005-01 title page and a 2022-08 newest revision.

**Coverage.** 990 of the 1,040 gold documents are dated (856 from Revision History, 134 from the
title page), which dates 2,018 inventory records through `doc_id`, PDF twins included. The other
7,062 are *Undated*: they sort last and drop out while a month range is set. Of those, 3,834 are
genuine VistA records (1,911 distinct documents) that were never fetched; 3,228 are not VistA.

**Fixed before this proposal (vdocs `9f9df51`, applied to the lake 2026-11-05):** a null revision
date no longer becomes the date `"None"` (67 documents had skipped their title-page fallback, and one
version group served VS GUI Technical Manual release 1.7.31.2 instead of 1.7.56.1); a revision dated
after the run month is ignored (GMRC `consum` records `3018-03`); and the measured revision-date
shapes (`07/24`, `12-22-2004`, `September 26, 2008`, …) now normalize — the newest date changed for 82
of 858 documents. The remaining gaps are backlogged in `TODO.md`.

## 5. Design

```
inventory/gold/inventory.json + registries ─▶ vdocs index ─▶ index.db ─▶ release bundle ─▶ vdocs-web
                                               (classify()  (one more    (ships it       (Inventory
                                                + profile_   view + vocab   whole)          mode)
                                                tags())      + meta hash)
```

**Producer — vdocs.**

- The index stage gains the gold inventory as an input (it has required the registries since
  `a5b4363`, so the gate policy and profiles are already covered). In the same atomic build that
  writes everything else it runs the existing `classify()` and `profile_tags()` over every record
  and writes one row per record.
- Each row carries `doc_id` (the existing join key to v_documents), application code and name, VDL
  section, doc type, title, file name, format, patch id, lifecycle label, system type, VDL URL, the
  four profile tags, the namespace, and the disposition with its reason.
- The read contract gains one projection view over that table and a capability that says it is
  populated — additive, so 1.6 → 1.7 and every 1.x consumer keeps working.
- v_documents gains the corrected last-updated date and its source (Revision History or title page),
  in the same bump. Inventory records get it through the `doc_id` join; the Library can use it too.
- Three vocabularies go into the existing vocab table: the six disposition definitions, the
  explanation of every reason (generated from `doctype-policy.yaml`, `scope-policy.yaml`,
  `system-types.yaml` and `noise-domains.yaml`), and namespace full names.
- `meta` gains the inventory's record count and content hash, stamped like the corpus hash.

**Gold status is not stored.** vdocs-web derives it by joining `doc_id` to v_documents, and finds
gold-only documents with the reverse join; storing it would copy a fact the contract already
publishes.

**Consumer — vdocs-web.**

- Reads the new view, v_documents and v_vocab: no new files, no new download, no access to
  `~/data/vdocs`.
- New read-only API routes for inventory facets, rows and a single record, with the Library's facet
  rules (OR within a facet, AND across, each facet counted with its own selection relaxed) and its
  own fixed facet list. Go tests against a fixture `index.db`.
- Inventory mode beside Library; the facet pane is reused and the reading pane becomes the results
  table and record panel. The Library's namespace names switch to the same vocabulary.
- An `index.db` without the capability (contract 1.6 or older) gets an explicit message naming the
  cause and the fix (re-run `vdocs index`), never an empty list.

## 6. Portability — vdocs-web stays self-contained

The binary does not change in kind: static, CGO-free, front-end embedded, built for Linux, macOS and
Windows by `make dist`. The data travels inside `index.db`, which the release bundle already ships
whole and vdocs-web already auto-downloads. Measured cost: the 9,080 rows with their facet columns
take 3.1 MB as a scratch SQLite table before indexes, against a 374 MB `index.db`.

## 7. Staleness

The browser shows the inventory as of the last `vdocs index`, not live state. `vdocs doctor` compares
the stamped inventory hash with the current `inventory.json` and goes RED when they differ, naming
the fix; the check is proved by planting a mismatched hash.

## 8. Order of work

1. **vdocs, the producer.** Tests first: a pure function from (records, policy, profile maps) to rows
   whose disposition counts equal `completeness_report` on the same input, and whose profile tags
   equal the gold documents' for records in gold; the contract bump passes the existing bump lint;
   the doctor staleness check reds on a planted mismatch. Then implement, `make check`, and re-run
   index on the shared lake only after confirming no operator run is live.
2. **vdocs-web, the consumer.** Update the embedded contract copy; tests for the facet counts, routes
   and the missing-capability path; then the Svelte mode with its unit tests; `make check`.
3. **Docs last, in the past tense**: the read-contract changelog entry and both READMEs.

## 9. Deliberately not building

- **Full-text or headings search over records not in gold** — they have no body.
- **Showing a VDL original inside vdocs-web.** va.gov answers with `X-Frame-Options: SAMEORIGIN`
  (checked 2026-11-05), so another origin cannot frame it; showing it would mean downloading and, for
  Word, converting each file at view time. The file icon opens the original in a new tab instead.
- **Fetch status in `index.db`** — it lives in `state.db`, mutable state outside the read contract;
  `vdocs inventory --status` stays the place to see why a fetch failed.
- Any live read of `~/data/vdocs` from vdocs-web; editing rulings or registries from the browser;
  charts beyond the one disposition bar; a separate inventory service or binary.

## 10. Open questions

1. **Should the never-fetched VistA documents be dated?** Reading the title page and Revision
   History of the 1,911 never-fetched documents once — without admitting them to gold — would date
   3,834 more records, about 64% of the inventory in total, and change the rule that omitted doc
   types are never fetched. *Measured:* va.gov ignores HTTP range requests (a 1 KB range returns the
   whole file), so nothing can be fetched by page. A Word file can still be cut short: its text is one
   ZIP entry ahead of the images, ending at a median 29% of the file — 219 MB instead of 1,863 MB
   across the 1,035 Word files vdocs holds. 1,903 of the 1,911 documents have a Word version, so the
   projected download is about 400 MB instead of about 3.4 GB. Word's own created/last-saved metadata
   sits at the end of the file and records saving, not content change, so it is not worth the full
   download.
2. **RED or WARN for a stale inventory** — a partial pipeline run leaves the inventory ahead of the
   index until index runs again.
3. **Index rebuild cost.** Making the inventory an index input means an inventory-only change
   rebuilds `index.db`. If that proves slow, the rows can move to a small stage after index, the way
   `merge` already writes the knowledge layer into `index.db`.
4. **Type families.** The Library shows only three families plus Other. In the inventory, Other holds
   the release notes, install guides and other doc types the policy omits, so the mockup lets each
   family open into its codes. Should the Library do the same?

## Fixes this proposal's measurements triggered (all landed 2026-11-05)

- `9c90213`, `5fbc388` — Surgery (SR) carried MailMan's name in `package-master.yaml`,
  `app-profiles.yaml` and `product-names.yaml`.
- `526c6d0` — nine `doctype-policy.yaml` reasons were cut at an unquoted comma.
- `9f9df51` — the three document-date bugs in §4.
- `a5b4363` — `index` did not re-run when the registries it reads change.
