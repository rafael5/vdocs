# Kickoff — A2: index the preamble and gate body coverage

> **To start the session**, `cd ~/projects/vdocs` and say:
>
> > Read `docs/prompts/a2-preamble-and-coverage-gate-kickoff.md` and execute it.

**Repo: `vdocs`** (`~/projects/vdocs`). Read `CLAUDE.md`, then
[`docs/proposals/end-to-end-search-architecture-review.md`](../proposals/end-to-end-search-architecture-review.md)
§3.2 (the finding and its cause), §6 A2, §7, §8 and §9 D2 (decided: floor 95% with a printed
exception list, tightened to 99% once the three known causes are fixed). Then read
`src/vdocs/stages/index/index_pure.py` (`shred_sections`: the first section starts at the first
retained heading; the whole-body fallback when no heading survives), `src/vdocs/kernel/markdown.py`
(`iter_headings` skips `## Contents`; `HEADING_RE` accepts `# ` with empty text),
`src/vdocs/stages/normalize/normalize_pure.py` (`recover_headings`, `infer_heading_levels`),
`src/vdocs/server/doctor.py` (`coverage_check`, `diagnose`, the policy loader) and
`registries/doctor-policy.yaml`.

Effort: `high`. Two small pure changes and one gate; the care goes into the gate failing closed.

**Binding facts, measured 2026-11-07:**

- Three documents checked by hand: `RMPR/rmpr_3_nppdum` has 78,223 body characters and 9,098
  indexed; its headings are `## Contents`, a `# ` line with the title "Using Surgical Implants"
  on the next line, and `# Appendix B`. `KMPS/kmps2_0um` (26,994 / 13,916) has `# ` before its
  `## Contents`. `PSO/pso_7_0_iep_um_4_pt2` (24,963 / 11,702) has only figure-caption headings.
- 29 latest documents have no heading at all and are already indexed whole by the fallback.
- `doctor` gates field coverage and anchors. Nothing compares a body with its chunks.
- The MCP review (`reports/mcp-review-coverage.json`) counted 78 latest documents below 95%
  word-token coverage and 222 below 99%, on the same corpus.

## Rules for the session

Same as A1: TDD; no stubs; check for a live operator run and back up `index.db` to the scratchpad
before the first rebuild; every report carries provenance; rebuild with `vdocs run --from index
--to manifest --force` then `vdocs doctor`. If A1 has landed, this session builds on it; if not,
it does not wait for it.

## Before building: confirm the plan

Record in `reports/a2-before.md`.

1. **Coverage per latest document.** For each row of `documents WHERE is_latest=1`, read
   `documents/gold/consolidated/<bundle_path>/body.md`, drop the frontmatter, count `\w+` tokens,
   and compare with the distinct tokens' count across the document's non-table chunks (exclude
   `chunk_id LIKE '%#table%'`; overlapping `#pN` windows repeat one block, so count tokens of the
   section texts, not the chunk texts, or de-duplicate the overlap). Report the distribution and
   the list below 95%. Expected: about 78 documents below 95%, with the three above among the
   worst. If the count is far from 78, find out why before going on: the two measurements must
   agree on what a token is.
2. **The cause, per document.** For every document below 95%, classify: (a) empty-title heading
   `^#+\s*$` present in the normalized body; (b) first retained heading after more than 5% of the
   body; (c) something else. Expected: (a) and (b) explain most; list every (c) with its first 200
   characters. If (c) dominates, the preamble fix is not the fix; stop and amend the proposal.
3. **Empty-title headings corpus-wide.** `grep -c` of `^#+\s*$` over
   `~/data/vdocs/documents/silver/text/03-normalized/*/*/body.md`, with the document list.
4. **Harness baseline.** `.venv/bin/python scripts/baseline_golden.py --out reports/a2-before.md`
   (or reuse A1's after-report if nothing has changed since; say which).

## Work plan

1. **Repair the empty-title heading in `normalize`** (pure function, test first): a heading line
   whose text is empty takes the next non-blank line as its text when that line is not itself a
   heading, a fence, a list item or a table row; otherwise the bare `# ` line is removed. Red
   case: the `rmpr_3_nppdum` shape. Bump `NormalizeStage.contract_ver` (3 → 4). This changes
   `body.md` for the affected documents, so `consolidate` and everything after re-run for them.
2. **A preamble section in `shred_sections`** (test first): when at least one heading is retained
   and the lines before the first retained heading carry a substantive token
   (`substantive_tokens`), emit a `Section` with slug `preamble`, title from `doc_title`, level 1,
   `section_path` empty, classified and `searchable` like any leaf, as the first section (`seq`
   0). The generated `## Contents` block is not substance: confirm `substantive_tokens` already
   ignores its link lines (`ARTIFACT_RE`), and add the test. Section ids are additive, so the
   read contract is unchanged; bump `IndexStage.contract_ver`.
3. **The coverage gate in `doctor`.** A pure check takes `(doc_key, body_tokens, indexed_tokens)`
   rows and the policy, returns FAIL for any latest document below the floor that is not in the
   exception list, and prints the exception list on every run (even when empty). Policy in
   `registries/doctor-policy.yaml`: a new block with the floor (95) and a list of
   `doc_key: reason` exceptions; the loader rejects an exception naming a document that is not in
   `documents` (fail closed: a vanished document must not keep an exception alive). The body token
   count comes from the gold body on disk; the indexed count from `doc_sections`/`chunks`. Red
   prove it: plant a document whose chunks are deleted on a scratch copy and watch it FAIL; plant
   an exception for a non-existent key and watch the loader refuse.
4. `make check` green. Rebuild: `vdocs run --from normalize --to manifest --force` this time,
   because step 1 changes normalized bodies. Then `vdocs doctor`.

## After building: confirm success

Record in `reports/a2-after.md` with provenance.

1. Coverage per latest document, same method as before: `RMPR/rmpr_3_nppdum`, `KMPS/kmps2_0um`
   and `PSO/pso_7_0_iep_um_4_pt2` at or above 95%; the count below 95% from about 78 down to the
   residue the gate names. Every remaining document below 95% is either in the exception list with
   a reason or is a FAIL the operator sees.
2. Empty-title headings in normalized bodies: 0.
3. `vdocs doctor` GREEN with the exception list printed. The planted-violation runs recorded.
4. Harness paired against the before report: no question loses its top-10 answer. A new
   `preamble` section may enter a result list; say where.
5. `make check` green in vdocs-web and vdocs-cli against the rebuilt index. Section counts moved
   (new `preamble` rows): confirm the web outline and the CLI `get section` handle a `preamble`
   slug.
6. Then decide, by reading the list, whether the floor can go to 99 now (D2 says: once the three
   known causes are fixed). If yes, set it and re-run `doctor`; if not, write the remaining causes
   into the proposal.

## Out of scope

Chunking changes other than the preamble; markup cleaning (A1); heading recovery for the
figure-caption documents beyond the preamble (they are covered by it); anything in the MCP.

## Close-out

Update the proposal's status line and §6 A2 with the commit and the numbers; update the line in
`docs/README.md`; move this prompt to `docs/prompts/historical/` in the landing commit; commit and
push; update the project memory note.
