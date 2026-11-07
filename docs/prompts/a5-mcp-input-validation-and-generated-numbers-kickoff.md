# Kickoff — A5: input validation, a time budget and generated numbers in the MCP server

> **To start the session**, `cd ~/projects/vdocs` and say:
>
> > Read `docs/prompts/a5-mcp-input-validation-and-generated-numbers-kickoff.md` and execute it.

**Repo: `vdocs`** (`~/projects/vdocs`). Read `CLAUDE.md`, then
[`docs/proposals/end-to-end-search-architecture-review.md`](../proposals/end-to-end-search-architecture-review.md)
§3.5 (the capture gap), §5.4, §6 A5, §7, §8 and Appendix B. Then the measurements in
[`docs/proposals/vdocs-mcp-interface-design.md`](../proposals/vdocs-mcp-interface-design.md) §2.4
(the nine drifted claims), §4.6 (the input-error rows), R1, R2, R3, R4 and R9. Then
`src/vdocs/server/mcp.py` (`TOOL_RULE`, `NOT_INDEXED_RULE`, `tool_orientation`, `tool_query`,
`Handler.__init__`), `src/vdocs/server/search.py` (the shared strings), and the `v_vocab`,
`v_inventory` and `meta` views in `contracts/read/v1.json`.

Effort: `medium`. Small, well-specified changes; the discipline is that no number is typed.

**Binding facts:**

- The `search` tool's one-line rule says about 27% of sections carry no indexed text; the index
  says 10.5% (5,476 of 52,093 live sections). The orientation hard-codes 52,128 / 5,469 / 4,246.
  The `lookup` description's example key `CPRS/or_um` does not exist.
- An invalid filter (`app: ["FileMan"]`), an empty query and a punctuation-only query all return
  zero hits plus the "retrieval artefact, read the body.md" warning. `k: "15"` returns "k must be
  1..50". A recursive CTE through `query` blocks the single-threaded server for more than 20 s.
- 216 held VDL listings have no document (209 DOCX, 7 PDF). No server surface says so.
- `v_vocab` holds the facet vocabularies (doc types, sections, personas, dispositions,
  namespaces); `documents` holds every `app_code` with its `app_name`. Both are the source for
  validation and for the nearest-code suggestions.
- The design (§14.5) claims the server refuses to start against an incompatible store; it does not
  check. vdocs-web has `CheckSchemaVersion` as the precedent.

## Rules for the session

TDD; no stubs; no lake rebuild (the server is read-only over `index.db`); the operator restarts
the client session after the change, say so. Every string the server emits that contains a count
or a percentage is computed at start-up from the index, never typed; a unit test enforces it.

## Before building: confirm the plan

Record in `reports/a5-before.md` with provenance.

1. **Drift inventory.** `grep -nE '[0-9]+(,[0-9]{3})*( ?%|\b)' src/vdocs/server/mcp.py
   src/vdocs/server/search.py` and list every digit-bearing claim about the corpus in a server
   string, with the live value from the index beside it (`SELECT count(*) FROM doc_sections
   WHERE is_latest=1`; the chunkless count from the `NOT EXISTS` query in the A3 kickoff; table
   chunks `SELECT count(*) FROM chunks WHERE chunk_id LIKE '%#table%'`; `corpus_doc_count` from
   `meta`). Expected: the 27% line and the three orientation numbers are stale; the rest match.
2. **The example key.** `SELECT count(*) FROM documents WHERE doc_key='CPRS/or_um'`: expected 0.
3. **Input-error behaviour over stdio.** `.venv/bin/python scripts/mcp_review/protocol.py` (or a
   hand-driven run with the same JSON-RPC lines): `app: ["FileMan"]`, `app: ["di"]`,
   `doc_type: ["Developer Guide"]`, an empty query, `"***"`, `k: "15"`, and a recursive CTE
   through `query` with a 25 s timeout. Record each response verbatim.
4. **Vocabulary available for validation.** `SELECT kind, count(*) FROM v_vocab GROUP BY kind`;
   `SELECT count(DISTINCT app_code) FROM documents WHERE is_latest=1` (expected 109); confirm
   `app_name` is populated for every code.
5. **Capture gap.** `SELECT i.format, count(*) FROM inventory i LEFT JOIN documents d ON
   d.doc_id=i.doc_id WHERE i.disposition='held' AND d.doc_id IS NULL GROUP BY 1`: expected 209
   and 7.
