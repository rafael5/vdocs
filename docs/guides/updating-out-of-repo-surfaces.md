# Operator note — the two out-of-repo surfaces that quote the chunk-less rule

**Status: ACTION NEEDED (2026-08-02).** Both surfaces below live outside this repo and are
**deliberately not edited by the pipeline work** (P7.3). They currently quote **26.7% / ~73%**,
which P6.1b made wrong by more than a factor of two, and one of them names three example sections
that are now searchable. An agent reading either will be told to go read a body file for text
`search` will hand it.

The in-repo sites were all updated together in `e374d9a` and are gated by
`test_no_client_surface_quotes_a_retired_coverage_constant`.

## The current measurement (production lake, 1,040 docs, 2026-08-02)

| `kind` | sections | return empty text |
|---|---:|---:|
| `ok` | 37,495 | **0** |
| `stub` | 463 | **0** |
| `container` | **11,543** | **4,648** |
| `hollow` | **2,627** | **821** |
| **total** | **52,128** | **5,469 (10.5%)** |

Reproduce: `vdocs run --only index` then count `doc_sections` (`is_latest=1`) with no row in
`chunks`.

## 1. `~/.claude/skills/vdocs-corpus/SKILL.md`

**The heading (line ~77).**
`## ⚠️ `search`/`section` do NOT cover the whole corpus — ~27% returns empty`
→ `## ⚠️ `search`/`section` do not cover the whole corpus — ~10.5% returns empty`

**The table (lines ~82–88)** → replace with the table above.

**The rule sentence (line ~91).** This is the part that changed *in kind*, not just in number:

> The rule is clean: **every `ok` and `stub` section of a current document has text; the entire gap
> is `container` + `hollow`.** Those carry `searchable=0` and have ZERO chunks…

→

> The rule is clean: **a section returns empty only when it has nothing of its own to return** — a
> bare heading whose substance lives in its subsections. `kind` is no longer the predictor: since
> P6.1b, 6,895 of 11,543 `container` sections and 1,806 of 2,627 `hollow` ones DO carry chunks
> (`searchable` is now "has any substantive token, or relocated content", not an alias for `kind`).

**⚠️ The worked example (lines ~95–101) is now false and must go.** It says `DI/fm22_2dg` has *251
of 846 sections empty*, naming `updatedie-updater`, `filedie-filer`, `finddic-finder`. Measured
today: **107 of 846**, and **all three named sections now return text**. Either drop the example or
restate it as history ("before 2026-08-02 this was 251 of 846 …").

**Line ~139** — "blind to `container`/`hollow` prose" → "blind to sections that carry no text of
their own".

**Keep the rule itself.** It is smaller now, not weaker: an empty result is still a retrieval
artefact, prose still lives in `body.md` and `tables/*.csv`, and the incident that motivated it
(four researchers reporting documented FileMan APIs as missing) is unchanged by the number.

## 2. The mounted `vdocs` MCP server instructions

Whatever is pinned in the MCP client config quotes the same retired rule. The server itself now
emits the corrected text from `server/search.py:NOT_INDEXED_RULE`, so **the fix is usually to stop
pinning a copy** and let the server's own `initialize` instructions + `orientation` speak. If a copy
must stay, this is the current wording:

> An empty result is a RETRIEVAL artefact, not a documentation gap: ~89% of live sections carry
> indexed text, and most of the 10.5% that do not are bare headings whose substance sits in their
> subsections. Prose can also live in the gold body.md and its rich-tables `tables/*.csv` sidecars.
> Read BOTH before you ever answer "not in the vdocs gold corpus".

## Why this note exists instead of an edit

Silent edits to another surface are how the five in-repo copies drifted apart in the first place.
These two are outside the gate's reach, so they get a diff an operator applies deliberately — and
if this file is still here at the next re-measure, that is itself the signal that the drift never
got closed.
