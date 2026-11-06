# vdocs machine interface — MCP and API: current state, measurements, recommendations

**Status:** proposal for review · 2026-11-06 · nothing in §6 is built yet.
**Partly superseded (2026-11-06, same day):** search is a keyword, exact-phrase and AND/OR/NOT
tool, not a natural-language one. The paraphrase framing below, which calls reworded questions the
largest loss, is withdrawn. R9, R10, R12 and R14 are replaced by
[`keyword-search-four-fixes.md`](keyword-search-four-fixes.md). The rest stays open here.
**Corpus measured:** `~/data/vdocs/index.db` · 1,040 documents (615 latest) · 57,804 chunks ·
`corpus_content_hash 5b118189…` · read contract 1.7 (the lake after the 2026-11-05 PXRM refresh).
**Evidence:** every number below comes from `scripts/mcp_review/*.py` and is recorded, with
provenance, in `reports/mcp-review-*.json` (re-run instructions in Appendix A).

## Abstract

vdocs exposes its gold VistA documentation corpus to machines through four front doors that share
one SQLite FTS5 index: an MCP server (`vdocs serve-mcp`), the `vdocs ask --json` command, the Go
`vdocs` binary (vdocs-cli), and the vdocs-web HTTP API. This review checks those surfaces against
the current code, defines what an optimal result looks like for a machine consumer, and measures
each surface. The measurements use the 24-question judged key, 707 automatically derived
known-item probes, and protocol-level runs of the real server. The ranking engine sits near a local
optimum for lexical retrieval: every BM25-side variant tried (stemming, stopword removal, AND-first
matching, prefix matching, per-document caps) was neutral or worse. The large remaining losses are
elsewhere. Identifiers are mis-tokenised: KIDS patch ids are found in the top five only 48% of the
time, and FileMan file numbers 50%. Retrieval is brittle to vocabulary: paraphrased questions fall
from 100% to 33% success. The interface makes agents pay for what the server could do itself: it
has no way to read a cited passage, it cites URIs it cannot resolve, and about 80% of its 2,268-token
search response is metadata. It also returns misleading guidance on invalid input, and nine claims
across the surfaces have drifted from the code. The proposal ranks fourteen changes by measured
effect and cost. It also names the changes that were measured and rejected.

## Executive summary

**What works.** On the judged key, the MCP `search` tool puts a correct answer in its top five for
23 of 24 questions (Success@5 0.958), ranks one first 71% of the time, and scores nDCG@10 0.655
(95% CI 0.55–0.76), MRR 0.795 and Recall@15 0.776. Latency is 125 ms median. Its honesty
machinery (pre-cited hits, the "zero hits is not absence" envelope) is ahead of most document
servers.

**Where an agent gets a wrong answer, by measurement:**

| Failure | Measured | Why |
|---|---|---|
| A question worded differently from the manual | Success@15 **1.00 → 0.33**, MRR 0.89 → 0.14 (12 paraphrases) | lexical matching. The response gives no sign of failure, so the agent trusts a plausible but wrong list |
| A KIDS patch id (`DG*5.3*1029`) | Success@5 **0.48**, precision@5 0.17 (256 builds) | single digits are dropped from the query, leaving `DG` OR `1029` |
| A FileMan file by number (`#50.7`) | Success@5 **0.50** (decimal 0.38) vs **0.90** by name (30 files) | `50.7` becomes `50` + a dropped `7`; the expansion map holds one file |
| A two-letter namespace (`OR`, `SD`, `EN`) | precision@5 **0.0** | the code is also an English word |
| An invalid filter (`app: ["FileMan"]`, `["di"]`) | 0 hits + "this is a retrieval artefact, read the body" | filters are never validated |
| `"exact phrase"`, `NOT` | quotes ignored; `NOT` is searched *for* (15 of 15 hits contain the excluded word) | query syntax is flattened silently |

**Where the interface costs the agent:**

- **No way to read a hit.** `lookup section` returned the section's text in 0 of 30 samples. Reading
  a passage takes hand-written SQL against `chunks`, or a filesystem read of a lake-relative
  `body_path`. The server never says where the lake root is, and a remote client cannot do that read
  at all.
- **Citations it cannot resolve.** Every hit carries a `vdocs://section/…` URI, but `resources/*`
  answers "method not found".
- **Payload.** A default search costs about 2,268 tokens: 15 hits at about 150 tokens each, with
  snippets only 20% of the bytes. The same content packs into 1,152 tokens. Section-collapsed hits
  with passages four times longer still fit in 1,691.
- **Protocol hygiene.** Version negotiation is pinned to `2024-11-05`. There are no tool
  annotations and no output schema, and 6 of 8 parameters lack descriptions. A runaway `query`
  blocked the single-threaded server for more than 20 s.

**Drift.** Nine claims disagree with the code:

- The `search` tool's one-line rule says about 27% of sections are unindexed; the measured figure
  is 10.5%.
- The `lookup` tool's own example key does not exist.
- Two project documents say the MCP surface is descoped, but it shipped in July 2026.
- The design document claims a store-version check that the server does not perform.
- The Go CLI's README says "PRE-CODE".
- The corpus skill (org-owned) still recommends `--k 8` on the Go binary.

**The other front doors.** The Go CLI ranks almost identically: 22 of 24 top-10 lists are the same,
and nDCG is 0.016 lower because it lacks the expansion and the parent/child reorder. The vdocs-web
`/api/candidates` route is not a search API. It returns zero results for 18 of 24 natural-language
questions (implicit AND within one chunk) and orders documents by title, not relevance.

**Recommendations (detail in §6).** All are unbuilt. Expected effects are measured where possible.

1. **Honesty and correctness, cheap:**
   - Generate every quoted number from the index at server start.
   - Validate filters and empty queries.
   - Put a time budget on `query`.
   - Fix the nine stale claims.
2. **Interface:**
   - Add a section-text tool that also performs the body.md fallback the instructions ask the
     agent to do by hand.
   - Serve the cited URIs as resources, or stop emitting them.
   - Return structured, section-collapsed, compact results: −25% to −49% tokens, +1.6 points of
     Recall@15.
   - Add tool annotations and parameter descriptions, negotiate the protocol version, and make
     facet codes discoverable without SQL.