6. **The claims outside the server** (R4): the two lines in `CLAUDE.md` and
   `docs/vdocs-user-guide.md` saying the MCP surface is descoped; design §14.5's start-up check;
   ADR row 014 ("official MCP Python SDK"); vdocs-cli's `README.md` status line and its 26.7% /
   "about a quarter" strings; the org-owned corpus skill's `--k 8`, 27% and "eventual" MCP.
   Confirm each is still there as described.

## Work plan

1. **Generated numbers (R1).** At `Handler.__init__`, compute live sections, chunkless sections and
   their share, table chunks, latest documents, the capture gap by format, and one existing
   `doc_key` to use as the example (deterministic: the first latest `doc_key` of the application
   with the most documents, or similar; chosen once, tested). Format `instructions`, `orientation`
   and every tool description from these values. Delete `TOOL_RULE`'s typed percentage. Add the
   capture-gap line to orientation. **Unit test:** a regex over the module's string literals (read
   the source file in the test) fails on any digit-bearing coverage claim; red-prove it by
   planting one.
2. **Validation (R2)**, pure functions in `search_pure.py` or a small new pure module, tests
   first: `app` and `doc_type` values are checked against the index (codes case-insensitively,
   and full application or document-type names accepted and mapped to their codes); an unknown
   value raises a `ToolError` that names the value and the three nearest valid codes with their
   names (`difflib.get_close_matches` is enough). An empty or token-less query raises a
   `ToolError` saying nothing was searched. A non-integer `k` raises a type error naming the
   expected type. The absence warning is therefore only ever emitted after a valid search.
3. **A time budget on `query` (R3).** `sqlite3.Connection.set_progress_handler` with a wall-clock
   budget of about 2 s on the read-only connection used by `tool_query`; on expiry a `ToolError`
   suggesting `LIMIT`, a narrower `WHERE`, or `search`. Keep the row cap. Test with a recursive
   CTE on a fixture.
4. **A facet listing without SQL (R9), the cheap form:** add to orientation a compact table of
   application codes with names and latest-document counts, and the document-type codes with
   labels, generated from the index; measure its token cost (expected a few hundred). If the
   operator prefers a tool instead, that is a build-time choice; do not build both.
5. **The start-up store check (design §14.5):** read `meta.read_schema_version`, compare the
   major version with the one the server was built for (`contracts/read/v1.json`), refuse to
   start on a major mismatch with a message naming both versions, and log a warning on a minor
   mismatch. Test both.
6. **Stale claims (R4):** fix `CLAUDE.md`, the user guide, design §14.5 (now true), ADR row 014.
   For vdocs-cli, fix its README and strings in that repo and run its `make check`. For the
   org-owned corpus skill, write the request text (what is wrong, the measured values, the exact
   lines) into the session's final message for the operator to carry to vista-forge; do not edit
   the skill.
7. `make check` green.

## After building: confirm success

Record in `reports/a5-after.md` with provenance, over stdio.

1. Drift count (step 1 method): 0 typed corpus numbers in server strings; every emitted number
   equals the live index value; the example key exists.
2. The seven input cases from step 3 return typed `ToolError`s naming the bad value and the
   nearest valid codes (filters), "nothing was searched" (empty query), or the expected type
   (`k`). The absence warning appears for none of them.
3. The recursive CTE returns an error in under 3 s, and a `search` issued right after it answers
   normally.
4. Orientation shows the capture gap and the facet table; its token cost recorded.
5. The server refuses to start against a fixture `index.db` whose `read_schema_version` major
   differs, and starts against the live one.
6. The R4 list: each item fixed or, for the skill, the request written. `make check` green in
   vdocs and vdocs-cli.

## Out of scope

Result shape, the read tool and resources (A3); the document unit (B1); the failure signal (B4);
any ranking or index change; editing anything under `~/vista-forge/`.

## Close-out

Update the proposal's status line, §6 A5 and Appendix B (R1–R4, R9 status) with the commit and
the numbers; update the line in `docs/README.md`; move this prompt to `docs/prompts/historical/`
in the landing commit; commit and push; update the project memory note; tell the operator to
restart the client session and hand over the vista-forge request text.
