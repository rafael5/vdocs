# Accounting for the whole library — exclusion reasons, and admitting the unique archive documents

**Status: DRAFT · proposed 2026-08-04 · needs sign-off before any code** ·
Evidence: [`vo5-archive-meaning-findings.md`](vo5-archive-meaning-findings.md)

Operator direction, 2026-08-04:

> *For the VBA documents, tag or label them as such, and the reason for not fetching being "not
> VistA". For the archive documents that are VistA related — yes we want them even if they are
> "old" or a clerk says they are "archived", because we want **all** VistA documentation accounted
> for and accessible: the code is still there and was never removed from VistA.*

The principle is accepted and is not in question here. What follows is the measurement of what it
would actually take, which turns out to be much smaller than the headline numbers suggest — and one
distinction that does most of the work.

## 1. The distinction that matters: *accounted for* vs *accessible*

They have very different costs, and conflating them is what makes this look big.

- **Accounted for** — we can enumerate every document the VDL lists, say whether we hold it, and if
  not, say exactly why. Cheap. Mostly already built; what is missing is that the *reason* is
  implicit in which gate stopped the record, and is never written down.
- **Accessible** — fetched, converted, indexed, searchable. Expensive per document.

The operator ask contains both. Recommendation: **make everything accounted for, and make the
unique documents accessible.** Duplicates need neither.

## 2. What is actually excluded, and why

Genuine VistA-system records (noise and decommissioned removed): **5,752**. Of those, 1,099 are
admitted. The gates that stop the rest are **not the archive label** — archive and active documents
are admitted at an almost identical rate:

| | records | PDF | doctype-omitted | admitted |
|---|---:|---:|---:|---:|
| active | 4,188 | 50% | 31% | **19%** |
| archive | 1,564 | 50% | 31% | **19%** |

**The pipeline does not disfavour archive documents at all.** Whatever else is true, "archived
material is being dropped because it is archived" is not happening.

**And the PDF barrier is almost entirely an illusion.** Of the 2,885 PDF-blocked records, **2,866
(99%) have a DOCX sibling of the same document** — the VDL publishes most manuals in both formats
and the pipeline deliberately prefers DOCX. Genuinely PDF-only across the entire library: **19
records.**

## 3. The real gap

Archive documents with no live counterpart — the ones that cannot be recovered from a newer
version — number **488**. Where they stand:

| | count | what it would take |
|---|---:|---|
| already held | 78 | nothing |
| **doctype-omitted** (DOCX, in scope, crawled) | **166** | a targeted admission rule |
| PDF-blocked but with a DOCX sibling | 241 | nothing — already reachable |
| **genuinely PDF-only** | **3** | converter routing |

**The whole gap is 169 documents.** They affect 16 applications — VBECS (27), ADT (25), ROR (24),
CPRS (23), GMRC (12), SD (11), PSO (10), MAG (9). Every one of those applications already has
admitted documentation, so no package is currently undocumented; these are additional historical
manuals for packages already covered.

> ⚠️ **The 488 is approximate.** It is derived from `anchor_key` matching, which the VO.5 work
> showed can miss a reworded duplicate. Re-derive it carefully before acting — that is a VO.1-shaped
> measurement, and it can only shrink the number, not grow it.

## 4. Proposal

### 4.1 Every excluded record carries an explicit reason (the accounting half)

Today four independent mechanisms exclude a record and only one writes a reason onto it:

| mechanism | reason recorded today |
|---|---|
| noise classification (`noise_type`) | a type, not a reason |
| app scope (`system_type` / `app_status`) | **none** |
| format (`out_of_scope_reason`) | the format only |
| doctype policy | in the registry, not on the record |

Add one computed field carrying a controlled vocabulary, written once where the funnel is already
evaluated, and surfaced on the gold inventory (the accounting surface):

```
not-vista:vba-form            1,096 archive + 88 other   ← the operator's ask, explicitly
not-vista:va-reference          137
not-vista:system-type=<value>   606   (Web client, VA enterprise service, COTS, middleware)
format:pdf-duplicate          2,866   ← we hold the DOCX of this document
format:pdf-only                  19   ← genuinely unreachable today
doctype-omitted:<code>        1,766
```

Two points this buys beyond the literal ask. First, `format:pdf-duplicate` versus `format:pdf-only`
is the difference between 2,885 alarming records and 19 real ones — the current single `pdf` reason
hides that. Second, once written down, "all VistA documentation accounted for" becomes a claim the
pipeline can *check*, not one we assert.

**Do not overload `out_of_scope_reason`.** It is published in read contract v1.6; changing its
meaning is a breaking change for consumers. New field, additive.

### 4.2 A sole-survivor admission rule (the accessibility half)

For the 166: rather than flipping the doctype policy — which would admit **1,766** documents and
re-create exactly the flood of ephemeral, version-bound content the Tier-A decision exists to
prevent — admit a document whose doctype is omitted **when it is the only surviving documentation
of its kind for its package**.

This encodes the operator's reasoning directly and computably: a release note for a patch that has
been superseded ten times over is ephemeral and stays out; a release note that is the *last*
surviving document of its type for code still running in VistA is the historical record and comes
in. It is data-driven, it is a rule rather than a list, and it does not reopen the policy question.

Ratio: **166 admitted instead of 1,766** — a tenth of the cost for the documents that actually
cannot be recovered elsewhere.

### 4.3 Route the 3 PDF-only documents

Docling already handles PDF and is already wired as an alternate converter via
`registries/converter-routing`. Three documents is small enough to route explicitly and verify by
reading them. The other 16 PDF-only records library-wide can follow if they prove worth it.

## 5. What this deliberately does not do

- **Does not admit the duplicates.** ~1,076 archive records duplicate a document we already hold;
  `consolidate` already folds the fetched ones into that document's version lineage. They are not
  lost, they are its history.
- **Does not change the doctype policy.** The Tier-A reference-core decision stands; 4.2 is a
  narrow, principled exception to it, not a reversal.
- **Does not reopen the `decommissioned` exclusion.** That was ruled on 2026-08-03 and is separate.
- **Does not infer VA's intent** from the `archive` label. Still unestablished; still VO.2–VO.4.

## 6. Cost

| | |
|---|---|
| 4.1 exclusion reasons | moderate — a computed field through `catalog` → `serve-inventory` → gold inventory; additive, no read-contract break |
| 4.2 sole-survivor rule | small — one predicate in the admission gate, plus a careful re-derivation of the 488 first |
| 4.3 PDF routing | small — 3 registry entries and a verification read |
| fetch + rebuild | 169 new documents on ~1,040; a rebuild, not a re-crawl |

## 7. Decision needed

1. Build 4.1 (accounting), 4.2 (sole-survivor admission), 4.3 (PDF routing) — or a subset?
2. Does this become a step inside `vdl-observatory`, or its own small effort? It is adjacent to VO
   (accounting for the source rather than harvesting it) but it changes what the corpus *contains*,
   which was `crawl-integrity`'s territory.
