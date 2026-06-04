# Migration Fidelity Measurement Framework

**Status:** Specification. **Date:** 2026-06-01. **Companion to:** `vdocs-design.md`.
**Audience:** the implementer; and the institutional stakeholder who must decide whether a
Word→GitHub migration preserves the authoritative record well enough to *consider* docs-as-code.

This framework answers one question, defensibly: **"How faithfully did each document survive
migration from its original Word/PDF source to GitHub markdown — and can we prove it?"** It
produces a measured, reproducible, per-document fidelity verdict and a corpus-level assurance
statement that a skeptic (or a regulator) can verify against the retained originals.

It exists because the migration is the **gating precondition**: the institution cannot
table docs-as-code at all unless full-fidelity migration of content, provenance, and change
history is *proven*, not asserted. This framework is that proof, made measurable.

---

## 1. The standard: what "full fidelity" means here

There are two standards, and conflating them is fatal to the proposal:

- **Lossless round-trip** — Word → markdown → Word renders byte-identical. **Not achievable,
  not the bar, not measured.** DOCX carries constructs markdown has no native model for
  (merged/nested cells, text boxes, SmartArt, embedded objects, equations, field codes, page
  layout). Promising this is dishonest.
- **Information fidelity + auditability + retained ground truth** — every *unit of
  information* (prose, tables, images, cross-references, structure, metadata, documented
  history) survives into the new medium; survival is **measured per document**; lossy cases
  are **flagged for remediation, never silently dropped**; and the immutable original is
  **retained as ground truth** so the claim is verifiable in perpetuity. **This is the bar.**

The institutional reframe this enables: stop asking "is it lossless?" (no) and ask "is the
loss *measured, bounded, remediated, and reversible?*" (yes, provably).

---

## 2. Principles

1. **Source-anchored.** The immutable bronze original is ground truth. Fidelity is always
   measured *against the source*, never asserted from the output alone.
2. **Independent extraction.** The reference signal is extracted from the source by a path
   **independent of the conversion pipeline** — otherwise we would measure the converter
   against itself and learn nothing.
3. **Dimensional before scalar.** Decompose into independently-measured dimensions; never
   collapse to one opaque number that can hide a catastrophic single-dimension failure.
4. **Recall-first, precision-guarded.** The primary risk is information *loss* (recall), but
   we also detect *fabrication/corruption* (precision): mojibake, duplicated title blocks,
   hallucinated or exploded content.
5. **Graded gate, not binary.** PASS / REVIEW / QUARANTINE. Nothing below bar is ever
   published as "faithful."
6. **Human-calibrated.** Automated metrics are validated against a human-rated golden sample,
   so the automated score is a *proven predictor* of true fidelity — not a number we invented.
7. **Reproducible & audited.** Deterministic scoring, stored with tool/framework versions and
   source/target hashes; re-runnable against retained originals forever.
8. **Honestly scoped.** What cannot be measured or migrated is enumerated explicitly (§14),
   because naming the gaps is what earns institutional trust.
9. **Currency is a fidelity dimension, over time.** Faithfulness is *maintained*, not asserted
   once: the corpus is continuously checked against the live upstream, drift is detected, and
   superseded documents are re-ingested and re-scored. A faithful migration of a stale source is
   no longer a faithful representation of the *current* authoritative record (§7.5).

---

## 3. The fidelity axes

| Axis | Question | Nature | §|
|---|---|---|---|
| **Content** | Did the information in the body survive? | graded recall/precision per dimension | §5 |
| **Provenance** | Is the document verifiably tied to its official source? | completeness checklist + a cryptographic hard gate | §6 |
| **Change history** | Is the documented/published evolution preserved? | recall + version coverage, explicitly scoped | §7 |
| **Currency** | Is the corpus still current with the authoritative upstream? | temporal drift state (upstream-anchored, not source-anchored) | §7.5 |

The first three axes are **source-anchored** (`S` vs `T`) and yield the per-document *migration*
verdict (§8): all three must clear their gates. **Currency (§7.5) is a distinct, upstream-anchored
axis** — it asks whether the faithfully-migrated document is also still the *latest*, and is
enforced as a **corpus-temporal** gate, not by flipping a per-document verdict. "Faithful" and
"current" are reported as two non-conflated claims. Retrieval quality over the *search* corpus
(`index.db` + `vectors.db`) is a further, machine-facing measurement — distinct from any per-document
migration axis — covered in §10.5.

---

## 4. Measurement methodology

For each document the framework holds two artifacts: **S** (the immutable source DOCX/PDF)
and **T** (the migrated markdown bundle: `body.md` + sidecars `tables/*.csv`, `history.yaml`,
`refs.yaml` + the asset references).

