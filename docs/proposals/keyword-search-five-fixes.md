# Good-enough keyword search — five small fixes

**Status: PROPOSED · 2026-11-06 · decisions D1–D3 taken 2026-11-06 as recommended · amended
2026-11-06: plain-English package names made a core part of fix 3, and search-box suggestions
added as fix 5, both at the operator's direction · nothing built.** Consumer: vdocs-web (fixes 1–3
and 5). Producer and MCP: vdocs (fixes 2–4). Read contract 1.7 → 1.8, additive, for fix 3 only.
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
were ruled out on 2026-06-08. Measured against that contract, every front door falls short:
- Quotes do nothing: only 63% of results contain the quoted phrase.
- NOT does the opposite: 99–100% of results contain the excluded word.
- The web console treats OR as a word to find, so it returns 4% of what it should.
- The web console lists results alphabetically. The right manual reaches the first page for only
  12 of 24 keyword searches; in relevance order it reaches the first page for 22.
- A plain-English name for a package ("blood bank", "email", "warfarin") puts that package's
  manuals on the web console's first page for 91 of 242 such names.

Five small fixes close this:
1. Sort the web console by relevance.
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

## 1. The contract

A person, or an agent, types keywords. Text in double quotes must appear as typed. AND, OR and NOT
combine terms. VistA identifiers typed exactly (a patch id, a file number, a routine reference) are
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

No keyword search returned zero results. The web console's empty pages come from full sentences:
requiring every word of "How do I load and install a KIDS distribution build?" leaves nothing.

**Package names.** For each of the 109 applications the reviewer drafted the plain-English names a
non-technical searcher might type (Appendix B, 242 names). Today the web console puts a manual of
that application on page 1 for 91 of them, and the MCP's top 10 holds one of its sections for 186.
The misses are names the manuals don't use: "email" (MailMan), "warfarin" (Anticoagulation
Management Tool), "means test" (Health Eligibility Center), "concussion" (Traumatic Brain Injury
registry).

## 3. The five fixes

### Fix 1: the web console orders results by relevance

- When the search box has text, order matching documents by their best passage's relevance
  score. Keep title order when there is no search text (pure facet browsing).
- Use FTS5's plain relevance score. The MCP's tuned column weights gave the same result here
  (MRR 0.810 vs 0.806, same page-1 and first-place counts), so no weights need copying into Go.
- When no document contains all the words, show the documents that contain any of them, best
  first, under one line saying so. On keyword searches this never happened (0 of 24). For full
  sentences it lifts the right manual onto page 1 from 5 of 24 to 23 of 24.
  - The facet counts then describe that wider set, about 500 documents.
  - Requiring every word stays the default because it keeps the facets meaningful: a median of 16
    matching documents, against 496 of 615 when any word will do.
- Cost: the relevance-ordered query took 1 ms for a keyword search and 125 ms for the largest
  any-word fallback, against 69–76 ms for today's title order on the same input.
- Change: one SQL query in vdocs-web's candidate listing, plus a notice line in the UI. No
  contract change.

### Fix 2: one query reader, the same rules in every front door

The rules:
- Text in double quotes is an exact phrase. A quote left open runs to the end of the query.
- AND, OR and NOT **in capitals** are operators. In lower case they are ordinary words.
  - A leading or trailing NOT is dropped.
  - NOT excludes per passage, the unit the index stores, and the search hint says so.
- A word containing `* ^ # . $ % /` stays whole, as one phrase of its parts with single characters
  kept. DG\*5.3\*1029, #50.7, $$GET1^DIQ and TCP/IP each match as written.
- Bare words with no operator between them are joined by the front door's default: all words in
  the web console, any word in the MCP (D1, decided).
- Single-character bare words are dropped, as today.
- Malformed input never produces an error. It degrades to plain words.

Measured on the prototype (top 5, MCP-style section results):
- Patch ids found: 124 → 216 of 256.
- `file #N`: 17 → 25 of 30.
- `FileMan file #N`: 15 → 23 of 30.
- Keyword questions: 20 of 24 in the top 10 either way.
- Full-sentence questions with the any-word default: 23 of 24, unchanged.

Agreement: the rules are about 40 lines in each language.
- Disagreement between the front doors is how they diverged today: AND in the web console, OR in
  the MCP, no expansion in the Go CLI.
- A short list of query → expected-match cases, kept beside the read contract in vdocs, would be
  copied into vdocs-web the same way the contract is, and both test suites would run every case.
  This list does not exist yet.

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
    - The operator edits the reviewer's drafts in Appendix B, the same arrangement as D3.
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
  - No loss elsewhere: with the whole table on, the 24 judged questions (keywords and sentences,
    web console and MCP) and the patch-id and file-number checks score exactly the same.
- **Contract:** read contract 1.8 adds the table. vdocs-web's vendored contract copy gains it.

### Fix 4: keyword-form test questions

- Each of the 24 judged questions gains its keyword form. The drafts are in Appendix A, written by
  the reviewer, who knew the answers; the operator edits them (D3, decided).
