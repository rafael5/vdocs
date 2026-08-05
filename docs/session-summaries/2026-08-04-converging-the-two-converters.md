# Converging the two converters — and being wrong about it six times

*2026-08-04 (later) · commits `b92e17b` … `a00f9e4` · continues
[the pattern-miner session](2026-08-04-pattern-miner-ruled-and-the-pdf-corpus-opened.md) after its
increment closed*

## Where this picked up

The earlier session ended with the PDF path readable but uneven against the DOCX path. The operator
drove the rest: converge the two, then prove they converged, then look at the result by eye.

## Converging the paths

**Figures (`b92e17b`).** 1,337 figures existed only as `<!-- image -->` placeholders — 539 in the
Kernel Developer's Guide alone. Worth correcting the framing it was asked in: there is no images
*sidecar*. DOCX figures go to a shared content-addressed store, `documents/assets/<sha>.<ext>`, and
PDFs now land in the same place, which is what vdocs-web's `/api/asset` serves. The fix is one
setting per format, and they are opposite: DOCX keeps `placeholder` because Docling parses no
alt-text from DOCX XML and we recover both media and alt-text from the zip ourselves; a PDF has
neither, so Docling must export them.

**Tables (`27f48b9`, `99294e1`).** 60% of gold documents carried raw `<table>` HTML that a Docling
document never has — and **5,386 chunks, 9.3% of the search index, were indexing `colgroup`,
`tbody` and `tr class="odd"` as search tokens**. Converting what GFM can faithfully express took
inline tables 8,086 → 4,031 and markup tokens down 52%. The half left as HTML is deliberate: 1,056
use colspan/rowspan, 2,023 hold a heading or list inside a cell, 134 are nested. Separately, 774
1×1 Word text-boxes turned out to be **verbatim machine output** — List Manager screens, HL7
messages, MailMan traffic — and 742 became fenced code blocks. That is a correctness fix as much as
a rendering one: a captured screen line like `# DRUG QTY # REFS DAYS SUPPLY` was parsing as a
markdown *heading* and entering the heading tree.

**Dimensions (`4de7d56`).** `capture.yaml` recorded a before/after for words and nothing else, so a
transform that halved a document's tables moved no recorded number. `kernel/profile` now counts a
body's shape and `normalize` records input, output and delta. It found a real gap on its first run:
images 488 → 456, of which **28 are inside tables lifted to CSV** — the sidecar keeps cell text but
not image refs.

## The head-to-head, and what it explained

The operator asked for the same document both ways. `fm22_2dg` — FileMan 22.2 Developer's Guide, 839
pages — was the only candidate that genuinely exercises code: **2,281 M-code references against 24
for the next-best imaging manual**.

Then the sharper question: *if these are Word files saved as PDF, the content must be identical — so
find out WHY each difference occurs.* That reframing was correct and produced the unifying rule:

> **What is *formatting* in Word becomes *content* in the PDF. What is *metadata* in Word is
> destroyed by the PDF.**

Dot leaders are a tab-stop setting in Word and literal glyphs once printed (494 vs 0). Heading
identity is an unambiguous Word *style* but only type size in a PDF, so Docling infers and
over-detects (2,113 vs 846). Alt-text, bookmarks and cross-references live in DOCX XML and simply
cease to exist — **12,141 cross-references across the corpus become zero**.

And the content really is the same: once each side's legacy TOC is removed, the two bodies agree to
**901 words, 0.65%**.

## What the comparison caught that no test could

`extract_tables` runs **before** the legacy-TOC capture, and a Docling TOC *is* a markdown table —
tall enough on an 839-page document to qualify for extraction. It was being filed as
`tables/table-01.csv`, so **619 TOC entries silently became 0** on exactly the documents whose
outline matters most. Every unit test passed, because they fed `legacy_toc_entries` directly rather
than through the stage's ordering (`557a702`).

The durable lesson: **test through the stage's ordering, not just the pure function.**

## Human review enters the loop

`scripts/review.py` (`e3a33be`) — the realisation that **the lake is unnecessary for iterating on
`normalize`**, because every body transform is a pure function of the converted markdown. **10
documents in 1.8 seconds**, source PDF beside today's gold, one `assets` symlink so images render.

The operator's first pass through it immediately found something no measurement had: *"almost
without exception the PDF has the correct and complete TOC and the markdown does not."*

True, and it separated into two causes. The Contents was capped at a **fixed two heading levels**,
so 704 of `fm22_2dg`'s 846 headings and 1,589 of `cprsguitm_0_636`'s 2,144 existed, carried anchors,
and were simply not listed — fixed in `a00f9e4`, coverage 15% → 89%. The second cause is open:
`psb_3_um` has **191 TOC entries and 19 detected headings**, so it sits at 10% at any depth.

## What was measured and *not* built

A code-block heuristic for the Word path — consecutive bold paragraphs with an M-code marker — was
tested on the 20 most code-dense documents and **invalidated**: 620 M-statement lines, only 28%
bold, and **13 of 20 documents have code with zero bold-marked lines**. The convention belongs to one
authoring family, and `fm22_2dg` — the document it was validated on — *is* that family. The
selection metric was wrong too: `code_refs` density picks API catalogues that *mention* routines in
table cells rather than documents containing code.

Nothing was built. That is the correct outcome.

## Six times the instrument was wrong, not the pipeline

Worth listing, because it is the session's real theme:

1. A word-count diff reported 1,457 words lost per document — it was tag-stripping `<[^>]+>` from
   VistA M code, where `$L(X)<3` reads as a tag.
2. A word-multiset diff then blamed `<RET>` — the check replaced tags with a space where the code
   replaced them with nothing, shifting word boundaries.
3. "205 code blocks missing from Pandoc" — markdown escaping (`\^`) defeating substring matching.
   Actually 244 of 281 present.
4. "Docling recovers 12% more text" — counting markup tokens as words. On content words **Pandoc is
   ahead**.
5. "Docling loses 3.4% of content" — it was the TOC, and the bodies agree to 0.65%.
6. Contents links "97% resolving" — a reimplemented slug de-duplication. Actually **100.000%**.

Every one was caught by suspecting the measurement. The rule earned again: **prove content
preservation with character multisets**, never word counts, and never tag-strip VistA prose.

## State at the end

`make check` exit 0 · **1,463 tests** · retrieval baseline untouched — no document changed.

**Open:** heading *detection* (the second half of the operator's TOC finding — `toc.yaml` already
holds the correct list, and `recover_headings_from_toc` is deliberately too strict to use it);
~494 dot-leaders on the PDF path; `cprsguitm_0_636` over-detecting headings 290%; back-links now
following the deeper TOC (2,144 in one document) and wanting a reader's judgement; and the **+174
admitted documents are still not fetched**, so none of this session's work is in the live corpus.
