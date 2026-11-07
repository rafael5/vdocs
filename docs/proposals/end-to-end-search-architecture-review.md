# vdocs end to end: capture, storage, indexing and search — an adversarial review

**Status:** proposal for review · 2026-11-07 · nothing in §6 is built.
**Corpus measured:** `~/data/vdocs/index.db` · 1,040 documents (615 latest) · 52,093 live sections ·
57,804 chunks · `corpus_content_hash 5b118189…` · read contract 1.8 · 363 MB. The lake after the
2026-11-05 PXRM refresh, with keyword-search fixes 1–5 built.
**Evidence:** every number below was measured in this session with the SQL and regular expressions
in Appendix A, run against the file above or a scratch copy of it. Where a number comes from an
earlier report it is cited by file name.
**Builds on, does not repeat:** [`vdocs-mcp-interface-design.md`](vdocs-mcp-interface-design.md)
(the 2026-11-06 MCP and API review, R1–R14) and
[`keyword-search-five-fixes.md`](keyword-search-five-fixes.md) (all five fixes built). Appendix B
lists which of R1–R14 are still open; this review re-ranks them inside a wider list rather than
re-measuring them.

## Abstract

vdocs fetches the VA Document Library, converts each manual to markdown, normalises it, groups
versions, and indexes the latest version of every manual into one SQLite file that four front doors
read: the MCP server, `vdocs ask`, the Go CLI and vdocs-web. The ranking engine has been tuned to a
local optimum and the query reader, synonyms and web ordering were fixed this week. This review
looks upstream and downstream of the ranker: what text actually reaches the index, how it is stored,
what redundancy the templated corpus carries into results, and what the MCP server still makes an
agent pay for.

The index is not clean. One in ten indexed tokens is markup rather than prose: HTML tags, image
hashes, link targets and the navigation line that sits in 80% of chunks. The corpus vocabulary
holds 11,486 hexadecimal asset hashes. Text before a document's first retained heading is never
indexed, which leaves one manual 88% unsearchable. 6.3% of chunks are byte-identical copies of
another chunk, almost all template text, and 13 pairs of "latest" documents are more than half
identical. The database stores every chunk twice, has never been analysed, and lacks the indexes
its own lookups need. None of these is hard to fix, none needs a model or a new dependency, and
each is measurable with the harness already in the repo.

The recommendations are ranked by effect per day of work. The first tier cleans the indexed text,
indexes the preamble, adds a coverage gate, returns section-level compact results with a read tool,
and finishes the database hygiene. The second tier adds a document-level ranking mode for the MCP,
structural synonym classes derived from the entity tables, duplicate-chunk collapse and a failure
signal. Vectors stay out, with the preconditions under which a section-level, incrementally
embedded `sqlite-vec` table would become worth a measured trial.

## Executive summary

**What is already right.** Section-aligned chunking with stable ids, latest-only indexing, one
query reader shared by every front door, a synonym table with every package's plain-English names,
pre-cited hits and the "zero hits is not absence" envelope. Query latency is not a problem: the FTS
query itself runs in 1–3 ms.

**Where search quality is still decided upstream of the ranker, measured:**

| Finding | Measured | Consequence |
|---|---|---|
| Markup inside the indexed text | 10.1% of body tokens are tags, image hashes, link targets or the back-to-contents line; HTML tags in 36% of chunks, the nav line in 80% | BM25 document lengths are inflated unevenly; `back` and `contents` are the 3rd and 4th most frequent terms in the corpus; 8% of the vocabulary is asset hashes; snippets carry chrome |
| Preamble never indexed | text before the first retained heading is dropped; `RMPR/rmpr_3_nppdum` indexes 9,098 of 78,223 characters | a whole manual is effectively unsearchable; the cause is an empty-title heading (`# ` on its own line) that Pandoc emits and the shredder discards |
| Exact duplicate chunks | 2,364 texts recur; 6,033 chunks, 3,669 redundant (6.3%) | duplicate slots in results; the XPAR parameter template ("Precedence:", "Values:") and DIBR template instructions left in by authors dominate |
| Near-duplicate latest documents | 13 pairs with Jaccard ≥ 0.5 over long chunks, 18 documents | the same pharmacy API manual is indexed three times under PSA, PSN and PSX; two ROR technical manuals and two Scheduling GUI manuals are consecutive versions both marked latest |
| Database hygiene | text stored twice (117 MB `chunks` + 126 MB FTS content); no `ANALYZE`; section lookup is a full scan; 11 FTS segments | 33% avoidable size; lookups that grow linearly with the corpus |
| Capture gap | 216 held VDL listings have no document (209 DOCX, 7 PDF) | admitted manuals that cannot be found at all |

**Where the MCP still costs the agent** (from the 2026-11-06 review, still open): no way to read a
cited passage in one call, 2,268 tokens per search page of which 80% is metadata, chunk slots rather
than section slots, invalid filters answered as "retrieval artefact", unbounded `query`, hard-coded
numbers in the tool text. Plain-English searches reach the right manual on web page 1 for 5 of 6
but a judged section in the MCP top 10 for only 1 of 6, because the MCP ranks sections and the web
ranks documents.

**Recommendations, ranked (detail in §6; none built):**

