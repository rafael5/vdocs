# Document Sidecar Design

**Status:** Design note (self-contained). **Date:** 2026-06-03.
**Companion to:** [`vdocs-design.md`](vdocs-design.md) (§5.2, §6.3–§6.7, §8) and
[`fidelity-framework.md`](fidelity-framework.md) (C2, C5, H1–H2, §6 provenance).
**Audience:** the implementer, and anyone deciding whether the sidecar split is sound enough
to certify migration fidelity.

This note answers three questions in one place: **what** the per-document sidecars are, **why
they are not uniform** across bundles and what the explicit split criteria are, and **how** they
are (and are not yet) consumed to raise and verify the quality of the final gold documents. It
closes with an honest audit of the verification gap and recommendations drawn from how other
large documentation/content-modernization efforts handle the same problem.

---

## 1. What a sidecar is, and the bundle that holds it

A gold/silver document is not one file — it is a **bundle**: a directory named for the
version-free document slug, containing `body.md` (prose + identity frontmatter) plus zero or
more *typed sidecar parts* that carry structured information lifted out of the prose
(`vdocs-design.md` §5.2). The body stays human-browsable markdown; the sidecars hold the
machine-owned structure that does not belong in running prose.

Per-document sidecars, emitted by the **`normalize`** stage
(`src/vdocs/stages/normalize/stage.py:13-21`, design §6.4/§6.7):

| Sidecar | Holds | Emitted at | Design § |
|---|---|---|---|
| `revisions.yaml` | this version's own revision-history table — entries (`date`, `version`, `pages`, `change`, `refs`) + `revision_newest` | `stage.py:148-155` | §6.4 |
| `tables/*.csv` | qualifying complex data tables lifted out of prose; the body keeps a reference link | `stage.py:156-160` | §6.4/§6.5 |
| `refs.yaml` | the `(stable_section_id ↔ github_slug ↔ original_bookmark)` anchor map + chosen `toc_depth` + outbound cross-ref map | `stage.py:161-168` | §6.7/§5.5 |
| `toc.yaml` | the original paper-era table of contents, captured verbatim **before** the legacy TOC leaves the body | `stage.py:172-181` | §6.7 |
| `flags.yaml` | fidelity signals: uncaptured title-page date, unparseable revision apparatus, unresolved legacy-TOC anchors | `stage.py:185-194` | §6.4/§6.7 |

One group-level sidecar, emitted by the **`consolidate`** stage per version group
(`src/vdocs/stages/consolidate/stage.py`, design §6.6):

| Sidecar | Holds | Emitted at | Design § |
|---|---|---|---|
| `history.yaml` | the ordered patch lineage of the whole version group — per member: `doc_id`, `version`, `patch_id`, `official_date`, `source_sha256`, `body_sha256` (CAS ref to the retained body), `is_latest`, and the member's folded `revisions` | `stage.py:96-102` | §6.6 |

The `TEXT_NORMALIZED`/`CONSOLIDATED` contracts are `TREE_*` over the whole bundle, so a sidecar
needs no separate contract — it travels with the bundle (`stage.py:13-14`).

---

## 2. Why sidecars are *not* uniform — the explicit split criteria

> **Short answer to "shouldn't every bundle carry the same sidecars?": no — and deliberately
> not.** A sidecar is emitted **iff the structure it represents was present in the source and
> was successfully captured.** The *rule* is uniform; the *resulting file set varies per
> document*. Absence is treated as a meaningful state, not a defect.

Each write is gated in `normalize/stage.py`:

- **`revisions.yaml`** — `if revisions:` (`stage.py:148`). Emitted only when a revision-history
  table is detected **and parses**. If a revision heading is found but the table is unparseable,
  the apparatus is **left in the body and a flag is raised** (`rev_flag`, `stage.py:110-112`) —
  never deleted blind. This is the capture-before-strip fail-safe in action.
- **`tables/*.csv`** — `for tab in tables:` (`stage.py:156`). One CSV per qualifying table;
  nothing written when no table qualifies.
