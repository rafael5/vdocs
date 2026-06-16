# Strategy — VDL modernization as a **content-quality** program, not a format migration

**Status:** strategy / for sign-off. **Date:** 2026-06-16. **Author:** Claude (Opus 4.8) with Rafael.
**Pilot package:** `DI` (VA FileMan 22.2). **Scope:** the editorial / information-architecture /
quality-automation layer of the VDL → docs-as-code program.
**Sits above:**
[`docs-as-code-master-publication-proposal.md`](docs-as-code-master-publication-proposal.md) (the
source-of-truth *inversion* + `publish`/L3 stage) and
[`fileman-integrated-master-poc-proposal.md`](fileman-integrated-master-poc-proposal.md) (the FileMan
pilot: consolidation, code-block reconstruction, live-VistA test, proofread gate).

> **The thesis in one line.** Converting the VDL Word manuals to Markdown is the mechanical **~20%**;
> the strategic **~80%** is *fixing the content* — auditing, de-duplicating, re-chunking, and
> consistency-gating 25 years of overlapping, drifted manuals into a structured, single-sourced,
> continuously-verified corpus. **Migrating the rot to a prettier medium is lipstick on a pig.** The
> two predecessor proposals build the *machine* and prove it on FileMan; this document specifies the
> *editorial standard and quality system* the machine must serve — grounded in the established
> doc-engineering frameworks (Diátaxis, topic-based authoring, single-sourcing, content audit, prose
> linting) rather than invented ad-hoc.

## Table of contents

