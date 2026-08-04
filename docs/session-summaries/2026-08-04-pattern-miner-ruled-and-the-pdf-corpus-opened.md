# The pattern miner is ruled off, and the PDF documents finally get in

*2026-08-04 · commits `21bbaeb` … `87c92a8` · closes the search-quality programme's fifth effort and
opens a completeness workstream inside `vdl-observatory`*

## Where this picked up

The session was asked to execute the **pattern-miner** kickoff — the last of the five quality
efforts, and a ruling rather than a build. It closed in one commit. Everything after it came from
the operator following the thread outward: what "archive" means, what the collection is missing,
and finally what it takes to read the documents that were never readable.

## PM — the miner is off the default rebuild path (`21bbaeb`)

198 proposals judged across four frequency bands, and the volume measured against the **gold**
bodies rather than the converted corpus the miner reads. Approving every furniture proposal would
remove **~59 KB of 81.6 MB: 0.073% of the corpus, 0.6 characters of a median retrieved passage.**
The 95% upper bound is 1.26%. The cost of proposing it was 4m41s of a ~26-minute rebuild.

The sample's real finding inverts the warning the proposal carried: **frequency predicts furniture
badly in both directions.** The ≥100-document band is 70% single characters and markdown debris
split out of screen captures — 16 of 23 harmful if approved. Below 30 documents, where 34,665 of
the 34,822 phrase proposals live, 92% is genuine content.

`Stage.on_demand` is a generic orchestrator flag, not a special case: an on-demand stage stays a
registered DAG node but is excluded from every range selection. Recovered 18% of a rebuild.

Corrections found: **the curated total is 109, not 29** (the proposal counted 16 boilerplate, then
counted the same registry again as "89 shared blocks"); design §9.6's claim that high-frequency
candidates "auto-approve" was struck (no code implemented it, and PM.1 measured it to be the wrong
rule); and `registries/templates` is curated and stamps nothing — `templates_stamped: 0`.

## VO.5 — what "archive" means, measured (`5a91ac8`)

Operator hypothesis: the archive-marked documents are older duplicate copies, kept because VA has
no version control. **Substantially confirmed, with two corrections that change what follows.**

**36.3% of the archive share is not VistA documentation at all** — 1,096 VBA benefits forms listed
across many application pages, of which 92.6% carry `archive` against 1.5% of active records. The
"38.2% archived" headline should never be quoted unqualified again.

Of the 2,170 genuine documents, **69.6% are an older or duplicate copy** (of comparable pairs: 72.2%
older, 25.7% the same version, 2.1% newer). The rest are release-pinned documents — the same absence
of version control in a different shape.

**But archive is not redundant in our corpus.** `consolidate` already folds the duplicates into
their live document's lineage; what survives labelled archive is the residue — **55 documents, zero
with an active twin**. Excluding archive would delete the only copy we hold of the DSS *User's
Guide*, IFCAP *Technical Manual*, VIST *User Manual* and Consults *User Guide*.

## VO.6–VO.9 — completeness defined and enforced (`e8ef0bc` proposal, `16771a3` build)

The operator's diagnosis reframed five separate problems as symptoms of one: **the corpus had no
definition of completeness**, so "we hold all VistA documentation" could not be checked and
exclusions never needed a stated reason.

- **VO.6** — every excluded record carries a reason from a closed vocabulary. Four mechanisms
  excluded records and only one wrote a reason; app-scope exclusions recorded nothing at all.
- **VO.7** — a **sole-survivor rule**: admit a doctype-omitted document when nothing newer
  supersedes it. **159 admitted, against the 1,766 a blanket policy flip would take.**
- **VO.8** — no document is excluded for being unreadable by our converter. Scoping this to sole
  survivors (as proposed) would have recovered **one** document; the format-based rule recovers six
  more of types the policy already wants — including **both CPRS Technical Manuals and both Kernel
  8.0 binders**, absent by no decision anyone made.
- **VO.9** — `vdocs completeness`, exit non-zero on any unreachable document. *Complete* does not
  mean "we hold everything"; it means nothing is missing for a reason we did not choose.
  `CONVERTIBLE_FORMATS` is the boundary between a decision and a limitation, in one place.

Two measurement traps corrected on the way: the PDF barrier is **99% illusion** (2,866 of 2,885
PDF-blocked records have a DOCX sibling; only 19 are PDF-only), and archive and active documents are
admitted at an **identical 19%** — the label was never the gate.

