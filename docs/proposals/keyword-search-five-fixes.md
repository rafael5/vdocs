# Good-enough keyword search — five small fixes

**Status: PROPOSED · 2026-11-06 · decisions D1–D3 taken 2026-11-06 as recommended; D1 revised
2026-11-06 when sentence search was dropped (keywords only) · amended 2026-11-06: plain-English
package names made a core part of fix 3, and search-box suggestions added as fix 5, both at the
operator's direction · fix 1 built in vdocs-web 2026-11-06 (`926e320`) · Appendices A, B and C
approved by the operator unchanged 2026-11-06 · fix 2 built in vdocs (MCP and `vdocs ask`,
`9bfc552`), vdocs-web (`9448e4f`) and the Go CLI (`e9f8b62`) · fix 4 built in vdocs (`bc0188a`) ·
fixes 3 and 5 not built.** Consumer: vdocs-web (fixes 1–3 and 5). Producer and MCP: vdocs (fixes
2–4). Read contract 1.7 → 1.8, additive, for fix 3 only.
**Evidence:** every number comes from a script in `scripts/mcp_review/` (`contract.py`, `fixes.py`,
`package_names.py`, `ranking.py`, `tiers.py`, `suggest.py`), recorded with provenance in the
matching `reports/mcp-review-<name>.json`. Corpus: `~/data/vdocs/index.db`, 1,040 documents (615 latest),
57,804 chunks, `corpus_content_hash 5b118189…`. The query readers, synonym lists, cards and suggestion
list in those scripts are measurement prototypes, not production code.
**Supersedes** the search-syntax and vocabulary parts of
[`vdocs-mcp-interface-design.md`](vdocs-mcp-interface-design.md): its recommendations R9, R10,
R12 and R14, and its framing of reworded questions as the largest loss.

## Abstract

vdocs search is meant for keywords, exact phrases in quotes and simple AND/OR/NOT, with results
ranked by relevance. It is not meant for natural-language understanding or semantic search; vectors
were ruled out on 2026-06-08. Full sentences are not a supported way to search either: the operator
dropped sentence search on 2026-11-06. Measured against that contract, every front door falls short:
- Quotes do nothing: only 63% of results contain the quoted phrase.
- NOT does the opposite: 99–100% of results contain the excluded word.
- The web console treats OR as a word to find, so it returns 4% of what it should.
- The web console lists results alphabetically. The right manual reaches the first page for only
  12 of 24 keyword searches; in relevance order it reaches the first page for 22.
- A plain-English name for a package ("blood bank", "email", "warfarin") puts that package's
  manuals on the web console's first page for 91 of 242 such names.

Five small fixes close this:
1. Sort the web console by relevance, scoring each manual by its three best passages.
2. One query reader that obeys quotes, operators and identifiers.
3. A synonym list whose core is plain-English package names: "blood bank" finds VBECS.
4. Keyword-form test questions to judge "good enough".
5. Suggestions in the web console's search box, so a searcher sees the manuals' own words while
   typing.

Three further "smart" methods were measured and are not proposed: searching a generated summary
card per manual first, pseudo-relevance feedback, and a link-count prior. Each made the right
manual's position worse on the judged questions (§6).

None needs a new service, model or dependency. The largest changes about 40 lines of query
handling in each front door.

## Contents

