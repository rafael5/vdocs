# vdocs-quality-vdl-observatory — implementation plan

Proposal: [`vdocs-quality-vdl-observatory.md`](vdocs-quality-vdl-observatory.md) ·
Tracker: [`vdocs-quality-vdl-observatory-tracker.md`](vdocs-quality-vdl-observatory-tracker.md) ·
Prompts: [`prompts/`](prompts/)

**Revised 2026-08-05 to match the adversarially-reviewed proposal.** The old "runs after
crawl-integrity (shared snapshot mechanism)" premise is void — no snapshot mechanism was built
there; VO.2 is greenfield. Commit subjects `VO.0:` … `VO.5:`. House rules: TDD, `make check` green
before commit, tick the tracker in the same commit. **Each step stops at its DoD** (proposal
Table 1) — new questions get written down, not pursued.

## VO.0 — Bank the current inventory (first; no design, no code)

Copy `inventory/bronze/catalog.raw.{json,csv}` and `inventory/gold/inventory.{json,csv}` to
`$DATA_DIR/inventory/snapshots/2026-06-10/` (named for the source crawl per `stage_runs`), plus a
one-paragraph `SNAPSHOT.md` naming that crawl. Verify each copy's sha256 equals its original.

**Done when:** checksums match and the directory exists — before any `vdocs fetch --all` or crawl.

## VO.1 — (optional, demoted) fill-rate report

Only if VO.3's report turns out to need it. CI.0 already measured the essentials.

## VO.2 — Snapshot on every successful crawl (bronze only)

In `crawl.run()`, after the floor check passes and bronze is written, also write
`snapshots/<crawl-date>/catalog.raw.json` — unless the canonical content hash (sha256 over sorted
`(section, app_url, doc_url, status, …)` rows, a pure function) equals the newest existing
snapshot's. Snapshots are never rewritten.

*Tests first:* (a) two differing crawls → two snapshots; (b) the earlier snapshot byte-identical
after the later crawl; (c) identical canonical content (including a page-reorder variant) → no new
snapshot.

## VO.3 — Delta between two snapshots, keyed on VDL numeric ids

Pure function: two `Catalog`s → per-section counts by `app_status` + doc-count deltas, keyed on
`appid`/`secid` parsed from the URLs the crawl already stores — never on names or `app_code`. A CLI
entry (`vdocs vdl-delta <a> <b>` or equivalent) prints the report.

*Tests first:* renamed app with unchanged `appid` reports as a rename, not departure+arrival; an
unchanged section reports **0**, not absent.

## VO.4a — Mass-transition tripwire (with VO.3, same report)

`app_status` is a regex over a display suffix (`crawl_pure.py:24`). If >5% of apps change status in
one delta, the report emits `SUSPECT-PARSER` and suppresses transition rows.

*Tests first:* cosmetic suffix change across all apps → one flag, zero transitions; one genuine
transition → one row, no flag.

*(VO.4b, optional, after VO.4a: per-transition rows — status change, decommission date arriving,
`cots_dependent` set — as report rows only; no new channel.)*

## VO.5 — Close the archive question

Append to [`vo5-archive-meaning-findings.md`](vo5-archive-meaning-findings.md): composition stands
as measured (2026-08-04); VA's **intent is unestablished and stays so** — a timeline starting 2026
cannot explain labels applied 2005–2022. Tick the tracker ✅. No further intent work.

## Sequencing

VO.0 immediately → VO.2 → VO.3 + VO.4a. VO.5 is a paragraph, any time. VO.1/VO.4b/VO.3b only after
Table 1 is fully ✅, and only on demand.

## Out of scope

Everything in proposal Table 3: gold-layer timelines, name-keyed identity, event channels,
backfill, intent inference, storage engineering. Fetch/admission changes remain
`crawl-integrity`'s (the VO.6–VO.9 completeness workstream was a recorded, operator-signed
exception).