| # | Change | Effort | Expected effect |
|---|---|---|---|
| A1 | Index clean text: strip tags, image targets, link targets and the nav line at chunk time (body.md unchanged) | 1 day | −10% index tokens, −8% vocabulary, clean snippets, removes a class of false matches; ranking effect measured before adoption |
| A2 | Index the preamble as its own section; add a per-document body-coverage gate to `doctor` | ½ day | the 78 documents below 95% coverage become visible and gated; `rmpr_3_nppdum` 12% → ~100% |
| A3 | Section-collapsed, compact, structured MCP results plus a section-text tool that does the body.md fallback itself (R5 + R7) | 2 days | −25% to −49% tokens per page, Recall@15 +0.016, round trips 3 → 2 |
| A4 | Database hygiene: external-content FTS, `ANALYZE`, FTS `optimize`, the missing indexes | ½ day | 363 → ~245 MB; lookups indexed; no contract change |
| A5 | Validate inputs, bound `query`, generate the numbers in tool text (R1–R3) | 1 day | no more false "retrieval artefact" on a typo; no stall |
| B1 | A document-level ranking mode in the MCP search tool (the web's 1, ½, ¼ aggregation) | 1 day | plain-English and package questions answered at the granularity they work at |
| B2 | Structural synonym classes generated from the entity tables: file number ↔ file name, option name ↔ option text; each class measured on/off as a block | 1 day + measurement | file-number lookups by name; menu options by their text |
| B3 | Collapse byte-identical chunks at index time into one chunk with an alias list, citing all | 1 day | duplicate slots 6.3% → 0 for exact copies |
| B4 | Failure signal in the response: graded top score plus unmatched terms (R11) | 1 day | agents reformulate instead of trusting a plausible wrong page |
| B5 | Near-duplicate document gate in `doctor` and a "variant of" label in results | ½ day | the 13 pairs are named, not silently served twice |
| C1 | Fetch the 216 held listings; a PDF conversion path for the 7 | per run | capture completeness |
| C2 | A section-level `sqlite-vec` table, incrementally embedded by chunk hash, only after B4 and an agent-reformulation key exist | weeks | the only lever left for the paraphrase gap; not now |

**Deliberately not proposed:** stemming, stopword removal, prefix matching, per-document caps, a
different k (all measured worse, §4.2 of the MCP review); a trigram tokenizer; blanket acronym
expansion; a synonym mining or approval workflow; whole-corpus embeddings as first built.

## Contents

- [Abstract](#abstract)
- [Executive summary](#executive-summary)
- [1. Scope, method and what is settled](#1-scope-method-and-what-is-settled)
- [2. The pipeline as a search system](#2-the-pipeline-as-a-search-system)
- [3. Findings: what reaches the index](#3-findings-what-reaches-the-index)
- [4. Findings: how it is stored](#4-findings-how-it-is-stored)
- [5. Findings: how it is searched and served](#5-findings-how-it-is-searched-and-served)
- [6. Recommendations](#6-recommendations)
- [7. Risks and mitigations](#7-risks-and-mitigations)
- [8. Verification plan](#8-verification-plan)
- [9. Decisions for the operator](#9-decisions-for-the-operator)
- [10. References](#10-references)
- [Appendix A: reproducing the measurements](#appendix-a-reproducing-the-measurements)
- [Appendix B: status of the 2026-11-06 recommendations](#appendix-b-status-of-the-2026-11-06-recommendations)

## 1. Scope, method and what is settled

**In scope.** Every stage from `crawl` to `merge` as far as it decides what text is searchable and
how; `index.db` as a storage format; the shared engine (`server/search.py`, `search_pure.py`); the
MCP server (`server/mcp.py`); the two Go consumers as readers of the same file. The gold markdown
and its sidecars as the reading surface.

**Out of scope.** The crawl and inventory layer's own correctness (audited in
[`reference/pipeline-adversarial-audit.md`](../reference/pipeline-adversarial-audit.md), 2026-08-01
and the observatory programme); vdocs-web's UI; the docs-as-code publication workstream.

**Method.** Read the code of each stage; query the live index for the shape of what it holds; sample
chunks for the share of markup; join chunks on their text for duplication; compare gold bodies with
their chunks for coverage; check query plans and database statistics. Where a change could be
measured before being built it was not: the harness rebuilds an index in about 45 s and that is the
right instrument (§8). This review names what to measure, not a predicted score.

**Settled, not reopened.** Vectors are out (direction reset 2026-06-08); sentence search is out
(2026-11-06); stemming, stopwords, AND-first, prefix, per-document caps and k are measured and
rejected; terms enter the synonym table one judged query at a time except package names; the
section id `<doc_key>/<slug>` is the citation unit; the read contract binds consumers to `v_*`
views and `chunks_fts`.

## 2. The pipeline as a search system

Sixteen wired stages (`cli/app.py:build_stages`). The table names only what each one decides for
retrieval, and the risk this review found there.

| Stage | Decides for search | State measured | Risk |
|---|---|---|---|
| crawl · catalog · serve-inventory | which VDL listings exist and are admitted (`held`) | 9,080 inventory rows: 1,280 held, 2,916 covered by another format, 1,656 excluded, 3,228 not VistA | a `held` listing with no document is invisible, not flagged as a search gap |
| fetch | which admitted listings become documents | 1,064 held rows have a document; **216 do not** (209 DOCX, 7 PDF) | capture completeness is reported by `completeness`, not by search |
| convert | the markdown shape: headings, tables, images | Pandoc for all but one document; empty-title headings (`# ` alone on a line) and raw HTML (`<p>`, `<td>`, `<span>`, `<u>`) survive | downstream stages treat these as content |
| discover · enrich · normalize | what is stripped (phrases, boilerplate, template scaffold, legacy TOC), what is relocated (tables → CSV), heading levels, anchors, the regenerated TOC and the back-to-contents lines | retention gate PASS ≥ 0.8; boilerplate 360 KB single-sourced; template STRIP only for DIBR and IG 2010s | normalize **adds** chrome the index later counts as text; the template registry covers two document types out of fourteen |
| consolidate | which document is `is_latest` in each version group | 615 anchors; two pairs of consecutive versions are both latest | a slug that carries its version defeats grouping |
| index | sections, chunks, FTS, entities | 52,093 live sections, 57,804 chunks (5,761 table chunks, 1,214 multi-part sections), 6,564 entities | the shredder drops the preamble; the FTS body is the raw markdown of the section |
| relate · resolve · merge | the graph, the SKL, the synonym table | 209,841 relations; 625 synonym rows | the SKL covers FileMan only, so file-name synonyms exist for one file |
| manifest · validate · doctor | the corpus card and the GREEN/RED gate | `doctor` gates field coverage and anchors; **no gate compares a body with its chunks** | a document can silently lose most of its text to the index |

The engine and the front doors sit after `merge` and read only `index.db`. Everything above the
line is where the text they rank is shaped.

## 3. Findings: what reaches the index

### 3.1 The FTS body is raw markdown, and a tenth of it is not prose

The `body` column of `chunks_fts` is the section's markdown exactly as `normalize` wrote it. Over a
random sample of 8,000 chunks (1.92 M tokens), stripping tags, image references, link targets,
heading marks and emphasis removes **10.1%** of the tokens. By class, over 6,000 chunks:

| Class | Share of body tokens | Chunks containing it |
|---|---|---|
| HTML tags (`<p>`, `<td>`, `<tr>`, `<col>`, `<span>`, `<u>`, `<strong>`, `<blockquote>`) | 7.2% (of which `<img …>` 2.3%) | 36% |
| Markdown link targets `](#slug)` | 1.6% | 81% |
| `[↑ Back to Contents](#contents)` | 1.3% | 80% |
| Bookmark spans `<span id="_Toc…">` | 0.5% | 8% |
| Table markers `_[Table N (extracted to CSV)](tables/table-NN.csv)_` | 0.3% | 5% |

What this does to retrieval:

- **Vocabulary.** The FTS vocabulary has 138,350 terms. 11,486 (8.3%) are 40–64-character
  hexadecimal strings, the content-addressed asset names inside `<img src>`; 205 are `_Toc` bookmark
  ids; 23,701 are bare numbers. None is ever a query term, and each costs index space.
- **Term statistics.** By document frequency the terms `back` (47,443 chunks) and `contents`
  (47,083) rank third and fourth in the whole corpus, behind only `to` and `the`. A query for
  "contents" or "back" is noise today. More importantly BM25's length normalisation sees a chunk
  with an HTML table as long and a chunk with the same words in a markdown table as short.
- **Payload.** The `snippet()` the MCP returns is cut from this column, so 15% of snippets carry the
  navigation line (MCP review §4.5).
- **False matches.** Queries containing `table`, `csv`, `span`, `id`, `img`, `src`, `toc` match
  markup.

One caution for the fix: the corpus writes keystrokes as `<Enter>`, `<RET>`, `<Tab>`. In the 6,000
sample `<Enter>` occurred 1,633 times. A naive "remove everything in angle brackets" deletes
content. The strip must whitelist HTML element names and keep inner text, keep `alt` text, keep
link labels and table cell text, and drop only targets, attributes and the nav line.

The gold `body.md` is not the problem and should not change: it is the reading surface, and the
back-to-contents lines are for people. The index should carry a cleaned projection of it.

### 3.2 Text before the first retained heading is never indexed

`index_pure.shred_sections` starts the first section at the first heading it keeps. Lines before
it are never chunked. Two things make that lossy:

- `iter_headings` skips the generated `## Contents`, and `shred_sections` drops a heading whose
  text is empty. Pandoc emits `# ` on its own line with the title on the next line for some
  converted documents. Both are correct individually; together they can push the "first retained
  heading" to the end of the manual.
- Documents whose only headings are figure captions promoted to headings (`## Figure 4-72: …`)
  have their running text before the first caption.

Measured on the 615 latest bodies: the preamble is 1.2% of all characters, but it is concentrated.
29 documents have no heading at all and are already handled by the whole-body fallback. The
remainder are the documents the MCP review flagged without a cause (§4.7: 78 documents below 95%
coverage). Three, checked by hand:

| Document | Body chars | Indexed chars | Headings |
|---|---|---|---|
| `RMPR/rmpr_3_nppdum` | 78,223 | 9,098 | `## Contents`, `# ` (empty) followed by "Using Surgical Implants", `# Appendix B` |
| `KMPS/kmps2_0um` | 26,994 | 13,916 | `# ` (empty) before `## Contents`, then 13 real headings |
| `PSO/pso_7_0_iep_um_4_pt2` | 24,963 | 11,702 | `## Contents`, then figure-caption headings |

The fix is one section: when the lines before the first retained heading carry substantive tokens,
emit them as a section with slug `preamble` titled from the document, searchable like any leaf. The
empty-title heading should also be repaired in `normalize` (join `# ` with the next non-blank
line), which fixes the reading surface too. And `doctor` should gate it: per latest document, the
share of body word tokens present in its chunks, FAIL below a floor or a named exception list.
Today nothing fails when a manual loses 88% of its text.

### 3.3 Template redundancy inside the index

The corpus is written from templates, and the templates show through:

- **Exact duplicate chunks.** 2,364 distinct chunk texts occur more than once; together 6,033
  chunks, 3,669 of them redundant (6.3% of all chunks, 3 MB). The top groups are the XPAR parameter
  documentation template (`###### Precedence: … System` 58×, `###### Values: … Yes/No` 32×, and a
  dozen more precedence variants), `User Roles with Access to This Option … All users` (72×
  across two heading levels), `Applies to … TRPCBroker Component` (30×), and the DIBR template's
  own instruction text left in by authors: `Appendix A—Revision History Archive … _[This section
  should be used to show all docume…` (31 documents). Stripping the nav line first changes the
  count by four groups: these are true template copies, not chrome artefacts.
- **Template instruction residue** is a quality defect in its own right: it is text the VA author
  was supposed to replace. The 31 copies of the revision-archive placeholder are a ready-made
  `registries/phrases` or boilerplate candidate; `discover` already mines near-duplicate blocks and
  this one has evidence in 31 documents.
- **Near-duplicate documents.** Joining latest documents on shared chunks longer than 200
  characters, 25 pairs share 20 or more; 13 pairs have Jaccard ≥ 0.5 over their long chunks, 18
  documents in all:

  | Jaccard | Shared | Pair | Reading |
  |---|---|---|---|
  | 0.94 | 226 | `PSA/phar_1_api_r0520` · `PSN/phar_1_api_0520` | the same Pharmacy API manual filed under three applications (PSX is the third, 0.77 with each) |
  | 0.73 | 217 | `HL7/hl71_6p56_p66` · `HL7/hl71_6smdm_p161` | two HL7 manuals sharing most of their body |
  | 0.68 | 188 | `LR/apump422` · `LR/lab_ap_lr_5_2_ug` | two Anatomic Pathology user guides |
  | 0.60 | 176 | `ROR/ror1_5_41tm` · `ROR/ror1_5_42tm` | **consecutive patch versions, both latest**: the version lives in the slug so grouping misses |
  | 0.53 | 27 | `SD/vs_gui_release_1_7_56_1_technical_manual` · `…1_7_64_1_tm` | same: two releases both latest |
  | 0.56 | 87 | `HBPC/hbh1_um` · `HBPC/hbh_um` | two editions of one manual |

  46 latest titles are shared by more than one latest document (72 pairs). The identity audit ruled
  cross-listed copies deliberate variants (they carry different patch references in the title), so
  merging them is wrong. Serving them unlabelled as three independent hits is also wrong: a search
  that lands on the pharmacy API spends three of its fifteen slots on one manual. The version pairs
  are a `consolidate` grouping miss and should be fixed there.

### 3.4 Table chunks and multi-part sections

5,761 table chunks make every extracted CSV searchable, with the caption repeated in each window.
1,214 sections are split into `#pN` parts; a hit on part 3 cites the section, which is right.
Section collapse at result time (R7) is the measured remedy for the duplicate slots this creates
(+0.016 Recall@15, 3.3% duplicate slots → 0). No chunking change is proposed: small-leaf merging
was built and measured to cost citation precision (nDCG 0.395 → 0.223), and the oversized split
is bounded and fence-aware.

### 3.5 Capture completeness

Of 1,280 `held` inventory rows, 1,064 have a document and 216 do not: 209 DOCX and 7 PDF. The
observatory tracks VDL growth; the search layer should know what it cannot search. A tiny
`v_inventory`-driven line in orientation ("216 admitted listings are not yet fetched; `vdocs
completeness` lists them") costs nothing and prevents a wrong "not documented". The 7 PDFs need a
conversion path: Docling is already a system dependency for one DOCX; routing PDFs to it is a
registry entry plus a measured check of what Docling makes of them.

## 4. Findings: how it is stored

### 4.1 index.db

| Object | Size | Note |
|---|---|---|
| `chunks_fts_content` | 126 MB | FTS5's own copy of every column, including `body` |
| `chunks` | 117 MB | the same text again, plus `doc_title`/`title`/`section_path` repeated per chunk in FTS |
| `chunks_fts_data` | 46 MB | the inverted index proper; 11 segments, never merged |
| `doc_sections` | 16 MB | 83,738 rows, half of them prior versions |
| `relations` + its primary-key index | 25 MB | 166,139 `cooccurs` edges that no front door reads at query time |
| `entity_mentions` + index | 11 MB | |
| everything else | < 5 MB | |

Observations:

- **The text is stored twice.** FTS5 supports an external content table: the index then reads
  column values from `chunks` on demand, `snippet()` and column reads keep working, and consumers
  see the same `chunks_fts` surface. `chunks` needs the three heading columns added (they belong
  there anyway for section-collapsed results). Saving: about 120 MB, a third of the file. Because
  `index` rebuilds atomically there is no delete-synchronisation risk.
- **Never analysed.** There is no `sqlite_stat1`. The planner has no row estimates for any join.
  One `ANALYZE` at the end of the build, or `PRAGMA optimize`, fixes that.
- **Missing indexes.** `SELECT 1 FROM chunks WHERE section_id = ?` is a full table scan (the MCP
  review measured 20 ms and growing); a document's outline (`doc_sections WHERE doc_key ORDER BY
  seq`) scans and sorts in a temp B-tree; `entity_mentions` has no `doc_key` index; `relations`
  has no index on its destination. The facet indexes on `documents` exist and are fine.
- **FTS segments.** 11 segments after the build. `INSERT INTO chunks_fts(chunks_fts)
  VALUES('optimize')` merges them once; the file is read-only afterwards so it never fragments.
- **Tokenizer.** Default `unicode61`, `detail=full`. Correct: phrase queries need positions, and
  the identifier problem was solved on the query side (fix 2), not by `tokenchars`. A trigram
  tokenizer was considered for substring matching of identifiers and rejected: it roughly triples
  the index and the phrase reader already finds `DG*5.3*1029` 216 times out of 256.
- **Per-chunk `doc_title`.** Repeating the document title in every chunk is how the 2.5 weight
  works, and it is why `user`, `manual`, `guide`, `version` are among the 20 most frequent terms.
  That is a known cost of the design and the weight sweep accepted it; no change.

### 4.2 The lake

| Tree | Size | Role |
|---|---|---|
| `documents/bronze` | 1.8 GB | raw DOCX/PDF, content-addressed: the evidence corpus |
| `documents/assets` | 1.2 GB | extracted images, content-addressed |
| `documents/silver/text` | 573 MB | three generations of markdown (181 + 181 + 212 MB) |
| `documents/gold/_shared/history` | 550 MB | 4,310 prior-version bodies, content-addressed |
| `documents/gold/consolidated` | 136 MB | the 615 reading bundles |
| `rich-tables`, `rich-assets` | 26 + 34 MB | the sidecars consumers download |

Nothing here is a problem at one-person scale and nothing should be deleted: bronze and history
are the fidelity layer the design relies on (§14.6 of the design). The two older silver
generations are regenerable from bronze and could be dropped after a green run if disk ever
matters. Not proposed now.

### 4.3 Format

Gold markdown with YAML frontmatter, a regenerated TOC, extracted tables as CSV sidecars, figures as
content-addressed assets, and one SQLite file carrying everything a reader needs: this is the right
shape for a corpus that must be searchable offline from three languages. The one thing missing is a
**clean-text projection** per section inside the database (what A1 indexes), so that a reader
tool, a snippet and the ranker all see prose rather than markup, while the markdown stays the
reading surface.

## 5. Findings: how it is searched and served

### 5.1 The engine after fixes 1–5

Keyword forms of the 30 judged questions score nDCG@10 0.425 overall and 0.524 on the 24 original
questions (`reports/fix4-golden-keywords.md`). Nine questions score zero: `kids-install-build`,
`fileman-add-field`, `fileman-file-200-new-person`, `vista-signon-credentials`, and five of the six
plain-English searches. Patch ids reach the top 5 for 216 of 256 and `file #N` for 25 of 30
(`reports/mcp-review-all-words.json`). Every package's plain-English names reach the right
application. The FTS query runs in 1–3 ms; the 120 ms the MCP review measured is Python overhead
(a new connection per call, snippet extraction over 45 rows), and is not worth optimising yet.

### 5.2 Granularity is the remaining structural gap

The web console ranks documents by their three best passages and puts the right manual on page 1
for 5 of the 6 plain-English searches; the MCP ranks sections and puts a judged section in its top
10 for 1 of 6 (decision D5). The same engine, the same index, a different unit. An agent asking
"how do I change my password" wants the manual first and the passage second. The MCP tool should
offer the document unit as an option, computed exactly as vdocs-web does it (one FTS query, each
document's passage scores sorted, the best three weighted 1, ½, ¼), returning per document its
best sections. Nothing new to invent: the Go code is the spec and the measurement exists.

### 5.3 Synonyms: what the table holds and where the next classes are

| Source | Rows |
|---|---|
| plain-English package names | 496 |
| application codes and namespaces → name | 118 |
| Kernel parts | 8 |
| hand-written terms with a judged query | 2 |
| SKL file names | **1** (file 200 → NEW PERSON) |

The entity tables already know 441 FileMan files, 1,953 routines, 3,592 globals, 256 builds, 159
RPCs and 78 options, and the registry holds 13,166 option names from the measured model. The SKL
projected only the FileMan file names, and only one reached the synonym table. The pragmatic
expansion is **structural classes generated from data the producer already holds**, each measured
as a block with the harness and the identifier probes, never curated word by word:

1. **FileMan file number ↔ file name**, from `entities` where `type = 'fileman_file'` joined to
   the names the manuals use ("file #2" ↔ PATIENT). The MCP review measured lookups by name at
   Success@5 0.90 and by number at 0.50 before fix 2; a two-way class closes the remaining gap
   and is the one the SKL was built for.
2. **Menu option name ↔ option text**, from `option-names.txt` (the display text a user sees ↔
   the internal name a technical manual cites).
3. **Document type words → a filter**, not a synonym: "user manual", "technical manual",
   "installation guide" typed as keywords should narrow `doc_type` rather than match the words
   `user` and `manual` in 39,000 chunks. This is a query-reader rule, measured like fix 2.

The 701-line acronym map stays off as a blanket expansion (it made results worse in June). Its
right use is the same gate: an acronym row enters only with a judged query, or as part of a class
whose on/off measurement is clean. The glossary (`gold/glossary.md`, 340 KB of VA-written
definitions) is the best mining source for candidate terms, but mining produces candidates, and
the 2026-08-04 ruling that candidates are not synonyms stands.

### 5.4 The MCP server

Everything in the 2026-11-06 review's §5 adversarial list still applies except the operator
syntax, identifier parsing and front-door drift items, which fixes 2 and 3 closed. The open items
and their order are in Appendix B. Three additions from this review:

- **A read tool is the single largest cost cut** and also the honesty fix: an agent that can read a
  cited section in one call stops guessing from a 16-token snippet, and a server that performs the
  body.md fallback itself can tell the difference between "unindexed" and "absent" instead of
  printing the same warning for both.
- **The orientation text should state the capture gap** (§3.5) and the live numbers (R1), both
  generated from `v_inventory` and `meta` at start-up.
- **Section-collapsed results need the heading columns in `chunks`** (A4 adds them), so the two
  changes should land together.

### 5.5 Vectors and `sqlite-vec`: the honest position

The June spike failed on **generating** embeddings (ONNX thread fan-out exhausted memory over 57k
chunks) and on the operating cost of re-embedding the corpus on every change. Neither objection is
about storage, and the second is not true once embeddings are keyed by chunk text hash: the PXRM
refresh changed one document, so an incremental run would have embedded a few hundred chunks.
57,804 vectors of 384 dimensions are 88 MB of float32 in a `sqlite-vec` virtual table, and a
brute-force nearest-neighbour scan over them is tens of milliseconds. So the option is real and
cheaper than it was judged to be.

It is still not recommended now, for three reasons that are about value, not feasibility:

1. The only loss it addresses is the paraphrase gap, and the operator has set the contract to
   keywords. The measured plain-English failures in the MCP are a granularity problem (§5.2) that
   B1 fixes without a model.
2. There is no failure signal yet (R11). Hybrid ranking without a way to tell when BM25 is
   confidently wrong fuses noise into good lexical results; every "smart" blend measured this week
   (cards, pseudo-relevance feedback, link prior) lost.
3. Consumers are Go binaries. A vector table they cannot read is a vdocs-only feature, and the
   contract would need a `sqlite-vec` loader in two more repositories.

Preconditions for a measured trial: B4 built and calibrated; a reformulation key of at least 30
paraphrase pairs the engine was not tuned on (R14); embeddings produced single-threaded,
incrementally, in the producer only; the vector table published as an optional file beside
`index.db`, never inside the read contract. No non-neural alternative (latent semantic indexing, a
document card) is worth building: the card experiment is the measurement of that family and it
lost on 24 of 24 questions' first-place count.

## 6. Recommendations

None of these exists yet. Each is small enough to be one TDD increment: test, implement, `make
check`, rebuild the index, run the harness, commit.

### Tier A: days of work, the largest effect

**A1. Index a clean projection of each section.**
In `index_pure`, a pure function turns a section's markdown into index text: drop the nav line and
table markers; replace HTML elements from a whitelist by their inner text, keeping `alt`; reduce
links and images to their labels; drop heading marks and emphasis; keep keystroke notation such
as `<Enter>`. The `body` column of `chunks_fts` and the `text` column of `chunks` carry this
projection; `body.md` is untouched. Property tests: every word token of the input that is not
inside a dropped construct survives; no `<`, `](`, `↑` or 40-plus-character hex token survives.
*Expected:* −10% index tokens, −8% vocabulary, clean snippets, false matches on markup gone.
*Measured before adoption:* the 30-question harness and the identifier probes on a rebuilt index,
paired per question; adopt if no question loses its top-10 answer.

**A2. Index the preamble and gate body coverage.**
`shred_sections` emits a `preamble` section for substantive text before the first retained
heading. `normalize` repairs the empty-title heading by joining `# ` with the next non-blank line.
`doctor` gains a per-document check: the share of body word tokens present in the document's
chunks, FAIL below 95% unless the document is in a named exception list in `doctor-policy.yaml`,
and the exception list is printed. Red-prove the gate with a planted document.
*Expected:* the 78 documents below 95% become visible; the three in §3.2 index fully.

**A3. Section-level, compact, structured MCP results, and a read tool.**
Collapse hits to one slot per section; send document metadata once per document; drop the
derivable `uri` and `doc_id` or move them into the document block; return `structuredContent`
with a declared output schema, keeping the text block; offer a concise and a detailed passage
length. Add a tool that returns a section's clean text with its parent, children and siblings, and
when the section has no chunks reads the passage from the gold body and inlines any referenced
CSV. This is R5 and R7 of the MCP review; the measurements there stand (−25% to −49% tokens,
Recall@15 +0.016, 3 → 2 round trips).

**A4. Database hygiene.**
Add `title`, `doc_title`, `section_path` to `chunks` and make `chunks_fts` an external-content
table over it. Add indexes on `chunks(section_id)`, `chunks(doc_key)`, `doc_sections(doc_key,
seq)`, `entity_mentions(doc_key)`, `relations(dst_type, dst_id)`. Run FTS `optimize` and `ANALYZE`
at the end of the build. Bump the read contract's minor version only if a view changes (it should
not). *Expected:* 363 → about 245 MB; section lookup and outline queries use indexes; `doctor`
asserts `sqlite_stat1` exists.

**A5. Input validation, a time budget, generated numbers (R1–R3).**
Reject unknown `app` and `doc_type` values with the nearest valid codes, accept names and
case-insensitive codes; treat an empty query as an input error; return a type error for a
non-integer `k`; give `query` a 2 s progress-handler budget; derive the section, chunkless and
table counts and the capture gap from the index at start-up and format every string from them; a
unit test fails on any digit-bearing coverage claim in a server string literal.

### Tier B: a day each, measured gains

**B1. A document unit for the MCP search tool.** An option on the search tool selects document
grouping: each document's score is its three best passages weighted 1, ½, ¼ (vdocs-web's rule),
and each document carries its best two or three sections. The web measurement is the prior:
right manual first for 19 of 24 keyword questions, 5 of 6 plain-English on page 1. Add a document
unit to the harness so the two units are graded side by side.

**B2. Structural synonym classes.** `merge` writes two generated classes into `search_synonyms`
with their own `source` values: FileMan file number ↔ name from the entity and SKL tables, and
menu option name ↔ text from the option registry. Each class is switched on alone and measured on
the 30 questions, the 256 patch ids, the 30 file numbers and the 238 package names; a class that
costs a judged question its top-10 place is not written. The doc-type-word rule goes into the
query reader with cases in `contracts/query/v1.json`.

**B3. Collapse byte-identical chunks at index time.** One chunk per distinct text; a small
alias table of the other `(section_id, doc_key)` pairs it stands for; the hit cites all of them.
Measured effect is the redundancy@10 column of the harness (0.087 today) and duplicate slots.

**B4. A failure signal (R11).** Grade the page from the top BM25 score (AUC 0.86 on 36 questions),
list the query terms that matched nothing in the corpus, and say in the instructions what to do on
a low grade: re-query in the manuals' vocabulary using the facet listing (R9). Calibrate on the
enlarged key (R14).

**B5. Near-duplicate document gate and label.** `doctor` computes long-chunk Jaccard between
latest documents and WARNs above 0.5 with the pair named; `consolidate` is fixed for the two
version pairs; results carry a `variant_of` list for cross-listed copies so an agent sees three
hits are one manual. Nothing is merged.

### Tier C: conditional

**C1. Capture the 216 held listings.** Run `fetch` for the 209 DOCX; route the 7 PDFs to Docling
via `converter-routing` and inspect the result before admitting them. Report the gap in
orientation until it is closed.

**C2. A section-level `sqlite-vec` trial**, only under the preconditions in §5.5.

### Deliberately not proposed

Stemming, stopword removal, prefix matching, per-document caps, a larger k; a trigram tokenizer;
blanket acronym expansion; synonym mining into the table; small-leaf chunk merging; shredding the
markdown into component files; deleting bronze, silver or history; a reranker model; changing
`body.md`.

## 7. Risks and mitigations

| Risk | Where | Mitigation |
|---|---|---|
| The clean projection deletes content (`<Enter>`, text inside HTML tables, link labels) | A1 | element whitelist, keep inner text; property test that every non-markup word survives; a per-document retention check between markdown and projection, red-proved |
| Cleaning changes BM25 enough to move judged answers | A1 | rebuild and run the paired harness before adoption; adopt only with no top-10 loss |
| A new preamble section changes section ids or counts consumers rely on | A2 | ids are additive (`<doc_key>/preamble`); `read_schema_version` minor bump; vdocs-web and vdocs-cli tests run against a rebuilt index |
| A coverage gate reds the whole library on known-bad documents | A2 | named exception list in `doctor-policy.yaml`, printed on every run; the gate fails closed when the list names a document that no longer exists |
| External-content FTS misreads if `chunks` and the FTS table drift | A4 | the build creates both in one transaction from the same rows; `doctor` compares `count(*)` and a sampled text equality |
| Section collapse hides a second relevant passage from the same section | A3 | the detailed mode returns the whole section text; the measurement showed no recall loss |
| Document grouping buries a short manual with one strong passage | B1 | the 1, ½, ¼ weights were chosen against exactly that case (HL7 security guide); keep the section unit as default for the MCP until measured |
| Generated synonym classes add noise (common file names such as FILE, OPTION) | B2 | distinctive-surface rule from `merge_pure` (digits, caret, or multi-word); per-class on/off measurement; no class written that costs a judged question |
| Duplicate collapse cites the wrong document first | B3 | alias list sorted by the ranking the chunk earned; every alias carried in the hit |
| The failure grade is miscalibrated and agents over-reformulate | B4 | expose it as a grade with its basis, not a verdict; calibrate on the enlarged key; measure agent runs before tightening the instructions |
| More tools and fields inflate the per-session token cost | A3, B1 | stay at five or six tools; measure `tools/list` tokens before and after |
| Measurement drift between corpora | all | every report carries `index_db`, `documents`, `chunks` and the hash (`reports/README.md`) |

## 8. Verification plan

1. Before any change, re-run the harness on the current index and record it as the baseline for
   this review (the fix 4 report is that baseline today: nDCG@10 0.425, MRR 0.495, redundancy@10
   0.087 on 30 questions).
2. Each increment rebuilds the index (about 45 s) and re-runs: the 30-question harness; the
   identifier probes (256 patch ids, 30 file numbers, 421 M APIs); the 238 package names; the
   `contracts/query/v1.json` cases; vdocs-web and vdocs-cli test suites against the rebuilt file.
3. Paired per question, wins and losses reported, not just the mean; a bootstrap interval on the
   mean as the MCP review did.
4. For A1, A2 and A4 add the structural checks: vocabulary size and hex-term count; per-document
   coverage distribution; file size; `EXPLAIN QUERY PLAN` for the three lookups in §4.1.
5. For A3 and A5 re-run the protocol script of the MCP review over stdio: tokens per page, round
   trips to a passage, the invalid-filter and runaway-query cases.
6. Every gate is red-proved with a planted violation before it is trusted.

## 9. Decisions for the operator

- **D1. Clean projection in the index (A1).** Recommended: yes, body.md unchanged. Alternative: strip
  only the nav line (R13 as written). The whitelist approach removes seven times more junk and is
  the same amount of code.
- **D2. Coverage gate floor (A2).** Recommended: 95% with a printed exception list, tightened to 99%
  once the three known causes are fixed.
- **D3. Default unit for the MCP search tool (B1).** Recommended: keep sections as the default and
  add documents as an option, until the harness grades both units.
- **D4. Which synonym classes to generate (B2).** Recommended: file numbers and option names, each
  measured alone. Routines and globals are already exact-match identifiers and need none.
- **D5. Whether to open a `sqlite-vec` trial (C2).** Recommended: not before B4 and R14 exist.

## 10. References

Repository documents:

- `docs/vdocs-design.md` §5.5 (stable ids), §6.6 (version lineage), §9.6 (registries), §14.6
  (search-corpus design: "index the anchor only", "context travels as metadata").
- `docs/proposals/vdocs-mcp-interface-design.md` (2026-11-06): R1–R14, the measurements in its
  §4 and the rejected variants in §4.2.
- `docs/proposals/keyword-search-five-fixes.md` (2026-11-06/07): the query contract, synonym
  table, fix 4 baseline and §6 "deliberately not building".
- `docs/reference/pipeline-adversarial-audit.md` (2026-08-01) and
  `docs/memory/pipeline-audit-remediation.md`: "a gate that works ≠ a gate that is enforced".
- `docs/proposals/vdocs-quality-synonym-layer/` (2026-08-04 ruling on terms) and the identity and
  classification audit in `docs/proposals/vdocs-quality-vdl-observatory/`.
- `reports/README.md` (how to read a measurement), `reports/fix4-golden-keywords.md`,
  `reports/mcp-review-*.json`.
- `contracts/read/v1.json`, `contracts/query/v1.json`, `registries/search-synonyms.yaml`,
  `registries/entities/entities.yaml`, `registries/doctor-policy.yaml`.
- Code: `src/vdocs/stages/index/index_pure.py` (`shred_sections`, `split_oversized`),
  `src/vdocs/stages/index/stage.py` (schema), `src/vdocs/kernel/markdown.py`
  (`substantive_tokens`, `is_searchable`), `src/vdocs/server/search.py`, `search_pure.py`,
  `mcp.py`, `src/vdocs/stages/merge/merge_pure.py` (`is_distinctive`).

External:

- SQLite, *FTS5 Extension*: external content tables, the `optimize` command, `bm25()`,
  `snippet()`, tokenizers. <https://sqlite.org/fts5.html>
- SQLite, *ANALYZE* and *PRAGMA optimize*. <https://sqlite.org/lang_analyze.html>
- Robertson, S. and Zaragoza, H. (2009). *The Probabilistic Relevance Framework: BM25 and Beyond.*
  Foundations and Trends in Information Retrieval 3(4). Length normalisation is why markup tokens
  matter.
- Model Context Protocol specification (2025-06-18): tools, `structuredContent`, resources,
  annotations. <https://modelcontextprotocol.io/specification>
- `sqlite-vec` documentation. <https://alexgarcia.xyz/sqlite-vec/>

## Appendix A: reproducing the measurements

All against `~/data/vdocs/index.db` (copy it before creating the vocabulary table; the live file
is opened read-only by consumers).

```sql
-- sizes per object
SELECT name, SUM(pgsize)/1024/1024 AS mb FROM dbstat GROUP BY name ORDER BY mb DESC;
-- statistics and segments
SELECT count(*) FROM sqlite_stat1;                 -- errors: table does not exist
SELECT count(DISTINCT segid) FROM chunks_fts_idx;  -- 11
-- query plans
EXPLAIN QUERY PLAN SELECT 1 FROM chunks WHERE section_id = 'x';          -- SCAN chunks
EXPLAIN QUERY PLAN SELECT * FROM doc_sections WHERE doc_key = 'x' ORDER BY seq;
-- vocabulary (on a copy)
CREATE VIRTUAL TABLE v USING fts5vocab('chunks_fts', 'row');
SELECT count(*), sum(cnt) FROM v;                  -- 138,350 terms, 15,254,735 occurrences
SELECT term, doc FROM v ORDER BY doc DESC LIMIT 10; -- to, the, back, contents, of, and, …
-- exact duplicate chunks
WITH h AS (SELECT text, count(*) c FROM chunks GROUP BY text HAVING c > 1)
SELECT count(*), sum(c), sum(c) - count(*), sum(length(text) * (c - 1)) / 1048576 FROM h;
-- near-duplicate latest documents
WITH t AS (SELECT doc_key, text FROM chunks WHERE length(text) > 200)
SELECT a.doc_key, b.doc_key, count(*) n FROM t a JOIN t b ON a.text = b.text AND a.doc_key < b.doc_key
GROUP BY 1, 2 HAVING n >= 20 ORDER BY n DESC;       -- Jaccard = n / (|a| + |b| - n)
-- chrome and markup prevalence
SELECT sum(text LIKE '%Back to Contents%') * 100.0 / count(*) FROM chunks;  -- 80.6
-- capture gap
SELECT i.format, count(*) FROM inventory i LEFT JOIN documents d ON d.doc_id = i.doc_id
WHERE i.disposition = 'held' AND d.doc_id IS NULL GROUP BY 1;             -- docx 209, pdf 7
-- latest documents sharing a title
SELECT count(*) FROM documents a JOIN documents b ON a.title = b.title AND a.doc_key < b.doc_key
WHERE a.is_latest = 1 AND b.is_latest = 1;                                -- 72 pairs
```

Markup share: over a random sample of chunk bodies, count `[^\W_]+` tokens before and after
removing, in order, `\[↑ Back to Contents\]\(#contents\)`, `<[^>]+>`, `!\[[^\]]*\]\([^)]*\)`,
`\]\(#?[^)]*\)`, `^#+\s+` and `[*_`]{1,3}`; per-class counts use the same patterns one at a time,
counting the tokens inside each match. Hex terms: vocabulary terms matching `[0-9a-f]{40,64}`.
Preamble: for each latest `documents.bundle_path`, read `body.md`, drop the frontmatter, and take
the characters before the first `^#+\s+\S` match; compare with `sum(length(text))` of the
document's non-table chunks.

## Appendix B: status of the 2026-11-06 recommendations

| R | Subject | Status 2026-11-07 | Here |
|---|---|---|---|
| R1 | generate the numbers in tool text | open | A5 |
| R2 | validate inputs | open | A5 |
| R3 | bound `query` | open | A5 |
| R4 | fix stale claims (CLAUDE.md, design §14.5, ADR 014, vdocs-cli README, corpus skill request) | open | unchanged; do with A5 |
| R5 | section-text tool with body.md fallback | open | A3 |
| R6 | resolvable `vdocs://` resources | open | with A3, or stop emitting the URI |
| R7 | structured, compact, section-collapsed results | open | A3 |
| R8 | annotations, parameter descriptions, version negotiation | open | with A3 |
| R9 | discoverable facet vocabulary | open | with A5 and B4 |
| R10 | identifier-aware parsing | **closed by fix 2** (patch ids 124 → 216 of 256) | — |
| R11 | failure signal | open | B4 |
| R12 | one engine behind every front door | **closed by fixes 2 and 3** (shared reader and table; web ranks documents by design) | B1 brings the document unit to the MCP |
| R13 | index hygiene: indexes, nav chrome, 320 link-polluted titles, 78 low-coverage documents | open; cause of the coverage loss found here (§3.2) | A1, A2, A4; the titles with A1 |
| R14 | grow the key: identifier, paraphrase, filtered, negative questions | partly: 6 plain-English questions added by fix 4 | precondition for B4 and C2 |