**Independent reference extraction (from S):** a *second*, pipeline-independent extractor
reads S into a neutral structured form — for DOCX via the OOXML / `python-docx` object model
(paragraphs, runs, tables, drawings, bookmarks, fields, styles); for PDF via a PDF text/table
extractor. This reference is imperfect; that imperfection is exactly why §9 anchors everything
to human judgment. The reference extractor is **frozen and versioned** so scores are stable.

**Target extraction (from T):** parse `body.md` + sidecars into the same neutral form
(headings, paragraphs, tables incl. CSV sidecars, image refs, links/anchors, lists).
**Reference resolution before comparison:** boilerplate/shared blocks that `normalize` subtracted
and replaced with a reference to the canonical single copy (vdocs-design §9.6) are **dereferenced
and re-inlined** into T before scoring — so single-sourcing is never mis-scored as dropped content
(C1 recall). Conversely, **template-scaffold** stripped as meaningless residue (recorded by `template_id`) and
**dead phrases** deleted via the curated `registries/phrases` (page furniture, revision-history
filler) are excluded from the source-token baseline, so removing registered noise is not penalized
as loss. Every move is auditable: a reference resolves to retained content, a strip/delete matches an
*approved registry entry* (no free-form removal), the disposition is recorded (C7), and bronze
(principle 1) still holds the untouched original — so the recall metric measures loss of *meaning*,
not loss of paper-era noise we removed on purpose.

**Normalization (applied to both sides before comparison):** Unicode NFC; whitespace
collapse; de-hyphenation of line-break hyphens; case-folding for text recall; smart-quote and
dash canonicalization. This prevents penalizing cosmetic, information-preserving differences.

**Determinism:** identical S+T+tool-versions → identical scores. Every score record carries
`source_sha256`, `target_sha256`, extractor versions, and framework version (§11).

---

## 5. Content fidelity dimensions

Each dimension yields a score in `[0,1]` plus diagnostics. Defaults below are **calibration
targets** (§9), not arbitrary — they are confirmed/adjusted against the golden sample.

| # | Dimension | What it measures | Metric | Hard floor | Target |
|---|---|---|---|---|---|
| C1 | **Text** | prose survives, no fabrication | token **recall** (S→T alignment) + **precision** (T not inflated) + paragraph coverage | recall ≥ 0.97 | ≥ 0.99 |
| C2 | **Structure** | heading tree preserved | heading-set recall + level accuracy + order (sequence similarity) | ≥ 0.90 | ≥ 0.97 |
| C3 | **Tables** | the highest-risk content (data dictionaries) | table-count recall + per-table cell-text recall + row/col dimension match (incl. CSV sidecars) | ≥ 0.95 | ≥ 0.99 |
| C4 | **Images/figures** | images and captions survive | image-count recall + caption recall + EMF/WMF→PNG success | ≥ 0.98 | 1.00 |
| C5 | **Cross-refs & links** | references resolve | internal-ref count recall + **resolvability** (dead-anchor rate) + hyperlink recall + **TOC integrity** (accuracy / completeness / round-trip) | recall ≥ 0.90, dead-anchor ≤ 0.02, **TOC dead-anchor = 0** | ≥ 0.98, 0.00 |
| C6 | **Lists** | procedures/steps intact | list-item recall + nesting-depth preservation | ≥ 0.95 | ≥ 0.99 |
| C7 | **Lossy-construct inventory** | constructs markdown can't natively hold | *inventory + disposition*, not a score (§13) | no `flagged-lost` | — |

**Per-dimension method notes**

- **C1 Text.** Token-level alignment (longest-common-subsequence / `SequenceMatcher`) between
  normalized S and T token streams. **Recall** = matched source tokens ÷ source tokens (catches
  dropped sections, truncation). **Precision** = matched ÷ target tokens (catches duplicated
  title blocks, exploded markers, mojibake-inserted noise). Also report **paragraph coverage**:
  fraction of source paragraphs with a ≥0.85-similar match in T (localizes *where* loss occurs).
