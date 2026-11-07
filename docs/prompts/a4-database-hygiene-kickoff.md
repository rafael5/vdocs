# Kickoff — A4: database hygiene for index.db

> **To start the session**, `cd ~/projects/vdocs` and say:
>
> > Read `docs/prompts/a4-database-hygiene-kickoff.md` and execute it.

**Repo: `vdocs`** (`~/projects/vdocs`). Read `CLAUDE.md`, then
[`docs/proposals/end-to-end-search-architecture-review.md`](../proposals/end-to-end-search-architecture-review.md)
§4.1 (including the same-day correction on external content), §6 A4, §7 and §8. Then
`src/vdocs/stages/index/stage.py` (`_SCHEMA`, the `build` closure), `src/vdocs/kernel/db.py`
(`build_atomic`, `replace_table_atomic`), `src/vdocs/stages/merge/stage.py` (the tables `merge`
replaces after `index`), `src/vdocs/server/doctor.py` and `contracts/read/v1.json` with its
`CHANGELOG.md`.

Effort: `medium`. Mechanical, with one decision taken by measurement.

**Binding facts, measured 2026-11-07:**

- `dbstat`: `chunks_fts_content` 126 MB, `chunks` 117 MB, `chunks_fts_data` 46 MB,
  `doc_sections` 16 MB, `relations` with its primary-key index 25 MB; file 363 MB.
- `sqlite_stat1` does not exist (no `ANALYZE` has ever run). `chunks_fts_idx` has 11 segments.
- `EXPLAIN QUERY PLAN`: `SELECT 1 FROM chunks WHERE section_id=?` is `SCAN chunks`;
  `SELECT * FROM doc_sections WHERE doc_key=? ORDER BY seq` is `SCAN doc_sections` plus a temp
  B-tree. The MCP review measured the section probe at 20 ms p50.