1. [The contract](#1-the-contract)
2. [What is wrong today](#2-what-is-wrong-today)
3. [The five fixes](#3-the-five-fixes)
4. [Good enough: targets](#4-good-enough-targets)
5. [Order of work](#5-order-of-work)
6. [Deliberately not building](#6-deliberately-not-building)
7. [Decisions](#7-decisions)
8. [References](#8-references)
9. [Appendix A: keyword forms of the judged questions](#appendix-a-keyword-forms-of-the-judged-questions)
10. [Appendix B: plain-English package names](#appendix-b-plain-english-package-names)
11. [Appendix C: plain-English keyword searches](#appendix-c-plain-english-keyword-searches)

## 1. The contract

A person, or an agent, types keywords, not sentences. Text in double quotes must appear as typed.
AND, OR and NOT combine terms. VistA identifiers typed exactly (a patch id, a file number, a routine reference) are
found. Results come back best first. A plain-English name for a package finds that package's
manuals: "blood bank" finds VBECS, "email" finds MailMan. That translation is part of the core
contract. Beyond package names, a small synonym list may add the technical name for a plain term,
or the reverse, so a non-technical searcher still finds the manual. That is the whole contract.

## 2. What is wrong today

**Syntax.** Each row is 60 queries built from the manuals' own section headings
(`reports/mcp-review-contract.json`):

| What is typed | Web console | MCP | Contract |
|---|---|---|---|
| A quoted two-word phrase | 63% of the top 10 contain it | 63%; results identical with or without the quotes | 100% |
| `a NOT b` | 100% contain *b*, and every result must also contain the word "not" | 99% contain *b* | 0% |
| `a OR b` | 4% of the true result set, because the word "or" must appear | correct | every section with either word |
| Two bare words | all words required | either word, but 98% of the top 10 have both | both are acceptable |
| A patch id in quotes, top 5 | 90% (it keeps the whole field as one phrase) | 51% (it splits the id and drops single digits) | ≈ 100% |

A phrase search had plenty to return: a median of 74 sections contain each test phrase. Typed
operator words are also very common ordinary words, so treating them as search terms adds noise.
"and" appears in 72% of sections, "or" in 50% and "not" in 35%.

**Ranking in the web console.** The 24 judged questions were rewritten as the keywords a person would
type (Appendix A). Results are counted at document level, because that is what the web console
lists (`reports/mcp-review-fixes.json`):

| Same matches, ordered by | Right manual on page 1 | Right manual first |
|---|---|---|
| Title, A→Z (today) | 12 / 24 | 4 / 24 |
| Relevance | 22 / 24 | 17 / 24 |

No keyword search returned zero results.

**Package names.** For each of the 109 applications the reviewer drafted the plain-English names a
non-technical searcher might type (Appendix B, 242 names). Today the web console puts a manual of
that application on page 1 for 91 of them, and the MCP's top 10 holds one of its sections for 186.
The misses are names the manuals don't use: "email" (MailMan), "warfarin" (Anticoagulation
Management Tool), "means test" (Health Eligibility Center), "concussion" (Traumatic Brain Injury
registry).

## 3. The five fixes

### Fix 1: the web console orders results by relevance

**Built 2026-11-06** in vdocs-web `926e320`, as described below. `/api/candidates` now returns the
documents together with a flag saying whether the any-word fallback produced them.
- Measured on the live API against the real index.db, with today's parser (fixes 2 and 3 not yet
  built). An independent Python computation gave the same order and fallback on all 48 queries
  tried: the 24 keyword forms and the 24 original question sentences.
  - Keywords: the right manual is on page 1 for 24 of 24 (12 before) and first for 20 of 24 (4
    before).
- A request took a median of 22 ms. The slowest took 334 ms: a long query whose any-word fallback
  matched nearly every passage.

- When the search box has text, order matching documents by relevance. Keep title order when
  there is no search text (pure facet browsing).
- A document's score comes from its three best-matching passages, weighted 1, ½ and ¼. A manual
  that covers the topic in several places then ranks above one that mentions it once, and a short
  manual with one strong passage still holds its place. The operator chose this on 2026-11-06.
  - Measured against ordering by the single best passage, on top of fixes 2 and 3
    (`reports/mcp-review-ranking.json`, variant `passages_decay`):

    | | Best passage only | Three passages, 1, ½, ¼ |
    |---|---|---|
    | Keyword questions: right manual on page 1 | 22 / 24 | 24 / 24 |
    | Keyword questions: right manual first | 17 / 24 | 19 / 24 |
    | 238 plain-English package names, synonyms off: right application on page 1 | 189 | 195 |
    | Same: right application first | 107 | 120 |

  - Adding the three passages at equal weight did slightly better on first place (20 of 24) but
    pushed the HL7 Package Security Guide, the exact answer to "HL7 security keys", from 1st to
    16th, because the guide has only one matching passage. With the 1, ½, ¼ weights it is 10th,
    still on page 1.
  - The weights were chosen after seeing that loss, so they are tuned on these 24 questions. The
    238 package names, which played no part in choosing them, improve as well.
  - The any-word fallback keeps the best-passage score: summing passages that each hold one common
    word favours long manuals.
- Use FTS5's plain relevance score. The MCP's tuned column weights gave the same result here
  (MRR 0.810 vs 0.806, same page-1 and first-place counts), so no weights need copying into Go.
- When no document contains all the words, show the documents that contain any of them, best
  first, under one line saying so. It is the safety net for keywords that never meet in one
  passage, such as "exam dosing"; on the 24 keyword questions it never fired. The operator kept it
  on 2026-11-06 when sentence search was dropped.
  - Requiring every word stays the default because it keeps the list short: a median of 16
    matching documents, against 496 of 615 when any word will do.
  - Correction found while building: the web console's facet counts do not follow the search text
    and never have, so the fallback leaves them unchanged. An earlier draft said they would
    describe the wider set.
- Cost: the relevance-ordered query took 1 ms for a keyword search and 125 ms for the largest
  any-word fallback, against 69–76 ms for today's title order on the same input.
- Change: one SQL query in vdocs-web's candidate listing, plus a notice line in the UI. The
  three-passage score is computed from that same query's rows (each document's passage scores,
  sorted, the best three weighted), so it adds no query. No contract change.

### Fix 2: one query reader, the same rules in every front door

**Built 2026-11-06** in vdocs (`9bfc552`), for the MCP search tool and `vdocs ask`, in vdocs-web
(`9448e4f`), and in the Go CLI, vdocs-cli (`e9f8b62`).
- The rules and 32 cases are in `contracts/query/v1.json`; vdocs's tests run every case and check
  each expected expression is valid FTS5.
- The MCP tool description, the MCP orientation and `vdocs ask --help` state the syntax in one
  line. When the any-word fallback runs, the MCP response and `vdocs ask --json` carry a note, and
  the terminal display prints it.
- Today's SKL expansion (file 200 → NEW PERSON) now attaches to its own term, until fix 3 moves it
  into the synonym table.
- Measured on the real index.db: keyword questions keep 20 of 24 in the MCP top 10; patch ids in
  the top 5 go from 124 to 216 of 256, and `file #N` from 17 to 25 of 30, as the prototype
  predicted.
- In vdocs-web, `internal/index/query.go` runs the vendored copy of the cases. The search box
  shows the syntax as its placeholder and on hover. Search text that makes no term (a lone letter,
  punctuation) counts as no search. On the live API the keyword questions keep 24 of 24 on page 1
  (20 first), and `allergies OR vitals` returns the full union of 128 documents, against 4% of it
  before.
- In vdocs-cli, `internal/lexical/query.go` runs the vendored copy of the cases. `vdocs search`
  and `vdocs facet search` require every keyword, fall back to any keyword with a note printed
  above the hits, and state the syntax in their help. The new build is installed as the `vdocs`
  on the PATH.

The rules:
- Text in double quotes is an exact phrase. A quote left open runs to the end of the query.
- AND, OR and NOT **in capitals** are operators. In lower case they are ordinary words.
  - A leading or trailing NOT is dropped.
  - NOT excludes per passage, the unit the index stores, and the search hint says so.
- A word containing `* ^ # . $ % /` stays whole, as one phrase of its parts with single characters
  kept. DG\*5.3\*1029, #50.7, $$GET1^DIQ and TCP/IP each match as written.
- Bare words with no operator between them must all appear, in every front door (D1, revised
  2026-11-06). When no passage holds them all, the front door returns the passages holding any of
  them and says so: the web console with its notice line (fix 1), the MCP with a note in its
  response, the Go CLI with a line before its results.
- Single-character bare words are dropped, as today.
- Malformed input never produces an error. It degrades to plain words.

Measured on the prototype (top 5, MCP-style section results):
- Patch ids found: 124 → 216 of 256.
- `file #N`: 17 → 25 of 30.
- `FileMan file #N`: 15 → 23 of 30.
- MCP keyword questions with all words and the fallback: 20 of 24 in the top 10, as with any
  word, and first place 12 → 13. The fallback never fired. Patch ids and file numbers are the same
  under both joins (`reports/mcp-review-all-words.json`).

Agreement: the rules are about 40 lines in each language.
- Disagreement between the front doors is how they diverged today: AND in the web console, OR in
  the MCP, no expansion in the Go CLI.
- The list of query → expected-match cases is `contracts/query/v1.json`, beside the read
  contract. vdocs-web and vdocs-cli copy it by hand, the way vdocs-web copies the read contract,
  and run every case.

The MCP's tool description and orientation each gain one line stating the syntax, and the web
search box gets a one-line hint. Those descriptions are how people and agents learn the syntax.

### Fix 3: synonyms, with plain-English package names at the core

The operator set this on 2026-11-06: keyword search must translate the plain-English name of a
package into its VistA package name and namespace, so "blood bank" finds VBECS. It is a core
capability, complete for every application, not an extra grown one question at a time.

- **One table of term → alternatives in `index.db`** (it does not exist yet), written by the
  producer from three sources:
  - **Plain-English package names (core).** Every application in the corpus gets the names a
    non-technical searcher would type. Each name expands to that application's package name, code
    and namespaces, which the producer already holds: the documents' application name, code and
    namespace columns, and the package master registry. Two Kernel parts that people name on their
    own get entries of their own: TaskMan ("background jobs") and KIDS ("patches").
    - The names are written once, for all 109 applications, in one registry file with one entry per
      application. That file does not exist yet.
    - The operator approved the reviewer's drafts in Appendix B unchanged on 2026-11-06.
  - **Generated, no curation:** application codes, namespaces and product abbreviations ↔ their
    names (307 pairs for 109 applications), plus today's one expansion (file 200 → NEW PERSON),
    which moves here so there is a single mechanism. Searching by code already finds the
    application's documents for 101 of 109 applications; with these pairs, 108.
  - **Other terms** (routines, files, concepts): hand-written, and an entry goes in only together
    with a judged query it fixes (fix 4).
- **At query time** (every front door), an unquoted word or phrase that matches a key gets its
  alternatives added as OR'd phrases. "blood bank ISBT" becomes ("blood bank" OR "VistA Blood
  Establishment Computer Software" OR "VBECS") AND "ISBT".
  - Text in double quotes is never expanded. Quoting is how to search for exactly what was typed.
  - A code expands only when typed in capitals, because many short codes are also ordinary words
    (AR, EN, MD, ART, LAB).
  - Capital AND, OR and NOT are always operators, and an operator word is never added as an
    alternative. The Order Entry application, whose code is OR, is found by its name or by CPRS.
- **A plain-English name must name a package, not a shared concept.**
  - The first draft gave Kernel "security keys", "sign on" and "menus", and gave FileMan "data
    dictionary". Every package's manuals use those words.
  - Expanding them to one package pushed other packages' answers down. The HL7 security-keys
    question fell from first to tenth in the web console and out of the MCP's top 15.
  - With those four removed, all 24 judged questions score exactly as before. Such words belong
    with the other terms, added only with a judged question.
- **Measured** on the 242 drafted names (`reports/mcp-review-package-names.json`). "Found" means a
  manual of that application is in the top 10:

  | Package name typed in | Found |
  |---|---|
  | Web console today (title order) | 91 / 242 |
  | Web console, relevance order (fix 1) | 193 / 242 |
  | Web console, relevance order and package names | 242 / 242 |
  | MCP today | 186 / 242 |
  | MCP with package names | 242 / 242 |

  - 242 of 242 is largely by construction, since each expansion names its application. What the
    table buys is the 49 names whose manuals don't use the searcher's word. In relevance order,
    "email" moves MailMan from 11th to 1st, "warfarin" moves the Anticoagulation Management Tool
    from 23rd to 1st, and "concussion" goes from not found to the Traumatic Brain Injury registry
    first.
  - "blood bank" already finds a VBECS manual first in relevance order, because the VBECS manuals
    say "blood bank". Today's title order puts the first VBECS manual 60th. The table makes the
    link hold whatever wording the manuals use.
  - Cost: the web console matches more documents, a median of 37 → 61 and at most 384 → 458, so
    facet counts grow.
  - No loss elsewhere: with the whole table on, the 24 judged questions (web console and MCP)
    and the patch-id and file-number checks score exactly the same.
- **Contract:** read contract 1.8 adds the table. vdocs-web's vendored contract copy gains it.

### Fix 4: keyword-form test questions

**Built 2026-11-06** in vdocs (`bc0188a`), as described below.
- Every question in `registries/golden-queries.yaml` carries its keyword form (`keywords:`), and
  the harness (`scripts/baseline_golden.py`) searches that form. It refuses a question without one.
  The weight sweep and the facet evaluation search the keyword forms too.
- The six plain-English searches are in the key as axis `plain-english`: 30 judged questions in
  all, plus the unjudged redundancy probe.
- The new baseline, on the real index.db (`reports/fix4-golden-keywords.json`, corpus
  `5b118189…`): the 24 keyword forms score nDCG@10 0.524 and MRR 0.609, with 20 in the top 10 and
  13 first. The six plain-English searches have 1 in the top 10 (nDCG@10 0.029). All 30 together:
  nDCG@10 0.425.
- The earlier baseline of record, nDCG@10 0.655, graded the sentences under the any-word reader
  that fix 2 replaced. It is not comparable and is retired. The same sentences under today's
  search score 0.451, but sentences are no longer graded.

- Each of the 24 judged questions gains its keyword form. The drafts are in Appendix A, written by
  the reviewer, who knew the answers; the operator approved them unchanged on 2026-11-06 (D3).
- Add six plain-English keyword searches of the kind a non-technical searcher types, judged the
  same way: reviewer drafts with their answers in Appendix C; the operator approved them unchanged
  on 2026-11-06.
  Today the right manual reaches the web console's page 1 for 3 of the 6, and the MCP's top 15
  for 1. They
  test the words the manuals don't use ("change password" where the manuals say verify code), so
  they are what fix 3's synonyms must fix.
- The golden key's question sentences stay as descriptions of what each question asks. The
  keyword form is what the harness grades, since sentence search was dropped.
- Keep the identifier probes in `scripts/mcp_review/fixes.py` (256 patch ids, 30 file numbers) as
  the identifier check.
- The syntax rules are checked by fix 2's shared cases, not by judged questions: a phrase either
  appears in a result or it does not.

### Fix 5: suggestions in the web console's search box

The operator added this on 2026-11-06 regardless of any measured gain. Suggestions show a
non-technical searcher the words the manuals use before they search. They change what people type,
not how results are ranked, so the judged questions cannot score them.

- **What is offered** as the person types, from two characters, at most 8. Each typed word must be
  the start of a word in the suggestion, ignoring case.
  - First, up to 3 **packages**: package names, codes, product names and fix 3's plain-English
    names, each showing what it stands for. "blood b" offers "Blood Bank → Laboratory (LR); VistA
    Blood Establishment Computer Software (VBECS)". "email" offers "email → MailMan (XM)". "taskm"
    offers "TaskMan" and "background jobs → TaskMan".
  - Then **headings** from the latest manuals, those used by the most documents first. "cancel
    ord" offers "Accept Orders: Cancel a Pending Order", "Canceling Lab Orders" and "Cancelling
    Orders".
- **Choosing one** puts its words in the box and runs the search. A package name goes in as typed,
  and fix 3 expands it. A heading goes in as a quoted phrase, so it finds that heading's sections and
  shows the person the phrase syntax.
- **Source:** vdocs-web builds the list when it starts, from index.db. Package names, codes and
  products come from the documents, headings from the latest documents' sections, and
  plain-English names from fix 3's synonym table. The read contract needs nothing beyond fix 3,
  because vdocs-web already reads the documents and sections views.
- **Size and speed** (`reports/mcp-review-suggest.json`): 549 package entries and 30,506 distinct
  headings, after removing leading numbers and markdown marks. Scanning the whole list took 34 ms
  per keystroke in the Python prototype, so no special index is needed at this size. Some headings
  stay noisy, such as a routine's first line; they are shown as the manuals have them.
- **Change:** an in-memory list and one small request in vdocs-web's API, which does not exist yet,
  plus a drop-down under the search box. It is built after fix 3 so that plain-English names are in
  from the start.
- **Check:** vdocs-web's tests confirm that every package name and plain-English name is offered
  once its first word is typed, and that choosing a heading searches for it as a phrase.

## 4. Good enough: targets

| Measure | Today | Prototype | Target |
|---|---|---|---|
| Web: right manual on page 1, keyword questions | 12 / 24 | 24 / 24 | ≥ 24 / 24 |
| Web: right manual first, keyword questions | 4 / 24 | 19 / 24 | ≥ 19 / 24 |
| Quoted phrase present in every result | 63% | by construction | 100% |
| Excluded word absent (per passage) | 0–1% of results | by construction | 100% |
| Web `a OR b`: share of true result set | 4% | by construction | 100% |
| Patch id in top 5 | 124 / 256 | 216 / 256 | ≥ 216 / 256 |
| `file #N` in top 5 | 17 / 30 | 25 / 30 | ≥ 25 / 30 |
| MCP keyword questions, top 10 | 20 / 24 | 20 / 24 | no loss |
| Application found by its code, top 10 | 101 / 109 | 108 / 109 | ≥ 108 / 109 |
| Plain-English package name: its manuals on web page 1 | 91 / 242 | 242 / 242 | every name in the edited list |
| Plain-English package name: its sections in the MCP top 10 | 186 / 242 | 242 / 242 | every name in the edited list |
| Judged questions and identifier checks, synonym table on vs off | — | identical | no loss |
| Plain-English keyword searches (Appendix C): right manual on web page 1 | 3 / 6 (after fix 1) | — | 6 / 6 |
| Plain-English keyword searches: a judged section in the MCP top 10 | 1 / 6 | — | 6 / 6 |
| Search-box suggestions, time per keystroke | none | 34 ms (Python, full scan) | under 50 ms |

## 5. Order of work

Each step: write the test first, then build, then run `make check`, measure against §4, commit.

1. **Fix 4 and Appendix B:** the keyword forms (Appendix A) and the plain-English package names
   (Appendix B) and the six plain-English keyword searches (Appendix C) were approved unchanged on
   2026-11-06. The golden harness grades the keyword forms (built 2026-11-06, `bc0188a`).
2. **Fix 1 (built 2026-11-06, vdocs-web `926e320`):** relevance order and the any-word fallback
   in vdocs-web. This is the largest visible gain and needs no contract change.
3. **Fix 2 (built 2026-11-06):** the reader in the MCP and `vdocs ask` (`9bfc552`), vdocs-web
   (`9448e4f`) and the Go CLI (`e9f8b62`, D2), with the shared cases.
4. **Fix 3, straight after fix 2:** the producer writes the synonym table (contract 1.8), and every
   reader applies it. The package names are complete for every application in the first release.
   Other hand-written terms are added one judged question at a time.
5. **Fix 5:** search-box suggestions in vdocs-web, reading the synonym table from step 4.

## 6. Deliberately not building

- **Vectors, embeddings or any semantic layer.** Ruled out 2026-06-08.
- **Opening a result at its best-matching passage.** That passage was a judged answer for only 13
  of 24 questions, a coin flip. The document opens as it does today.
- **The old 696-entry acronym list.** It was built on 2026-06-08 and switched off after it made
  results worse.
- **A synonym approval workflow, entity resolution or automatic synonym mining.** The synonym-layer
  ruling of 2026-08-04 stands for terms: they are added one judged question at a time. Package
  names are the exception the operator set on 2026-11-06. They are a bounded list, one entry per
  application, written once and checked by the package-name measurement.
- **Stemming, stopword lists, prefix matching, per-document caps.** All were measured on 2026-11-06
  as neutral or worse.
- **Full-sentence search.** Dropped by the operator on 2026-11-06: the search boxes take keywords.
  A sentence still gets results, through the any-word fallback, but sentences are not measured or
  tuned for.
- **Column-weight tuning for the web console.** Plain relevance matched the weighted version.
- **An any-word default in the web console.** It would make the facet counts meaningless.
- **A summary card per manual, searched first or blended in** (`reports/mcp-review-tiers.json`).
  - The card was generated, not hand-written. It held the manual's title, package names,
    plain-English names, document type, Monograph purpose, top two heading levels, the first 80
    words of its introduction, and its 10 most distinctive words.
  - Listing the manuals whose card matches first, then the rest, put the right manual first for 14
    of 24 keyword questions instead of 17.
  - Blending the card into the ranking was also worse (by reciprocal-rank fusion, which merges two
    orderings by position). First place fell from 17 to 16, and the MCP was worse too.
  - The card does help a query that names a package: first place for 107 → 143 of 238 names, with
    synonyms off. Fix 3 already puts every package name on page 1.
  - The cause: a card says what a whole manual is about, while the questions ask for a task inside
    one. "NEW PERSON file" moved the right manual from 3rd to 13th, behind manuals about the file in
    general.
  - Hand-written abstracts fall with it.
- **Pseudo-relevance feedback.** This adds the top results' shared distinctive words and searches
  again. It was worse everywhere.
  - MCP keyword questions in the top 10: 20 → 14.
  - In the web console it was tried only where the any-word fallback fires, which keyword
    searches almost never do; there it moved first place from 20 to 11.
  - The added words come from the largest manuals and pull results off topic. A fallback search
    also took three times as long (104 → 327 ms).
- **A link-count prior.** index.db's 29,593 document-to-document links join documents that mention
  the same significant entity; they are not citations. As a mild weight it moved one keyword
  question onto page 1 and cost first places in the MCP. A stronger weight was worse. The effect is too small and too unstable to build.

## 7. Decisions

All three were taken by the operator on 2026-11-06, as recommended. D1 was revised the same day.

**Operator direction, 2026-11-06.** Translating plain-English package names into the VistA package
name and namespace is a core capability of keyword search (fix 3). The operator approved the drafts
in Appendix B unchanged on 2026-11-06. Search-box suggestions (fix 5) are in scope regardless of measured gain.

- **D1. The default for bare words.** First decided: any word, ranked, in the MCP, because agents
  send sentences. **Revised 2026-11-06, when sentence search was dropped: all words in every front
  door, falling back to any word, with a notice, when no passage holds them all.** On the 24
  keyword questions the MCP keeps 20 of 24 in the top 10 and gains a first place (12 → 13);
  identifier lookups are unchanged; the fallback never fired.
- **D2. Whether the Go CLI (vdocs-cli) is in scope.** Recommended: yes, same reader, same shared
  cases. It is a port of the MCP engine, and leaving it out keeps a third set of rules alive. The
  alternative is to stop presenting it as an agent path. **Decided: in scope.**
- **D3. Who writes the keyword wording of the test questions.** Recommended: the operator edits
  the reviewer's drafts (Appendix A), because the drafts were written by someone who knew the
  answers. **Decided: the operator edits them.** The operator approved them unchanged on
  2026-11-06.

## 8. References

- [`vdocs-mcp-interface-design.md`](vdocs-mcp-interface-design.md): the wider machine-interface
  review. Its section-text tool, honest filter errors, stale figures and response size remain open
  there.
- [`vdocs-quality-synonym-layer/`](vdocs-quality-synonym-layer/): the 2026-08-04 ruling against a
  curated synonym queue.
- [`offline-lexical-search-plan.md`](offline-lexical-search-plan.md): the 2026-06-08 direction
  reset (lexical-first, no vectors).
- SQLite FTS5 query syntax (phrases, AND/OR/NOT, bm25): <https://www.sqlite.org/fts5.html>.
- `scripts/mcp_review/contract.py` → `reports/mcp-review-contract.json`;
  `scripts/mcp_review/fixes.py` → `reports/mcp-review-fixes.json`;
  `scripts/mcp_review/package_names.py` → `reports/mcp-review-package-names.json`;
  `scripts/mcp_review/ranking.py`, `tiers.py` and `suggest.py` → `reports/mcp-review-ranking.json`,
  `reports/mcp-review-tiers.json` and `reports/mcp-review-suggest.json`. Re-run from the repo root
  with
  `.venv/bin/python scripts/mcp_review/<name>.py > reports/mcp-review-<name>.json`.

## Appendix A: keyword forms of the judged questions

Reviewer drafts, approved by the operator unchanged on 2026-11-06 (D3).

| Judged question | Keyword form |
|---|---|
| kids-install-build | KIDS install build |
| pharmacy-api-dispense | pharmacy API dispense |
| fileman-add-field | add field data dictionary |
| rpc-broker-client-call | RPC Broker client call |
| mailman-decnet-transmission | DECnet transmission script |
| radiology-cancel-exam | cancel radiology exam |
| pharmacy-release-signed-order | release digitally signed order |
| tiu-unsigned-notes | unsigned progress notes |
| vpr-allergy-data | VPR allergy |
| lab-file60-audit | audit laboratory test file |
| cprs-enter-immunization | enter immunization CPRS |
| vbecs-accept-order | VBECS accept order |
| hl7-security-keys | HL7 security keys |
| fileman-file-200-new-person | NEW PERSON file |
| fileman-import-host-file | import host file |
| fileman-input-transform-definition | "input transform" |
| fileman-blddialog-icr-number | BLD^DIALOG ICR |
| quasar-package-wide-variables | QUASAR package wide variables |
| hl7-table-0136-values | HL7 table 0136 |
| kids-backup-transport-global | backup "transport global" |
| hl7-start-tcpip-link | start TCP/IP logical link |
| fileman-file-access-security | file access security |
| vista-signon-credentials | sign on access code verify code |
| fileman-finder-api | FIND^DIC finder |
| taskman-monitor | monitor TaskMan |

The golden key holds 25 questions, 24 of them judged. `pharmacy-api-dispense` has no judged
answers yet, so its keyword form is not counted.

## Appendix B: plain-English package names

Reviewer drafts, approved by the operator unchanged on 2026-11-06. Each row is one application in
the latest corpus.
- The package name, code and namespaces come from data the producer already holds. They are what
  each plain-English name expands to.
- The plain-English names were written by hand from each application's own name and its Monograph
  purpose (`registries/inventory/app-profiles.yaml`).
- Where VistA's PACKAGE file gives a different namespace from the documents', the operator can add
  it. For VBECS, the PACKAGE file says VBEC, but the manuals print VBEC in only 3 passages against
  1,216 for VBECS.
- Order Entry's code, OR, is left out because OR is an operator.

| Application | Package name | Code and namespaces | Plain-English names (draft) |
|---|---|---|---|
| ACKQ | Quality Audiology and Speech Analysis and Reporting | ACKQ | audiology, speech pathology |
| ACR | Ambulatory Care Reporting | ACR, SD | outpatient encounter reporting |
| ADT | Admission Discharge Transfer | ADT, DG | admissions, discharges, bed control |
| AMT | Anticoagulation Management Tool | AMT | blood thinners, warfarin, anticoagulation clinic |
| ANRV | Visual Impairment Service Team | ANRV | blind rehabilitation, low vision |
| AR/WS | Automatic Replenish / Ward Stock | AR/WS, PSGW | ward stock, restocking |
| ASCD | Automated Service Connected Designation | ASCD | service connection, disability rating |
| ASU | Authorization Subscription Utility | ASU, USR | signing permissions, cosignature |
| CPRS | Computerized Patient Record System | CPRS | electronic health record, patient chart, medical record |
| CRHD | Shift Handoff Tool | CRHD | shift change, handoff |
| DGBT | Beneficiary Travel | DGBT | travel pay, mileage reimbursement |
| DGJ | Incomplete Records Tracking | DGJ | incomplete records, chart deficiencies |
| DI | FileMan | DI | database |
| DVBA | Automated Medical Information Exchange | DVBA | disability exams, compensation and pension |
| EC | Event Capture System | EC | workload capture, procedure counts |
| ECME | Electronic Claims Management Engine | ECME, BPS | pharmacy claims, prescription insurance claims |
| ECX | Decision Support System Extracts | ECX | cost accounting, managerial cost accounting |
| EDIS | Emergency Department Integration Software | EDIS | emergency department, emergency room, tracking board |
| EFR | Embedded Fragments | EFR | embedded fragments, shrapnel |
| EN | Engineering | EN | equipment maintenance, work orders, biomedical engineering |
| EPI | Emerging Pathogens Initiative | EPI | infectious disease reporting, disease surveillance |
| FB | Fee Basis | FB | community care payments, non-VA care, fee for service |
| FFP | Fugitive Felon Program | FFP | fugitive felons, outstanding warrants |
| FH | Nutrition and Food Service | FH | dietetics, diet orders, meals |
| FIM | Functional Independence Measurement | FIM | rehabilitation assessment, functional status |
| GEN | Generic Code Sheet | GEN | code sheets |
| GMPL | Problem List | GMPL | patient problems, diagnosis list |
| GMR | Intake and Output | GMR | fluid intake, fluid balance |
| GMRA | Adverse Reaction Tracking | GMRA | allergies, drug allergies, adverse drug reactions |
| GMRC | Consult/Request Tracking | GMRC | consults, referrals |
| GMRV | Vitals/Measurements | GMRV | vital signs, blood pressure, pulse |
| GMTS | Health Summary | GMTS | patient summary report |
| HBPC | Home Based Primary Care | HBPC | home care, home health |
| HL7 | HL7 | HL7 | interfaces, interface messages |
| IB | Integrated Billing | IB | billing, insurance billing, copayments |
| IBD | Automated Information Collection System | IBD | encounter forms, scannable forms |
| IVMB | Health Eligibility Center | IVMB | means test, income verification |
| KMPD | Capacity Management Tools | KMPD | capacity planning |
| KMPR | Resource Usage Monitor | KMPR | resource usage |
| KMPS | Statistical Analysis of Global Growth | KMPS | database growth, global growth |
| KMPV | VistA System Monitor | KMPV | system monitoring, performance metrics |
| LA | Universal Interface | LA | lab instruments, instrument interface |
| LEDI | Electronic Data Interchange | LEDI, LA | reference lab, send-out lab tests |
| LR | Laboratory | LR, LA | lab, lab tests, lab results |
| MAG | VistA Imaging System | MAG | medical images, scanned documents, image capture |
| MC | Medicine | MC | cardiology, EKG, endoscopy |
| MD | Clinical Procedures | MD | medical devices, device interface, dialysis |
| MMRS | Methicillin Resistant Staph Aureus | MMRS | staph infection, infection control |
| MPIF | Master Patient Index | MPIF | duplicate patients, patient identity, ICN |
| NCR | National Clozapine Coordination | NCR | clozapine monitoring |
| NUPA | Patient Assessment Documentation Package | NUPA | nursing assessments, nursing documentation |
| NUR | Nursing | NUR | nurses, nursing staff |
| ONC | Oncology | ONC | cancer registry, tumor registry |
| OOPS | Automated Safety Incident Surveillance Tracking System | OOPS | employee injuries, workplace accidents |
| OR | Order Entry / CPRS |  | orders, ordering |
| PAIT | Patient Appointment Info. Transmission | PAIT | appointment extract |
| PCMM | Primary Care Management Module | PCMM, SD | primary care teams, PACT, patient panels |
| POC | Point of Care | POC, LA | point of care testing, bedside testing, glucose meters |
| PRC | IFCAP | PRC | purchasing, procurement, purchase orders |
| PRCA | Accounts Receivable | PRCA | patient debts, collections, patient bills |
| PRCN | Equipment / Turn-In Request | PRCN | equipment requests, equipment turn-in |
| PREA | Advanced Medication Platform | PREA | pharmacist medication profile, medication review |
| PRF | Patient Record Flags | PRF, DG | behavioral flags, flagged patients |
| PRPF | Integrated Patient Funds | PRPF | patient trust accounts, personal funds |
| PRS | Personnel and Accounting Integrated Data | PRS | payroll, timekeeping, time and attendance |
| PSA | Drug Accountability | PSA | drug inventory, pharmacy inventory |
| PSB | Bar Code Medication Administration | PSB | bar code scanning, medication administration, barcode |
| PSD | Controlled Substances | PSD | narcotics, controlled drugs |
| PSJ | Inpatient Medications | PSJ | inpatient pharmacy, unit dose, IV medications |
| PSN | National Drug File | PSN | drug file, drug database, drug classes |
| PSO | Outpatient Pharmacy | PSO | prescriptions, refills |
| PSS | Data Management | PSS | pharmacy setup, drug setup |
| PSU | Benefits Management | PSU | drug usage reports, pharmacy benefits |
| PSX | Consolidated Mail Outpatient Pharmacy | PSX | mail order pharmacy, mailed prescriptions |
| PX | Patient Care Encounter | PX | encounters, visits, workload |
| PXRM | Clinical Reminders | PXRM | reminders, preventive care reminders |
| QAC | Patient Advocate Tracking System | QAC | patient complaints, compliments |
| QAM | Clinical Monitoring System | QAM | quality monitoring |
| QAO | Occurrence Screen | QAO | adverse event screening, quality review |
| QAP | Survey Generator | QAP | surveys, questionnaires |
| QMIM | Quality Management Integration Module | QMIM | credentialing, incident reporting |
| RA | Radiology/Nuclear Medicine | RA | x-ray, imaging exams, radiology exams |
| RMDS | RAI/MDS | RMDS | nursing home assessment, long-term care assessment, minimum data set |
| RMPR | Prosthetics | RMPR | artificial limbs, wheelchairs, home oxygen |
| ROEV | Military Eye Vision Injury | ROEV | eye injuries, vision injuries |
| ROR | Clinical Case | ROR | HIV registry, hepatitis C registry, case registry |
| RT | Record Tracking | RT | paper records, chart tracking, record room |
| SD | Scheduling | SD | appointments, clinic schedules |
| SPN | Spinal Cord Injury and Disorders Outcomes | SPN | spinal cord injury |
| SQLI | SQL Interface | SQLI, DI | SQL, ODBC |
| SR | Surgery | SR | operating room, surgical cases, anesthesia |
| SRA | Surgery Risk Assessment | SRA | surgical outcomes, surgical quality |
| TBI | Traumatic Brain Injury | TBI | brain injury, concussion |
| TIU | Text Integration Utility | TIU | progress notes, clinical notes, discharge summaries |
| VALM | List Manager | VALM | list screens |
| VAQ | Patient Data Exchange | VAQ | patient record exchange, other facility records |
| VBECS | VistA Blood Establishment Computer Software | VBECS | blood bank, blood transfusion, blood products |
| VDEF | VistA Data Extraction Framework | VDEF | HL7 message extraction |
| VPR | Virtual Patient Record | VPR | patient data extract |
| WII | Wounded Ill and Injured Warriors | WII | wounded warriors, injured service members |
| WV | Womens Health | WV | mammogram, pap smear, maternity |
| XM | MailMan | XM | email, mail messages, mail groups |
| XOBV | VistALink | XOBV | Java connector, J2EE |
| XQOR | Kernel Unwinder | XQOR | protocol menus, protocols |
| XT | Kernel Toolkit | XT | developer utilities, routine tools |
| XU | Kernel | XU | user accounts |
| XWB | Remote Procedure Call Broker | XWB | remote procedure calls, client server |
| YS | Mental Health | YS | psychological tests, mental health assessments, crisis line |
| ZSLOT | SlotMaster | ZSLOT | quick login |
| XU (part) | TaskMan | TaskMan | background jobs, scheduled tasks |
| XU (part) | Kernel Installation and Distribution System | KIDS, XPD | patches, software installation |

## Appendix C: plain-English keyword searches

Reviewer drafts for fix 4, approved by the operator unchanged on 2026-11-06. Each uses a word the
manuals avoid: password for verify code, jobs for tasks, printer for device, email for mail
message.
- Every judged section was checked present, latest and searchable in index.db. Each was graded by
  reading its passage text: 3 ideal, 2 highly relevant, 1 related. Notes on what was left out are
  in `scripts/mcp_review/plain_questions.py`.
- "Today" is the web console as built by fix 1 (document rank of the first manual holding a judged
  section, out of the documents matched), and the MCP as it is now (rank of the first judged
  section in its top 15). Source: `reports/mcp-review-plain-questions.json`.
- Next, they join `registries/golden-queries.yaml` with their keyword forms, and fix 3's
  hand-written synonyms are added one search at a time until each passes.

| Keyword search | What it asks | Judged answers (grade) | Today, web | Today, MCP |
|---|---|---|---|---|
| **change password** | How a user changes their VistA password; the manuals call it the verify code. | `XU/krn_8_0_sm_signon_security_ug/defining-a-strong-verify-code` (3); `XWB/xwb_1_1_sm_r/change-vista-verify-code-component` (2); `PRC/ifcp5_1ldqt_user_manual/changing-your-verify-code` (2); `XU/krn_8_0_sm_signon_security_ug/lifetime-of-verify-code` (1); `EDIS/edp_um/changing-your-verify-code` (1) | 7 of 39 | not in top 15 |
| **create user account** | How a system administrator adds a new VistA user (Kernel, NEW PERSON file). | `XU/krn_8_0_sm_signon_security_ug/adding-new-users` (3); `XU/krn_8_0_sm_signon_security_ug/add-a-new-user-to-the-system-option` (3); `XU/krn_8_0_sm_signon_security_ug/edit-an-existing-user-option` (1) | 28 of 122 | not in top 15 |
| **background jobs** | What runs work in the background in VistA: TaskMan, which the manuals call background tasks. | `XU/krn_8_0_sm_taskman_ug/introduction` (3); `XU/krn_8_0_sm_taskman_ug/taskman-user-interface` (3); `XU/krn_8_0_sm_taskman_ug/summary` (2); `XU/krn_8_0_dg_taskman_ug/overview` (2) | 4 of 57 | not in top 15 |
| **set up printer** | How a printer is defined for VistA: an entry in Kernel's DEVICE (#3.5) file with a terminal type. | `XU/krn_8_0_sm_device_handler_ug/device-35-file` (3); `XU/krn_8_0_sm_device_handler_ug/terminal-type-32-file` (2); `XU/krn_8_0_sm_device_handler_ug/printing-to-devices` (1) | 18 of 125 | not in top 15 |
| **enter patient allergies** | How a clinician records a patient's allergy: Adverse Reaction Tracking (GMRA), or CPRS's Allergies pane. | `GMRA/gmra_4_0_um/enteredit-patient-reaction-data` (3); `GMRA/gmra_4_0_um/enteredit-patient-reaction-data-1` (3); `CPRS/cprsguium/entering-allergies` (3); `CPRS/cprsguium/entering-new-allergies` (2); `GMRA/gmra_4_0_um/entering-allergies-from-the-cover-sheet` (2) | 1 of 50 | 4 |
| **send email** | How a user sends a message in VistA: MailMan's Send a Message option. | `XM/xm_8_0_userguide/smlsend-a-message-option` (3); `XM/xm_8_0_getstartguide/sending-mail` (3); `XM/xm_8_0_userguide/sending-mail` (2); `XM/xm_8_0_netrefguide/sending-network-messages` (1) | 58 of 64 | not in top 15 |
