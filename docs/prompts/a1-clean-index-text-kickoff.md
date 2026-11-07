# Kickoff — A1: index a clean projection of each section

> **To start the session**, `cd ~/projects/vdocs` and say:
>
> > Read `docs/prompts/a1-clean-index-text-kickoff.md` and execute it.

**Repo: `vdocs`** (`~/projects/vdocs`). Read `CLAUDE.md`, then
[`docs/proposals/end-to-end-search-architecture-review.md`](../proposals/end-to-end-search-architecture-review.md)
§3.1 (the finding), §6 A1 (the change), §7 (risks), §8 (verification) and §9 D1 (decided:
clean projection in the index, `body.md` unchanged). Then read `src/vdocs/stages/index/index_pure.py`
(`shred_sections`, `split_oversized`, `table_chunk_text`), `src/vdocs/stages/index/stage.py` (the
FTS fill), `src/vdocs/kernel/markdown.py` (`ARTIFACT_RE`, `substantive_tokens`, the one place the
chrome patterns already live) and `src/vdocs/server/search.py` (`snippet()` over the `body`
column).

Effort: `xhigh`. This is a text-transformation design with a property test, not a mechanical step.

**Binding facts, measured 2026-11-07:**

- vdocs-web rebuilds a document's preview and section text from the markdown in `v_chunks.text`
  (`~/projects/vdocs-web/internal/index/index.go`, `Preview` and `SectionText`), and vdocs-cli
  reads `chunks.text` for `get section`. **`chunks.text` stays markdown.** The clean projection
  goes into the FTS `body` column only (and the FTS `title` column, see step 4).
- The corpus writes keystrokes as `<Enter>`, `<RET>`, `<Tab>`: 1,633 `<Enter>` in a 6,000-chunk
  sample. A tag strip must whitelist HTML element names.
- HTML tables (`<table>`, `<tr>`, `<td>`, `<th>`, `<col>`) are real content in 36% of chunks. Their
  cell text must survive; only the tags go.

## Rules for the session

- TDD: test first, red, implement, green, `make check` before every commit.
- No stubs, no dangling artefacts: nothing is documented before it exists, and a half-built
  increment is reverted, not committed.
- The shared lake: before any rebuild run `pgrep -af "vdocs run"` and look at
  `~/data/vdocs/reports/*.log`; if an operator run is live, wait. Copy `~/data/vdocs/index.db` to
  the session scratchpad before the first rebuild so the previous index can be restored if A1 is
  not adopted. A running vdocs-web keeps the old file open until restarted; restarting it is the
  operator's call, say so rather than doing it.
- Every measurement file carries `index_db`, `documents`, `chunks` and `corpus_content_hash`
  (`reports/README.md`). A number without provenance is not evidence.
- Rebuild chain: `vdocs run --from index --to manifest --force`, then `vdocs doctor`. About 45 s
  for `index`.

## Before building: confirm the plan

Run these against `~/data/vdocs/index.db` (a scratch copy for the vocabulary table) and record the
results in `reports/a1-before.md`. Expected values are from the review; a material difference
means the plan is wrong, so stop and amend the proposal before writing code.