Fetch targets **1,044 → 1,218 (+174), zero departures**, so the CI.4 composition gate stays green
with no acknowledgement needed. **The +174 are admitted but not yet fetched.**

## VO.8a — assessing the conversion before admitting it (`8ce880a`, `1c16e27`)

All 19 PDF-only documents were converted outside the production lake and measured against
`pdftotext` as independent ground truth. **19/19 succeeded, 4,089 pages, coverage 1.160 — no text
lost.** Where coverage dips, Docling is correctly separating running headers and footers.

**OCR rescued the Blood Bank manual**: 440 of its 623 pages (71%) carry no embedded text at all;
`pdftotext` recovers 38,721 words, Docling 142,156. Accuracy is good — 92.4% of prose tokens
recognised, the residue real vocabulary (`crossmatch`, `autologous`, `hbsag`). OCR damage is 1.65%
and its signature is **lost inter-word spaces**, not wrong characters.

The assessment paid for itself immediately: `_docling_convert` finished by re-reading the source as
a **DOCX zip** to recover image alt-text. VO.8 had routed PDFs into that same function, where it
raises `BadZipFile` — **all 19 would have failed to convert**, reported by the error gate as a
corpus defect rather than a wiring bug.

## VO.8b/c/e/f — the table of contents, which turned out to be the whole outline

The blocker VO.8a found: Docling renders a legacy TOC as a **markdown table**, and `normalize` could
not see it — a `|`-delimited row never ends in a page number, so the strip bounded at the first row.

- **VO.8b** (`a246931`) — three corpus shapes, each found by measuring: cells duplicated across all
  four columns, several entries run together in one cell, and a single entry **split across cells**.
  Entries are *found* (title + leader + page), never split on a page-number pattern — a section
  number like `2.1.1` is itself a valid page-number match. And the whole TOC is **one table**, so a
  contiguous run that proves itself with ≥1 parsable entry is the block; judging rows individually
  left 420 of the Blood Bank manual's 423 TOC lines in the body.
  **dot-leaders 7,198 → 991 (86%), entries captured 1 → 3,921, bodies −22.7%.**
- **VO.8c** (`8038f37`) — the outline from the document's own section numbering, guarded to
  documents with no hierarchy. Kernel SM **839 flat headings → five levels**; nested `## Contents`
  with GitHub-slug anchors and 381 back-links. Blast radius on the existing corpus: **2 of 615, both
  improvements.**
- **VO.8e** (`396d263`) — correlate the TOC back to the body to re-create the headings Docling's
  *visual* detection missed. **+815 sections** on 5,400 detected.
- **VO.8f** (`8d0407c`) — Docling and Pandoc converge on one `toc.yaml`. They already wrote the same
  file; two of its four columns were dead on the PDF path. **3,921 entries, 65% resolved, up from
  zero**, and an A/B proves it a no-op for Pandoc (+1 entry, 0 new flags).

## What measuring caught that reasoning would not have

Four defects in this session's own work were found only by running it against the real corpus:

1. Splitting TOC cells on a page-number pattern tears `2.1.1 Example.....2` apart.
2. Promoting recovered headings to the *shallowest* level swamped the Kernel DG's lone title, so the
   flat-document guard stopped firing and **silently destroyed the five-level outline** VO.8c had
   just built.
3. A "List of Tables" is a legacy TOC too, so **captions were being promoted to sections**.
4. `_docling_convert`'s DOCX-zip image recovery would have failed every PDF.

And one method note worth keeping: **gold has no legacy TOC** (586 of 615 carry a *derived*
`## Contents`; 494 carry `toc.yaml`). Any TOC measurement taken against gold returns zero whether the
code is right or broken — `02-enriched` is the only honest place to test.

## State at the end

`make check` exit 0 · **1,389 tests** · coverage 96.3% · retrieval baseline untouched
(`reports/rr3-after-twin-demotion.*`, hash `726d22a4…`, 57,895 chunks) — no document changed.

**Open and unstarted:** VO.8d (PDF figures are not extracted — 539 placeholders in the Kernel DG
alone), 5,429 undecoded HTML entities, the CPRS Technical Manuals and Blood Bank manual gain
sections but no depth (their headings are unnumbered and their TOC carries no indentation), and the
**+174 admitted documents are still not fetched** — the corpus holds 1,040 until someone runs
`vdocs fetch --all` and rebuilds. VO.1–VO.4, the observatory's actual timeline workstream, have not
been started.
