# Proposal — FileMan **Integrated Master**: the VDL → docs-as-code proof of concept

**Status:** proposal / for sign-off. **Date:** 2026-06-16. **Author:** Claude (Opus 4.8) with Rafael.
**Pilot package:** `DI` (VA FileMan 22.2, official 2025-07).
**Builds on:** [`docs-as-code-master-publication-proposal.md`](docs-as-code-master-publication-proposal.md)
(the source-of-truth inversion + `publish`/L3 stage) and
[`rich-publication-and-pdf-export-proposal.md`](rich-publication-and-pdf-export-proposal.md)
(`kernel/figures.py` asset substrate).

> **Why this proposal is distinct.** The master-publication proposal flips *each* gold document into a
> self-contained github-native `.md` **1:1** — same nine FileMan manuals, just materialized. This
> proposal does the harder, higher-value thing the user actually asked for: **consolidate the nine
> overlapping FileMan manuals into one integrated, internally-consistent master set**, and use that
> single well-bounded package to prove out the four migration requirements end-to-end —
> github-as-truth, docs-as-code, **100% proofread**, and **every code example live-tested on a working
> VistA, in real code blocks**. FileMan is the right pilot: foundational, stable (22.2 is the long-term
> baseline), heavily code-bearing, and closed (one package, nine docs, one DBA namespace).

## Table of contents

