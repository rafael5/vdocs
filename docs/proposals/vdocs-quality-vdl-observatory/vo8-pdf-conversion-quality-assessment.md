# VO.8 — Docling conversion quality on the 19 PDF-only documents

**Assessed 2026-08-04**, outside the production lake — nothing entered the corpus. All 19 PDF-only
genuine VistA documents were downloaded, converted with the exact settings the pipeline uses
(`docling --to md --image-export-mode placeholder`), and measured against `pdftotext` as ground
truth: it reads the PDF's own text layer with no layout model, so it is an independent lower bound
on recoverable words.

**Verdict: convert them.** Quality is good enough to admit, with one fix needed first and two
follow-ups. 19/19 converted successfully, 4,089 pages, **764,262 reference words → 886,831
recovered**.

## 1. No text is lost anywhere

| | |
|---|---|
| documents converted without error | **19 / 19** |
| overall coverage vs. the text layer | **1.160** |
| lowest coverage of any document | 0.893 |

Nothing falls meaningfully below 1.0, and where it dips the cause is correct: Docling **separates
running headers and footers** as `page_footer` items and drops them from the markdown. In one
9-page guide it isolated 22 such items — "Dental Record Manager Plus V 1.2 ii January 2025". That
is page furniture removed, not content lost, which is why the tiny 4-page release notes sit at
0.89–0.94 while everything substantial sits at or above 1.0.

## 2. OCR rescued two documents that were genuinely unreadable

The Laboratory Blood Bank manual is catalogued as "scanned doc" and it is: **440 of its 623 pages
(71%) carry no embedded text at all.** `pdftotext` recovers 38,721 words; Docling recovers
**142,156** — coverage 3.67 — because it runs OCR on the image-only pages. Page 60 returns nothing
from the text layer and a complete VistA Blood Bank roll-and-scroll transcript from Docling.

The DRM+ p90 back-out guide is the same story in miniature: 6 of 21 pages have no text layer,
coverage 1.487.

**OCR accuracy is good.** Against the repo's own English lexicon with basic morphology, **92.4% of
prose tokens are recognised**, and the unrecognised residue is dominated by real Blood Bank
vocabulary — `crossmatch`, `autologous`, `hbsag`, `worklist`, `xmatched`. Genuine OCR damage is
**1.65% of tokens**, and its signature is *lost inter-word spaces* rather than wrong characters:
`abnormaldonortests`, `abscreenresultsare`, `adequateforfacility`, plus occasional character slips
(`accesaion`, `additionai`). Meaning survives for a reader; the affected tokens will not match
keyword queries.

## 3. ⛔ The blocker: table-shaped tables of contents survive the strip

Docling renders each legacy TOC as a **markdown table**, frequently duplicating every row across
four columns. `normalize` is built to capture such a TOC to `toc.yaml` and strip it, but its
detector does not recognise this shape:

`_is_toc_nav_line` returns **False** for a table row — the trailing `|` defeats `_TRAILING_PAGE_RE`
and the row is not a loose TOC entry — so `has_prose` becomes true, the strip bounds at the first
table row, and the TOC stays. Measured on the Kernel Developer's Guide:

| | before | after `strip_legacy_toc` |
|---|---:|---:|
| dot-leader runs | 3,417 | **3,416** |
| TOC entries captured to `toc.yaml` | — | **1** |

Across all 19: **4,133 table-shaped TOC rows, 49,105 words (5.5% of the corpus text)**. Worst case
is the Kernel Developer's Guide at **11.9% of its body**.

**This is the safe failure, not the dangerous one.** Nothing is deleted without a record — the
content is *retained* rather than lost, so capture-before-strip is not violated and the precedent
incident does not repeat. But the consequences are real: bloated bodies, a regenerated `## Contents`
sitting beside an un-stripped legacy one, and thousands of dot-leader entries indexed as searchable
text, which is exactly the "text that matches queries without meaning anything" the pattern-miner
effort was about.

**Fix before admitting:** teach `_is_toc_nav_line` the table-row form so the existing capture-then-
strip path fires. This is a detector widening in `normalize`, not a new mechanism.

## 4. Follow-up: no heading hierarchy

**15 of 19 documents come out with a single heading level**; the four largest reach two. This is
not a markdown-export artifact — Docling's own JSON document model assigns **every** `section_header`
`level: 1`. It detects headings visually and does not infer depth from a PDF.

`normalize.infer_heading_levels` will not repair it: that function removes *gaps* in an existing
hierarchy, it does not create one, so a flat tree stays flat.

Retrieval still works — sections chunk and index correctly, and the text is searchable. What
degrades is navigation and the `section_path` signal, which RR.2's weight sweep showed is live. A
1,127-page binder with 2,291 headings all at one level has a meaningless section tree.

**Partly recoverable from numbering:** 48 of ~58 headings in the DIBR guides carry section numbers
(`1.`, `1.2`, `1.2.3`), and depth follows directly — `_NUMBERING_RE` in `discover_pure` already
parses that shape. But it is uneven: the installation guides have zero numbered headings. Worth
doing for the documents it fits; not a universal fix.

## 5. Follow-up: figures are not extracted from PDFs

Docling emits `<!-- image -->` placeholders and the DOCX image-recovery pass does not apply to PDFs
(see the defect below). The Kernel Developer's Guide alone carries **539** such placeholders, the
Systems Management binder 372, the AHOBP manual 188. The text is complete; the figures are not
retrieved. Docling supports `--image-export-mode referenced|embedded`, so this is a wiring question,
deliberately left open here.

## 6. A defect this assessment caught before it shipped

`_docling_convert` ended by re-reading the source bytes as a DOCX zip to recover image alt-text —
a DOCX affordance. VO.8 routed PDFs into that same function, where `extract_pictures` raises
`BadZipFile`. **All 19 documents would have failed to convert**, and the per-document error gate
would have reported it as a corpus defect rather than a wiring bug. Fixed in `8ce880a`
(`recovers_docx_images`); PDFs keep Docling's own markdown.

## 7. Minor

- **5,429 undecoded HTML entities** across the 19 (`OI&amp;T`). A cheap decode pass.
- Conversion cost: ~1.5 s/page warm. The Blood Bank manual took **60 minutes** (OCR on 440 pages);
  everything else totalled about 50 minutes for 3,466 pages.

## 8. Recommendation

1. **Fix the table-shaped TOC detector** (§3) — the one true blocker.
2. Then admit and build; the 19 add ~677,000 words of Kernel, CPRS and Blood Bank documentation the
   corpus does not have.
3. Schedule heading-depth-from-numbering (§4) and PDF figure export (§5) as separate work.
4. Decode HTML entities (§7).

## Reproducing

PDFs, markdown, logs and `assessment.json` are in the session scratchpad (not committed — 60 MB).
Re-run: download the 19 `doc_url`s from the PDF-only set (`out_of_scope_reason == "pdf"` and no DOCX
sharing the `anchor_key`), `docling --to md --image-export-mode placeholder`, then compare word
counts against `pdftotext`, and per-page `pdftotext` to find the OCR'd pages.
