# Kickoff — A3: section-level compact MCP results and a read tool

> **To start the session**, `cd ~/projects/vdocs` and say:
>
> > Read `docs/prompts/a3-mcp-section-results-and-read-tool-kickoff.md` and execute it.

**Repo: `vdocs`** (`~/projects/vdocs`). Read `CLAUDE.md`, then
[`docs/proposals/end-to-end-search-architecture-review.md`](../proposals/end-to-end-search-architecture-review.md)
§5.4, §6 A3, §7, §8, §9 D3 (decided: sections stay the default unit; the document unit is B1, not
this session) and Appendix B. Then the measurements this builds on in
[`docs/proposals/vdocs-mcp-interface-design.md`](../proposals/vdocs-mcp-interface-design.md): §4.2
(section collapse: +0.016 Recall@15, duplicate slots 3.3% → 0), §4.5 (2,268 tokens per page;
compact 1,152; section-collapsed with 260-character passages 1,691), §4.6 (protocol conformance),
R5, R6, R7, R8. Then `src/vdocs/server/mcp.py`, `server/search.py` (`search_envelope`,
`keyword_search`, `_hit`), `server/search_pure.py` (`demote_restating_parents`),
`server/ids.py`, and `scripts/mcp_review/protocol.py` and `tokens.py` (the instruments).

Effort: `xhigh`. This is interface design; tool names and field names are chosen at build time and
must not appear in any document before they exist.

**Binding facts:**

- The MCP server is hand-rolled JSON-RPC over stdio, tools only, protocol `2024-11-05`, registered
  at user scope (`claude mcp get vdocs`). Changing it means the operator restarts the client
  session; say so, do not try to restart anything.
- `lookup section` returns rows, never text. Reading a passage today takes SQL via `query` or a
  filesystem read of `body_path`, which a remote client cannot do.
- Every hit carries a `vdocs://section/<id>` URI that `resources/read` cannot open (R6).
- vdocs-web already has the reference behaviour for section text: `SectionText` joins the
  section's non-table chunks in part order and strips the nav line
  (`~/projects/vdocs-web/internal/index/index.go`).
- The three-sources rule (index → body.md → tables CSV) is an instruction to the agent today. A3
  makes the server perform it.

## Rules for the session

TDD; no stubs; no new tool is named in documentation before it exists; the tool count stays at
five or six. No lake rebuild is needed for A3 (it changes the server, not the index), so the
shared-lake rule reduces to: open `index.db` read-only, as the server already does.

## Before building: confirm the plan

Record in `reports/a3-before.md` with provenance.