1. **Markup share.** Over 8,000 random `chunks_fts.body` rows, count `[^\W_]+` tokens before and
   after removing, in order: `\[↑ Back to Contents\]\(#contents\)`, `<[^>]+>`,
   `!\[[^\]]*\]\([^)]*\)`, `\]\(#?[^)]*\)`, `^#+\s+`, `` [*_`]{1,3} ``. Expected: about 10%
   removed. Per class (same patterns one at a time): HTML tags about 7% (`<img>` about 2.3%),
   link targets about 1.6%, the nav line about 1.3%.
2. **Chrome prevalence.** `SELECT sum(text LIKE '%Back to Contents%')*100.0/count(*) FROM chunks`:
   expected 80.6. Share of chunks containing `<`+letter: expected about 36%.
3. **Vocabulary.** On the scratch copy: `CREATE VIRTUAL TABLE v USING fts5vocab('chunks_fts',
   'row')`; total terms expected 138,350; terms matching `[0-9a-f]{40,64}` expected 11,486; the
   top-10 by document frequency should include `back` and `contents`.
4. **Keystroke notation.** Count distinct `<[A-Za-z]+>` tokens that are *not* HTML element names
   across a 6,000-chunk sample, and list them (`<Enter>`, `<RET>`, `<Tab>`, …). This list is the
   whitelist's negative test.
5. **Link-polluted titles.** `SELECT count(*) FROM doc_sections WHERE is_latest=1 AND title LIKE
   '%](#%'` and the distinct documents involved. Expected about 320 titles in about 10 documents.
6. **Snippet chrome.** Run the golden keyword forms through `server.search.keyword_search` at
   k=15 and count snippets containing `Back to Contents` or `<`: expected about 15%.
7. **Baselines.** `.venv/bin/python scripts/baseline_golden.py --out reports/a1-before.md`
   (the harness writes the JSON beside it; expected nDCG@10 0.425 over 30 queries, 0.524 over the
   24 originals). Then the identifier probes through the production engine the way
   `scripts/mcp_review/synonyms.py` does (the probe lists are in `scripts/mcp_review/_common.py`;
   the other `mcp_review` scripts use a prototype reader and are not the instrument): patch ids
   in the top 5 expected 216 of 256, `file #N` 25 of 30. Record both in the before report.

If step 1 shows markup well under 5%, or step 4 finds keystroke notation the whitelist cannot
distinguish from tags, write that into the proposal and stop.

## Work plan

1. **A pure projection function in `index_pure.py`.** Input: a section's markdown text. Output:
   index text. Rules, each with its own test case first:
   - drop the nav line `[↑ Back to Contents](#contents)` and the table marker
     `_[… (extracted to CSV)](tables/…)_` entirely;
   - an HTML element from a whitelist (`p`, `span`, `u`, `strong`, `em`, `b`, `i`, `br`,
     `blockquote`, `li`, `ul`, `ol`, `table`, `thead`, `tbody`, `tr`, `td`, `th`, `col`,
     `colgroup`, `div`, `a`, `sup`, `sub`, `code`, `pre`) loses its tags and keeps its inner text;
     `<img …>` keeps its `alt` text and nothing else; any other `<…>` is left as written (that
     is the keystroke notation);
   - a markdown link or image keeps its label or alt text and loses its target;
   - heading marks `#`, emphasis marks and inline code marks go; fenced code keeps its content
     and loses the fence lines;
   - whitespace is collapsed.
2. **Property tests (Hypothesis)**, in `tests/property/`: every `[^\W_]+` token of the input that
   is not inside a dropped construct survives in the output; the output contains no `<` followed
   by a whitelisted element name, no `](`, no `↑`, no token matching `[0-9a-f]{40,64}`; a
   keystroke token from the step-4 list survives unchanged; the text of an HTML table cell
   survives.
3. **Wire it into the FTS fill** in `stage.py`: the `body` column of `chunks_fts` receives the
   projection of the chunk text (prose chunks and table chunks alike; a table chunk is already
   plain). `chunks.text` is unchanged. Bump `IndexStage.contract_ver` (18 → 19) with a comment
   saying why; `read_schema_version` does not change (no view or column changes).
4. **Titles.** Apply the link-label rule to the section title before it is written to
   `doc_sections.title` and the FTS `title` column, so the 320 titles become their label text. The
   column's meaning (the heading text) is unchanged, so the read contract is unchanged; note it in
   `contracts/read/CHANGELOG.md` as a data correction under 1.8, not a version.
5. **`make check`** green. Rebuild the derived stores and run `vdocs doctor`.

## After building: confirm success

Record in `reports/a1-after.md` with provenance, and the paired comparison in
`reports/a1-paired.md`:

1. Markup share (step 1 above) under 0.5% of body tokens; the residue listed and all of it
   keystroke notation. Nav-line prevalence in `chunks_fts.body`: 0. Hex-hash vocabulary terms: 0.
   `back` and `contents` out of the top 100 terms by document frequency. Total vocabulary down by
   roughly 8%.
2. Link-polluted titles: 0.
3. Snippet chrome: 0%.
4. **Ranking, paired per question** against `reports/a1-before.json`: the 30 keyword questions
   with nDCG@10, MRR and recall@10 per query, wins and losses counted, and a bootstrap interval on
   the mean (4,000 resamples, as `scripts/mcp_review/surfaces.py` does). **Adoption rule:** no
   question loses its judged answer from the top 10. If one does, read the two result lists, say
   why, and either fix the projection or revert the rebuild from the scratchpad copy and record
   the result in the proposal. Patch ids and `file #N` in the top 5: not below 216 and 25.
5. `vdocs doctor` GREEN. `make check` green in `~/projects/vdocs-web` and `~/projects/vdocs-cli`
   (their fixtures build their own tables; the point is that nothing in the contract moved).
6. index.db size before and after (expect the FTS content and index to shrink by about a tenth).

## Out of scope

Changing `body.md` or `chunks.text`; the preamble (A2); section collapse and the read tool (A3);
indexes and `ANALYZE` (A4); any ranking weight or tokenizer change; stemming; a trigram index.

## Close-out

- Update the proposal's status line and §6 A1 with "built `<commit>`, measured" and the before
  and after numbers; update the one line in `docs/README.md`.
- Move this prompt to `docs/prompts/historical/` in the commit that lands the work.
- Commit and push (`Co-Authored-By: Claude …`). Update the project memory note
  `end-to-end-search-review.md` with the outcome.
- If the adoption rule failed and the rebuild was reverted, say so in the proposal and in the
  final message, with the per-query evidence.
