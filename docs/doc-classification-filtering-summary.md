# Document Classification & Filtering — Consolidated Design

> **Status:** consolidated snapshot as of 2026-06-09. This document unifies the classification,
> enrichment, and filtering logic that grew through iterative discovery (app-scope gate, doc-type
> policy, Monograph-derived app profiles, software-class, the B1 anchor-key fix) into one coherent
> reference. It is descriptive of the *current* code/registries, and prescriptive about how the
> pieces fit together. Where the code and this doc disagree, treat it as a bug report against one of
> them.

## Table of contents

1. [Why this exists & the two-plane model](#1-why-this-exists--the-two-plane-model)
2. [Master table — every descriptive field & tag](#2-master-table--every-descriptive-field--tag)
3. [The admission funnel — gates in pipeline order](#3-the-admission-funnel--gates-in-pipeline-order)
4. [The gates & filters in detail](#4-the-gates--filters-in-detail)
5. [Inventory enrichments (control plane) — field by field](#5-inventory-enrichments-control-plane--field-by-field)
6. [Document enrichments (gold frontmatter)](#6-document-enrichments-gold-frontmatter)
7. [App-profile enrichments (the Monograph/#9.4 layer)](#7-app-profile-enrichments-the-monograph94-layer)
8. [Controlled vocabularies (taxonomies)](#8-controlled-vocabularies-taxonomies)
9. [Iterative discovery → consolidated decision log](#9-iterative-discovery--consolidated-decision-log)
10. [Open items & proposed next steps](#10-open-items--proposed-next-steps)

**Confidence legend** (used throughout): 🟢 **High** — deterministic, source-verified · 🟡 **Medium** —
regex/registry-curated heuristic · 🔴 **Low** — prior / needs-review / not-yet-derived.

---

## 1. Why this exists & the two-plane model

vdocs turns the VA VistA Document Library into a clean markdown corpus + an offline lexical search
index. Getting there means deciding, repeatedly, **what a document *is*** (classification) and
**whether it belongs in gold** (filtering). Those decisions live across two medallion planes:

- **Inventory plane (control plane, metadata only).** `crawl → catalog → serve-inventory`. One row
  per document *link* (`EnrichedRecord`), enriched with identity, classification, and noise/scope
  flags. The conformed `catalog.enriched` and the blessed gold `inventory.{json,csv,db}` live here.
- **Document plane (data plane, content).** `fetch → convert → … → consolidate → index`. The bytes,
  the markdown bundles, the version-collapsed gold corpus, and `index.db`.

Two orthogonal **app profiles** sit beside the inventory: `registries/inventory/app-profiles.yaml`
(purpose / audience / software-class per application, derived from the VistA Monograph + FileMan
file #9.4). They answer *"what is this application and who runs it,"* which the inventory rows don't.

Classification is **data, not code** (tenet #13): every gate reads a version-controlled registry; no
stage hard-codes a list.

---

## 2. Master table — every descriptive field & tag

Layers: **INV** = inventory `EnrichedRecord` · **DOC** = gold document frontmatter · **PROF** =
`app-profiles.yaml` · **GATE** = policy registry / computed at fetch. Role: **id** identity/join ·
**class** classification · **filter** selection/facet · **search** ranked retrieval · **gate**
admission decision · **prov** provenance.

| Field / tag | Layer | Derived from | Role | Conf |
|---|---|---|---|---|
| `doc_id` (`app:doc_slug`) | INV/DOC | `app_name_abbrev` + `doc_slug` | id | 🟢 |
| `anchor_key` (`app:pkg:doc_code:stem`) | INV | `kernel.ids.anchor_key` (+ slug stem) | id, gate (version-collapse) | 🟢 |
| `group_key` (`app:pkg:patch_ver`) | INV | patch parse | id (version) | 🟢 |
| `app_name_abbrev` | INV | VDL `(CODE)` → fallback → `pkg_ns` | id, filter | 🟢 |
| `app_name_full` / `canonical_pkg` | INV | VDL + package-master | class | 🟢 |
| `pkg_ns` | INV | patch prefix / package-master | id, filter | 🟡 |
| `section_name` / `section_code` | INV | VDL section + section-codes | class, filter | 🟢 |
| `system_type` | INV | system-types registry (by abbrev) | **class, gate (app-scope)** | 🟡 |
| `cots_dependent` | INV | system-types registry | class | 🟡 |
| `app_status` | INV | VDL ("decommissioned …") | **gate (app-scope)** | 🟢 |
| `doc_code` | INV/DOC(`doc_type`) | doc-types regex over title | **class, filter, gate (doctype)** | 🟡 |
| `doc_label` | INV | doc-types registry label | class | 🟡 |
| `doc_subject` / `doc_subtitle` | INV | title minus boilerplate | search | 🟡 |
| `doc_search_aliases` | INV | typo-correction aliases | search | 🟡 |
| `doc_layer` (anchor\|patch\|plain) | INV | patch parse | class | 🟡 |
| `doc_labelling` (code\|manual) | INV | manual-slugs registry | class | 🟡 |
| `doc_title` | INV/DOC(`title`) | VDL link text (mojibake-fixed) | search | 🟢 |
| `doc_slug` | INV/DOC(path) | filename normalize | id | 🟢 |
| `doc_stem` (version-free) | computed | `kernel.ids.slug_stem(doc_slug)` | id (logical doc) | 🟡 |
| `doc_format` (docx\|pdf\|doc) | INV | URL extension | **gate (docx-only)** | 🟢 |
| `patch_id` / `patch_ver` / `patch_num` | INV/DOC | title parse (`DG*5.3*1057`) | id (version order) | 🟡 |
| `noise_type` (vba_form\|va_ref\|test_document) | INV | noise-domains registry | **gate (noise)** | 🟡 |
| `out_of_scope_reason` | INV | derived (non-docx format) | **gate (docx-only)** | 🟢 |
| `*_url` (app/doc/companion/github) | INV | crawl | prov | 🟢 |
| `source_sha256` / `source_url` | DOC | fetch CAS | prov | 🟢 |
| `published` / `version` / `tool_ver` | DOC | normalize/enrich | prov | 🟢 |
| `app_purpose` *(profile)* | PROF | Monograph Brief Description / manual extract | class, search | 🟢/🔴 |
| `function_category` *(SPM Product Line)* | PROF | Monograph | class, filter | 🟢 |
| `audience_primary` / `_secondary` | PROF | SPM line → persona map (reviewed) | **class, filter** | 🟡 |
| `software_class` (I/II/III) | PROF | VDL membership (I) / doc reclass (III) | class, filter | 🟢/🔴 |
| `vasi_status` | PROF | Monograph (Production/Inactive/…) | class, filter (importance) | 🟢 |
| `business_owner` | PROF | Monograph | class | 🟢 |
| `parent_package` | PROF | FileMan #9.4 roster | id (rollup) | 🟢 |
| `reader_audience` (clinical/technical/admin/any) | search facet | doc-type → audiences.yaml | **filter, search** | 🟡 |
| `app_in_scope` *(proposed field)* | GATE | scope-policy (system_type+status) | **gate** | 🟢 |
| `doc_kept` / `tier` *(proposed field)* | GATE | doctype-policy | **gate, filter** | 🟢 |

> Two audience axes — keep them distinct: **`reader_audience`** (who reads *this doc type* — a facet
> over `doc_code`) vs **`audience_primary`** (who operates *the app* — a profile attribute). See §8.

---

## 3. The admission funnel — gates in pipeline order

Every document passes the same funnel. Each gate only ever **narrows**; nothing downstream re-widens.

```
crawl ─▶ catalog(enrich) ─▶ serve-inventory ════ HARD GATE (completeness/classification) ════▶
                                                  blesses the gold inventory = the fetch gate
fetch  ── select_fetch_targets() applies the ALWAYS-ON ADMISSION GATE ───────────────────────▶
         G1 noise   ∧  G2 docx-only  ∧  G3 app-scope  ∧  G4 doc-type policy
convert ─▶ discover ─▶ enrich ─▶ normalize ─▶ consolidate ══ G5 version-collapse (anchor_key) ══▶
                                                              one anchor per logical doc + lineage
index ─▶ manifest    (gold corpus + index.db + facets)
```

- **G1–G4 are conjunctive and always-on** in `fetch_pure.select_fetch_targets` — independent of the
  operator's `--app/--section/--all` selection. A doc enters the corpus only if it clears **all four**.
- **G5 (consolidation)** isn't an *admission* gate — it's de-duplication: it collapses the surviving
  versions of one logical document into a single anchor (and retains prior bodies as lineage).
- The **serve-inventory HARD GATE** is a different beast: a *quality* gate that refuses to bless an
  inventory that's incomplete vs the crawl or carries unclassified noise/system_type — it doesn't
  drop documents, it blocks the whole run until classification is sound.

**Net effect on the real corpus:** ~3,728 in-scope-docx links → G3+G4 admit **~1,390** (37%) → G5
collapses versions to the gold anchor set. (G4 alone removes ~63% — the install/changelog/fragment
doc-types; see §4.)

---

## 4. The gates & filters in detail

| # | Gate | Where | Registry / logic | Removes | Reversible? |
|---|---|---|---|---|---|
| HARD | Inventory quality | `serve-inventory` postflight | `serve_pure.evaluate_gate` | nothing (blocks run) | n/a |
| G1 | **Noise** | fetch (always-on) | `noise-domains.yaml` → `noise_type` | VBA forms, off-VDL refs, test docs (~1,343) | edit registry |
| G2 | **DOCX-only scope** | fetch (always-on) | `out_of_scope_reason` (non-docx) | PDF/DOC-only logical docs (§1) | scope decision |
| G3 | **App scope** | fetch (always-on) | `scope-policy.yaml` + `GatePolicy.app_in_scope` | non-VistA (COTS/web/enterprise) + decommissioned apps (74 apps) | toggle registry |
| G4 | **Doc-type policy** | fetch (always-on) | `doctype-policy.yaml` + `GatePolicy.doctype_kept` | Tier B/C/D doc-types (~2,338 docs) | per-code `decision` toggle |
| G5 | **Version-collapse** | `consolidate` | `anchor_key` grouping | redundant versions (kept as lineage, not deleted) | n/a (de-dup) |
| G6 | **Version-depth** *(proposed)* | fetch (selection) | latest-only / `max_versions=N` | superseded versions (~40% of kept) | toggle; trade-off = loses lineage |

**The admission gate is one predicate:** `GatePolicy.admits(rec) = not noise ∧ docx ∧ app_in_scope ∧
doctype_kept`. Defined in `src/vdocs/stages/fetch/fetch_pure.py`, loaded from the two policy
registries by `fetch/policy.py::load_gate_policy`, fingerprinted into `fetch`'s SKIP_IF_UNCHANGED so a
policy edit re-runs fetch.

**App-scope rule (G3):** in-scope ⟺ `system_type` starts with `VistA` **and** `app_status` ≠
`decommissioned`. VistA hybrids (`VistA + GUI/COTS/middleware`) stay in. The Monograph-only
"VASI = Inactive" exclusion is applied at the *profile* layer, not the live gate (the inventory has
no `vasi_status`). The real corpus has **0 unclassified** in-scope apps, so nothing real is dropped.

**Doc-type tiers (G4):** keep **Tier A** (14 reference codes); omit **B** (install/ops, 7), **C**
(version-delta changelog incl. RN/CRU/VDD/PDD/WF, 5), **D** (fragments, 4). `default: keep` is
fail-safe — a new/unmapped doc-type is admitted and surfaces for triage, never silently dropped.

**Version-collapse (G5) & the B1 fix:** `anchor_key` is the version-group key. It was
`app:pkg:doc_code` — too coarse, so 115/295 anchors over-grouped **324 distinct documents** (e.g. all
42 `XU:XU:UG` Kernel guides), demoting ~40 to `is_latest=0` (present in `index.db` but absent from
gold/FTS). **Fixed** by folding the version-stripped `doc_slug` stem in:
`app:pkg:doc_code:<stem>` — versions of one doc share the stem (still collapse); distinct manuals get
distinct stems (stay separate). `anchor_relpath` keys on the stem too, so distinct guides no longer
collide on one `<app>/<pkg>_<doc_code>` path.

---

## 5. Inventory enrichments (control plane) — field by field

`EnrichedRecord` (38 columns; `registries/inventory/` + `src/vdocs/stages/catalog/`). Grouped by role.

**Section / application context** — `section_name`·`section_code` (the VDL editorial section →
CLI/FIN/GUI/INF/MON; the *functional* axis), `app_name_full`·`app_name_abbrev`·`canonical_pkg`
(identity, post package-master canonicalization), `doc_subject_raw`·`doc_search_aliases` (search
hooks), `app_status` (active/decommissioned — feeds G3). 🟢/🟡

**System classification** — `system_type` (VistA / Web client / COTS product / …, by app abbrev via
`system-types.yaml`; **the G3 lever**), `cots_dependent`. 🟡 — registry-curated; a missing mapping
yields `unclassified` (surfaced by the HARD GATE).

**Patch identity** — `pkg_ns`, `patch_ver`(+`_major`/`_minor`), `patch_num`, `patch_id`(+`_full`),
`multi_ns`, `group_key`, **`anchor_key`** (the version-group key; B1-fixed). Used for version
ordering (consolidate) and lineage. 🟡 (parse-dependent) / 🟢 (`anchor_key` formula).

**Document identity / classification** — `doc_code`·`doc_label` (doc-type, regex over title; **the G4
lever**, also a search facet), `doc_subtitle`·`doc_subject` (cleaned title for search),
`doc_layer`(anchor/patch/plain), `doc_labelling`(code/manual), `doc_title`, `doc_filename`,
`doc_slug` (+ derived `slug_stem`), `doc_format` (**the G2 lever**). 🟡/🟢.

**Filter/gate flags** — `noise_type` (**G1**), `out_of_scope_reason` (**G2**, auto-derived: non-docx
⇒ out). 🟡/🟢.

**URLs / provenance** — `app_url`·`doc_url`·`companion_url`·`github_md_url`·`github_md_raw_url`. 🟢.

---

## 6. Document enrichments (gold frontmatter)

Baked onto each consolidated `body.md` by the `enrich`/`normalize`/`consolidate` stages. 11 keys:

| Key | Source | Use | Conf |
|---|---|---|---|
| `app_code` | inventory `app_name_abbrev` | filter, path | 🟢 |
| `doc_type` | inventory `doc_code` | filter, facet | 🟡 |
| `pkg_ns` | inventory | join, anchor reconstruction | 🟡 |
| `patch_id` | inventory | version display | 🟡 |
| `title` | inventory `doc_title` | search, display | 🟢 |
| `section` | inventory `section_code` | filter | 🟢 |
| `published` | revision/cover date | recency | 🟡 |
| `version` | doc metadata | display | 🟡 |
| `source_url` | fetch | provenance | 🟢 |
| `source_sha256` | fetch CAS | provenance, dedupe | 🟢 |
| `tool_ver` | pipeline | reproducibility | 🟢 |

> **Gap (open item):** the frontmatter does **not** yet carry the *operator-audience*,
> *software_class*, *function_category*, or *app_in_scope/doc_kept* tags. Those live only in the
> inventory/profiles today; baking them into frontmatter + `index.db` facets is the next step (§10).

---

## 7. App-profile enrichments (the Monograph/#9.4 layer)

`registries/inventory/app-profiles.yaml` — one profile per application (92 from the **VistA Monograph
July 2023** §4, 21 curated fallback, 83 excluded). Each profile:

| Field | Source | Use | Conf |
|---|---|---|---|
| `purpose` / `purpose_long` | Monograph *Brief Description* / *Full Description*; else manual extract | the app's reason-for-existing; search | 🟢 monograph / 🔴 manual |
| `function_category` | Monograph *SPM Product Line* (19-value VA taxonomy) | functional grouping, filter | 🟢 |
| `audience_primary` / `audience_secondary` | SPM line → operator persona (reviewed map + 15 per-app overrides) | **who operates the app**; filter | 🟡 |
| `software_class` (I/II/III) | VDL membership ⇒ **I**; explicit own-doc reclass ⇒ **III**; **II** = needs VA SAC list | national/local importance | 🟢 I / 🔴 II,III |
| `vasi_status` | Monograph (Production / Technical Reference Only / Not A System / Inactive) | lifecycle importance gradient | 🟢 |
| `business_owner` | Monograph | ownership, audience tie-breaker | 🟢 |
| `parent_package` | FileMan #9.4 roster (sub-prefix/sub-product rollup) | rollup (KMP*→KMP, DGFFP→DG…) | 🟢 |
| `namespace` | Monograph + #9.4 enrichment | join to inventory `pkg_ns` | 🟢 |
| `evidence` / `source` / `reviewed` / `confidence` | provenance | auditability | 🟢 |

**Operator-audience taxonomy (5):** `clinical` (physicians/nurses/pharmacists/lab) · `clinical-admin`
(MAS/clerks/registrars/HIM) · `business-admin` (billing/fiscal/HR) · `developer` (programmers/API) ·
`sysadmin` (IRM/installers). Derived from `function_category` (one reviewed decision per ~19 product
lines), with per-app overrides where a line mixes personas (e.g. all of SPM "Health Informatics").

**Software-class derivation (verified via the `vista` CLI):** FileMan file #9.4 PACKAGE has **no class
field** — class I/II/III is a SAC/FORUM attribute. So: **I** (national) is the deterministic default
(the VDL only catalogs nationally-released software); **III** (local) only on an explicit app-level
reclassification in the app's own docs (1 app: NUPA); **II** is not assignable without the published
VA SAC list (future `software-class.yaml`, joined by namespace).

---

## 8. Controlled vocabularies (taxonomies)

| Vocabulary | Values | Registry | Axis |
|---|---|---|---|
| **section_code** | CLI · FIN · GUI · INF · MON (5) | `section-codes.yaml` | editorial / functional area |
| **doc_code** | 29 codes (UM,UG,TM,DG,API,DIBR,IG,RN,…) | `doc-types.yaml` | what kind of document |
| **doc-type tier** | A (keep) · B/C/D (omit) | `doctype-policy.yaml` | admission value |
| **reader_audience** | clinical · technical · admin · any | `audiences.yaml` (by doc_code) | who reads *the doc* |
| **operator-audience** | clinical · clinical-admin · business-admin · developer · sysadmin | `app-profiles.yaml` (by app) | who runs *the app* |
| **system_type** | VistA(+GUI/COTS/middleware) · Web client · COTS product · VA enterprise service · Integration middleware · VBA system · Data patch · Program documentation (11) | `system-types.yaml` | platform / scope |
| **function_category** | 19 SPM Product Lines (Patient Care Services, Clinical Services, VHA Finance, …) | Monograph | what the app does |
| **software_class** | I (national) · II (field/national-optional) · III (local) | Monograph + (future) SAC list | distribution scope |
| **vasi_status** | Production · Technical Reference Only · Not A System · Inactive | Monograph | lifecycle |
| **noise_type** | vba_form · va_ref · test_document · "" | `noise-domains.yaml` | chrome vs content |

---

## 9. Iterative discovery → consolidated decision log

| Discovery (this workstream) | Consolidated decision |
|---|---|
| VDL `(CODE)` is the app abbreviation source; gaps need backfill | `abbrev-fallback.yaml` + `package-master.yaml`, then `pkg_ns` |
| Title alone can't tell you an app's purpose/audience | Derive purpose from the **VistA Monograph §4** (parse, not synthesize); audience follows purpose |
| Section ("Clinical") ≠ who operates the app | Two audience axes: `reader_audience` (doc) vs `operator-audience` (app) |
| "Clinical" must split care-staff vs clerical | 5-persona operator taxonomy; registries→clinical-admin uniformly; PCE→clinical |
| Class I/II/III asked for, but #9.4 has no class field (vista-CLI verified) | `software_class` = I default (VDL) + III on explicit reclass; II deferred to VA SAC list |
| COTS/web/decommissioned shouldn't enter gold | **G3 app-scope gate** (`scope-policy.yaml`), enforced at fetch |
| Install/changelog/fragment doc-types are low-value & flood search | **G4 doc-type policy** (keep A, omit B/C/D), reversible toggle |
| The gates belong before consolidation | Both enforced in `select_fetch_targets` (front-loaded; ~63% removed pre-convert) |
| Omitted doc-types are also the version-churners | G4 removes ~66% of consolidation collapse-work automatically |
| `anchor_key` over-groups distinct docs (B1) | Fold logical-doc **stem** into `anchor_key`/`anchor_relpath` |
| `--latest-only` looked like 71% savings | Illusory on the broken key (would delete 324 docs); ~40% safe **after** B1 |

---

## 10. Open items & proposed next steps

1. **Bake the new tags into the document plane.** Add `app_audience`, `software_class`,
   `function_category`, `app_in_scope`, `doc_kept`/`tier` to gold frontmatter **and** `index.db`
   facets (today they live only in the inventory/profiles; search can't filter on them offline). The
   pure predicate already exists (`GatePolicy`, `app-profiles.yaml`) — promote it to a baked field in
   `catalog`/`enrich` + a join in `consolidate`/`manifest`.
2. **Materialize the app-scope gate as an inventory field** (`app_in_scope` + `app_scope_reason`) and
   `state.db` skip-logging, with a regression fixture locking the 1,390/2,338 + 83-`_excluded` splits.
   See `docs/prompts/scope-gatekeeper-kickoff.md`.
3. **Class II via the VA SAC list** — seed `registries/inventory/software-class.yaml` by namespace to
   split true Class II out of the Class I default.
4. **Version-depth gate (G6 `--latest-only`)** — now unblocked by the B1 fix; ~40% fewer
   fetch/convert/consolidate ops on kept docs. Trade-off: forgoes historical-body lineage for
   `push --replay-history` — ship as a reversible toggle, not a default.
5. **Backfill the lake for B1** — re-run `catalog → serve-inventory → … → consolidate → index` so the
   ~324 recovered documents actually land in gold (the fix is code-only until then).
6. **`scope-policy.yaml` manual overrides** — per-app allow/deny with rationale, for edge cases the
   `system_type`/`app_status` rule misses (e.g. Class-3/unsupported `NUPA`).