- [1. Why this is a content program (the 80/20 argument)](#1-why-this-is-a-content-program-the-8020-argument)
- [2. Diagnosis — the five content-defect classes (grounded in the FileMan gold)](#2-diagnosis--the-five-content-defect-classes-grounded-in-the-fileman-gold)
- [3. Target macro-IA — Diátaxis, not "learn/use/build/operate" by feel](#3-target-macro-ia--diátaxis-not-learnusebuildoperate-by-feel)
- [4. The unit of work — topic-based authoring (one topic = one job)](#4-the-unit-of-work--topic-based-authoring-one-topic--one-job)
- [5. Chunking is a dual mandate — readers *and* editors](#5-chunking-is-a-dual-mandate--readers-and-editors)
- [6. Killing drift — single-sourcing, glossary, and a controlled vocabulary](#6-killing-drift--single-sourcing-glossary-and-a-controlled-vocabulary)
- [7. What to copy from Microsoft (and what to skip)](#7-what-to-copy-from-microsoft-and-what-to-skip)
- [8. The method — content audit → ROT triage → crosswalk (don't migrate the mess)](#8-the-method--content-audit--rot-triage--crosswalk-dont-migrate-the-mess)
- [9. The quality system — automated gates that prevent re-rot](#9-the-quality-system--automated-gates-that-prevent-re-rot)
- [10. "100% proofread" defined properly — machine + AI + human layering](#10-100-proofread-defined-properly--machine--ai--human-layering)
- [11. How the three proposals compose](#11-how-the-three-proposals-compose)
- [12. Phased plan](#12-phased-plan)
- [13. Decision table & open questions](#13-decision-table--open-questions)
- [14. Sources](#14-sources)

---

## 1. Why this is a content program (the 80/20 argument)

The whole content-strategy literature has one consensus warning for exactly this project: **"don't
migrate your mess."** Lift-and-shift "indiscriminately migrates all content and is widely
discouraged" because it "perpetuate[s] poor content quality in the new system" (Concentrix; Lullabot:
migration is "editorial judgment, not autopilot copying"). The European Commission's content audit
**removed ~80% of its corpus as redundant/outdated/trivial** before migrating — the format change was
never the point.

The vdocs pipeline has already done the mechanical 20% extremely well: VDL DOCX/PDF → clean Markdown +
CSV + YAML, content-addressed, deduplicated, version-collapsed, indexed. That is a real achievement
and it is *necessary*. It is not *sufficient*. The gold corpus is **faithfully-converted rot**: the
same 25-year-old overlaps, contradictions, terminology drift, and 100-page information-dumps, now in
Markdown instead of Word. The predecessor proposals' "1:1 materialization" path (master-publication
§3) makes it *render on github.com* — necessary plumbing, still not the quality lift.

**This strategy makes the 80% explicit, measurable, and gated**, so "modernize the VDL" means
*the content got better*, not *the bytes moved*.

## 2. Diagnosis — the five content-defect classes (grounded in the FileMan gold)

Measured on the nine FileMan `DI` gold documents (the pilot; ~63,700 lines / ~2.9 MB; numbers from
the FileMan POC proposal §1–§2). These are the concrete, countable gaps a quality program must close —
generalizable to every VDL package:

| # | Defect class | Evidence in FileMan gold | Framework it violates |
|---|---|---|---|
| **D-1** | **Redundancy / overlap** | ScreenMan taught in `scrn_tut` *and* documented in `um2`; Browser/Inquire/security re-explained 3–4×; two UM volumes split by Word page-count, not topic | Single-sourcing / DRY (drift) |
| **D-2** | **Mixed modes per page** (the information-dump) | Each manual braids tutorial + how-to + reference + explanation in one linear file; the Developer's Guide alone is 25,475 lines | Diátaxis (mode separation) |
| **D-3** | **Terminology drift** | Same concepts named differently across manuals authored over two decades; no enforced glossary despite a 324 KB corpus `glossary.md` existing | Controlled vocabulary |
| **D-4** | **Code not code** | **0** fenced code blocks across all nine docs; ~135 bold-as-code lines; ~1,180 backslash-escaped `\$`/`\_`/`\*` artifacts; ~1,285 detached `Figure N:`/`Example N:` captions | Reference fidelity / executability |
| **D-5** | **Structural residue** | ~1,600 `legacy-toc-unresolved` flags; 76 table CSV sidecars rendered as dead `_[Table N]` links; placeholder CSV headers (`col_3`) | Render fidelity |

The predecessor proposals already own **D-4** (FileMan POC §5: code-block reconstruction + live test)
and **D-5** (master-publication §4/§7: tables/images/boilerplate + fidelity gate). **D-1, D-2, D-3 are
the editorial core this strategy adds** — and they are the defects no pipeline transform can fix
mechanically, because they require *deciding what the content should say and where it should live*.

## 3. Target macro-IA — Diátaxis, not "learn/use/build/operate" by feel

The FileMan POC (§4) proposes a `learn/use/build/operate` tree. That instinct is right but should be
**grounded in [Diátaxis](https://diataxis.fr/)** — the established framework Microsoft Learn's content
types already align to — rather than invented per-package. Diátaxis says documentation serves exactly
**four user needs**, on two orthogonal axes (action vs. cognition × acquisition/study vs.
application/work), and **mixing them on one page fails all readers at once** (the literal cause of
D-2):

|  | **Acquisition** (at study / learning) | **Application** (at work / coding) |
|---|---|---|
| **Action** | **Tutorials** — learning-oriented lessons | **How-to guides** — task-oriented recipes |
| **Cognition** | **Explanation** — understanding ("why") | **Reference** — information ("the facts") |

Mapping the proposed tracks to the canonical modes (keep the friendly directory names as URLs if
desired, but author to the *mode's discipline*):

| Proposed track | Diátaxis mode | Discipline the mode enforces | FileMan source material |
|---|---|---|---|
| `learn/` | **Tutorials** | Guaranteed-to-work lessons; *ruthlessly minimise explanation*; "we will…" | `fm22_tutorial`, `scrn_tut`, `dde_tutorial` |
| `use/` | **How-to guides** | Action only, no teaching/digression; serves the already-competent | `um1` + `um2` + DAC `*8` (merged) |
| `build/` | **Reference** | Austere, neutral, consulted-not-read; mirrors the machinery | `fm22_2dg` DBS/classic API |
| `operate/` | **How-to + Reference** | Install/admin recipes vs. file/global/security facts | `fm22_2tm`, `fm22_krn8_file_security` |
| *(new)* `concepts/` | **Explanation** | "Why FileMan works this way"; admits perspective; weaves understanding | *extracted* from the explanatory prose currently buried in every manual |

**Why this matters beyond pedantry:** Diátaxis gives an objective test for D-2. Every paragraph
answers the *Compass*: action or cognition? acquisition or application? A paragraph that can't answer
crisply is mixed-mode and must be split or relocated. This converts "this manual is a mess" from
opinion into a **mechanical editorial checklist**, and it's the same checklist for FileMan, Kernel,
and every package after — the reusable template the whole-VDL ambition needs.

Critically, Diátaxis is explicitly an **iterative, no-big-bang** method ("don't try to work on the
big picture… good structure develops from within"): choose any page → assess with the Compass →
make one improvement → publish → repeat. That fits the medallion pipeline and the
"continuously-shippable" house cadence far better than a monolithic rewrite.

## 4. The unit of work — topic-based authoring (one topic = one job)

The atomic deliverable is **not a manual; it is a topic**: per OASIS DITA, "a unit of information…
short enough to be specific to a single subject or answer a single question, but long enough to make
sense on its own." Two properties matter:

- **Bounded** — one topic = one job. Microsoft's own rule of thumb: a procedure with **>12 steps is
  probably too long** and should be split. The 25,475-line FileMan Developer's Guide becomes *one page
  per API call* (`build/dbs-api/en-dik.md`, …), each with its tested code block.
- **Self-contained** — understandable when arrived at cold, because in the search era **"every page is
  page one"** (Mark Baker): readers land on *any* page first. NN/g's data is blunt — users **scan, not
  read** (79% scan; ~20–28% of words read; pages over ~111 words get half-read at best). A topic must
  establish its own context, assume a qualified reader (and link the unqualified to what qualifies
  them), and front-load its conclusion (inverted pyramid).

This is also the **information-typing** discipline (DITA concept/task/reference), which exists to
"avoid mixing content types, thereby losing reader focus" — the same anti-D-2 force as Diátaxis, at
the page level. And **minimalism** (Carroll) is the editorial filter on top: cut every sentence that
doesn't serve the reader's task. A 25-year corpus accreted enormous ceremony; minimalism is the
license to delete it.

## 5. Chunking is a dual mandate — readers *and* editors

The user's instinct that chunking serves *both* audiences is exactly right and is the strongest
single argument for small topics. The two cases are independent and both decisive:

**For readers** (§4 above): scannability, information scent (descriptive headings/links — vague
"Overview"/"Notes" headings kill scent), progressive disclosure (lead with the 80% path, defer edge
cases), and EPPO self-containment. A reader needs *the one answer*, not a 100-page dump to grep by eye.

**For editors — chunk size changes the *math* of collaborative git editing on three independent axes:**

| Axis | 2,000-line monolith | 100-line topic | Source |
|---|---|---|---|
| **Merge conflicts** | Two SMEs editing different sections collide on the same file | Two SMEs editing two topics **never conflict** (git is per-line/per-file) | GitHub merge-conflict model |
| **Review quality** | Diff buried in a huge file; blows past the **200–400 LOC** window where reviewers find 70–90% of defects | Whole change sits inside the effective-review sweet spot; approved faster | Cisco/SmartBear code-review study |
| **Ownership routing** | One over-broad CODEOWNER for the whole file | `docs/fileman/security/…` routes to the **exact package SME** | GitHub CODEOWNERS (path-matched) |

Add **semantic line breaks** (one sentence per source line; rendered output unchanged) so even
within-topic edits produce one-sentence diffs — making prose review as granular as code review. The
net: *a small-topic corpus is not just nicer to read; it is the only structure in which a distributed
set of VA SMEs can collaboratively edit on GitHub without serializing on giant files.*

## 6. Killing drift — single-sourcing, glossary, and a controlled vocabulary

D-1 and D-3 are the same disease — **copy-based reuse** — and have one cure: **reference-based reuse**.
"You create a copy, edit for the variant… six months later five versions of the same warning sit in
five files and nobody knows which is current." Single-sourcing makes "update one copy but not the
others" *structurally impossible* because there are no other copies. Three mechanisms, all already
half-present in the corpus:

1. **Includes / transclusion** for shared prose — the corpus already single-sources boilerplate as
   `_shared/boilerplate/bp-<hash>.md`; MkDocs `pymdownx.snippets` (`--8<-- "file.md"`) renders it.
   This *is* the Microsoft `[!INCLUDE]` model. Extend it from boilerplate to any concept explained more
   than once (ScreenMan, Browser, security) — define once in `concepts/`, transclude/cross-link
   everywhere else. Kills D-1.
2. **A single glossary as a shared include** — the 324 KB corpus `glossary.md` becomes the *one*
   definition per term, transcluded (and ideally hover-rendered), retiring per-manual re-definitions.
3. **A controlled vocabulary (termbase)** — the industry answer to multi-author/multi-decade drift is
   literally an **A–Z approved-term list with named forbidden synonyms** (Google's and Microsoft's word
   lists; aerospace's ASD-STE100 "one word = one meaning"). The two **draft registries already on this
   branch** — `docs/product-names.draft.yaml` and `docs/product-abbreviations.draft.yaml` — are the
   seed of this termbase. The strategic move is to make them **machine-enforced** (§9): compile them
   into Vale substitution rules so "VistA" never re-drifts to "Vista"/"VISTA", `FileMan` stays
   `FileMan`, and every package name resolves to its approved spelling — *as a CI gate, not a manual
   pass.*

## 7. What to copy from Microsoft (and what to skip)

Microsoft Learn is the right template, but the proposals should copy it *precisely*, distinguishing
the durable patterns from the build-coupled ones that would break the "renders on raw github.com"
requirement (master-publication D1):

**Copy (the durable model):**
- **Repo is the source of truth; the site is a derived build** (`git repo → OPS/DocFX → learn.microsoft.com`).
  This is exactly the *inversion* (master-publication §8); our MkDocs build is the OPS analog.
- **Content types declared in front matter** (`ms.topic: tutorial|how-to|concept|reference|overview`).
  Adopt a `doc_type`/`ms.topic`-equivalent and **gate it to the Diátaxis vocab** (§3) — the front
  matter *is* the mode contract, queryable for a coverage dashboard.
- **Generate reference, hand-write the rest.** Microsoft auto-generates .NET API reference from
  structured source (XML doc-comments → YAML → template) and only hand-writes concept/how-to/tutorial.
  The VistA analog is decisive: **generate FileMan/file/global/option/RPC reference from the data
  dictionary + KIDS + routine source as structured `data/*.yml`, drift-gated** (master-publication §4,
  D4), and reserve human editing for the conceptual/how-to/tutorial Markdown. Don't hand-curate big
  reference tables that a generator should own.
- **Nav declared as data**, separate from content (`toc.yml`); **per-package `toc.yml` stitched into a
  master** (DocFX nested-TOC) — the model for assembling FileMan + Kernel + … into one site.
- **The contribution loop**: Edit-pencil → fork → PR → automated validation (build + link-check) →
  CODEOWNERS sign-off → label-gated merge. PR **preview deployments** so reviewers see rendered output.

**Skip on disk (build-only extensions that garble raw GitHub):** the triple-colon family
(`:::row:::`, `:::image:::`, `:::moniker:::`), tabs, and `[!INCLUDE]` *all render as literal text on
github.com*. Keep the committed `.md` to the **GitHub-legible subset**: standard GFM + GitHub-native
alerts (`> [!NOTE]`) — which both GitHub and MkDocs render. Use build-time richness (snippets,
admonitions, tabs, `mike` version selector) only where the *rendered site* needs it and the raw file
still reads cleanly. This resolves master-publication D1/Q3 in favor of *self-contained, raw-readable*
masters.

## 8. The method — content audit → ROT triage → crosswalk (don't migrate the mess)

The discipline that turns the 80% from aspiration into a worklist, per the content-strategy canon
(NN/g; Halvorson & Rach; digital.gov). Run it per package, FileMan first:

1. **Content inventory** (quantitative, automatable) — one row per gold topic/section: title, source
   manual, source_url/sha, line count, doc_type, table/figure/code counts, owner. The pipeline already
   emits most of this (`corpus-manifest.json`, `index.db`); the audit reuses it.
2. **Content audit** (qualitative, human-judgment — "a robot-free zone," but **AI-assisted triage**,
   §10) — score each item against the Diátaxis Compass + a quality rubric → a **disposition** per item.
3. **ROT triage** — flag **R**edundant (the D-1 overlaps → merge/single-source), **O**utdated (stale
   procedures, broken refs), **T**rivial (ceremony minimalism deletes). Disposition vocabulary:
   **keep / merge / rewrite / retire**.
4. **Gap analysis** — what readers *need but no manual answers* (mined from real `vdocs ask`/search
   queries and support questions): net-new topics to author, not just cleanup. This is where the corpus
   gets genuinely *better than the originals*.
5. **Crosswalk (old → new), as a drift-gated registry** — every retired manual/section/figure ID →
   its new topic home, capturing **N→1 merges and 1→N splits** (where references silently break). This
   is the FileMan POC's `reference/crosswalk.md` (§4/§8) generalized: it is simultaneously (a) the audit
   trail proving *nothing was dropped* (the VA-reviewer guarantee), (b) the redirect map that keeps
   inbound links and prior `index.db` citations resolving, and (c) a coverage gate input.

The crosswalk is the linchpin artifact: it makes consolidation **auditable** rather than a leap of
faith, which is what lets a risk-averse VA accept that nine manuals collapsing to one lost no content.

## 9. The quality system — automated gates that prevent re-rot

The reason the VDL rotted is that quality was a *periodic manual act* that stopped happening.
Docs-as-code's core move is to make quality a **continuously-enforced CI invariant** — "a PR with a
broken link fails the build, just like code with a failing test." The stack (all offline-capable,
matching the house airgapped/zero-ML-dependency posture; one `docs-ci.yml`, each job a required status
check):

| Layer | Tool | Gate it enforces | Notes |
|---|---|---|---|
| **Prose / style** | **Vale** + Google or Microsoft style package + **VistA `Vocab`** | One enforced voice; **terminology from §6 termbase as substitution rules** (forbidden→approved) | Compile `product-names`/`abbreviations` registries → Vale rules; gate on `error` |
| **Structure** | **markdownlint-cli2** | Heading hierarchy (MD001), **alt-text required (MD045)**, fenced-code language tags (MD040) | MD045/MD001 double as a11y gates |
| **Spelling** | **typos** (Rust) + domain whitelist | Low-false-positive spell-check tuned for VistA jargon | `accept.txt` shares the termbase |
| **Links / anchors** | **lychee** (`--offline` internal = build-fail) + MkDocs 1.6 `validation.anchors` + **mkdocs-redirects** (crosswalk) | No dead internal links/anchors; crosswalk redirects resolve | Scheduled *external* check opens an auto-issue, doesn't break PRs |
| **Build** | `mkdocs build --strict` | Nav/link warnings → non-zero exit | Pin a known-good MkDocs version |
| **Accessibility** | **pa11y-ci** / Lighthouse-CI against built `site/` | **WCAG 2.1/2.2 AA** (Section 508) — legally load-bearing for a VA audience incl. disabled Veterans | Federal precedent: 18F, CivicActions, NIST OSCAL |
| **Front-matter** | schema validator | `doc_type` ∈ Diátaxis vocab; required fields; `status` lifecycle | Feeds the coverage dashboard |

**Future-proofing (anti-re-rot):** CODEOWNERS on `registries/` + the pipeline + per-package topic
dirs (route to package SMEs); `status`/`last_reviewed` front matter as freshness signal; a **scheduled
cron** that re-crawls VDL and opens an issue when an upstream hash changes or a fetch 404s (reusing the
existing `permanent_missing`/fetch idempotency). Note the vdocs-specific wrinkle: because the corpus is
*generated*, git "last-modified" is moot (regen touches everything) — so freshness must pin to the
**upstream source SHA in front matter**, not git age. CODEOWNERS belongs on the *human-curated inputs
that actually rot* (registries, pipeline, hand-edited concept topics), not the generated reference.

## 10. "100% proofread" defined properly — machine + AI + human layering

The FileMan POC §6 already frames proofread-as-a-gate; this sharpens *how AI participates safely*,
which is the part most likely to go wrong on an **authoritative** corpus where a fluent-but-wrong edit
launders a hallucination into a citable VA source. Three layers, escalating cost, each gating
`publish`:

1. **Mechanical (deterministic, free, runs on every PR)** — the §9 stack: Vale/markdownlint/typos/
   lychee/build/a11y/front-matter all green. Catches D-3, D-5, and style/structure objectively.
2. **AI-assisted editorial (advisory, human-gated)** — within strict guardrails the 2024–26 consensus
   demands:
   - **AI proposes, a human merges. Never auto-merge authoritative docs.** (Red Hat's HITL pattern:
     bot posts a checklist of candidate edits → human unchecks false positives → PR opens for *approved
     files only*.)
   - **AI edits are bounded transformations, not additions** — proofread *this paragraph*, summarize
     *this section*, draft alt-text for *this figure*, flag *candidate* contradictions across two docs.
     Anything additive carries a human-verified citation. (Cross-doc contradiction detection is
     research-stage — flag for a curator, don't trust it to *decide*.)
   - **AI output passes the same deterministic gates** (layer 1) before human review. "AI suggests and
     accelerates; deterministic policy decides and enforces."
   - **Adversarial verification is triage, not authority** — a second agent refutes each finding to
     rank it; LLM-as-judge is fragile (a single token can fool it), so it filters the human's queue,
     it never closes the loop.
3. **Human sign-off, per topic, recorded in front matter + git** — `status: reviewed` +
   `last_reviewed` + reviewer. "100%" = a gate that **fails if any topic is still `imported`**. The
   state is queryable: *"FileMan: 142/142 topics reviewed, 318/318 code blocks verified on
   vehu+foia-t12, 0 Vale errors, 0 dead links."* That dashboard line **is** the modernization claim,
   made falsifiable.

This is the safe synthesis the user's "comprehensive proofreading" ask needs: AI does the
*scale* (no human reads 63,700 lines unaided), determinism does the *enforcement*, humans own the
*authority*.

## 11. How the three proposals compose

```
                 THIS DOC — content-quality & IA STRATEGY (the editorial standard + quality system)
                 · Diátaxis macro-IA   · topic-based chunking   · single-source/termbase
                 · content-audit/ROT/crosswalk method   · Vale/a11y/CI quality gates
                 · safe AI proofread layering
                          │ defines the standard the machine must meet
        ┌─────────────────┴───────────────────────────────┐
   MASTER-PUBLICATION PROPOSAL                      FILEMAN POC PROPOSAL
   (the machine + the inversion)                    (prove it on one package)
   · publish/L3 stage  · materialize tables/        · consolidate 9 FileMan manuals
     images/boilerplate  · fidelity gate            · code-block reconstruction (D-4)
   · index/rich/PDF derive from master              · live-VistA verify-docs
   · git replaces history/versioning                · proofread gate, dual-engine
```

- The **master-publication proposal** is the *delivery mechanism* (how gold becomes a github-native,
  self-contained, derive-from-master corpus). This strategy tells it *what "good" means* (Diátaxis
  modes in front matter; GitHub-legible subset; termbase-as-Vale; reference-generated-not-hand-edited).
- The **FileMan POC** is the *pilot that proves the whole stack* on the foundational package. This
  strategy supplies its missing editorial rigor: ground `learn/use/build/operate` in Diátaxis (§3),
  add `concepts/` (Explanation), run the audit/ROT/crosswalk method (§8), and adopt the §9 quality
  gates and §10 AI guardrails.
- **FileMan first, then along the dependency graph** (Kernel → MailMan → clinical) is correct *because*
  the deliverable of the pilot is a **reusable template** — the Diátaxis checklist, the gate config,
  the crosswalk registry shape, the termbase — not a one-off. That reusability is the entire argument
  for a "strategic, targeted, domain-first" approach over a uniform bulk migration.

## 12. Phased plan

Additive to the predecessor plans; each phase independently shippable, TDD-first where it touches the
pipeline, and continuously publishable per the Diátaxis iterative method.

- **P0 — standard sign-off (this doc).** Settle §13. Ratify Diátaxis as the macro-IA, the
  GitHub-legible-subset rule, the §9 gate stack, and the §10 AI guardrails as program-wide policy.
- **P1 — quality-gate harness (package-agnostic).** Stand up `docs-ci.yml`: Vale (Google base +
  seeded VistA `Vocab` compiled from `product-names`/`abbreviations` drafts), markdownlint-cli2,
  typos, lychee `--offline`, `mkdocs build --strict`, pa11y-ci, front-matter schema. Prove green on a
  tiny hand-built sample. *This is the standard made executable — do it before bulk content work so
  every later topic is born gated.*
- **P2 — FileMan content audit + crosswalk registry.** Inventory (from manifest/index) → AI-assisted
  audit → ROT triage → gap list → drift-gated `crosswalk.yml`. Output: a per-topic disposition sheet
  (keep/merge/rewrite/retire) — the worklist for the 80%.
- **P3 — Diátaxis re-chunk of FileMan.** Execute the dispositions: split mixed-mode dumps into typed
  topics (tutorial/how-to/reference/explanation), merge the UM volumes + fold DAC, extract `concepts/`,
  single-source ScreenMan/Browser/security/glossary as includes. Reference content generated to
  `data/*.yml`, drift-gated. Crosswalk kept current as the audit trail.
- **P4 — proofread to 100% (machine + AI + human).** Drive every FileMan topic to `status: reviewed`
  with all §9 gates green and (per FileMan POC) every code block verified on vehu/foia-t12. Ship the
  coverage dashboard.
- **P5 — templatize + next package.** Extract the FileMan run into a reusable kit (Diátaxis checklist,
  gate config, crosswalk shape, termbase) and point it at **Kernel** — proving the strategy
  generalizes along the dependency graph.

## 13. Decision table & open questions

| # | Decision | Recommendation | Why |
|---|---|---|---|
| S1 | Macro-IA framework | **Diátaxis** (4 modes + the two axes), front-matter-typed | Established, Microsoft-aligned, gives an objective mixed-mode test; replaces by-feel tracks |
| S2 | Authoring unit | **Topic-based** (one topic = one job, self-contained/EPPO) | Serves scanning readers *and* enables conflict-free, CODEOWNER-routed git editing |
| S3 | Reuse model | **Reference-based single-sourcing** (includes + glossary + termbase) | The only structural cure for D-1/D-3 drift; registries already seeded |
| S4 | Terminology enforcement | **Termbase → Vale substitution rules** in CI | Makes consistency a continuous invariant, not a manual re-read of thousands of pages |
| S5 | On-disk format | **GitHub-legible GFM subset** (+ GH alerts); build-only richness in the site only | Keeps the master raw-readable on github.com (master-publication D1); resolves its Q3 toward self-contained |
| S6 | Reference content | **Generated from structured source** (`data/*.yml`), drift-gated; hand-write only concept/how-to/tutorial | The Microsoft model; keeps big tables diffable/queryable and out of hand-editing |
| S7 | Migration method | **Audit → ROT → crosswalk before re-chunk** | "Don't migrate the mess"; makes consolidation auditable for VA |
| S8 | AI's role in proofread | **Bounded, human-gated, citation-grounded, deterministic-gate-passing** | Prevents laundering hallucinations into an authoritative VA source |
| S9 | Quality enforcement | **CI gates as required status checks** (Vale/mdlint/typos/lychee/strict-build/a11y) | Prevents re-rot; the reason docs-as-code beats periodic manual QA |

**Open questions:**

1. **Diátaxis depth for the pilot** — full four-mode re-chunk of all nine FileMan manuals in P3, or
   prove the method on the Developer's Guide (reference) + one tutorial first, then expand?
2. **Style-guide base** — Google (CC BY 4.0, developer-oriented, forkable) vs. Microsoft (broader,
   matches the "mirror Microsoft" framing) as the Vale base under the VistA overlay?
3. **Termbase format/ownership** — promote `product-names.draft.yaml`/`abbreviations.draft.yaml` to a
   committed termbase now (and who curates additions)? TBX-portable, or stay YAML?
4. **Gap-fill authority** — net-new topics (§8.4) that no manual ever stated assert facts about VistA;
   who is the SME of record that signs off (an editorial/clinical call, not engineering)?
5. **Reference-generation scope for FileMan** — generate the file/global/option/RPC reference from the
   live data dictionary now (strongest fidelity, more build), or hand-curate from the gold tables for
   the pilot and automate in P5?
6. **Dashboard home** — where does the coverage/freshness dashboard live (a `vdocs` CLI report, a
   built site page, or both), and is "% topics `reviewed`" the headline VDL-modernization KPI?

## 14. Sources

Grounding for the frameworks cited above (research synthesized 2026-06-16):

- **Diátaxis** — https://diataxis.fr/ (foundations, compass, map, how-to-use). The four modes, the two
  axes, mode-mixing as the root documentation failure, the no-big-bang iterative method.
- **Topic-based authoring / information typing** — OASIS DITA topic definition & info-typing
  (docs.oasis-open.org/dita); **EPPO** "Every Page is Page One," Mark Baker (everypageispageone.com);
  **minimalism**, John Carroll, *The Nurnberg Funnel* (MIT Press, 1990).
- **Reader chunking** — NN/g: *How Users Read on the Web* (scanning), *How Little Do Users Read?*,
  *Progressive Disclosure*, *Information Scent*, *Inverted Pyramid*, *F-Shaped Pattern*.
- **Editor chunking** — GitHub *About merge conflicts* & *About code owners*; Google eng-practices
  *Small CLs*; Cisco/SmartBear peer-review study (200–400 LOC / 70–90% defect window);
  Semantic Line Breaks (sembr.org).
- **Single-sourcing / drift** — Write the Docs *Documentation Principles* (DRY/ARID/Unique); Paligo
  *Single Source of Truth*; DITA conref/transclusion; controlled vocabulary: ASD-STE100, Google &
  Microsoft A–Z word lists, TBX/ISO 30042.
- **Microsoft Learn model** — Microsoft Contribute guide: metadata schema & `ms.topic`, markdown
  reference (alerts/includes/`:::`), code-in-docs (`:::code` from real source), git/PR workflow, OPS/
  DocFX build, `toc.yml`, monikers; .NET auto-generated reference from XML doc-comments.
- **Content audit / migration** — NN/g *Content Inventory and Auditing 101*; Halvorson & Rach
  *Content Strategy for the Web*; digital.gov ROT; Concentrix/Lullabot "don't migrate the mess"; EC
  ~80%-ROT figure.
- **Quality automation** — Vale (vale.sh) + errata-ai Microsoft/Google packages; markdownlint;
  typos; lychee; MkDocs 1.6 `validation` + `--strict`; MkDocs-Material (snippets/macros/mike/offline);
  pa11y/axe/Lighthouse; VA Section 508 (digital.va.gov) + WCAG 2.1/2.2 AA.
- **AI guardrails** — State of Docs 2026; Red Hat Code-to-Docs HITL; "deterministic guardrails";
  *One Token to Fool LLM-as-a-Judge*; hallucination-containment surveys (RAG grounds facts, not logic).

> Detailed per-claim citations (URLs) are retained in the research notes backing this strategy and can
> be inlined on request; the frameworks above are the load-bearing ones for sign-off.