- **C2 Structure.** Compare the ordered heading list (text + level). Recall on normalized
  heading text; level accuracy on matched headings; order via sequence similarity. Drives the
  `doc_sections` tree, anchors, chunking — structural loss is high-impact.
  - **Template conformance (an independent structural oracle — principle #2).** Beyond `S`→`T`,
    structure is also checked against the document's **template schema** (the computable
    `(doc_type, era)` structure mined and retained by `discover`; vdocs-design §9.8). The schema is
    an expectation *independent of both the source and the converter*, so it gives structure a
    *second* independent reference. Two signals come out of it:
    - **`template_self_conformance`** — does `T` satisfy the sections/markers the document's own
      matched template *guarantees*? A required section absent in `T`, a TOC entry resolving to no
      heading, or broken numbering is a high-confidence **extraction/refinement defect** — caught
      without trusting the imperfect reference extractor, and a strong precision/recall corroborator.
    - **`canonical_compliance`** — does the document's era-template conform to the curated **canonical
      `doc_type` schema**? Divergence here is a *source* structural-drift signal (a modernization
      backlog item), **not** a migration defect. Keeping the two apart is the point: *fails its own
      template* ⇒ pipeline bug; *conforms to era but not canonical* ⇒ faithful migration of a
      divergent original.
  - **Sidecar completeness — typed absence + count reconciliation (a build-health hard gate).**
    Structure also includes the **machine-owned sidecars** `normalize` lifts out of the body
    (`revisions.yaml`, `tables/*.csv`, `refs.yaml`, `toc.yaml`). A *missing* sidecar is ambiguous —
    "nothing to capture" vs. "a detector silently failed" look identical — so every bundle carries a
    **`capture.yaml`** recording each capture attempt's typed outcome (`captured` / `failed` /
    `absent-expected` / `absent-unexpected`) plus an independent residue re-scan of the normalized
    body (vdocs-design §6.4). Two reconciliation checks turn that into a gate, enforced by `validate`:
    - **Per-document typed absence.** Any `absent-unexpected` (detector found nothing but the residue
      scan still sees the structure) or `failed` (recognised-but-unparseable) outcome is a
      structural-extraction defect → blocks, exactly like a missing required section. This is the one
      check that catches a *single* document's silently-missed table/revision-table — the failure mode
      the `S`→`T` recall metric and the corpus aggregates both miss when the rest of the corpus parses
      cleanly.
    - **Corpus count reconciliation.** The per-sidecar emission counts `normalize` records to
      `state.db:stage_runs[counts]` are checked against expectation: a class going `absent-expected`
      across the *entire* corpus (e.g. zero `tables/*.csv` over hundreds of table-bearing manuals), or
      a count that **drops** versus the prior run with no matching source change, is an implausible
      aggregate → a whole-detector failure, re-classified `absent-unexpected` and blocked. This is the
      completeness dimension (produced vs. expected) standard in data-quality validation, applied at
      corpus scale to catch failures no per-document score can.
- **C3 Tables.** Greedy best-match each source table to a target table or its CSV sidecar;
  per-pair cell-text recall + dimension match; aggregate weighted by source cell count.
  Specifically detects the v1 failure modes: tables exploded into bare list markers (precision
  collapse), merged cells flattened, tables dropped.
- **C4 Images.** Count of `<drawing>`/embedded images in S vs distinct asset (sha256)
  references in T; caption recall via figure-caption matching. Records EMF/WMF conversion
  outcomes.
- **C5 Cross-refs & links.** Count of Word cross-reference fields / bookmarks / hyperlinks vs
  markdown links/anchors; **resolvability** = internal links pointing at a real anchor ÷ all
  internal links (the dead-anchor rate, tied to the stable-ID system). Zero dead anchors is the
  publish target.
  - **Ref-resolution gate (the severed-conref check — generalised from TOC to all cross-refs).** The
    `refs.yaml` sidecar records, per bundle, the live anchor set (one row per heading: `slug` +
    `stable_id`) **and** the outbound cross-ref map (each original Word `_Toc…`/`_Ref…` bookmark →
    its resolved slug, or `UNRESOLVED`). DITA migrations report that the most common silent-loss mode
    is a **severed cross-reference** — a link whose target id changed, broken silently. `validate`
    therefore resolves **every** outbound ref against that bundle's live anchor set and classifies
    each, keeping two failure modes apart:
    - **severed** — the resolved target slug matches **no** live anchor row. A ref that *was* good
      now points nowhere — a true dead anchor and a silent regression. This is the same round-trip
      the **TOC integrity** check below specifies (every TOC entry → a real heading), generalised to
      *all* cross-references. **Hard floor: zero severed cross-refs** — any one blocks.
    - **unmapped** — the `UNRESOLVED` marker `normalize` already wrote for a Word bookmark it could
      not map to any heading. Triage (2026-06-03, 1.5k-bundle corpus) split this into two classes by
      bookmark kind, because conflating them miscalibrated the C5 rate:
      - **`_Toc…` (heading-targeting → the C5-bounded, recoverable class).** A TOC-field bookmark
        targets a heading, so it *should* resolve. Today ~0.76 of `_Toc` refs are unmapped — not
        because the target is absent but because Pandoc drops some heading bookmark spans, so
        `anchors_pure` (which captures spans inline on heading lines) has nothing to capture. The
        mapping is reconstructible from the legacy TOC (which records `_Toc… ↔ heading-title`, already
        captured to `toc.yaml`): a tracked **`normalize` legacy-TOC-correlation follow-up**. The
        C5 ≤ 0.02 resolvability target applies to **this** rate (over the heading-targeting universe).
      - **`_Ref…`/other (non-heading → expected-unmapped, outside C5).** A Word cross-reference to a
        figure / table / numbered item / page span — unmappable to a heading anchor by construction
        (0 of 844 `_Ref` refs resolve on the real corpus; ~64% of all unmapped). Reported only;
        **excluded** from the C5 rate's denominator.
      Both are **reported metrics, never gated**. The dead-anchor hard floor applies to **severed**
      refs + the **TOC entries + heading tree** round-trip (below), not to every inbound body cross-ref.
    Keeping them apart is the point — *severed* is a silent regression to catch; *unmapped* `_Toc` is
    the recoverable resolvability gap to drive down; *expected-unmapped* `_Ref` is the by-construction
    baseline to measure, not block on.
  - **TOC integrity (the highest-value navigation check).** Because the TOC is the primary
    navigational *and* semantic structure (vdocs-design §6.7) and is *derived from the heading tree*,
    it is scored explicitly: **accuracy** (TOC entries match the heading tree), **completeness**
    (every in-scope heading is listed), **resolvability** (every entry links to a real heading —
    **zero** dead anchors, a hard floor), and **round-trip** (every targeted heading carries a
    back-to-Contents link). The *original* Word TOC is the cross-check, not the target: entries it
    lists that are absent from `T` localize a dropped heading (an extraction defect), while entries
    present in `T` but missing from the original TOC flag a stale source TOC. TOC failures are
    **gate-blocking**, not advisory — a broken map is worse than an ugly one.