1. **Protocol run.** `.venv/bin/python scripts/mcp_review/protocol.py` against the live server
   over stdio: tokens per default search page (expected about 2,268 at k=15), duplicate section
   slots (expected about 3.3%), the `tools/list` and `initialize` token costs (542 and 150), the
   client's requested protocol version versus the answered one, and the four input-error cases
   (invalid `app`, empty query, string `k`, runaway CTE: these are A5's, record them only).
2. **Token shapes.** `scripts/mcp_review/tokens.py`: today, compact, section-collapsed with
   260-character passages. Expected 2,268 / 1,152 / 1,691. If the ratios differ materially from
   the review, the design targets move with them; say so.
3. **Round trips to a passage today.** Trace one golden question end to end over stdio:
   `orientation`, `search`, then the SQL needed to read the top hit's text. Record the call count
   and the total tokens.
4. **Chunkless sections.** `SELECT count(*) FROM doc_sections s WHERE is_latest=1 AND NOT EXISTS
   (SELECT 1 FROM chunks c WHERE c.section_id=s.section_id)`: expected about 5,470 (10.5%).
   Pick three and confirm by hand that the passage under the heading exists in `body.md` at
   `bundle_path` and, where the heading has a `tables/*.csv` reference, that the CSV exists under
   `rich-tables/<app>/<slug>/tables/`.
5. **Which clients.** `claude mcp get vdocs` and the protocol version the current Claude Code
   client requests (from step 1). The server must answer with a version it implements.

## Work plan

1. **Section collapse, pure, in `search_pure.py`** (test first): from the over-fetched ranked
   rows, one slot per `section_id`, keeping the best-ranked chunk's score and snippet and the
   count of matching parts; order preserved; `demote_restating_parents` still applies. Then in
   `search.py`, over-fetch stays at 3× and the collapse runs before truncation to `k`.
2. **A compact envelope, pure** (test first): documents once, each with its hits; per hit the
   section id, title, path, score, parts matched, and either a snippet (concise) or a passage of
   about 260 characters around the best match (detailed). `uri` and `doc_id` leave the hit:
   `doc_id` moves into the document block; the URI is emitted only if step 5 makes it resolvable.
   The text block keeps the JSON for older clients; `structuredContent` carries the same object
   and the tool declares an output schema for it. The `warning`/`note` semantics of
   `search_envelope` are unchanged. `vdocs ask --json` emits the same envelope (one builder, three
   surfaces).
3. **A read tool** (test first, with a fixture index and a fixture gold tree): given a section id,
   return its text (non-table chunks joined in part order, nav line stripped, markdown kept), its
   parent, children and siblings from `doc_sections`, and the ids of its table chunks. When the
   section has no chunks, read the passage under that heading in `body.md` (from the heading line
   to the next heading of equal or shallower level) and inline the rows of any `tables/*.csv` it
   references, with a `source` field saying `index` or `body.md`. An outline mode returns the
   document's headings with `kind` and whether each has indexed text. A miss is the same typed
   "NOT FOUND IN THE INDEX" text `lookup` uses.
4. **Protocol hygiene (R8):** `readOnlyHint`/`idempotentHint` true and `openWorldHint` false on
   every tool, a `title` per tool, a description per parameter with one real example each (the
   example key verified to exist at start-up, which A5 generalises), and version negotiation:
   answer with the requested version when it is one the server implements, else the latest it
   implements, and implement what that version requires of a tools-only server.
5. **Citations (R6), decide at build time after reading the spec:** either serve
   `vdocs://section/{id}` through `resources/read` by delegating to the read tool's logic and
   advertise a resource template, or stop emitting the URI. The proposal recommends serving it
   because the URI is the published citation contract (design §5.5). Whichever is chosen, no hit
   carries a URI the protocol cannot open.
6. Update the server's `instructions`, `orientation` and the `search` description so they describe
   the read tool and the collapsed shape, and drop the hand-performed body.md instruction where
   the server now does it. `make check` green.

## After building: confirm success

Record in `reports/a3-after.md` with provenance, over the real stdio transport.

1. Tokens per default search page: at most 1,700 in detailed mode and at most 1,200 in concise
   mode (−25% / −49%). `tools/list` cost before and after (the read tool adds about 135 tokens;
   the total must not grow by more than that plus the parameter descriptions).
2. Duplicate section slots at k=15 on the 30 golden questions: 0.
3. Harness paired against the current baseline: nDCG@10 and MRR unchanged (collapse does not
   reorder sections), Recall@15 not below the baseline (expected +0.016 or more).
4. One call reads a hit's text; one call reads a chunkless section from `body.md` with its CSV
   inlined; the three hand-checked sections from the before step all return their passage.
5. Every URI in a response resolves through `resources/read`, or no response carries a URI.
6. Protocol: the answered version equals the requested one for the current client; annotations
   and titles present on every tool; every parameter described; `structuredContent` validates
   against the declared schema in the test suite.
7. `vdocs ask --json` and the MCP return the same envelope for the same query.

## Out of scope

The document unit (B1); input validation, the `query` time budget and generated numbers (A5, but
if A5 has not landed, do not hard-code any new number into a server string: read it from the
index); any change to the ranking or the index; editing the org-owned corpus skill (write the
request text for vista-forge instead).

## Close-out

Update the proposal's status line, §6 A3 and Appendix B (R5–R8 status) with the commit and the
numbers; update the line in `docs/README.md`; update `docs/vdocs-user-guide.md` where it describes
the MCP tools (past tense, what exists); move this prompt to `docs/prompts/historical/` in the
landing commit; commit and push; update the project memory note; tell the operator the client
session must be restarted to load the new tool list.