- **`refs.yaml`** — `if anchor_map.rows:` (`stage.py:161`, comment: *"conditional, like
  revisions.yaml — no anchors → no sidecar"*). Needs at least one heading.
- **`toc.yaml`** — `if anchor_map.legacy_toc:` (`stage.py:172`). Only the ~small fraction of
  docs that shipped a paper TOC produce one.
- **`flags.yaml`** — `if doc_flags:` (`stage.py:185`). Only when at least one fidelity signal
  was raised this run.

At the group level, `consolidate` propagates a sidecar only when the **latest** member has one:
`flags.yaml` (`stage.py:90-91`) and `toc.yaml` (`stage.py:94-95`) travel with the anchor only
`if latest.doc_id in flag_bytes / toc_bytes`. `history.yaml` is the one sidecar **always**
written, because the lineage record always exists for a group.

### 2.1 Why uniformity would *lower* fidelity signal

The design treats **presence as data** (the same "discovery is data, not code" tenet that drives
the registries). Three reasons the asymmetry is intentional:

1. **An empty sidecar lies.** A `revisions.yaml` with zero rows is indistinguishable from "this
   document genuinely has no revision history" — but those are very different fidelity facts.
   *Absence* plus an optional `flags.yaml` entry distinguishes "nothing to capture" from
   "something was there and we could not parse it."
2. **`flags.yaml` is the catch-all that makes the asymmetry safe.** The §6.4 fail-safe is
   *nothing leaves the body without a trace*. You do not need every bundle to carry every
   sidecar — you need every *uncaptured or dropped* construct to leave a flag.
3. **Cost and noise.** Forcing `toc.yaml` onto the majority of docs with no paper TOC just
   creates empty files for QA to wade through, diluting the signal that a present file carries.

Real-run shape confirms the sparsity by design: ~469 normalized docs against only ~22
`revisions.yaml` (implementation tracker). Most VA manuals carry neither a revision table nor a
legacy TOC.

### 2.2 The one invariant that *is* uniform

The fail-safe — **every uncaptured structure leaves a `flags.yaml` trace** — is the uniform
guarantee. The file *set* is not uniform; the *no-silent-loss* property is. This is the load-
bearing contract for everything in §3 and §4.

---

## 3. How sidecars raise and verify gold quality

### 3.1 Ordering and currency — `revisions.yaml` → `history.yaml`

`consolidate` folds each member's `revisions.yaml` into the group lineage
(`_fold_revisions`, `stage.py:150-156`) and computes `official_date` = the revision table's
newest date when captured, **else** the title-page `published` date baked into identity
frontmatter (`_member_from`, `stage.py:130-132`; `consolidate_pure.official_date`). That date is
the sort key that orders a version group oldest→newest and selects the latest member as the
anchor body. It also feeds the currency/freshness axis (fidelity §7.5) and the change-history
gate **H1** (revision-narrative recall ≥ 0.98).

### 3.2 TOC integrity — `toc.yaml` + `refs.yaml`

`toc.yaml` (original page-numbered entries, captured verbatim before strip) cross-checked against
`refs.yaml` (the derived anchor map) is what makes the **C5 TOC-integrity hard gate** computable:
round-trip every original entry to a live anchor, target **TOC dead-anchor = 0** (fidelity §5
C5). `refs.yaml` also records the `toc_depth` `normalize` chose, so `index` rebuilds the contents
at the same depth, and section IDs derive from its `stable_section_id`.

### 3.3 Loss visibility — `flags.yaml`

`flags.yaml` carries the capture-before-strip signals to the gold grain (it travels with the
anchor, `consolidate/stage.py:88-91`) so a retained/flagged residue is visible where QA reads it.
It is the input the structural-fidelity **C2** oracle is meant to consume.

### 3.4 Provenance and latest-member — `history.yaml`

Each lineage member carries `source_sha256` — the byte-for-byte provenance against the retained
bronze original (the fidelity §6 **HARD GATE**) — and the `body_sha256` CAS ref to its retained
normalized body, kept write-once in `gold/_shared/history`. `index` reads every `history.yaml`
to mark which member of each group is `is_latest` (design §14.6).

---

## 4. Verification status — honest audit (the open gap)

> **Status (2026-06-03): being closed.** The recommendations in §5.1/§5.2/§5.5 are now folded into
> the architectural source of truth (`vdocs-design.md` §6.4 typed `capture.yaml`; §8 `validate`
> sidecar-verification slice) and `fidelity-framework.md` (C2 count reconciliation, C5 ref-resolution
> gate). The chosen typed-absence mechanism is a **new per-bundle `capture.yaml`** (not an extension
> of `flags.yaml`) — see §5.1 for the decision rationale. The section below describes the gap **as it
> stood before** that work, and remains the reference for *why* each change exists.

The caveat that motivated this note is real and was, until this work, **unmitigated**. Verification of
sidecars was specified but **not implemented**, and a missing sidecar was therefore ambiguous
in the running code.

**What exists:**

- `fidelity/compliance_pure.py` — a pure template-conformance oracle (§9.8). It scores `body.md`
  headings against an expected `(doc_type, era)` template schema and returns PASS / REVIEW /
  QUARANTINE (`score_extraction_compliance`, `blocks_publish`). **It reads only `body.md`
  headings** (`_heading_titles`, `compliance_pure.py:58-61`) — it never opens any sidecar.
- `normalize` emits per-sidecar counts in `RunResult.counts` (`stage.py:202-219`:
  `revision_sidecars`, `tables_sidecars`, `refs_sidecars`, `toc_sidecars`, `flag_sidecars`),
  persisted to `state.db:stage_runs[counts]`.

**What does not exist yet:**

- **No `fidelity/stage.py` and no `validate` stage.** Phase 5 (`fidelity`·`validate`) is `☐
  TODO` in the implementation tracker. `compliance_pure.py:16-18` itself says the `stage.py`
  driver "lands with Phase 5."
- **No consumer of the sidecar counts.** Nothing reads `stage_runs[counts]` to compare expected
  vs. actual emission (e.g. "0 `tables/*.csv` across 469 docs ⇒ table extraction likely
  silently broke").
- **No benign-vs-failure absence classification.** `consolidate` reads sidecars only
  `if path.is_file()` and treats absence as benign with no flag and no log:
  `_fold_revisions` returns `([], "")` for a missing file (`stage.py:150-156`); `flags.yaml` /
  `toc.yaml` are read only when present (`stage.py:66-71`).

**Verdict:** the *design* is sound — conditional emission, capture-before-strip fail-safes, and
emitted counts give verification everything it needs. But the harness that would *use* those
signals is not built. Until it is, these absences are indistinguishable in code:

| Sidecar missing | Benign meaning | Failure meaning | Trace today |
|---|---|---|---|
| `revisions.yaml` | no revision table in source | extraction silently failed | flag **only** if a revision heading was detected but unparsed; **no flag** if detection itself missed a real table |
| `tables/*.csv` | no qualifying tables | table extraction failed | **none** |
| `refs.yaml` | no headings | anchor pass failed | **none** for the file itself |
| `toc.yaml` | no paper TOC in source | TOC capture failed | **none** |

The `flags.yaml` fail-safe covers the cases where a strip step *fires* but cannot fully parse.
It does **not** cover the cases where a *detector* never fires on a structure that was actually
present — that class of silent loss is invisible until a verification stage compares against the
source or against corpus-level expectations.

---

## 5. Recommendations — aligning with industry practice

These map the gap in §4 onto how comparable large documentation/content-modernization and
data-pipeline systems solve it.

### 5.1 Make absence a typed verdict, not a missing file

Borrow the **explicit-null vs. missing** distinction that data-quality frameworks enforce.
Great Expectations treats a value as exceptional only when it is *clearly* null, separating a
true absent value from an empty string or default — and lets you assert
`ExpectColumnValuesToBeNull` early in a pipeline and `…ToNotBeNull` later, so completeness is
checked *per stage* as data flows down
([Great Expectations — managing missing data](https://docs.greatexpectations.io/docs/reference/learn/data_quality_use_cases/missingness/)).
Apply the same idea: have `normalize` always record, per bundle, **why** each sidecar is absent —
`absent_expected` (detector ran, nothing present) vs. nothing-recorded (which a verifier then
reads as `absent_unexpected`). A cheap implementation: extend `flags.yaml` (or a tiny
`capture.yaml` manifest) to log every capture *attempt* and its outcome, so absence always has a
provenance record. This is the single highest-value change.

> **Decision (2026-06-03): a new per-bundle `capture.yaml`, not an extension of `flags.yaml`.**
> The two files have opposite lifecycles. `flags.yaml` is **sparse** — written only when a strip step
> fired-but-failed, and its load-bearing property (§2.1, §2.2) is exactly that *a present flags file
> means attention is needed*. A typed-absence manifest is **dense and always present** (every bundle
> has the same capture attempts, mostly benign `absent-expected`). Folding it into `flags.yaml` would
> force that file to be written for every bundle and dominated by benign records — destroying the
> sparse-signal property §2 relies on. `capture.yaml` keeps the two concerns separate (exceptions vs.
> completeness manifest), matches the *explicit-null vs. missing* distinction directly, and is the
> natural seed for the §5.3 signed bundle manifest (parts + hashes + outcomes) — which `flags.yaml`
> could never become. Four outcomes are recorded: `captured`, `failed` (recognised-but-unparseable),
> `absent-expected` (detector ran, residue re-scan agrees), and `absent-unexpected` (detector found
> nothing but an independent residue re-scan still sees the structure — a per-document silent miss).
> The residue re-scan is what catches a *single* doc's silent miss; corpus count reconciliation (§5.2)
> catches whole-detector failures. Both are gated by `validate`. See `vdocs-design.md` §6.4 / §8.

### 5.2 Add the expected-vs-actual reconciliation the counts already enable

`normalize` already emits per-sidecar counts; nothing consumes them. The data-quality norm is a
**completeness check** that compares produced rows against an expectation and fails the run on
drift (the completeness dimension in
[GX/PySpark validation](https://medium.com/99p-labs/data-validation-measuring-completeness-consistency-and-accuracy-using-great-expectations-with-c0ad2924e425)).
Wire a verification step that reads `stage_runs[counts]` and trips when an aggregate is
implausible (e.g. zero tables corpus-wide, or a sidecar count that drops between runs without a
corresponding source change). Cheap, corpus-level, and catches whole-detector failures that
per-doc flags cannot.

### 5.3 Treat sidecars as a signed provenance manifest

The content-provenance world (C2PA Content Credentials) standardizes exactly this pattern: a
**sidecar file alongside the asset** carrying a manifest, used when you cannot or should not
embed metadata in the asset itself
([Content Authenticity — understanding manifests](https://opensource.contentauthenticity.org/docs/manifest/understanding-manifest/)).
`history.yaml` already carries `source_sha256` + `body_sha256`; the natural next step is to make
the **bundle manifest** the verifiable unit — enumerate every part with its hash and its
capture-outcome — so a skeptic can verify the bundle is complete and untampered, which is the
fidelity framework's stated bar ("provable, not asserted").

### 5.4 Adopt step-level input/output attestation across the DAG

Supply-chain frameworks (SLSA / in-toto) record the materials (inputs) and products (outputs) of
each pipeline step so you can prove step A's output X was the input to step B
([artifact provenance & attestations](https://secure-pipelines.com/ci-cd-security/artifact-provenance-attestations-slsa-in-toto/)).
vdocs is a 17-stage DAG with content-addressed artifacts — it is unusually well-positioned to
record, per stage, "consumed these sidecars, produced those," turning the §4 gap (no
cross-stage reconciliation) into a checkable chain. ML-lifecycle provenance systems extend the
same C2PA sidecar with per-step attestations
([Atlas framework](https://arxiv.org/html/2502.19567v2)) — the same shape applies here.

### 5.5 Audit the references that sidecars create — they are fragile

DITA migrations report that the most common silent-loss mode is a **severed cross-reference**: a
`conref` whose target id changed is silently broken, and standard practice is to *manually audit
conrefs and cross-topic links* and run a full validation build, because validators are what keep
the source clean over time
([DITA conref resolution](https://www.dita-ot.org/dev/reference/preprocess-conref.html);
[RWS structured-content migration guide](https://www.rws.com/content-management/tridion/resources/dita-ccms-migration-guide-template/)).
`refs.yaml`'s anchor + outbound-link map is vdocs' direct analogue. The `validate` hard gate
should resolve every outbound ref recorded in `refs.yaml` against the live anchor set and fail on
any dead anchor — the same round-trip the C5 gate already specifies, generalized to all
cross-refs, not just TOC entries.

### 5.6 Priority order

1. **§5.1** — record capture-attempt outcomes so absence is never ambiguous (fixes the core gap).
   **— specified + implemented** (per-bundle `capture.yaml`, `normalize`; vdocs-design §6.4).
2. **§5.2** — reconcile emitted counts in a verification step (catches whole-detector failures).
   **— specified + implemented** (`validate` count-reconciliation gate; vdocs-design §8, FF C2).
3. **§5.5** — resolve `refs.yaml` outbound links in the `validate` gate (catches the fragile-ref class).
   **— specified + implemented** (`validate` ref-resolution gate; vdocs-design §8, FF C5).
4. **§5.3 / §5.4** — bundle manifest + per-stage attestation (raises the proof from "flagged" to
   "verifiable"). **— deferred** (stretch; `capture.yaml` is the seed but the signed manifest is not built).

---

## 6. Summary

- Sidecars are **typed parts of a bundle**, split off by `normalize` (`revisions.yaml`,
  `tables/*.csv`, `refs.yaml`, `toc.yaml`, `flags.yaml`) and `consolidate` (`history.yaml`).
- They are **deliberately non-uniform**: emitted iff the structure was present and captured.
  Uniformity would erase the distinction between "nothing to capture" and "capture failed."
- The uniform invariant is the **fail-safe**, not the file set: nothing leaves the body without a
  `flags.yaml` trace — *when a strip step fires*.
- They raise quality via ordering/currency (`revisions`→`history`), TOC integrity
  (`toc`+`refs`), loss visibility (`flags`), and provenance (`history.source_sha256`).
- **The verification harness that would consume these signals is not yet built** (Phase 5
  `fidelity`/`validate` are TODO), so a missing sidecar is currently ambiguous in code. §5 gives
  the industry-aligned path to close that: typed absence, count reconciliation, ref resolution,
  and a signed bundle manifest.