- **C6 Lists.** Ordered/unordered/nested item counts and nesting depth.
- **C7 Lossy constructs.** Not scored — *inventoried* (§13): each text box, embedded object,
  equation, SmartArt, form field, multi-column region is detected in S and assigned a
  **disposition**: `converted` (faithfully represented), `sidecar` (preserved out-of-body), or
  `flagged-lost` (could not be represented — forces QUARANTINE).

---

## 6. Provenance fidelity

Not a recall score — a **completeness checklist plus one cryptographic hard gate**:

- **HARD GATE (must be 100%):** `source_sha256` present in T and **matching the retained
  bronze original** byte-for-byte. This is the unbroken, verifiable chain of authority from the
  GitHub document back to the official Word source. A document failing this **cannot** be
  declared faithful, regardless of content score.
- **Completeness (fraction of required provenance fields present + well-formed):**
  `source_url`, authoring package/office (authority), version/patch identity, publication date,
  the identity-frontmatter required keys, and the lineage record (converter, tool versions,
  timestamps).

`P_score = completeness × (sha256_verified ? 1 : 0)`. Provenance gate: `sha256_verified = true`
**and** `completeness ≥ 0.98`.

This axis is the most reassuring to the institution and the most fully achievable: the chain of
authority becomes *stronger* than a Word file in a folder, because every claim is cryptographically
traceable.

**Capture completeness is part of "provable, not asserted."** Provenance proves the body came from
the source; it must also be provable that **nothing was silently dropped on the way out of the body**.
The per-bundle `capture.yaml` (vdocs-design §6.4) makes that auditable: every structure `normalize`
lifts to a sidecar leaves a typed record (`captured` / `failed` / `absent-expected` /
`absent-unexpected`), so a reviewer can confirm each absent sidecar is *explained* rather than merely
missing.

This is realised by the **signed bundle manifest** (`bundle.yaml`, vdocs-design §6.6): `consolidate`
writes, into each gold anchor bundle, the complete part list with each part's `sha256` + byte length,
the folded `capture.yaml` outcomes, the member `source_sha256` provenance roots, and a `bundle_digest`
(sha256 over the sorted `path:sha256` lines). The `validate` gate **recomputes** every part hash from
disk, confirms the on-disk part set equals the manifest exactly, and recomputes the digest — so the
whole bundle (body *and* sidecars) is a **verifiable, untampered unit**, not asserted: a skeptic
re-runs the hashes and gets the same answer (the §6/§11 reproducibility-is-auditability principle
applied to bundle completeness). "Signed" here is a verifiable **content digest** (recompute to
verify, key-free); a *keyed* signature over `bundle_digest` is a future increment once key management
exists. Per-stage provenance (which stage produced which artifact, by hash) is already recorded in
`state.db:stage_runs` (`inputs_fp`/`outputs_fp`); a formal exportable in-toto/SLSA chain over it is
deferred. `history.yaml` (`source_sha256` + `body_sha256`) remains the body↔source link; the manifest
extends that guarantee to the bundle as a whole.

---

## 7. Change-history fidelity

