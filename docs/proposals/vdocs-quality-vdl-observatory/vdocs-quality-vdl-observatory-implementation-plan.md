# vdocs-quality-vdl-observatory — implementation plan

Proposal: [`vdocs-quality-vdl-observatory.md`](vdocs-quality-vdl-observatory.md) ·
Tracker: [`vdocs-quality-vdl-observatory-tracker.md`](vdocs-quality-vdl-observatory-tracker.md) ·
Prompts: [`prompts/`](prompts/)

⛔ **Runs after `vdocs-quality-crawl-integrity`** (shared snapshot mechanism). Commit subjects
`VO.1:` … `VO.5:`. House rules: TDD, `make check` green before commit, tick the tracker in the same
commit.

## VO.1 — Measure what the inventory already tells us

Before building anything, establish what the current single snapshot already contains and what it
structurally cannot answer. Several signals are captured and unused: `app_status` (8,907 records),
`cots_dependent` (404), `decommission_date` (115, spanning 2005–2022), `out_of_scope_reason`.

Produce: the distributions, the fields' fill rates, and an explicit list of the questions that need
*more than one* snapshot to answer. That list is the specification for VO.3.

**No storage format is designed before this exists.**

## VO.2 — Keep every snapshot (do this early; it cannot be backdated)

Preserve each crawl's inventory as a dated, immutable record instead of overwriting it. Keep the
structured inventory, not another copy of the document payloads — the inventory is small and the
payloads are already content-addressed and write-once.

Design notes:
- **Immutable and dated.** A snapshot is evidence; it is never rewritten, and the crawl that
  produced it is identifiable.
- **Cheap enough to always do.** If keeping a snapshot is expensive or optional, it will be skipped
  exactly when the source is changing fastest.
- Reuse the existing inventory medallion rather than inventing a parallel store.

*Tests first:* two crawls produce two retained snapshots; the earlier one is byte-identical after the
later crawl; a re-run that finds nothing new does not fabricate a snapshot.

## VO.3 — The timeline view

Counts and composition per crawl — by library section, by document type, by `app_status` — so "how
fast is section X changing?" is a query. Driven by the question list from VO.1.

*Tests first:* fixture snapshots produce the expected deltas; a section that did not change reports
zero rather than being absent.

## VO.4 — Lifecycle transitions as events

Surface the changes worth knowing: an application moving `active → archive → decommissioned`, a
decommission date appearing, a `cots_dependent` flag being set. An event someone can be told about
is more useful than a table someone must remember to query.

Where the pipeline already has an alerting surface, use it rather than adding a second one.

*Tests first:* a status transition between two fixture snapshots emits exactly one event with both
states named; an unchanged application emits none.

## VO.5 — Answer the archived-share question

**38.2% of the library (3,404 of 8,907 records) is marked `archive`, and nobody has established what
VA means by it.** Determine it: sample archived records, compare the label against what the documents
themselves say, and check whether the corresponding VistA code is still present (the `vista-meta`
measured model can answer that side).

The outcome is a written finding: what `archive` means operationally, and therefore how much of the
corpus should be treated as historical rather than current. **If it cannot be established, say so
explicitly and record what was tried** — an honest unknown is a result; a guess presented as a
finding is not.

## Sequencing

VO.1 → VO.2 (early, time-sensitive) → VO.3 → VO.4, with VO.5 runnable in parallel once VO.1 is done.

## Out of scope

Changing what is fetched or admitted (that is `crawl-integrity`), inferring VA's intent behind a
label, and backfilling history that was never recorded.