- Add about six plain-English questions of the kind a non-technical searcher types, judged the same
  way. These are what the hand-written synonyms must fix. The shape is "user accounts" (the
  manuals say NEW PERSON) or "background jobs" (TaskMan). These two examples are illustrations,
  not judged entries.
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
| Web: right manual on page 1, keyword questions | 12 / 24 | 22 / 24 | ≥ 22 / 24 |
| Web: right manual first, keyword questions | 4 / 24 | 17 / 24 | ≥ 17 / 24 |
| Web: right manual on page 1, full sentences | 5 / 24 | 23 / 24 | ≥ 22 / 24 |
| Quoted phrase present in every result | 63% | by construction | 100% |
| Excluded word absent (per passage) | 0–1% of results | by construction | 100% |
| Web `a OR b`: share of true result set | 4% | by construction | 100% |
| Patch id in top 5 | 124 / 256 | 216 / 256 | ≥ 216 / 256 |
| `file #N` in top 5 | 17 / 30 | 25 / 30 | ≥ 25 / 30 |
| MCP keyword questions, top 10 | 20 / 24 | 20 / 24 | no loss |
| MCP full sentences, top 10 | 23 / 24 | 23 / 24 | no loss |
| Application found by its code, top 10 | 101 / 109 | 108 / 109 | ≥ 108 / 109 |
| Plain-English package name: its manuals on web page 1 | 91 / 242 | 242 / 242 | every name in the edited list |
| Plain-English package name: its sections in the MCP top 10 | 186 / 242 | 242 / 242 | every name in the edited list |
| Judged questions and identifier checks, synonym table on vs off | — | identical | no loss |
| Each plain-English question in the key | not yet judged | — | right manual on page 1 |
| Search-box suggestions, time per keystroke | none | 34 ms (Python, full scan) | under 50 ms |

## 5. Order of work

Each step: write the test first, then build, then run `make check`, measure against §4, commit.

1. **Fix 4 and Appendix B:** the operator edits the keyword forms, supplies or approves the
   plain-English questions, and edits the plain-English package names. The golden harness grades
   the keyword form alongside the question.
2. **Fix 1:** relevance order and the any-word fallback in vdocs-web. This is the largest visible
   gain and needs no contract change.
3. **Fix 2:** the reader in vdocs-web, the MCP and the Go CLI (D2), with the shared cases.
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
- **Column-weight tuning for the web console.** Plain relevance matched the weighted version.
- **An any-word default in the web console.** It would make the facet counts meaningless.
- **A summary card per manual, searched first or blended in** (`reports/mcp-review-tiers.json`).
  - The card was generated, not hand-written. It held the manual's title, package names,
    plain-English names, document type, Monograph purpose, top two heading levels, the first 80
    words of its introduction, and its 10 most distinctive words.
  - Listing the manuals whose card matches first, then the rest, put the right manual first for 14
    of 24 keyword questions instead of 17. One sentence question fell from 1st to 369th.
  - Blending the card into the ranking was also worse (by reciprocal-rank fusion, which merges two
    orderings by position). First place fell from 17 to 16 for keywords and from 20 to 18 for
    sentences. The MCP was worse on both.
  - The card does help a query that names a package: first place for 107 → 143 of 238 names, with
    synonyms off. Fix 3 already puts every package name on page 1.
  - The cause: a card says what a whole manual is about, while the questions ask for a task inside
    one. "NEW PERSON file" moved the right manual from 3rd to 13th, behind manuals about the file in
    general.
  - Hand-written abstracts fall with it.
- **Pseudo-relevance feedback.** This adds the top results' shared distinctive words and searches
  again. It was worse everywhere.
  - Web console, when the any-word fallback fires (15 of 24 sentences): first place 20 → 11, or
    20 → 15 when merged with the first search.
  - MCP keyword questions in the top 10: 20 → 14.
  - The added words come from the largest manuals and pull results off topic. A fallback search
    also took three times as long (104 → 327 ms).
- **A link-count prior.** index.db's 29,593 document-to-document links join documents that mention
  the same significant entity; they are not citations. As a mild weight it moved one keyword
  question onto page 1, and cost one first place among sentences and one in each MCP set. A
  stronger weight was worse. The effect is too small and too unstable to build.

## 7. Decisions

All three were taken by the operator on 2026-11-06, as recommended.

**Operator direction, 2026-11-06.** Translating plain-English package names into the VistA package
name and namespace is a core capability of keyword search (fix 3). The operator edits the drafts in
Appendix B, as with D3. Search-box suggestions (fix 5) are in scope regardless of measured gain.

- **D1. The MCP's default for bare words.** Recommended: any word, ranked. With it, full-sentence
  questions still reach the top 10 for 23 of 24, and keyword questions are unchanged at 20 of 24.
  The alternative, all words, drops full sentences to 2 of 24, with 18 returning nothing, and
  agents often send sentences. **Decided: any word, ranked.**
- **D2. Whether the Go CLI (vdocs-cli) is in scope.** Recommended: yes, same reader, same shared
  cases. It is a port of the MCP engine, and leaving it out keeps a third set of rules alive. The
  alternative is to stop presenting it as an agent path. **Decided: in scope.**
- **D3. Who writes the keyword wording of the test questions.** Recommended: the operator edits
  the reviewer's drafts (Appendix A), because the drafts were written by someone who knew the
  answers. **Decided: the operator edits them.**

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

These are reviewer drafts, for the operator to edit (D3).

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

These are reviewer drafts, for the operator to edit, as with Appendix A. Each row is one application
in the latest corpus.
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