"Change history" means several distinct things; fidelity requires measuring the *achievable*
ones and explicitly scoping out the unachievable:

- **H1 Revision-narrative recall.** The document's own revision-history table → `history.yaml`.
  Metric: revision-entry recall = entries captured ÷ entries present in the source table; field
  completeness per entry (date/version/author/description). Floor ≥ 0.98 (verbatim preservation
  is expected).
- **H2 Published-version coverage.** The sequence of historically published versions/patches,
  backfilled into git history (one commit per published version, dated/attributed from the
  revision metadata). Metric: versions represented ÷ known published versions for the group.
- **H3 Scope statement (mandatory, not a score).** The migrated history is faithful to the
  **published record at published-version granularity** — **not** to intermediate
  pre-publication edits (tracked changes / internal DMS audit trails), which never existed in
  the public artifacts and **cannot** be reconstructed. This limitation is recorded on every
  document so no one mistakes the git log for a keystroke-level history.

`H_score` = weighted(H1, H2); H3 is carried as a fixed disclosure flag.

---

## 7.5 Currency / freshness fidelity (the temporal axis)

Axes §5–§7 measure migration fidelity **at a point in time**: given the retained source `S`, did
`T` preserve it? They are silent on a different failure — `S` itself going **stale** because VDL
published a newer patch the corpus never ingested. A document can be PASS-faithful yet no longer
represent the *current* authoritative source. **Currency** closes that gap; it is the temporal
extension of the provenance chain (§6): provenance proves `T ↔ S`, currency proves
`S ↔ upstream-latest`.

Unlike §5–§7, currency is **upstream-anchored**, not source-anchored: it compares the corpus
against the live VDL catalog, so it is produced by the pipeline's scheduled change-detection pass
(mechanism in `vdocs-design.md` §7.6 / §8), not by the `S`↔`T` comparator.

**Per-document currency state** (a recorded *state*, not a `[0,1]` score — more honest than a
manufactured number):

| State | Meaning |
|---|---|
| **CURRENT** | corpus version == latest published VDL version; checked within the freshness SLA |
| **STALE** | VDL published a newer patch/version (or re-posted changed bytes) not yet ingested |
| **UNCHECKED** | not verified against VDL within the SLA window — currency cannot be asserted |
| **WITHDRAWN** | gone/superseded upstream; the retained anchor + bronze remain, flagged not deleted |

**Detection signal (cheap → authoritative).** Published version + patch + revision date from the
re-crawled catalog (cheap pre-filter) → HTTP conditional GET (ETag / Last-Modified) where VDL
supplies it → **sha256 of the fetched bytes as ground truth**. VDL frequently re-posts the same
filename for a new patch and rarely sends reliable validators, so the **content hash — already held
in the CAS — is the dependable drift signal**; metadata only narrows the candidate set to hash.

**Metrics.** Per document: `last_checked_at`, `last_changed_at`, `corpus_version`,
`upstream_version`, `staleness_age`.

**Gate (corpus-level, not per-document).** Currency does **not** retroactively void a faithful
migration — a STALE document was still faithfully migrated *for the version it captured*, so it
does not flip a per-document PASS to QUARANTINE. Instead the **corpus** may claim *"current"* only
if every non-WITHDRAWN document is CURRENT (or STALE-with-reprocessing-queued) **and** the whole
corpus was checked within the SLA. STALE-and-unqueued or mass-UNCHECKED fails the corpus currency
claim. This keeps per-document *faithful* (§8) and corpus *current* as separate, non-conflated
assurances.

**Self-healing (detection feeds the pipeline, not a human).** A STALE/NEW document is re-processed
incrementally (only it flows down the DAG) and, if it is a new patch of an existing document,
becomes the new latest member of its version group: the **anchor document updates, the prior body
is retained, `history.yaml` is appended** (vdocs-design §6.6). The re-processed document is then
**re-scored by §5–§7 automatically**, so migration fidelity and currency stay jointly true over
time. An always-current corpus and a complete patch lineage are two outputs of one incremental loop.

---

## 8. Scoring and the gate

**Per-document composite** uses a **weakest-link + weighted-average hybrid** so a great score
in one dimension can never mask a destroyed dimension:

```
content_composite = Σ wᵢ · Cᵢ           (weights wᵢ: tables & cross-refs weighted high for
                                          technical manuals; defaults below, tunable + recorded)
verdict:
  QUARANTINE  if  any Cᵢ < hard_floorᵢ
              or  provenance gate fails
              or  any lossy construct = flagged-lost
              or  content_composite < 0.90
  REVIEW      if  not QUARANTINE
              and (content_composite < target_band  OR  any Cᵢ in [floor, target))
  PASS        if  all Cᵢ ≥ targetᵢ  and  composite ≥ 0.98  and  provenance+history gates pass
```

