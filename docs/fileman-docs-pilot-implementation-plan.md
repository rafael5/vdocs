# Implementation Plan — FileMan docs-as-code pilot (`fileman-docs` + the `va-docs-portal` SSG)

**Status:** implementation tracker (how/status). **Date:** 2026-06-16. **Author:** Claude (Opus 4.8) with Rafael.
**Executes:** [`vdl-content-quality-and-ia-strategy.md`](vdl-content-quality-and-ia-strategy.md) on a
strategic FileMan subset. **Inherits machine/pilot detail from**
[`docs-as-code-master-publication-proposal.md`](docs-as-code-master-publication-proposal.md) and
[`fileman-integrated-master-poc-proposal.md`](fileman-integrated-master-poc-proposal.md).

> **Locked decisions (from sign-off Q&A, 2026-06-16):**
> 1. **SSG = MkDocs-Material, extended** — adopt it as the new tool; add a multi-repo aggregation layer
>    + a per-source **edit-me** hook so one portal builds from `fileman-docs` + future `kernel-docs` + ….
> 2. **Pilot subset = mode-diverse minimal** — one doc per Diátaxis mode, smallest viable, to prove the
>    full *chunk → single-source → gate → publish → site* loop end-to-end.
> 3. **Local preview first** — `fileman-docs` and `va-docs-portal` are **local git repos** (no remote
>    yet); preview on `localhost`. Public GitHub + Pages deferred until the pilot is gate-green, but
>    `edit_uri` / CODEOWNERS are authored now for the eventual push.

## Table of contents