3. **Engine:**
   - Parse identifiers as phrases when the identifier *is* the query. Measured: patch ids
     Success@5 0.48 → 0.79, file numbers 0.50 → 1.00, M APIs 0.94 → 0.96, zero golden regressions.
   - Return a failure signal, so an agent knows when to reformulate. The top BM25 score separates
     useful from useless lists with AUC 0.86.
4. **Consolidation:**
   - Use one ranking engine behind every machine front door.
   - Fix index hygiene: missing indexes, navigation chrome in 81% of chunks, 320 link-polluted
     titles, 78 documents below 95% body coverage.
   - Grow the judged key with identifier, paraphrase and negative questions.

**Measured and not recommended:**

| Variant | Change in nDCG@10 |
|---|---|
| Porter stemming | +0.027, CI crosses zero, 12 of 24 questions worse, Success@5 −8 points |
| Stopword removal | −0.075 |
| AND-first matching | −0.070 |
| Prefix matching | −0.101 |
| At most three hits per document | Recall@15 −0.27 |

Raising k beyond 15 is past the knee measured earlier. Embeddings remain ruled out by the
2026-06-08 direction reset; the vocabulary gap is addressed lexically (§6, R9 and R11).

## Table of contents

- [Abstract](#abstract)
- [Executive summary](#executive-summary)
- [1. Scope and method](#1-scope-and-method)
- [2. Current state](#2-current-state)
  - [2.1 The MCP server](#21-the-mcp-server)
  - [2.2 The shared engine](#22-the-shared-engine)
  - [2.3 The four front doors compared](#23-the-four-front-doors-compared)
  - [2.4 Consistency audit — claims against code](#24-consistency-audit--claims-against-code)
- [3. What "optimal" means for a machine consumer](#3-what-optimal-means-for-a-machine-consumer)
- [4. Measurements](#4-measurements)
  - [4.1 Judged key, by surface](#41-judged-key-by-surface)
  - [4.2 Ranking variants on the same engine](#42-ranking-variants-on-the-same-engine)
  - [4.3 Adversarial probe classes](#43-adversarial-probe-classes)
  - [4.4 Identifier-aware query parsing](#44-identifier-aware-query-parsing)
  - [4.5 Response economics](#45-response-economics)
  - [4.6 Protocol conformance and safety](#46-protocol-conformance-and-safety)
  - [4.7 Index coverage of the gold body](#47-index-coverage-of-the-gold-body)
  - [4.8 Can the response signal its own failure?](#48-can-the-response-signal-its-own-failure)
- [5. Adversarial analysis](#5-adversarial-analysis)
- [6. Recommendations](#6-recommendations)
- [7. Target state at a glance](#7-target-state-at-a-glance)
- [8. Verification plan](#8-verification-plan)
- [9. Limits of this review and open decisions](#9-limits-of-this-review-and-open-decisions)
- [10. References](#10-references)
- [Appendix A — reproducing the measurements](#appendix-a--reproducing-the-measurements)

## 1. Scope and method

**In scope:**

- The MCP server (`src/vdocs/server/mcp.py`).
- The engine it shares with `vdocs ask --json` (`server/search.py`, `server/search_pure.py`).
- The Go `vdocs` binary (`~/projects/vdocs-cli`, binary built 2026-07-24).
- The vdocs-web JSON API (`~/projects/vdocs-web/internal/api`, the running instance on `:8765`).
- The published read contract (`contracts/read/v1.json`).

Pipeline stages are in scope only where they limit what search can find (§4.7).

**Relevance.** Two independent rulers are used, and neither is the engine itself:

- **The judged key** (`registries/golden-queries.yaml`): 24 labelled questions with 109 graded
  answers. The metric code is inlined, in the house style of `baseline_golden.py`.
- **Automatically derived probes**, judged by exact text containment:
  - 421 M APIs whose defining section is titled with the API reference.
  - 256 KIDS build ids, where a hit counts if its text contains the exact id.
  - 30 FileMan files, where a hit counts if its text names the file *and* its number.
  - 109 application codes, where a hit counts if it belongs to that application.

**Statistics.** The key is small, so every mean carries a 95% bootstrap interval (4,000 resamples).
Every comparison is paired per question and reported as wins and losses, not just a mean.

**Surfaces were measured as built:**

- The MCP server over its real stdio transport.
- The Go binary as a subprocess.
- vdocs-web over HTTP.

What-if variants reuse the production SQL, column weights, expansion and parent/child reorder, and
change one thing each.

**Token counts** use a 4-characters-per-token heuristic; no tokenizer is available on this machine.
They are good for comparing shapes, not for billing.

## 2. Current state

### 2.1 The MCP server

Hand-rolled newline-delimited JSON-RPC 2.0 over stdio. Capabilities: tools only. Registered at user
scope (`claude mcp get vdocs` → `.venv/bin/vdocs serve-mcp`).

| Tool | Input | Output | Notes |
|---|---|---|---|
| `orientation` | — | text: provenance pins, table list, citation contract, the three-sources rule | 426 tokens; numbers hard-coded |
| `search` | `query`, `k` (1–50, default 15), `app[]`, `doc_type[]` | JSON `{hits[], hit_count, warning?}`. Each hit has 11 fields: score, section_id, doc_key, doc_id, doc/section titles, app_code, doc_type, snippet (16 tokens), `vdocs://` uri, `body_path` | the `vdocs ask` engine |
| `lookup` | `kind` ∈ doc / section / entity, `key` | the raw table row(s) + a citation; a section lookup adds `has_indexed_text` and, when that is false, fallback guidance | **never returns section text** |
| `query` | `sql` (SELECT/WITH), `max_rows` ≤ 500 | `{columns, rows, row_count, truncated}` | read-only connection, **no time limit** |

Session overhead before any work:

- The `tools/list` definitions: 542 tokens.
- The `initialize` instructions: 150 tokens.
- `orientation`, if the agent follows the "call first" rule: another 426 tokens.

### 2.2 The shared engine

`lexical_search` is the single engine behind the MCP `search` tool and `ask` / `ask --json`, and
the golden harness imports it directly. It runs in eight steps:

1. Tokenise on `[A-Za-z0-9_]+`, dropping tokens shorter than two characters.
2. Quote each token and OR-join them.
3. Add a phrase clause for any token in the entity-derived expansion map. That map holds **one**
   entry today: 200 → NEW PERSON.
4. Rank by field-weighted `bm25` (document title 2.5, section title 2.0, section path 1.5, body 1.0)
   over `chunks_fts`. The table uses FTS5's default `unicode61` tokenizer, with no stemming.
5. Apply the `app_code` / `doc_type` pre-filter.
6. Over-fetch 3×.
7. Reorder so that a parent heading which merely restates its child follows that child.
8. Truncate to k.

Results are **chunks**, so one section can occupy several slots.

### 2.3 The four front doors compared

| | MCP `search` / `ask --json` | Go `vdocs search` | vdocs-web `/api/candidates?q=` | read contract (`v_*` views) |
|---|---|---|---|---|
| Unit returned | chunk hit (pre-cited) | chunk hit | **document** list | rows |
| Query parsing | alnum tokens ≥2, OR | same (ported) | whitespace tokens, **implicit AND within one chunk** | n/a |
| Expansion (200 → NEW PERSON) | on | **off** ("a measured negative result", which predates the entity-derived map) | off | n/a |
| Parent/child reorder | on | **off** | n/a | n/a |
| Ordering | weighted bm25 | weighted bm25 | **by title** | n/a |
| Default k | 15 (agents) / 8 (terminal) | 10 | all matches | n/a |
| Filters | app, doc_type | none on `search` (a separate `facets` op) | every facet axis + entity + FTS scope | SQL |
| Read a section's text | **no** (SQL via `query`) | `get section` (refuses chunkless sections and names the fallbacks) | `GET /api/section/{id}` | `v_chunks` |
| Versioned contract check | **none** | none | refuses on major mismatch | — |

The vdocs-web route is the backend of a faceted browser, not a ranked search API. §6 R12 asks for
that to be decided explicitly.

### 2.4 Consistency audit — claims against code

| # | Claim | Where | Measured | Severity |
|---|---|---|---|---|
| 1 | "~27% of sections … carry no indexed text" | `mcp.py` `TOOL_RULE`, embedded in the `search` and `lookup` descriptions | **10.51%** (5,476 of 52,093 live sections: 4,641 container + 835 hollow). The same file's orientation and instructions correctly say 10.5% | high: it is the line some clients surface alone, and it inflates the fallback burden 2.5× |
| 2 | "52,128 live sections", "5,469 (10.5%)", "4,246 tables" | orientation and instructions, hard-coded | 52,093 · 5,476 · 4,246 | low today, but nothing gates it: the doctor's card-drift check covers `CORPUS.md`, not the MCP strings |
| 3 | `lookup` example `doc_key` `'CPRS/or_um'` | `search`/`lookup` tool description | **no such key** (MISS) | medium: the one example an agent copies fails |
| 4 | "the MCP/agent surface is descoped" | `CLAUDE.md`, `docs/vdocs-user-guide.md` | shipped 2026-07-05, registered user-wide | medium |
| 5 | the server "refuses to start against an incompatible store" | design §14.5 | no version check in `mcp.py` (vdocs-web has one) | medium |
| 6 | "MCP via the official MCP Python SDK" | design ADR table, row 014 | hand-rolled JSON-RPC; the SDK is descoped | low |
| 7 | `vdocs://` resources for doc / section / entity | design §14.3 (marked v-next) | URIs are emitted in every hit, but `resources/list` returns −32601 | medium: a citation format that does not resolve |
| 8 | "Status: PRE-CODE. No Go is written yet." and "26.7% / about a quarter" | vdocs-cli `README.md`, `ops/get.go` help, `tui/browser.go` | about 4,800 lines of Go shipped; 10.5% | medium (a dangling artifact by the house rule) |
| 9 | `vdocs search … --k 8 --json`, "~27% returns empty", the MCP server is "the eventual … front door" | `~/vista-forge/workspace/skills/vdocs-corpus/SKILL.md` (**org-owned**) | k=15 is the measured knee; 10.5%; the MCP server exists | medium: **a request to vista-forge, not a change made from here** |

Minor, recorded for completeness:

- `lookup doc` on a prior version returns the version-free `body_path`, which is the *latest*
  body.
- 68 of 441 `fileman_file` entities have one- or two-character names (`0`, `01`).
- `rpc:ORWDX SAVE` is not an entity, although the phrase occurs in 3 chunks; only 159 RPC entities
  exist.
- 46 latest documents share their cleaned title with another latest document, for example two
  "EDIS — Technical Manual".

## 3. What "optimal" means for a machine consumer

A person scans the top few results and stops. An agent pays tokens for every result it is handed,
reads them all, and then acts on what it read. So the measures that matter are different:

- whether the answer is *anywhere in the page* the agent receives;
- how many tokens and round trips it costs to get the answer into context;
- whether the server ever lets the agent conclude something false.

Position still matters, because models under-use material in the middle of long contexts [9]. But
"is the answer in the page" dominates "is it first". The targets below are **this review's
proposals**, set from the measured knee, current performance and common IR practice [5–8]. They
are not an industry standard. No published standard exists for MCP document servers.

| Family | Metric | Definition | Why it matters to an agent | Today | Proposed target |
|---|---|---|---|---|---|
| Effectiveness | **Success@k** (k = default page) | a judged answer appears in the returned page | the agent can only use what it is handed | 0.958 @15 | ≥ 0.95 |
| | Recall@k | share of judged answers in the page | multi-part questions need more than one passage | 0.776 @15 | ≥ 0.85 |
| | nDCG@10, MRR | graded ranking quality, rank of first answer | ordering still steers attention [9] | 0.655, 0.795 | ≥ 0.70, ≥ 0.80 |
| | Known-item Success@1 | an identifier lookup (API, patch, file) returns its defining passage first | identifiers are the commonest agent query in a technical corpus | API 0.68 · patch 0.23 · file 0.27 | ≥ 0.80 each |
| | Paraphrase retention | Success@k on reworded questions ÷ on originals | agents restate the user's words, not the manual's | 0.33 | ≥ 0.70 (with agent reformulation) |
| Economics | Tokens per response | at the default k | a search should not crowd out the answer | 2,268 | ≤ 1,500 |
| | Evidence density | share of response tokens that are document text | metadata is not evidence | ≈ 0.20 | ≥ 0.50 |
| | Duplicate-slot rate | slots repeating an earlier section | wasted slots | 0.033 | 0 |
| | Round trips to a cited passage | calls from question to readable passage text | each trip costs latency, tokens and error risk | 3 (orientation, search, SQL) or a filesystem read | 2 |
| Honesty | False-absence rate | "not documented" when the corpus has it | the worst failure for this server | not directly measured (needs agent runs) | 0 |
| | Input-error fidelity | invalid input produces an error that says what is wrong | a silent empty result looks like absence | invalid filters and empty queries give a misleading warning | 100% |
| | Failure-signal AUC | a response field predicts that the page holds no answer | lets the agent reformulate instead of trusting junk | none exposed (top score, unexposed as such, 0.86) | ≥ 0.80, exposed |
| Contract | Citation resolvability | every cited id or URI resolves *through the same interface* | a citation the client cannot open is not a citation | `body_path` 615/615 on disk but not via MCP; URIs 0% | 100% via the protocol |
| | Schema conformance | results validate against a declared output schema | clients can parse without guessing | no schema | 100% |
| | Claim drift | numbers and examples in tool text that disagree with the index | stale guidance mis-steers every session | 9 items | 0, gated |
| Operations | Latency p50 / p95 | per search | interactive loops | 125 / 152 ms | ≤ 200 / 500 ms |
| | Worst-case bound | longest any call may run | one bad call should not stall the session | unbounded | ≤ 2 s, then a typed error |

## 4. Measurements

### 4.1 Judged key, by surface

24 labelled questions, k = 15 unless stated (`reports/mcp-review-surfaces.json`).

| Surface | nDCG@10 (95% CI) | MRR | Recall@10 | Recall@15 | S@1 | S@5 | S@15 | dup slots | p50 / p95 ms |
|---|---|---|---|---|---|---|---|---|---|
| **MCP / `ask --json`** | **0.655** (0.554–0.755) | 0.795 | 0.718 | 0.776 | 0.708 | 0.958 | 0.958 | 0.033 | 120 / 149 (in-process); 125 / 152 over stdio |
| Go `vdocs search` | 0.639 (0.528–0.747) | 0.792 | 0.694 | 0.762 | 0.708 | 0.958 | 0.958 | 0.033 | 233 / 268 (process per call) |

- **Go against Python, paired:** nDCG −0.016 (0 wins, 2 losses); 22 of 24 top-10 lists identical;
  mean top-10 Jaccard 0.975. The two losses are the questions the expansion and the reorder were
  built for.
- **The one question no surface answers** in its top 15 is `fileman-add-field`, which was already 0
  in the baseline of record.
- **Baseline drift.** The baseline of record was 0.6447 on a different corpus (57,895 chunks). Today's
  0.6554 is the first measurement on the refreshed lake, so compare `chunks` and the hash, not the
  number alone (`reports/README.md`).

**vdocs-web `/api/candidates`** (document level):

| Input | Zero-result questions | Relevant document in first 10 rows (title-ordered) |
|---|---|---|
| The natural-language question | **18 / 24** | 5 / 24 |
| The question as keywords (stopwords removed) | 4 / 24 | 19 / 24 |
| *MCP, distinct documents in its top 10 (for comparison)* | 0 / 24 | 23 / 24 |

### 4.2 Ranking variants on the same engine

Each variant changes one thing. Deltas are paired against production
(`reports/mcp-review-surfaces.json`, `paired_vs_mcp`).

| Variant | Δ nDCG@10 (95% CI) | wins / losses | Δ Recall@15 | Δ S@5 | Verdict |
|---|---|---|---|---|---|
| Section collapse (one slot per section) | +0.002 (0, +0.005) | 1 / 0 | **+0.016** (0, +0.043), 2 / 0 | 0 | **adopt**: removes the 3.3% duplicate slots at no cost |
| Porter stemming (scratch index, same weights) | +0.027 (−0.016, +0.083) | 8 / 12 | +0.015 | **−0.083** | not proven; more questions lose than win |
| Stopword removal | **−0.075** (−0.136, −0.024) | 4 / 12 | −0.019 | −0.042 | reject: BM25's IDF already discounts them, and removing them costs context |
| AND-first, OR fallback | −0.070 (−0.169, +0.035) | 5 / 15 | −0.066 | −0.083 | reject |
| Prefix matching (`instal*`) | **−0.101** (−0.187, −0.024) | 7 / 13 | −0.044 | −0.083 | reject |
| Porter + stopwords | −0.069 | 9 / 10 | −0.043 | −0.083 | reject |
| At most 3 hits per document | **−0.090** | 0 / 14 | **−0.266** | −0.042 | reject: answers cluster in one manual |

**Reading.** BM25 tuning is exhausted on this key. The column-weight sweep reached the same
conclusion earlier (`reports/rr2-weight-sweep.*`). The levers left are what the query means (§4.4)
and what the response carries (§4.5).

### 4.3 Adversarial probe classes

`reports/mcp-review-adversarial.json`, `reports/mcp-review-extra.json`.

| Class | n | Query form | S@1 | S@5 | S@15 | MRR | Note |
|---|---|---|---|---|---|---|---|
| M API known item | 421 | the reference, `$$GET1^DIQ` | 0.682 | 0.936 | 0.990 | 0.790 | `^`, `$` and `%` are split off: `FIND^DIC` ≡ `FIND DIC` |
| | | as a question, "What does `$$GET1^DIQ` do …?" | 0.762 | 0.952 | 0.981 | 0.844 | the context words help |
| KIDS patch id | 256 | `DG*5.3*1029` | **0.230** | **0.484** | 0.652 | 0.336 | precision@5 0.17; `5` and `3` are dropped |
| FileMan file by number, integer | 17 | "FileMan file #44" | — | **0.588** | — | — | by name: 0.882 |
| FileMan file by number, decimal | 13 | "FileMan file #50.7" | — | **0.385** | — | — | by name: 0.923 |
| Application by code vs by name | 109 | `PSO` vs "Outpatient Pharmacy" | — | — | — | — | precision@5 0.787 vs 0.903; the two return only 48% of the same documents |
| Two-letter codes | 21 | `OR`, `SD`, `EN`, `LA`, `MC`, `RA` | — | — | — | — | precision@5 0.0, 0.0, 0.0, 0.2, 0.2, 0.2 |
| Namespace in a question | 1 | "OR namespace routines" | — | — | — | — | top 5: MPIF ×3, KMPR, IB; none is OR |
| Paraphrase | 12 | reworded golden questions | — | — | **0.333** (was 1.000) | **0.144** (was 0.889) | Recall@15 0.743 → 0.124 |
| Operator syntax | 4 | `"input transform"`, `KIDS NOT install` | — | — | — | — | quotes: identical results; `NOT` is a search term, and 15 of 15 hits contain "install" |
| Long pasted text | 1 | 180 words | — | — | — | — | 1.84 s (vs 125 ms typical) |

The paraphrases were written by this reviewer to avoid the manual's key nouns. That is an adversarial
upper bound on the vocabulary gap, not a sample of real agent traffic.

### 4.4 Identifier-aware query parsing

The what-if adds, for each identifier-shaped span, one adjacent-token **phrase** clause with single
digits kept, on top of the unchanged production query. Identifier-shaped spans are:

- an M reference (`TAG^ROUTINE`);
- a patch id (`NS*V*P`);
- a FileMan number after "file" or "#".

The FTS index already stores `DG*5.3*1029` as the adjacent tokens `dg 5 3 1029`. Only the query side
discards the digits.

| Rule | Golden key Δ (nDCG / Recall@15) | API S@5 | Patch S@1 / S@5 / MRR | File S@1 / S@5 / MRR |
|---|---|---|---|---|
| Production | — | 0.936 | 0.230 / 0.484 / 0.336 | 0.267 / 0.500 / 0.370 |
| v1: always add the phrase | −0.020 / −0.028; 2 questions lose their top-5 answer | 0.964 | 0.520 / 0.785 / 0.637 | 0.767 / 1.000 / 0.869 |
| **v2: only when the identifier is the query** (≤3 other words), and skip numbers the expansion map already covers | **0 / 0**: does not fire on any golden question | **0.964** | **0.520 / 0.785 / 0.637** | **0.767 / 1.000 / 0.869** |

Why v1 regressed, read from the results:

- On "What is FileMan file 200, the user account file?" the `file 200` phrase competed with the
  existing NEW PERSON expansion: nDCG 0.42 → 0.00.
- On "What is the ICR number for the BLD^DIALOG API?" boosting every mention of `BLD^DIALOG` buried
  the one ICR passage.

v2 encodes the distinction between a lookup and a question about an attribute. ⚠️ **v2 was shaped
after seeing v1's regressions, and the key has no identifier-only question.** The key therefore
proves "no regression" only vacuously, and the gains come only from the derived probes. Before this
ships, the key needs identifier questions it was not tuned on (R14).

### 4.5 Response economics

`reports/mcp-review-protocol.json`, `reports/mcp-review-tokens.json`.

| Shape (k = 15, golden questions) | Median tokens | vs today | What the agent gets |
|---|---|---|---|
| **Today**: indented JSON, 11 fields per hit, 16-token snippet | **2,268** (max 2,983; ≈150 per hit) | — | snippets are 19.6% of bytes. `uri` + `doc_id`, both derivable from other fields, are 13.4%. 15% of snippets contain navigation chrome (`[↑ Back to Contents]`) |
| Same content, compact: document metadata once, no derivable fields, chrome stripped | 1,152 | **−49%** | identical information |
| Section-collapsed + 260-character passages (≈4× the snippet) | 1,691 | **−25%** | four times more evidence text, no duplicate slots |
| Reading the top three sections in full (today needs SQL or a filesystem read) | 1,162 | — | median section 320 tokens, p90 2,137 |

The cheapest complete answer path today is `orientation` (426), then `search` (2,268), then a
hand-written `query` for the text (≈200–2,000). That is three calls, and the third requires
knowing the schema.

### 4.6 Protocol conformance and safety

`reports/mcp-review-protocol.json`; spec references [1–3].

| Check | Observed | Expected under current MCP practice |
|---|---|---|
| Version negotiation | client asked `2025-06-18`, server answered `2024-11-05` | answer with the requested version if supported, else the latest supported version [1] |
| Capabilities | `tools` only. `resources/list`, `resources/templates/list` and `prompts/list` → −32601 | resources wherever the server emits resource URIs [2] |
| Tool annotations | none | `readOnlyHint: true`, `idempotentHint: true`, `openWorldHint: false` [3] |
| Output schema / `structuredContent` | none; JSON inside a text block | declare `outputSchema` and return `structuredContent`, keeping the text block for older clients [2] |
| Parameter descriptions | 6 of 8 missing (`search.query/k/app/doc_type`, `lookup.kind/key`) | every parameter described, with an example and the allowed codes or where to find them [4] |
| Tool titles | none | human-readable `title` [2] |
| Invalid filter (`app: ["FileMan"]`, `["di"]`, `doc_type: ["Developer Guide"]`) | 0 hits + "RETRIEVAL artefact … read the body.md" | a tool error naming the bad value and the nearest valid codes [4] |
| Empty or punctuation-only query | 0 hits + the absence warning | an input error: nothing was searched |
| `k: "15"` (string) | error text "k must be 1..50" | a type error that says "integer" |
| Zero-hit warning for terms absent from the whole lake | byte-identical to the warning for terms that are in body.md but unindexed (1 distinct text across 3 absent terms) | the server can check the body.md and table sources itself and say which case applies |
| Runaway `query` (recursive CTE) | no answer within 20 s; the single-threaded server is blocked for every tool | a time budget, then a typed error |
| `lookup section` latency | 20 ms p50, 27 ms p95. `chunks(section_id)` has no index (`EXPLAIN`: `SCAN chunks`), so this grows with the corpus | an index |

### 4.7 Index coverage of the gold body

`reports/mcp-review-coverage.json`.

The three-sources rule tells every agent to read body.md and the table sidecars before answering
"not in the corpus". The measurements put a size on what that rule is protecting.

- **Sections:** 10.51% of live sections have no chunks, all of them container or hollow headings;
  every `ok` and `stub` section has chunks.
- **Words:** across all 615 latest bodies, the index (chunks plus section titles) holds **98.66%**
  of body.md word tokens. The bodies hold 11.0 million tokens, measured with YAML frontmatter
  removed.
- **Tables:** all 4,246 sidecar tables are also searchable, as 5,226 table chunks.
- **Citations:** `body_path` resolves for 615 of 615 latest documents (and 425 of 425 prior), and
  agrees with `bundle_path` 615 of 615. A tables directory exists for 437 of 615 latest documents.

So for most documents the fallback reading recovers little. The residue is concentrated:

- 222 documents fall below 99% coverage, and 78 below 95%.
- The worst is `RMPR/rmpr_3_nppdum` at **15.9%**: its 78 KB body has a single indexed section
  (Appendix B).
- Next: `PSO/pso_7_0_iep_um_4_pt2` 48%, `PSN/psn_4_p296_um_cp` 57%, `KMPS/kmps2_0um` 60%,
  `DI/fm22_krn8_file_security` 66%.

The cause is not established by this review. It is not simply text before the first heading, since
the PSO and KMPS documents start their headings early. It is flagged for a pipeline investigation
(R13). The practical conclusion for the interface: the fallback should be **targeted** at those
documents and performed by the server (R5). A blanket instruction to every agent is the wrong tool.

### 4.8 Can the response signal its own failure?

Measured over 36 questions (24 golden + 12 paraphrases, 9 of which fail to put any judged answer in
the top 15). The question is whether something the server already computes predicts failure:

- the top hit's BM25 score separates successes from failures with **AUC 0.856**;
- the share of the question's content words found in the top three hits manages AUC 0.626.

The score is in the payload today, but it is an unnormalised BM25 value with no stated meaning. No
agent can act on it. The sample is small, so treat 0.86 as "worth exposing and calibrating", not as
a calibrated threshold.

## 5. Adversarial analysis

Ways an agent ends up with a wrong or costly answer, ordered by likelihood × cost:

1. **Silent irrelevance (most likely, highest cost).** A reworded question returns a full, plausible
   page with no answer in it (paraphrase Success@15 0.33). Nothing in the response says so. The
   absence warning fires only on *zero* hits, and OR semantics almost never produce zero hits (0 of
   24 golden questions). The honesty rule guards the rare failure, not the common one.
2. **Identifier misparse.** Patch ids, decimal file numbers and two-letter namespaces lose their
   meaning in the tokenizer before ranking starts (§4.3). These are exactly the strings a developer
   or agent pastes from code or a KIDS log.
3. **Invalid filters dressed as retrieval artefacts.** A natural guess (`"FileMan"`, `"di"`,
   `"User Manual"`) returns zero hits plus instructions to go read body.md. The agent spends effort
   on a fallback for a typo, or worse, records a gap.
4. **Operator illusion.** Quotes are ignored and `NOT` is searched for. An agent that believes it ran
   a phrase or exclusion search reasons from a result it did not get.
5. **A fallback the agent cannot perform.** Off this machine, `body_path` is unreadable, and the
   server never states the lake root. On this machine, the stale "~27%" line inflates how often the
   agent believes a fallback is needed.
6. **Front-door drift.** The same question gives different answers through the Go CLI (no expansion,
   no reorder) and vdocs-web (AND semantics, title order, zero results for 75% of questions). An agent
   following the corpus skill uses the Go binary at k=8, which is neither the measured default nor
   the MCP engine.
7. **Self-inflicted stall.** One expensive `query` blocks the whole server, because the transport is
   a single synchronous loop.
8. **Redundant slots.** These were measured small: 3.3% duplicate sections at k=15. Cross-listed
   variants (2,914 document-title + heading pairs recur across latest documents) are deliberate per the
   identity audit, so they are labelled, not merged.

## 6. Recommendations

None of these exists yet. Each states its intent, the evidence, the expected effect and how it
would be verified. Tool names are left to build time.

### P0 — honesty and correctness (small, no design risk)

**R1. Generate every number the server says from the index.**

- At start-up the server already reads `meta`. It should also derive the live-section count, the
  chunkless share and the table count, then format the instructions, orientation and tool
  descriptions from those values.
- Delete the hard-coded `TOOL_RULE` "~27%".
- Replace the `CPRS/or_um` example with a key verified to exist at start-up.
- Add a unit test that fails if a digit-bearing coverage claim appears in a server string literal.
  This applies the house rule "generate the reference from the implementation".
- *Verify:* the drift count in §2.4 rows 1–3 goes to 0, and the planted-number test goes red.

**R2. Validate inputs and say exactly what is wrong.**

- Reject unknown `app` / `doc_type` values with an error listing the closest valid codes. Accept
  case-insensitive codes and the full application or document-type names (both are already in
  `v_documents`).
- Treat an empty or token-less query as an input error.
- Return a type error for non-integer `k`.
- *Verify:* §4.6 rows 7–9 return typed errors, and the absence warning appears only after a valid
  search.

**R3. Bound `query`.**

- Add a progress-handler time budget (≈2 s) and keep the row cap.
- On expiry return a tool error that suggests `LIMIT`, or `search` instead.
- *Verify:* the runaway CTE returns an error in under 3 s, and other tools stay responsive.

**R4. Fix the stale claims.**

- `CLAUDE.md` and the user guide: the MCP server is live, lexical only.
- Design §14.5: implement the major-version check, mirroring vdocs-web's `CheckSchemaVersion`, or
  delete the claim.
- Correct ADR row 014.
- vdocs-cli: rewrite its README status, and its 26.7% and "quarter" strings.
- File a **request** to vista-forge for the `vdocs-corpus` skill (27%, `--k 8`, "eventual" MCP).
  The skill is org-owned and is not edited from here.

### P1 — interface (largest cut in agent cost)

**R5. A section-text tool that performs the fallback itself.**

- Given a `section_id` from a hit, return its indexed text: chunks joined in order, navigation chrome
  stripped, flattened table chunks excluded (as vdocs-web's `SectionText` already does), plus the ids
  of its parent, children and siblings.
- When the section has no chunks, read the passage under that heading from the gold body.md, and
  name any `table-NN.csv` it references with the CSV inline.
- A document-outline mode (the headings with their kind) would let an agent navigate before reading.

This turns the three-sources *instruction* into a *capability*. It works for clients that cannot
reach the lake, and it follows the established search-then-fetch pairing for document servers [11].

*Expected:* round trips to a cited passage drop from 3 (one of them schema-dependent SQL) to 2. The
instructions shrink accordingly.

*Verify:* the protocol script reads a hit's text in one call, and reads a chunkless section from
body.md.

**R6. Make citations resolvable through the protocol.**

- Either serve the `vdocs://section/{id}` URIs as MCP resources (`resources/read` plus a URI
  template) and attach them to results as resource links [2],
- or stop emitting a URI the protocol cannot open.

Implementing them is recommended, because the URI is already the published citation contract
(design §5.5). `body_path` should stay as a local convenience, with orientation stating the lake
root.

*Verify:* 100% of cited URIs resolve via `resources/read`.

**R7. Return structured, compact, section-level results.**

- Declare an output schema and return `structuredContent`, with the JSON text block kept for older
  clients [2].
- Collapse hits to one slot per section.
- Send document metadata once per document, not per hit.
- Drop the derivable `uri` and `doc_id` fields, or move them into the document block.
- Strip navigation chrome from snippets.
- Offer a concise/detailed switch [4]: concise = today's snippet, detailed = a passage of about 260
  characters.

*Expected:* −49% tokens for the same content, or −25% with four times more evidence; Recall@15
+0.016, duplicate slots 0.033 → 0.

*Verify:* `tokens.py` medians and the `surfaces.py` collapse variant.

**R8. Protocol hygiene.**

- Annotate every tool `readOnlyHint` / `idempotentHint` true and `openWorldHint` false [3]. Add
  `title`s.
- Describe every parameter, with one real example each.
- Negotiate the protocol version properly. The hand-rolled server must then honour whichever version
  it advertises, or move to the official SDK. That is a dependency decision for the operator; the
  measured gaps do not require it.
- *Verify:* §4.6 rows 1–6 pass.

**R9. Discoverable vocabulary without SQL.**

Today the valid `app` and `doc_type` codes, their names and their counts are only reachable through
hand-written SQL, and the measurements show names outperform codes (precision@5 0.90 vs 0.79;
two-letter codes 0–0.2). Either:

- add the codes as a compact table in orientation (≈109 apps × 2 columns), or
- add a small facet-listing tool returning code, name, document count and a one-line description
  from `v_vocab`.

Both are cheap. Choose by token budget.

*Verify:* an invalid filter's error (R2) and orientation both name valid codes.

### P1 — engine

**R10. Identifier-aware query parsing (v2 rule, §4.4).**

- Add an adjacent-token phrase clause, digits kept, for M references, patch ids and FileMan numbers,
  when the identifier is the query.
- Skip numbers the expansion map already covers.

*Expected* (measured on derived probes):

| Probe | Success@1 | Success@5 |
|---|---|---|
| Patch ids | 0.23 → 0.52 | 0.48 → 0.79 |
| File numbers | 0.27 → 0.77 | 0.50 → 1.00 |
| M APIs | 0.68 → 0.72 | 0.94 → 0.96 |
| Golden key | unchanged | unchanged |

*Pre-condition:* R14's identifier questions in the key, because v2 was shaped after seeing v1. The
rule belongs in `search_pure` (pure, property-testable) so that every front door inherits it (R12).
It also covers what the expansion map was meant to do for file numbers: the map repairs 1 of 233
split files, while this rule needs no curation.

**R11. Tell the agent when to doubt the page.**

- Add a response field that grades the page from the top score (calibrated on the key, initial AUC
  0.86).
- Add a list of query terms that matched nothing in the corpus.
- Extend the instructions: on a low grade, re-query in the manual's vocabulary (application names,
  FileMan file names, menu option names), using R9's vocabulary.

Paraphrase brittleness (0.33) is the largest measured loss. For a lexical engine the remedy is a
better second query from the agent, which needs a signal and a vocabulary. Accepting several
reformulations in one call and fusing them by reciprocal rank fusion [10] is a plausible next step.
It is *not* recommended until a measured agent-reformulation set exists.

*Verify:* AUC of the exposed field ≥ 0.80 on the enlarged key.

### P2 — consolidation and hygiene

**R12. One ranking engine behind every machine front door.**

- The Go binary should port the expansion, reorder and identifier rules, behind its existing
  Python-parity test, or stop presenting itself as the agent path. The skill currently points agents
  at it.
- vdocs-web should state that `/api/candidates` is a browsing filter. If it is meant for machines, it
  needs OR semantics, BM25 order and section hits.
- *Verify:* the top-10 Jaccard between surfaces is 1.0 on the key, or the surfaces are documented
  as different products.

**R13. Index hygiene that changes what search can see.**

- Add `chunks(section_id)` and `chunks(doc_key)` indexes.
- Strip `[↑ Back to Contents]` at chunk time. It is in 46,603 of 57,804 chunks (80.6%) and in
  every body column BM25 scores.
- Repair 320 live section titles (10 documents) that carry raw markdown-link syntax, for example
  `[START^ACKQAG01 [2](#startackqag01)](#startackqag01)`.
- Investigate the 78 documents below 95% body coverage (§4.7).
- *Verify:* coverage ≥ 99% for every latest document, or a printed, named exception list.

**R14. Grow the key to cover what agents actually send.**

Add identifier-only lookups, paraphrase pairs, filtered questions, and negative questions (terms the
corpus truly lacks). Track the §3 table on every corpus release in a `reports/` rollup. Today the key
has no identifier-only questions, so a whole query class can regress unseen.

**Deliberately not proposed.**

- No embeddings or reranker models: out of scope since the direction reset.
- No stemming, stopword handling, AND-first, prefix matching or per-document caps (§4.2).
- No change to k (15 is the measured knee).
- No prompt templates, and no new tools beyond R5 and possibly R9. Four or five tools is the right
  size for this corpus; each extra tool costs every session about 135 tokens of definitions.

## 7. Target state at a glance

| Dimension | Today (measured) | Intended after P0–P1 (not built) |
|---|---|---|
| Tools | 4; text only; no annotations or schema | 5–6; structured output; annotated; every parameter described |
| Read a cited passage | SQL via `query`, or a filesystem read | one call, including chunkless sections via body.md |
| Citations | `vdocs://` URIs that do not resolve | resolvable resources + resource links |
| Search page | 2,268 tokens; chunk slots; 16-token snippets | ≈1,150–1,700 tokens; section slots; concise or detailed passages |
| Identifier lookups | patch S@5 0.48, file numbers S@5 0.50 | ≈0.79 and ≈1.00 (probe-measured) |
| Failure signal | none | graded page + unmatched terms |
| Invalid input | silent empty + misleading warning | typed error naming valid values |
| Worst-case call | unbounded | ≈2 s budget |
| Claim drift | 9 items | 0, test-gated |

## 8. Verification plan

1. Each recommendation names its check. All checks are the committed scripts in
   `scripts/mcp_review/`, run against the production lake and written to `reports/mcp-review-*.json`
   with provenance.
2. "No golden question regresses" stays the acceptance bar for any engine change (R10, R11, R12), on
   the enlarged key (R14).
3. R1's planted-number test and R3's runaway query are red-proved before their fixes land, so the
   gate is shown to fail.

## 9. Limits of this review and open decisions

**Limits:**

- The key is 24 questions. Intervals are wide (nDCG CI ±0.10), so the small deltas in §4.2 are
  directional.
- Paraphrases (§4.3) were written by the reviewer.
- Derived probes judge relevance by text containment, which tends to over-credit.
- Token counts are heuristic.
- The false-absence rate, the metric that matters most here, needs end-to-end agent runs that this
  review did not do.
- The Go binary measured was built 2026-07-24. Its source may be newer, but the README and help
  strings show it is not.

**Decisions for the operator:**

1. Is vdocs-web's `/api` a machine API, or only the browser's backend (R12)?
2. Is the Go binary a supported agent path?
3. Keep the hand-rolled transport, or adopt the official MCP SDK when moving to a current protocol
   version (R8)?
4. Facet codes in orientation, or a separate tool (R9)?

## 10. References

1. Model Context Protocol — Specification 2025-06-18, *Lifecycle* (version negotiation).
   https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle
2. Model Context Protocol — Specification 2025-06-18, *Server: Tools* (`outputSchema`,
   `structuredContent`, resource links, `title`) and *Server: Resources*.
   https://modelcontextprotocol.io/specification/2025-06-18/server/tools ·
   https://modelcontextprotocol.io/specification/2025-06-18/server/resources
3. Model Context Protocol — Specification 2025-03-26, *Tool annotations* (`readOnlyHint`,
   `destructiveHint`, `idempotentHint`, `openWorldHint`).
   https://modelcontextprotocol.io/specification/2025-03-26/server/tools
4. Anthropic Engineering, "Writing effective tools for agents — with agents" (2025): consolidate
   around workflows, return high-signal context, response-format switches, token efficiency,
   actionable errors, evaluation-driven tool design.
   https://www.anthropic.com/engineering/writing-tools-for-agents
5. K. Järvelin, J. Kekäläinen, "Cumulated gain-based evaluation of IR techniques," *ACM TOIS* 20(4),
   2002 (nDCG).
6. E. M. Voorhees, "The TREC-8 Question Answering Track Report," *TREC-8*, 1999 (MRR).
7. N. Thakur et al., "BEIR: A Heterogeneous Benchmark for Zero-shot Evaluation of Information
   Retrieval Models," *NeurIPS Datasets and Benchmarks*, 2021 (nDCG@10 / Recall@k practice; BM25
   as a strong baseline).
8. S. Es et al., "RAGAS: Automated Evaluation of Retrieval Augmented Generation," arXiv:2309.15217,
   2023 (context precision / recall for retrieval feeding an LLM).
9. N. F. Liu et al., "Lost in the Middle: How Language Models Use Long Contexts," *TACL* 12, 2024.
10. G. V. Cormack, C. L. A. Clarke, S. Büttcher, "Reciprocal Rank Fusion outperforms Condorcet and
    individual rank learning methods," *SIGIR* 2009.
11. OpenAI, "Building MCP servers for ChatGPT and API integrations" (the `search` + `fetch` tool
    pairing for document connectors). https://platform.openai.com/docs/mcp
12. Anthropic, "Introducing Contextual Retrieval" (2024): BM25 plus chunk-context headers as a
    retrieval baseline. https://www.anthropic.com/news/contextual-retrieval
13. S. Robertson, H. Zaragoza, "The Probabilistic Relevance Framework: BM25 and Beyond,"
    *Foundations and Trends in IR* 3(4), 2009.
14. B. Efron, R. Tibshirani, *An Introduction to the Bootstrap*, Chapman & Hall, 1993.
15. SQLite FTS5 documentation: tokenizers (`unicode61`, `porter`), phrase queries, `bm25()`.
    https://www.sqlite.org/fts5.html

**Internal:**

- `reports/rr3-after-twin-demotion.*` (baseline of record);
  `docs/proposals/vdocs-quality-response-ranking/` (the k=15 knee, the parent/child reorder);
- `docs/proposals/vdocs-quality-synonym-layer/` §10 (why the expansion map stays one entry);
- `docs/reference/pipeline-adversarial-audit.md`;
- `contracts/read/v1.json`;
- `~/projects/vdocs-web/internal/index/` (the web query core).

## Appendix A — reproducing the measurements

Run from the repo root against the production lake:

- **vdocs-web** must be serving `~/data/vdocs/index.db` on `127.0.0.1:8765` for `surfaces.py`.
- **The Go binary** is expected at `~/go/bin/vdocs`.
- **`surfaces.py` writes a scratch Porter index** of about 180 MB to the directory given as its
  argument (default: the system temp directory).

| Script | Output | Measures |
|---|---|---|
| `scripts/mcp_review/coverage.py` | `reports/mcp-review-coverage.json` | §2.4 counts, citation resolvability, body coverage |
| `scripts/mcp_review/surfaces.py [scratch-dir]` | `reports/mcp-review-surfaces.json` | §4.1, §4.2 |
| `scripts/mcp_review/protocol.py` | `reports/mcp-review-protocol.json` | §2.1, §4.5, §4.6 (drives the real `serve-mcp`) |
| `scripts/mcp_review/adversarial.py` | `reports/mcp-review-adversarial.json` | §4.3 |
| `scripts/mcp_review/extra.py` | `reports/mcp-review-extra.json` | §4.3 number phrases, §4.8, the `NOT` probe |
| `scripts/mcp_review/idaware.py [v2]` | `reports/mcp-review-idaware-v{1,2}.json` | §4.4 |
| `scripts/mcp_review/tokens.py` | `reports/mcp-review-tokens.json` | §4.5 shapes |
| `scripts/baseline_golden.py --k 15` | `reports/mcp-review-golden-k15.{md,json}` | the house harness at the MCP default |