- [1. What the current FileMan gold set actually is](#1-what-the-current-fileman-gold-set-actually-is)
- [2. The three defect classes a master must fix](#2-the-three-defect-classes-a-master-must-fix)
- [3. The consolidation thesis — integrate, don't mirror](#3-the-consolidation-thesis--integrate-dont-mirror)
- [4. Target information architecture — the integrated master set](#4-target-information-architecture--the-integrated-master-set)
- [5. Requirement #4 — code in code blocks, live-tested on VistA](#5-requirement-4--code-in-code-blocks-live-tested-on-vista)
- [6. Requirement #3 — 100% proofread, as a gate](#6-requirement-3--100-proofread-as-a-gate)
- [7. Requirements #1 & #2 — github-as-truth, docs-as-code](#7-requirements-1--2--github-as-truth-docs-as-code)
- [8. Requirement #5 — additional ideas to de-risk the migration](#8-requirement-5--additional-ideas-to-de-risk-the-migration)
- [9. Phased plan](#9-phased-plan)
- [10. Decisions & open questions](#10-decisions--open-questions)

---

## 1. What the current FileMan gold set actually is

Grounded in the lake at `gold/consolidated/DI/<slug>/` (2026-06-16). Nine documents, **~63,700 lines /
~2.9 MB of markdown**, all FileMan 22.2, all dated 2025-07. Each is a `body.md` + sidecars
(`tables/*.csv`, `toc.yaml`, `bundle.yaml`, `history.yaml`, `flags.yaml`).

| slug | type | what it is | lines | md tables | csv | fig/example captions |
|---|---|---|---:|---:|---:|---:|
| `fm22_2dg` | DG | **Developer's Guide** (Programmer Manual) — the DBS/classic API reference | 25,475 | 315 | 53 | 528 |
| `fm22_2um2` | UM | **User Manual, Vol 2** — end-user roll-and-scroll reference | 14,424 | 290 | 9 | 404 |
| `fm22_tutorial` | TRG | **Getting Started** — orientation tutorial | 5,706 | 171 | 1 | 1 |
| `fm22_2um1` | UM | **User Manual, Vol 1** — end-user roll-and-scroll reference | 5,334 | 76 | 7 | 151 |
| `scrn_tut` | TRG | **ScreenMan Tutorial** | 4,512 | 58 | 0 | 25 |
| `dde_tutorial` | TRG | **DDE Utility Tutorial** (advanced) | 3,339 | 0 | 0 | 105 |
| `fm22_2tm` | TM | **Technical Manual** — install/admin, files, globals | 2,814 | 98 | 5 | 32 |
| `fm22_2p8_dac_ug` | UG | **Data Audit (DAC) User Guide** — patch `DI*22.2*8` | 1,596 | 14 | 2 | 36 |
| `fm22_krn8_file_security` | SG | **File Security** (Kernel 8 cross-ref) | 484 | 4 | 0 | 3 |

**The overlap is the story.** These nine docs were authored as separate Word deliverables over two
decades and re-explain the same FileMan concepts from different angles:

- **Two user-manual volumes** (`um1`+`um2`, ~20K lines) are one reference arbitrarily split by Word
  page count, not by topic.
- **Three tutorials** (`tutorial`, `scrn_tut`, `dde_tutorial`) each re-teach features the user manuals
  also document — ScreenMan, Browser, Inquire, editing — with their own walkthroughs.
- **The Developer's Guide** (40% of the corpus) is the API reference and barely overlaps the
  end-user material, but shares terminology that drifts between docs.
- **Technical Manual + File Security** overlap on access/security/file-protection.

A 1:1 materialization preserves all of that redundancy and drift. The user asked to **consolidate** —
that is the value.

## 2. The three defect classes a master must fix

Measured across the nine `body.md` files — these are the concrete, countable gaps between "ingested
gold" and "publishable, proofread, code-true master":

1. **Zero code blocks.** ` ```fence ` count across all nine docs = **0**. Every M example is rendered
   as **bold inline text** and every global listing as an escaped prose paragraph. From `fm22_2dg`:

   > **S DIC="^DIZ(662001,",L=0,BY=.01,(FR,TO)="",FLDS="your field list"**
   > **S BY(0)="^TMP(\$J,"**

   and `^TMP(\$J,3)=""` as a plain line. There are **~135 bold-as-code lines** and **~1,180
   backslash-escaped `\$`/`\_`/`\*` artifacts**. Code is neither syntactically marked, copyable,
   highlightable, nor testable. This is the single biggest fidelity gap and directly blocks
   requirement #4.

2. **Captioned-but-detached figures/examples.** ~**1,285** `Figure N:` / `Example N:` caption lines
   introduce code, screen captures, or global dumps that follow as loose prose. The caption→content
   binding is textual only.

3. **Unresolved structural residue.** Every doc carries a `legacy-toc-unresolved` flag (10–571 hits
   each, ~1,600 total) and tables live as **76 CSV sidecars** rendered in gold as
   `_[Table N (extracted to CSV)](tables/table-NN.csv)_` links — invisible on github.com. The CSVs
   also carry placeholder headers (`col_3`) and some flattened multi-column layouts (a known issue
   already noted in the master-publication proposal §4).

The master-publication proposal addresses #3 (tables/images/boilerplate) generically. **#1 and #2 are
FileMan-specific and largely new** — they are the heart of this POC.

## 3. The consolidation thesis — integrate, don't mirror

**Claim:** the right master is **not nine documents**; it is **one FileMan documentation set** with a
single coherent information architecture, in which every concept is documented **once** (single-source)
and cross-referenced, not re-explained per manual.

Consolidation means three editorial operations the pipeline cannot do mechanically and the existing
1:1 publish stage explicitly does not attempt:

- **Merge** the two user-manual volumes into one end-user reference; fold the standalone DAC user
  guide in as a section (it is just patch `*8` of the same system).
- **De-duplicate & reconcile** overlapping explanations (ScreenMan is taught in `scrn_tut` *and*
  documented in `um2`; Browser, Inquire, security appear 3–4×). Keep the best single explanation,
  cross-link the rest, and resolve contradictions against **live VistA behavior** (§5) — VistA is the
  tie-breaker, which is exactly what makes this a *proof of concept* and not just reformatting.
- **Re-track** the material by audience into a learn/use/build/operate spine (§4), rather than by the
  accident of which Word file it shipped in.

This is also why FileMan is the ideal pilot for the *whole VDL*: if we can prove an integration +
proofread + live-test gate on the package every other VistA package depends on, the pattern
generalizes outward along the dependency graph.

## 4. Target information architecture — the integrated master set

One MkDocs-Material site (matches house Python stack; decision D2 in the master proposal), GFM-first on
disk so the raw GitHub UI renders it. Nine source docs → **four integrated tracks + a reference spine**:

```
docs/fileman/                         # the integrated FileMan master
  index.md                            # landing: what FileMan is, the four tracks, version banner
  learn/                              # ← fm22_tutorial + scrn_tut + dde_tutorial (the 3 tutorials)
    getting-started.md
    screenman.md
    dde-utilities.md
  use/                                # ← fm22_2um1 + fm22_2um2 + fm22_2p8_dac_ug (merged end-user ref)
    editing-and-inquiry.md
    output-and-reporting.md
    data-audit.md                     # DAC patch *8, folded in
    ...
  build/                              # ← fm22_2dg (Developer's Guide / DBS API reference)
    dbs-api/                          # one page per API call, each with a TESTED code block (§5)
      en-dik.md  en1-dip.md  ...
    classic-api/
    cross-references.md
  operate/                            # ← fm22_2tm + fm22_krn8_file_security (admin/install/security)
    technical-manual.md
    file-security.md
  reference/                          # structured, machine-queryable (data-file backed, drift-gated)
    files.md  globals.md  errors.md   # the big reference tables, from data/*.csv|yml
  _includes/                          # shared boilerplate (single-sourced)
  media/                              # materialized figures (relative refs)
  data/                               # reference-table source-of-truth
  mkdocs.yml  toc.yml  CODEOWNERS
```

An explicit **old→new crosswalk** (`reference/crosswalk.md`) maps every section of the nine retired
manuals to its home in the integrated set, so VA reviewers can verify nothing was dropped — this
crosswalk is itself a fidelity artifact (it feeds the §6 coverage gate).

## 5. Requirement #4 — code in code blocks, live-tested on VistA

This is the centerpiece and the part with no precedent in the existing proposals. Two sub-problems:

### 5a. Reconstruct real code blocks

A `codeblock` transform (new, in the `publish` L3 stage) recovers fenced code from the bold-inline /
escaped-prose patterns of §2-defect-1:

- **Detect** runs of bold M (`**S DIC=...**`), escaped global listings (`^X(\$J)=""`), and
  caption-introduced ("Figure N:", "Example N:") code regions.
- **Reconstruct** into fenced blocks with a language tag — propose **` ```mumps `** for code and
  **` ```text `** (or a custom `console` lexer) for captured roll-and-scroll terminal sessions, where
  user input vs. system output matters.
- **Un-escape** `\$ \_ \*` back to literal `$ _ *` inside code.
- **Bind** the preceding `Figure N:`/`Example N:` caption to the block (becomes the block's label /
  preceding bold line), fixing defect #2.

Deterministic, gated, reviewable as a diff. No AI required for the mechanical recovery; an AI assist is
useful only to *classify* ambiguous regions (is this prose or a code line?), and that classification is
then human-confirmed.

### 5b. Live-test every example against a working VistA — **already feasible today**

Both VistA engines are **running locally right now**: `vehu` (YDB-VistA) and `foia-t12` (IRIS-VistA).
The org contract mandates engine access **only** through the `m-driver-sdk` → `m-ydb`/`m-iris` stack
via `m vista exec --engine ydb|iris …` (raw `docker exec` is a denied red-gate). That gives us a
sanctioned, dual-engine execution path — and dual-engine is a *feature*: a FileMan example that behaves
identically on YDB-VistA and IRIS-VistA is doubly trustworthy.

**The doctest model.** Each reconstructed code block carries machine-readable test metadata in a
fenced-block attribute or an adjacent HTML comment, e.g.:

````markdown
```mumps
S DIC=200,DIC(0)="AEQ",X="USER,TEST" D ^DIC W Y
```
<!-- vdocs-test: engine=both; setup=fixtures/new-person.m; expect=/^200\^/; idempotent -->
````

A new **`vdocs verify-docs`** harness:

1. Extracts every block tagged for execution from the integrated master.
2. Runs it through `m vista exec` against `vehu` and/or `foia-t12` from a known fixture state.
3. Asserts the captured output matches the documented output (the roll-and-scroll session shown in
   the doc *becomes* the expected result — the doc is the test oracle).
4. **Red-gates** the doc on mismatch, and on green **stamps the page** `verified_on: <engine> <date>`
   in front matter.

This is "executable documentation": the FileMan manual's examples stop being prose assertions and
become a passing test suite. It is the strongest possible form of "100% proofread" for the code, and
it is the differentiating proof the whole VDL migration needs — *the docs are true because they ran.*
Read-only/destructive examples are tagged (`readonly` vs `setup`-fixtured) so verification never
mutates a shared engine; we coordinate engine use per the org's shared-lake rule.

## 6. Requirement #3 — 100% proofread, as a gate

"100% proofread" must be **enforced and stamped**, not asserted. Three layers, each red-gating
`publish`:

- **Mechanical gate** (deterministic): zero residual `\$`/`\_` escapes outside code blocks; zero
  `legacy-toc-unresolved` flags; every image ref resolves to a committed `media/` file; every
  reference table matches its `data/` source (drift check); no orphaned `_[Table N]` placeholders;
  schema-valid front matter; markdown lints clean. (Extends the master proposal's §7 fidelity gate.)
- **Code gate** (executable): §5b — every executable block passes on at least one engine; blocks that
  *can't* be auto-verified are explicitly flagged `manual-review` (never silently skipped — silent
  truncation reads as "covered" when it isn't).
- **Editorial gate** (semantic, AI-fanned + human sign-off): a multi-agent proofread pass over each
  consolidated page checks for (a) consistency with the source manuals via the §4 crosswalk
  (nothing dropped), (b) internal contradiction across the merged material, (c) terminology drift
  against the corpus glossary, (d) prose/grammar. Findings are adversarially verified (a second agent
  tries to refute each), then a **human reviewer signs off per page** — recorded as
  `status: reviewed` + `last_reviewed` + reviewer in front matter and git history. "100%" =
  every page in `status: reviewed` or better, enforced by a gate that fails if any page is still
  `imported`.

The proofread *state* therefore lives in front matter and is queryable: a dashboard can show "FileMan:
142/142 pages reviewed, 318/318 code blocks verified on vehu+foia-t12."

## 7. Requirements #1 & #2 — github-as-truth, docs-as-code

These are exactly the inversion already specified in
[`docs-as-code-master-publication-proposal.md`](docs-as-code-master-publication-proposal.md) §8 — this
POC **inherits** it rather than re-deriving it:

- The integrated FileMan master repo becomes authoritative; Word/VDL is frozen as the one-time import,
  recorded as `source_url`/`source_sha256`/`imported_from` front matter (§5 of that proposal).
- `index.db`, rich viewing, and PDF export are rebuilt **from the master**, not from internal gold.
- Git replaces `_shared/history` + `anchor_key` versioning; PRs + CODEOWNERS (routed by track/owner)
  replace the Word edit-and-re-upload loop; "Edit this page" targets the master.
- MkDocs-Material build = the Microsoft Learn relationship (repo is source; site is a derived build).

What this POC *adds* on top of that inversion is everything in §3 (integration), §5 (code blocks +
live test), and §6 (proofread gate) — the layers that turn a 1:1 mirror into a genuine consolidated,
verified master.

## 8. Requirement #5 — additional ideas to de-risk the migration

- **Crosswalk-as-contract.** The old→new section crosswalk (§4) is a generated, drift-gated registry —
  the org's `source-tag → generate → registry → red-gate` discipline applied to "did we drop
  anything." It is the auditable proof to VA that consolidation lost no content.
- **Pick FileMan precisely because everything depends on it.** Proving the gate on the base package
  lets the migration expand along the VistA dependency graph (Kernel → MailMan → clinical) with a
  reusable template, not a from-scratch effort per package.
- **Bidirectional traceability to code.** FileMan docs reference real routines (`^DIC`, `EN^DIK`) and
  files (`#.84`). Link doc API pages to the live routine source and to the corpus `index.db` entity,
  so a reader (or an agent) jumps doc → code → live behavior. This is a unique advantage of owning the
  engine.
- **Diff-driven freshness.** Because examples are executed, a future FileMan patch that changes
  behavior makes the doc's verify-gate go red automatically — the docs can't silently rot. Wire
  `vdocs verify-docs` into scheduled CI against `vehu`/`foia-t12`.
- **Glossary as shared include.** The corpus already has a 324 KB `glossary.md`; surface FileMan terms
  as a single-sourced include + hover-glossary, killing the per-manual re-definition drift.
- **Section-508 / accessibility carry-over.** The 22.2 source already did a 508 pass (per
  `history.yaml`: decorative-image marking, relative URLs). Preserve and gate that (alt-text required
  on non-decorative `media/`), so the docs-as-code master is born accessible.
- **Start the published repo as a vista-cloud-dev staging mirror**, not a VA-facing repo, until the
  gate is proven on FileMan — then propose it to VA as the model. (Resolves master-proposal Q4 for the
  POC.)

## 9. Phased plan

Each phase independently shippable, TDD-first, gated; the existing pipeline keeps working throughout.

- **P0 — sign-off (this doc).** Settle §10. Confirm FileMan as pilot, MkDocs-Material, dual-engine
  verify.
- **P1 — code-block reconstruction (§5a).** `codeblock` transform over the nine `body.md`; un-escape;
  caption binding. Output: fenced ` ```mumps `/` ```console ` blocks, mechanical gate green. *Smallest
  proof first:* run it on `fm22_2dg` DBS-API section alone.
- **P2 — live-test harness (§5b).** `vdocs verify-docs` via `m vista exec` against `vehu` + `foia-t12`;
  doctest metadata schema; per-block verify + front-matter stamping. Prove on the DBS-API pages.
- **P3 — integration & IA (§3, §4).** Merge UM volumes; fold DAC; de-dup tutorials vs UM; build the
  four-track tree + crosswalk registry; reference-table data files.
- **P4 — proofread gate (§6).** Mechanical + code + editorial layers; multi-agent proofread + human
  sign-off; `status` lifecycle; coverage dashboard. Drive FileMan to 100% reviewed.
- **P5 — inversion (inherit master proposal §10 P4–P5).** Re-point `index.db`/rich/PDF at the master;
  seed the published repo as the import commit; CODEOWNERS + edit-this-page; propose to VA.

## 10. Decisions & open questions

| # | Decision | Recommendation | Why |
|---|---|---|---|
| F1 | Code fence language | **`mumps`** for code, **`console`/`text`** for terminal sessions | Highlightable, copyable, lexer-friendly; separates input from captured output |
| F2 | Verify engines | **both `vehu` + `foia-t12`** where applicable | Dual-engine agreement is stronger proof; SDK stack mandates the driver path anyway |
| F3 | Integration depth | **full re-track into learn/use/build/operate** (not 1:1) | This is the actual ask; 1:1 is already covered by the master proposal |
| F4 | Proofread "100%" definition | **every page `status: reviewed`+ AND every executable block green** | Makes the claim a gate, not a slogan |
| F5 | Repo home for POC | **vista-cloud-dev staging mirror first** | De-risk before proposing to VA |

**Open questions:**

1. **Doctest fixture model** — how much shared VistA state can examples assume? Per-block setup
   fixtures vs. a seeded baseline snapshot of `vehu`/`foia-t12`? (Affects determinism + idempotency.)
2. **Ambiguous code/prose classification** — acceptable to require human confirmation on the
   minority of regions the detector can't classify, or do we need a higher-recall heuristic first?
3. **Destructive examples** — FileMan edit/delete examples mutate data. Tag-and-skip-execution, or
   run against a throwaway file (`^DIZ` test global) the doc can safely create/destroy?
4. **Consolidation authority** — when two source manuals contradict and *both* differ from live VistA,
   who signs off on the reconciled text (this is an editorial/clinical-SME call, not an engineering
   one)?
5. **Version model** — FileMan 22.2 only for the POC, or design the git-tag-per-patch versioning
   (master proposal Q1) now so DAC `*8`-style patches slot in cleanly?