Default content weights: C1 text 0.25 · C2 structure 0.15 · C3 tables 0.25 · C4 images 0.10 ·
C5 cross-refs 0.15 · C6 lists 0.10. (Recorded per run; re-tuned only with re-calibration §9.)

- **PASS (green)** — auto-publishable as faithful.
- **REVIEW (amber)** — human spot-check + sign-off before publish; the reviewer's verdict is
  recorded and feeds re-calibration.
- **QUARANTINE (red)** — mandatory manual remediation; **never** auto-published as faithful.
  This is the explicit, sized "remediation tail" (§13).

**Currency is a parallel, corpus-level verdict (§7.5).** The PASS/REVIEW/QUARANTINE gate above is
the *migration*-fidelity verdict for the version a document captured; the upstream moving on does
not void it. Whether the corpus is *current* is the separate currency gate — tracked per document
as a state and rolled up at corpus level (§10). The two claims, "faithful" and "current," are
reported independently.

**Template self-conformance feeds the gate; canonical compliance does not (§5 C2).** A document
missing a section its *own* template guarantees is treated as a structural defect — it escalates to
**REVIEW**, or **QUARANTINE** if the missing element implies dropped content — because it signals the
*pipeline* failed. **Canonical** non-compliance never blocks: a faithfully-migrated but structurally
old guide is still faithful; it is recorded as a modernization item in the §10 rollup, not a gate
failure. (Keeping these apart prevents penalizing the migration for the source's own structural drift.)

---

## 9. Calibration & validation — the credibility engine

This is what converts the automated composite from "a number we made up" into "a predictor of
true fidelity, validated against human ground truth at a stated confidence." Without it the
framework is unconvincing to an institution; with it, the institution can trust PASS without
re-reading every document.

1. **Golden sample.** A **stratified random sample** across app, doc_type, and complexity
   (sized for the target confidence/margin — e.g. a few hundred documents for a ~3k corpus).
2. **Human rating.** Trained reviewers rate each sampled document's true fidelity per axis on a
   defined rubric, blind to the automated score. Capture **inter-rater reliability** (e.g.
   Cohen's/Krippendorff's α) to prove the human signal itself is reliable.
3. **Validate the predictor.** Measure agreement between the automated verdict and human
   judgment (confusion matrix, ROC/AUC of the composite vs human pass/fail). Establish the
   key institutional claim, e.g. *"automated-PASS documents are human-confirmed faithful at
   ≥99% (95% CI …)"* and *"the gate's false-PASS rate is ≤ X%."*
4. **Set thresholds from data.** The §5/§8 floors and targets are *fitted* so that PASS
   achieves the required confidence — not guessed.
5. **Re-calibrate on change.** Any change to the converter, reference extractor, or framework
   re-runs calibration; thresholds and the predictor claim are versioned with the toolchain.

---

## 10. Corpus-level assurance & acceptance sampling

Beyond per-document verdicts, the institution needs a *corpus* statement with confidence:

- **Rollup:** N documents; % PASS / REVIEW / QUARANTINE; per-dimension score distributions;
  the remediation-tail list (every QUARANTINE/REVIEW doc, with its failing dimension).
- **Acceptance sampling (AQL-style).** Even among auto-PASS documents, audit a continuing
  random sample to maintain a *measured* published-fidelity error rate with a confidence
  interval — the same statistical QA discipline used in regulated manufacturing, and highly
  defensible to an institution. Publishes a standing claim like *"audited published error rate
  ≤ X% at 95% confidence."*
- **Tail sizing.** The single most useful number for an institutional decision:
  *"M% of the corpus migrates clean (PASS); R% needs human remediation — here is the exact
  list and the estimated effort."* This turns an open-ended fear into a budgeted task.
- **Freshness rollup (currency, §7.5).** The temporal sibling of the per-document rollup: the
  currency-state distribution (CURRENT / STALE / UNCHECKED / WITHDRAWN), the last full-corpus
  check timestamp, the count of superseded documents currently re-processing, and the standing
  claim *"X% CURRENT; whole corpus checked within N days; 0 STALE-unqueued."*
- **Template-compliance rollup (§5 C2 template conformance).** Per `doc_type`: the share of
  documents conforming to the **canonical** schema, the distribution of deviations, and the divergent
  list — e.g. *"73% of user guides conform to the canonical user-guide template; 27% are pre-canonical
  structural drift (modernization backlog)."* Separately, the count of **template-self-conformance
  failures** — documents missing a section their own template guarantees — which is the pipeline-bug
  signal, not a source-drift signal. The first is a corpus-quality statement; the second is a build
  health metric.

---

## 10.5 Retrieval-quality measurement (search fidelity)

The axes above measure *migration* fidelity (faithful `S`→`T`) and *currency*. They do **not** measure
whether the machine interface actually returns the right thing — and condensing the corpus (anchor
docs, dedup, boilerplate/phrase registries) is done largely *to improve retrieval*. That benefit must
be **measured, not asserted** — the same discipline §9 applies to migration. Retrieval quality is a
distinct, machine-facing axis over the **search corpus** (`index.db` + `vectors.db`), separate from
the per-document migration verdict.

**The layering it validates.** Search corpus ≠ evidence corpus (vdocs-design §14.6): the
index/embeddings are curated and **anchor-only**; bronze + history is complete and immutable. This
section measures the *former* (does search work) without touching the *latter* (provenance).
Condensation should *raise* retrieval quality at *zero* fidelity cost — and we prove **both**, so the
design's central bet (whole-source fidelity *and* condensed machine-discoverability) is verified on
its machine half, not just its human half.

**Golden query set.** A labeled set of representative queries — factual lookups, entity/RPC/file-number
queries, cross-document questions, and **version-sensitive** questions — each with human-judged
relevant sections (by stable ID), stratified across app, doc_type, and query kind and sized for a
target confidence (as in §9). Inter-annotator agreement is recorded so the relevance labels are
themselves trustworthy.

**Metrics — per mode (semantic · lexical · hybrid-RRF), each measured independently:**
- **precision@k / recall@k / nDCG / MRR** against the judged-relevant set.
- **redundancy@k** — share of top-k that are near-duplicates of a higher-ranked hit; the direct
  payoff of single-sourcing + anchor-only indexing (target ≈ 0).
- **over-strip rate (chunk self-sufficiency — the condensation guardrail).** Condensation raises
  signal-to-noise only up to a point: strip past it and a chunk loses the context that lets it stand
  alone, embedding as an unanchored fragment that *hurts* recall (vdocs-design §6.5 — the
  don't-over-decompose optimum; the curve peaks then falls). This metric is the precision counterpart
  to `redundancy@k`: over each section-chunk of the condensed body, the share that are **hollow** —
  a content heading whose retained body falls below a substantive-token floor **and** carries no
  resolvable referent (no `_shared/` boilerplate link, `tables/*.csv` stub, or asset reference that
  would re-supply the meaning). A chunk reduced to a *referent* (content relocated, not lost) is **not**
  counted — that is by-design decomposition, dereferenced before scoring (§4); only a chunk stripped to
  a bare heading is a defect. Container headings (those whose substance lives in subsections) are
  excluded. Target ≈ 0; any hollow content chunk drops the document below PASS (never silently faithful),
  and a body that is mostly hollow QUARANTINEs. Computed at the `fidelity` stage from `text@normalized`
  chunk segmentation — no source needed, so it is a pure, deterministic, T-only check (the
  `overstrip_pure` kernel), and it is the search-corpus enforcement of the §6.5 guardrail.
- **version-correctness** — share of hits that are `is_latest`; with anchor-only indexing this should
  be ~100%, and any stale hit is a defect.
- **answer-correctness** — for RAG-style use, whether the retrieved context supports the correct
  answer (LLM-judged against a key, human-audited).

**Ablation (the causal claim).** Run the golden set **with vs. without** condensation
(boilerplate/phrase removal, anchor-only indexing). The delta quantifies the lift — turning
"redundancy hurts retrieval" from a belief into a measured number with a confidence interval. Re-run
on any change to chunking, the embedding model (its id+version gates `vectors.db`), or the registries.

**Gate / rollup.** A standing retrieval-quality claim — e.g. *"hybrid nDCG@10 = 0.x (95% CI …);
redundancy@10 ≤ y%; 100% of hits current"* — published alongside the migration and currency rollups
(§10). A regression below threshold blocks release of the **search index** (the human corpus is gated
separately, §8) — so the machine interface cannot silently degrade.

**Why it belongs in this framework.** It shares the spine: deterministic, reproducible,
human-calibrated, versioned with the toolchain — the same credibility engine (§9) applied to search
instead of conversion.

---

## 11. Reproducibility, lineage, audit

Every per-document fidelity record stores: `source_sha256`, `target_sha256`, reference-extractor
version, converter version, framework version, weights/thresholds used, timestamp, and the human
reviewer verdict if any. Because the bronze originals are retained immutably and scoring is
deterministic, **any party can recompute every score at any time** and get the same answer.
Reproducibility *is* auditability — a regulator verifies rather than trusts. The fidelity report
is itself a versioned, signed artifact.

---

## 12. Outputs

**Per-document fidelity record** (one JSON per document; illustrative shape):

```json
{
  "doc_id": "...", "source_sha256": "...", "target_sha256": "...",
  "framework_version": "1.0", "converter_version": "...", "ref_extractor_version": "...",
  "scored_at": "2026-06-01T...Z",
  "content": {
    "C1_text": {"recall": 0.992, "precision": 0.998, "paragraph_coverage": 0.99},
    "C2_structure": {"score": 0.97, "template_id": "user-guide/2008",
                     "template_self_conformance": 1.0, "canonical_compliance": 0.82,
                     "missing_required_sections": []},
    "C3_tables": {"count_recall": 1.0, "cell_recall": 0.991},
    "C4_images": {"recall": 1.0, "caption_recall": 0.95},
    "C5_xref": {"recall": 0.98, "dead_anchor_rate": 0.0,
                "toc": {"accuracy": 1.0, "completeness": 1.0, "dead_anchors": 0, "round_trip": 1.0}},
    "C6_lists": {"recall": 0.99},
    "over_strip": {"content_chunks": 41, "over_strip_rate": 0.0, "hollow": [], "verdict": "PASS"},
    "C7_constructs": [{"type": "text_box", "count": 2, "disposition": "sidecar"}],
    "composite": 0.985
  },
  "provenance": {"sha256_verified": true, "completeness": 1.0, "score": 1.0},
  "history": {"revision_recall": 1.0, "version_coverage": 0.93,
              "scope": "published-version granularity; pre-publication edits out of scope"},
  "currency": {"state": "CURRENT", "corpus_version": "...", "upstream_version": "...",
               "last_checked_at": "2026-06-01T...Z", "last_changed_at": "2026-05-12T...Z"},
  "verdict": "PASS",
  "human_review": null
}
```

**Corpus fidelity report** — the §10 rollup + distributions + remediation tail + the §9
calibration result + the acceptance-sampling claim.

**Institutional scorecard** — a one-page human-readable summary: the headline claims (PASS %,
confidence, error-rate ceiling, tail size + effort), suitable for a decision-maker.

---

## 13. Lossy-construct inventory & the remediation tail

C7 produces, per document, an inventory of every construct markdown cannot natively hold, each
with a disposition (`converted` / `sidecar` / `flagged-lost`). Any `flagged-lost` forces
QUARANTINE. Aggregated across the corpus this *is* the remediation tail: a finite, enumerated,
estimable list of documents needing human attention — never a silent loss. The institution sees
exactly what doesn't migrate cleanly and what it costs to fix, before deciding anything.

---

## 14. What this framework deliberately does NOT measure

Stated plainly, because naming the limits is what makes the rest credible:

- **Visual/layout pixel fidelity.** Intentional — wrong bar (§1). We preserve information, not
  pagination, fonts, or page breaks.
- **Internal pre-publication edit trails.** Tracked changes and VA internal DMS audit logs are
  not in the public artifacts and cannot be reconstructed (§7 H3).
- **Correctness of the original.** We measure faithful *transfer*, not whether the source
  document was itself accurate or current.
- **Cross-renderer rendering equivalence.** We validate well-formed GFM, not identical
  rendering across every possible markdown viewer.
- **Reference-extractor perfection.** The independent extractor is imperfect; §9 human
  calibration is precisely what bounds and accounts for that.

---

## 15. How it plugs into vdocs

- Runs as a measurement over `convert`/`normalize` output against the retained bronze source —
  naturally a contract-bound stage (`fidelity`, gold-derive layer) producing the per-document
  records and the corpus report, fingerprinted and lineage-stamped like every other stage.
- The **`validate` hard gate consumes it**: a document may be published as *faithful* only if
  it is PASS, or REVIEW with a recorded human sign-off. QUARANTINE blocks publication.
- It depends on and reinforces the design's load-bearing decisions: **bronze immutability**
  (ground truth to score against), **determinism** (reproducible/auditable), **stable IDs**
  (anchor resolvability in C5), and **lineage** (every score traceable).
- **The scheduled change-detection pass drives re-scoring (currency, §7.5).** A periodic
  crawl-diff (`vdocs refresh`, vdocs-design §7.6) detects upstream drift and re-runs only the
  changed documents through convert → normalize → `fidelity`, so each per-document record is
  refreshed when — and only when — its source changes. Currency and migration fidelity are thereby
  kept jointly true without re-scoring the whole corpus on every run.

---

## 16. The decision this unlocks

This framework is the resolution of the catch-22. Because it can be run **unilaterally over the
already-public VDL corpus** — no institutional change required — it produces, as finished
evidence: the migrated corpus, a measured per-document fidelity verdict, a calibrated confidence
claim, a sized remediation tail, and a cryptographic provenance chain to every official source,
all reproducible against retained originals. The institution then evaluates *a completed,
measured, reversible migration* rather than committing to a promise. The proof is the product;
this framework is how the proof is made measurable and defensible.