- [0. The three artifacts (architecture)](#0-the-three-artifacts-architecture)
- [1. The pilot subset — what each doc proves](#1-the-pilot-subset--what-each-doc-proves)
- [2. Repo topology & on-disk layout](#2-repo-topology--on-disk-layout)
- [3. The quality-gate harness (runs locally now, CI later)](#3-the-quality-gate-harness-runs-locally-now-ci-later)
- [4. The `va-docs-portal` SSG — MkDocs-Material, extended](#4-the-va-docs-portal-ssg--mkdocs-material-extended)
- [5. Phases L0–L6](#5-phases-l0l6)
- [6. What stays mechanical (vdocs) vs editorial (fileman-docs)](#6-what-stays-mechanical-vdocs-vs-editorial-fileman-docs)
- [7. Definition of done (pilot acceptance)](#7-definition-of-done-pilot-acceptance)
- [8. Risks & open questions](#8-risks--open-questions)

---

## 0. The three artifacts (architecture)

```
   ~/data/vdocs (the lake)                ~/projects/fileman-docs (NEW local repo)        ~/projects/va-docs-portal (NEW local repo)
  ┌───────────────────────┐    export    ┌───────────────────────────────────┐   build  ┌────────────────────────────────────┐
  │ gold/consolidated/DI/ │ ───────────▶ │ docs-as-code MASTER (edited here) │ ───────▶ │ MkDocs-Material, extended (SSG)    │
  │  fm22_2dg/ scrn_tut/  │  (vdocs      │  · Diátaxis-typed topics          │ (submod) │  · consumes fileman-docs (+kernel- │
  │  fm22_2tm/ …          │   one-time)  │  · _includes/ media/ data/        │          │    docs later) via git submodule   │
  └───────────────────────┘              │  · mkdocs.yml CODEOWNERS .vale.ini│          │  · per-source EDIT-ME button hook  │
            ▲                            │  · gate config (CI-ready)         │          │  · search · offline · localhost    │
            │ verify-docs (vehu/foia-t12)└───────────────────────────────────┘          └────────────────────────────────────┘
            │  re-runs the code blocks                    ▲   editors/peer reviewers open PRs here          │ make serve → http://localhost:8000
            └─────────────────────────────────────────────┘◀────────────────── edit-me button ─────────────┘
```

- **`vdocs`** (this repo) gains two capabilities, both scoped to the subset: a **`export-fileman`**
  command (the mechanical first-pass materialization into `fileman-docs`) and the **`verify-docs`**
  harness (live-VistA test of reconstructed code blocks). Neither writes to the lake; both are derive-only.
- **`fileman-docs`** is the **docs-as-code source of truth** — pure content + config, no Python pipeline.
  It is what editors edit and what the edit-me button targets. It owns its own gate config so it can be
  CI-gated independently once it has a remote.
- **`va-docs-portal`** is the **new SSG tool**, deliberately package-agnostic: it consumes *N* `*-docs`
  repos (FileMan now; Kernel, MailMan, … later) and renders one Microsoft-Learn-style static site. Adding
  a package = adding a submodule, not changing the tool.

## 1. The pilot subset — what each doc proves

Verified in the lake (`gold/consolidated/DI/<slug>/body.md`, 2026-06-16). Four sources, each exercising
a distinct Diátaxis mode and a distinct part of the standard:

| Source slug | Lines | Diátaxis mode | What it proves in the pilot |
|---|---:|---|---|
| `fm22_krn8_file_security` | 484 | **Reference + How-to** | Smallest end-to-end pass: front-matter rewrite, boilerplate→`_includes`, regenerated-TOC cleanup, mode split. The "hello-world" of the whole loop. |
| `scrn_tut` (ScreenMan) | 4,512 | **Tutorial** | Learning-oriented re-chunk; **de-dup vs the user manuals** (ScreenMan is also in `um2`) → single-source the concept, cross-link the tutorial. |
| `fm22_2tm` (Technical Manual) | 2,814 | **How-to + Reference (operate)** | A *slice* only (install/admin + the file/global tables); reference tables → `data/*.yml` drift-gated; narrative tables inlined. |
| `fm22_2dg` (Developer's Guide) | 25,475 | **Reference (API)** | A **handful of DBS-API calls only**, one page each — already split on `### ^DIE:`/`### ^DIK:`/`### ^DIC:` headings. Proves **code-block reconstruction + live-VistA verify** (the centerpiece). |

**DBS-API pick (safe-first for the pilot):** `$$GET1^DIQ` (retrieve), `^DIC` (lookup), `EN^DID`
(print/display DD) as **read-only**; plus **one write** — `FILE^DIE` (or `^DIE`) — exercised against a
**throwaway `^DIZ(` test file** the example creates and destroys, so verification never mutates shared
engine state (resolves FileMan-POC open-Q3 for the pilot). Destructive `^DIK` delete examples are
**tagged `manual-review`** for the pilot, not auto-executed.

**Explicitly out of pilot scope:** `fm22_2um1`/`um2` full merge, DAC `*8`, `fm22_tutorial`,
`dde_tutorial`, and the bulk of the Developer's Guide. They join in the post-pilot expansion once the
template is proven.

## 2. Repo topology & on-disk layout

### `~/projects/fileman-docs` (the master)

```
fileman-docs/
  docs/
    index.md                     # landing: what FileMan is, the modes, version banner
    learn/                       # TUTORIALS
      screenman.md               #  ← scrn_tut, re-chunked
    use/                         # HOW-TO
      file-access-security.md    #  ← fm22_krn8_file_security (how-to half)
    build/                       # REFERENCE (API)
      dbs-api/
        get1-diq.md  dic.md  en-did.md  file-die.md   # one page per call, tested
    operate/                     # HOW-TO + REFERENCE (admin)
      technical-manual.md        #  ← fm22_2tm slice
    concepts/                    # EXPLANATION
      file-access-security.md    #  ← reference half of File Security, the "why"
    reference/
      crosswalk.md               # old section → new topic (audit artifact, drift-gated)
  _includes/                     # single-sourced boilerplate + glossary terms
  media/                         # materialized figures (relative refs)
  data/                          # reference-table source of truth (*.yml), drift-gated
  mkdocs.yml                     # LOCAL preview config (portal overrides for the aggregate build)
  CODEOWNERS                     # routes /build → DBA-API owner, /operate → sysadmin owner, …
  .vale.ini  .vale/             # prose-lint config + VistA Vocab
  .markdownlint-cli2.yaml  typos.toml  lychee.toml
  .github/workflows/docs-ci.yml # authored now, dormant until a remote exists
  Makefile                      # make gate (lint+linkcheck+build-strict+a11y), make serve
  README.md
```

Front matter per topic carries the §5 schema from the master proposal **plus the Diátaxis type**:
`doc_type` ∈ `{tutorial, how-to, reference, explanation, overview}` (the `ms.topic` analog, gated to the
controlled vocab), frozen `source_url`/`source_sha256`/`imported_from`, and the lifecycle fields
`status` (`imported|reviewed|maintained|deprecated`), `last_reviewed`, `owner`, and (for API pages)
`verified_on`.

### `~/projects/va-docs-portal` (the SSG tool)

```
va-docs-portal/
  mkdocs.yml                     # the aggregate site config (Material theme, plugins, nav)
  sources/
    fileman-docs/                # git submodule → ~/projects/fileman-docs (local for now)
    # kernel-docs/               # (future) just add a submodule
  overrides/                     # Material theme overrides (banner, footer, edit-link template)
  hooks/edit_links.py            # MkDocs hook: rewrite each page's edit URL to ITS source repo
  Makefile                       # make serve (localhost) · make build · make a11y
  pyproject.toml / requirements  # mkdocs-material + plugins (pinned)
```

## 3. The quality-gate harness (runs locally now, CI later)

The §9 strategy stack, made executable as a `make gate` target in `fileman-docs` **and** mirrored in
`docs-ci.yml` (dormant until the repo has a remote). All tools are offline-capable, matching the house
airgapped posture:

| Gate | Tool | Config | Fails on |
|---|---|---|---|
| Prose / terminology | **Vale** + Google base pkg + **VistA `Vocab`** | `.vale.ini`, `.vale/` | `error`-level: banned synonym, wrong casing of `VistA`/`FileMan`/`MUMPS`/`KIDS`/RPC names |
| Structure + a11y source | **markdownlint-cli2** | `.markdownlint-cli2.yaml` | MD001 (heading skips), **MD045 (missing alt text)**, MD040 (unfenced code lang) |
| Spelling | **typos** | `typos.toml` (VistA whitelist = same termbase) | unknown token not in whitelist |
| Links / anchors | **lychee `--offline`** + MkDocs 1.6 `validation.anchors=warn` | `lychee.toml` | dead internal link / unresolved anchor |
| Build | `mkdocs build --strict` (pinned MkDocs) | `mkdocs.yml` | nav/link warning → non-zero |
| Rendered a11y | **pa11y-ci** (WCAG 2.1 AA) against built `site/` | `.pa11yci` | contrast/ARIA/heading-order violation |
| Front matter | schema check (small Python) | `schema/topic.yml` | missing field, `doc_type` ∉ Diátaxis vocab, `status` ∉ vocab |

**Termbase wiring (the §6 single-sourcing move):** `docs/product-names.draft.yaml` +
`docs/product-abbreviations.draft.yaml` (already on this branch) are promoted to a committed termbase and
**compiled** into (a) Vale `accept.txt`/`reject.txt` + a `Vale.Terms` substitution style and (b) the
`typos.toml` whitelist by a tiny `vdocs build-termbase` generator — one source, two enforcers, drift-gated.

## 4. The `va-docs-portal` SSG — MkDocs-Material, extended

What "extended" means, concretely (this is the only net-new tool-building in the plan, and it's small):

1. **Multi-repo aggregation.** Each package's docs are a **git submodule** under `sources/`; the portal
   `mkdocs.yml` sets `docs_dir`/nav to compose them. (Submodules chosen over `mkdocs-multirepo-plugin`
   for v1: transparent, offline-deterministic, no fetch-at-build. The plugin is the fallback if
   submodule ergonomics bite.) Adding `kernel-docs` later = `git submodule add` + one nav line.
2. **Per-source edit-me button** — the one real piece of code. MkDocs' global `edit_uri` can't express
   "different source repo per page," so `hooks/edit_links.py` (MkDocs native `hooks:`) computes each
   page's edit URL from which `sources/<repo>` subtree it came from, mapping to that repo's GitHub
   `…/edit/main/docs/<path>`. Material's `content.action.edit` renders the pencil. Locally (no remote)
   the URL is a configured placeholder; it goes live unchanged on push.
3. **Search** — Material's built-in offline lunr search (no external service).
4. **Offline + optimized** — Material `offline` + `navigation.prune` plugins so the built `site/` is a
   zip-distributable, file://-openable artifact — matching the vdocs offline ethos and letting a
   reviewer preview without even running a server.
5. **Nav** — `mkdocs-awesome-pages-plugin` so each `*-docs` repo owns its own `.pages` ordering and the
   portal doesn't hand-maintain a giant `nav:`.
6. **Versioning (deferred)** — `mike` reserved for when FileMan 22.2 + a future patch coexist; not wired
   in the pilot.

## 5. Phases L0–L6

Each phase TDD-first where it touches `vdocs` code, independently shippable, and leaves the corpus
gate-green. Status legend: ⬜ not started.

### ⬜ L0 — Scaffolding + gate harness (no real content)
- Create local git repos `~/projects/fileman-docs` and `~/projects/va-docs-portal`.
- Stand up MkDocs-Material skeleton + the full §3 gate config in `fileman-docs`; prove `make gate`
  green on a placeholder `index.md`.
- ✅ **`vdocs build-termbase` generator landed** (`kernel/termbase.py` + CLI; TDD, gate-green): compiles
  the curated `product-names.yaml` / `typo-corrections.yaml` / glossary acronyms → `accept.txt` + a Vale
  `substitution` style + a `typos` extend-words snippet (1117 approved terms). Source is the *curated*
  registries, not the noisy `docs/*.draft.yaml` (those were already curated into them 2026-06-10).
  *Follow-up:* some product `full` names in `product-names.yaml` are noisy doc-title fragments — a
  registry-curation cleanup, harmless in `accept.txt` (unmatched Vale exceptions) but worth a pass.
- **Gate:** `make gate` green on the skeleton; termbase generator unit-tested.
- *(= strategy P1.)*

### ⬜ L1 — Mechanical export: gold → `fileman-docs` first pass (`status: imported`)
- Add `vdocs export-fileman --subset` (extends the planned `publish`/L3): for the four slugs, emit
  self-contained GFM — resolve assets→`media/` (reuse `kernel/figures.py`), inline narrative tables,
  reference tables→`data/*.yml`, boilerplate→`_includes/`, rewrite front matter (frozen provenance +
  lifecycle), and run **code-block reconstruction** over the DBS-API pages (bold-as-code/escaped-prose →
  ```` ```mumps ````/```` ```console ````, un-escape `\$ \_ \*`, bind `Figure N:`/`Example N:` captions).
- Commit the output to `fileman-docs` as the **imported baseline** (every topic `status: imported`).
- **TDD (vdocs):** pure transforms (`*_pure.py`) for code-block reconstruction + table classify + front-
  matter rewrite, each test-first. **Gate:** subset exports; `make gate` green; zero residual `\$`/`\_`
  outside code; no dangling `media/`/`_[Table N]` refs.
- *(= master-publication P1/P2 + FileMan-POC P1, subset-scoped.)*

### ⬜ L2 — Content audit + crosswalk
- Inventory the subset from `corpus-manifest.json`/`index.db`; AI-assisted audit (Diátaxis Compass per
  section) → **ROT triage** (keep/merge/rewrite/retire) → **gap list**; write drift-gated
  `reference/crosswalk.md` (+ `crosswalk.yml` source) mapping every old section → new topic, capturing
  N→1 merges and 1→N splits.
- **Gate:** crosswalk covers 100% of subset source sections (coverage check red-gates); disposition sheet
  produced.

### ⬜ L3 — Diátaxis re-chunk (the editorial 80%)
- Execute the dispositions **in `fileman-docs`**: split File Security into `use/` (how-to) + `concepts/`
  (why); chunk ScreenMan into learning topics and single-source its concept vs the (out-of-pilot) UM;
  slice the Technical Manual into `operate/`; chunk the chosen DBS-API calls one page each; extract
  shared concepts + glossary terms into `_includes/`.
- Every topic typed (`doc_type` ∈ vocab), minimalism-trimmed, scannable (descriptive headings, inverted
  pyramid), semantic-line-broken for clean diffs.
- **Gate:** `make gate` green on all re-chunked topics; crosswalk current; no topic > the "one job"
  smell test (flag >12-step procedures for split).

### ⬜ L4 — Live-VistA `verify-docs` on the DBS-API blocks
- Add `vdocs verify-docs`: extract execution-tagged blocks, run via `m vista exec --engine ydb|iris`
  against **vehu + foia-t12** from a known fixture state, assert captured output matches the documented
  roll-and-scroll, **red-gate** mismatches, stamp `verified_on:` on green. Read-only APIs run as-is;
  the `FILE^DIE` write runs against a throwaway `^DIZ(` file; `^DIK` delete tagged `manual-review`.
- **TDD (vdocs):** harness logic test-first with a fake engine; real-engine run is an integration gate.
  **Gate:** every executable DBS-API block green on ≥1 engine (both where applicable); none silently
  skipped.
- *(= FileMan-POC P2, subset-scoped. Check the shared-lake/engine rule before running.)*

### ⬜ L5 — Build the `va-docs-portal` SSG
- Build the §4 portal: add `fileman-docs` as a submodule; Material theme + offline/prune/awesome-pages/
  search plugins; write `hooks/edit_links.py` (per-source edit URL); theme override for the banner +
  edit pencil. `make serve` → `http://localhost:8000`.
- **Gate:** portal builds `--strict`; the edit-me button on every page resolves to the correct
  (placeholder-GitHub) `fileman-docs` path; search returns subset topics; built `site/` opens offline.
- Prove extensibility: a stub `sources/kernel-docs` submodule slots in with one nav line (then removed).

### ⬜ L6 — Proofread to 100% + reviewer preview loop
- Drive every subset topic to `status: reviewed` via the §10 machine + AI + human layering (AI proposes
  diff-scoped edits → human accepts → sign-off recorded in front matter + git). Generate a **coverage
  dashboard** page (`X/Y reviewed · A/B DBS blocks verified · 0 Vale errors · 0 dead links`).
- Document the **peer-reviewer workflow** (local): clone portal + submodule, `make serve`, browse,
  click edit-me → edit in `fileman-docs` → local commit/PR.
- **Gate:** coverage gate fails if any subset topic is still `imported`; all §3 gates + all L4 verifies
  green. **This is the pilot's definition of done (§7).**

## 6. What stays mechanical (vdocs) vs editorial (fileman-docs)

A clean seam keeps the pipeline deterministic and the human work bounded:

| Mechanical — **in `vdocs`**, deterministic, tested, gated | Editorial — **in `fileman-docs`**, human + AI-assisted, reviewed |
|---|---|
| Asset/table/boilerplate materialization; front-matter rewrite | Diátaxis mode decisions (split/merge/relocate) |
| Code-block reconstruction + un-escape + caption binding | Reconciling contradictions against live VistA |
| `verify-docs` execution + stamping | Minimalism trimming; prose/clarity edits |
| Termbase → Vale/typos config generation | Gap-fill: net-new topics no manual stated |
| Crosswalk coverage check | Per-topic `reviewed` sign-off |

`vdocs export-fileman` runs **once** to seed the baseline; thereafter `fileman-docs` is the master and
the only re-runs are `verify-docs` (CI freshness) and re-`export` of a *newly added* package — never a
re-overwrite of edited topics.

## 7. Definition of done (pilot acceptance)

The pilot is done when, for the four-doc subset:
1. `~/projects/fileman-docs` holds re-chunked, Diátaxis-typed, single-sourced topics; **every topic
   `status: reviewed`** (coverage gate green).
2. **All §3 gates pass** (`make gate` green: Vale 0 errors, markdownlint incl. MD045 alt-text, typos,
   lychee, `mkdocs build --strict`, pa11y WCAG 2.1 AA, front-matter schema).
3. **Every executable DBS-API block verified** on vehu and/or foia-t12 (`verified_on` stamped); none
   silently skipped.
4. The **crosswalk** accounts for 100% of subset source sections (nothing dropped — the auditable proof).
5. `~/projects/va-docs-portal` builds the site and **serves it on `localhost`**, with a working **edit-me
   button per page** pointing at the (eventual) `fileman-docs` GitHub path, offline-openable `site/`.
6. A one-paragraph **coverage dashboard** states the numbers, and the **peer-reviewer local-preview
   workflow** is documented.

At that point the public-GitHub + Pages step is a mechanical follow-on (push the two repos, flip
`edit_uri` from placeholder to real, enable Pages), and **Kernel becomes the next package by reusing the
template** — the strategic payoff.

## 8. Risks & open questions

1. **MkDocs per-source edit URL** is the one genuinely custom bit; if `hooks/edit_links.py` proves
   fragile against submodule path resolution, fall back to `mkdocs-multirepo-plugin` (purpose-built for
   this). Low risk, isolated.
2. **Code/prose classification recall** — the minority of DBS-API regions the detector can't classify get
   `manual-review`, never silent drop (carried from FileMan-POC). Acceptable for a pilot?
3. **Reference-table generation depth** — for the Technical Manual slice, hand-curate `data/*.yml` from
   the gold CSVs for the pilot, or generate from the live data dictionary now? (Plan assumes hand-curate;
   automate in the Kernel expansion.)
4. **AI proofread reviewer of record** — who signs off `status: reviewed` for FileMan (editorial/SME
   call, not engineering)? For the local pilot, Rafael is the reviewer of record; flag for real VA SME
   sign-off before any public push.
5. **Engine coordination** — `verify-docs` must honor the shared-lake/engine rule (check for a live
   operator run; use only the `m vista exec` driver path; never raw `docker exec`).
6. **Repo home at push time** — Q3 deferred org placement (vista-cloud-dev vs personal); revisit at the
   public-push follow-on, since it sets CODEOWNERS identities and the edit_uri host.