- `v_chunks.text` must stay markdown: vdocs-web rebuilds previews from it. So an external-content
  FTS table needs `chunks` to carry a clean `body` beside `text` (A1's projection), and the saving
  is the FTS content copy minus that column. The proposal's rule: build it only if it saves at
  least 40 MB.
- The ranking must not change at all. Indexes and statistics do not touch BM25; `optimize` merges
  segments without changing term statistics. Any ranking difference is a bug.

## Rules for the session

TDD; no stubs; check for a live operator run and back up `index.db` to the scratchpad before the
first rebuild; every report carries provenance; rebuild with `vdocs run --from index --to manifest
--force` then `vdocs doctor`.

## Before building: confirm the plan

Record in `reports/a4-before.md`.

1. **Sizes.** `SELECT name, SUM(pgsize)/1024/1024 FROM dbstat GROUP BY name ORDER BY 2 DESC` and
   the file size. Expected as above.
2. **Statistics and segments.** `SELECT count(*) FROM sqlite_stat1` (expected: no such table);
   `SELECT count(DISTINCT segid) FROM chunks_fts_idx` (expected 11).
3. **Plans and timings.** `EXPLAIN QUERY PLAN` and wall time for: the section probe; a document's
   outline (`doc_sections WHERE doc_key ORDER BY seq`); `entity_mentions WHERE doc_key=?`;
   `relations WHERE dst_type=? AND dst_id=?`; and the production search SQL from
   `server/search.py` (expected: FTS scan, PK lookup on `documents`, temp B-tree for the ORDER BY,
   1–3 ms). Record which use an index.
4. **Ranking fingerprint.** Run the 30 golden keyword forms and the identifier probes through
   `server.search.keyword_search` at k=45 (the over-fetch window) and save the ordered
   `chunk_id` lists with their scores to `reports/a4-ranking-before.json`. This is the equality
   check for after.
5. **The external-content decision, on a scratch copy.** Copy `index.db` to the scratchpad. Add
   to `chunks` the columns the FTS table would read (`title`, `doc_title`, `section_path`, and a
   `body` column holding the FTS `body` text as it is today, or A1's projection if A1 has landed),
   fill them from `chunks_fts`, create a new FTS5 table with `content='chunks'` over them, drop
   the old one, `VACUUM`, and measure the file size. Record the saving. **Rule:** at least 40 MB
   saved, or external content is not built and the kickoff continues with indexes, statistics
   and `optimize` only. Write the measured number and the decision into the proposal's §6 A4.
6. **Consumer fixtures.** Confirm that vdocs-web's and vdocs-cli's tests create their own
   `chunks_fts` tables (`grep -rn "CREATE VIRTUAL TABLE chunks_fts" ~/projects/vdocs-web
   ~/projects/vdocs-cli`) and read `chunks_fts` only through `MATCH`, `bm25()`, `snippet()` and
   column reads, never through `rowid` or `INSERT` against a real index. External content changes
   none of those.

## Work plan

1. **Indexes in `_SCHEMA`** (test first: a test that builds a fixture index and asserts each
   named index exists and that `EXPLAIN QUERY PLAN` for the four lookups contains no `SCAN` of
   the table): `chunks(section_id)`, `chunks(doc_key)`, `doc_sections(doc_key, seq)`,
   `entity_mentions(doc_key)`, `relations(dst_type, dst_id)`. `relations` is written by `relate`
   through `replace_table_atomic`, so its index belongs with that table's DDL in `relate`, not in
   `index`'s schema; check where the table is created and put the index there.
2. **End-of-build statistics and merge** in the `build` closure of `index` and after every
   `replace_table_atomic` that touches a large table: `INSERT INTO chunks_fts(chunks_fts)
   VALUES('optimize')`, then `ANALYZE`. Test: after the fixture build `sqlite_stat1` exists and
   `chunks_fts_idx` has one segment.
3. **`doctor` check** (pure, test first): FAIL when `sqlite_stat1` is missing or when any of the
   four lookups plans a table scan; red-prove by running it against the pre-A4 scratch copy.
4. **External content, only if step 5 said yes:** `chunks` gains the columns; `chunks_fts` is
   declared with `content='chunks'` and `content_rowid='rowid'`; the fill inserts into `chunks`
   and then rebuilds the FTS index with the `rebuild` command; `v_chunks` keeps its columns (the
   new ones are not added to the view unless a consumer needs them, which none does today, so the
   read contract is unchanged). Test: a fixture built both ways returns identical rows for the
   same `MATCH`.
5. Bump `IndexStage.contract_ver` (and `RelateStage`'s if its DDL changed). `make check`.
   Rebuild and `vdocs doctor`.

## After building: confirm success

Record in `reports/a4-after.md`.

1. Sizes per object and file size. Segments: 1. `sqlite_stat1` present with rows for `chunks`,
   `doc_sections`, `documents`, `entity_mentions`, `relations`.
2. Plans: the four lookups use their indexes; the section probe under 1 ms. The production search
   plan unchanged apart from statistics.
3. **Ranking byte-identical:** the k=45 `chunk_id` lists and scores for all 30 questions and the
   identifier probes equal `reports/a4-ranking-before.json`. Any difference is a defect to explain
   before the work lands.
4. `vdocs doctor` GREEN including the new check. `make check` green in vdocs, vdocs-web and
   vdocs-cli; the running vdocs-web, once restarted by the operator, serves a preview and a
   search from the rebuilt file.
5. If external content was built: the saving recorded; `snippet()` output for ten golden hits
   identical before and after.

## Out of scope

Changing what text is indexed (A1); chunking (A2); the server (A3, A5); dropping any table the
read contract exposes; `relations` pruning (the 166,139 `cooccurs` edges are read by `relate`'s
consumers at build time, not at query time, and are not this increment's business).

## Close-out

Update the proposal's status line and §6 A4 with the commit, the external-content decision and
the numbers; update the line in `docs/README.md`; move this prompt to `docs/prompts/historical/`
in the landing commit; commit and push; update the project memory note.
