# Proposal — bound the legacy-TOC strip + add a content-retention gate

**Status:** implemented (2026-06-13) — code on branch `index-fallback-section`, pending re-normalize/re-index
**Scope:** `normalize` stage (`_scan_legacy_toc`) + a new `fidelity` content-retention guardrail.
**Owner:** Rafael / Claude

## Problem

`normalize`'s legacy-TOC strip (`_scan_legacy_toc`, `normalize_pure.py`) can delete the **entire
body** of a Pandoc-flattened document. The ATX-heading branch, on finding a heading whose text
matches a curated TOC title (e.g. *"Table of Contents"*), drops that heading **and every line up to
the next markdown heading**. A flattened doc (Word styling rendered as bold pseudo-headings, no real
ATX headings — the same class the `index` shredder's whole-body fallback addresses) has **no
terminating heading**, so the strip runs to EOF and removes the document.

### Evidence (bisection on the live lake, 2026-06-13)

Running `normalize_body`'s steps on the *enriched* (pre-normalize) body, word counts:

| doc | enriched | after `strip_legacy_toc` | removed |
|---|---|---|---|
| RMPR Prosthetics Inventory (`rmpr_3_p61_um`) | 37,780 | **27** | 37,753 |
| RMPR Prosthetics Processing (`rmpr_3_um`) | 27,536 | 213 | 27,323 |
| RMPR `rmpr_3_182` | 25,900 | 200 | 25,700 |
| RMPR NPPD UM (`rmpr_3_nppdum`) | 13,124 | 2,255 | 10,869 |
| PRCA ICD-10 UM (`icd_10_um_tp_4_5_281`) | 1,177 | 232 | 945 |

Other steps (recover-headings, subtract-phrases/boilerplate) leave the body intact; the loss is
entirely `strip_legacy_toc`. Content is present through `02-enriched`; only `03-normalized` is gutted.

### True scope — 5 docs, not 126

A first scan flagged 126 docs that lost >50% of their enriched body in normalize. **That count is
misleading:** normalize also lifts large tables to `tables/*.csv` sidecars (by design), which
legitimately shrinks the body. Isolating `strip_legacy_toc`'s own contribution: Kernel TM lost only
1,128 words to it (its 70k drop is table relocation); PRC, Pharmacy TM, IB similarly. **Exactly 5
docs** have `strip_legacy_toc` removing >50% of the body — all Pandoc-flattened.

### Why the existing over-strip gate missed it

`fidelity/overstrip_pure.score_over_strip` measures *hollow sections ÷ content sections*. A fully
gutted doc has **zero** content sections → `0/0` → "no content sections scores PASS". The over-strip
gate detects *bare sections that remain*; it is blind to a body that was deleted **whole**. This is a
real gap that let the defect pass the GREEN de-novo build.

## Fix 1 — bound the ATX-heading TOC strip (the defect)

In `_scan_legacy_toc`'s ATX branch, decide the region `[heading+1, next_heading)` and check whether
it contains **substantive prose** — any non-blank line that is *not* a loose TOC entry
(`_is_loose_toc_entry`; entries always end in a `(#anchor)` page-link, so body prose never matches).

- **No prose in the region** (a clean TOC: entries + blanks until the next heading) → drop the whole
  region. **Byte-identical to today** for every well-formed doc.
- **Prose present** (a flattened doc whose "TOC region" is really the body) → drop only the
  *contiguous leading run* of TOC-entry/blank lines and **stop at the first prose line**. The body is
  preserved.

This is the same contiguous-entry discipline the plain-text branch already uses, applied to the ATX
branch only when needed — so no well-formed doc changes, and the 5 flattened docs keep their bodies.

## Fix 2 — content-retention guardrail (the missing gate)

Add a `fidelity` guardrail orthogonal to over-strip: **retention** = fraction of the enriched body's
words still accounted for after normalize, counting both the kept body and words **relocated** to
referents (extracted-table CSVs). This is an S-vs-T check (needs the pre-normalize body), unlike the
T-only over-strip gate.

```
retention = min(1, (normalized_body_words + relocated_table_words) / enriched_body_words)
PASS ≥ 0.80 · REVIEW ≥ 0.50 · QUARANTINE < 0.50   (thresholds tunable on the golden set)
```

Counting relocated table words is what prevents a false positive on legitimately table-heavy TMs
(Kernel TM retains ~all its words across body+CSV). The `normalize` stage has all three inputs
(enriched body in, normalized body out, `ExtractedTable` list) and records the per-doc verdict;
`validate` blocks on QUARANTINE (REVIEW unless signed off), matching the other guardrails.

## Validation & rollout

1. **TDD** Fix 1: a flattened-doc case (TOC heading → entries → headingless prose) must keep the
   prose; a clean-TOC case must stay byte-identical. Existing `strip_legacy_toc` tests stay green.
2. **TDD** Fix 2: `content_retention` verdict cases (full body kept; table-relocated; gutted).
3. **Golden-set**: run the normalize unit + integration suites; confirm no diff on well-formed docs.
4. **Re-normalize → re-index** the lake (shared-lake action, operator-coordinated). Confirm the 5
   docs recover their bodies and the retention gate is GREEN corpus-wide.

Fixes are independent of the `index` whole-body fallback and the `fts_doc_title` name-search fix
(both already shipped); they ride the same eventual re-normalize/re-index.
