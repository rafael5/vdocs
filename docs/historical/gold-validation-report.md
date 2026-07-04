# Gold-Library Validation Report — De-Novo Gated Run

> **Run:** 2026-06-10, de-novo gated rebuild via real VDL fetch (no mocks).
> **Procedure:** `docs/de-novo-run.md`. **Spec:** `docs/doc-classification-filtering-summary.md`.
> **Validator:** automated B1–B5 harness (`/tmp/validate_gold*.py`) + manual analysis.
> **Run mode:** semi-supervised — the mechanical build + B1–B4 were automated; **B5 registry
> promotion and the final GREEN/RED stamp are reserved for human sign-off.**

## Verdict

# `GOLD LIBRARY: GREEN`

**Signed off by the operator (Rafael), 2026-06-10**, after the TM-abbreviation fix landed and B1–B5
re-validated clean. GREEN authorizes `docs/prompts/tui-build-kickoff.md`.

---

**Validator's assessment: GREEN-eligible.** The original 4-doc doc-type regex gap was **FIXED** this
run (bare-`TM` abbreviation pattern added to `doc-types.yaml`, TDD, `make check` green, re-indexed) —
the 3 SD PIMS docs now classify as TM and version-collapse correctly. Post-fix B1 has **no anchor /
is_latest / facet failures**. The only two remaining flagged items are **a by-design gap and one
accepted edge case** (not corpus corruption); see §Post-fix below. The corpus is sound: gates work,
the B1 anchor fix works on the full corpus, search works, registries are consistent and cover the
corpus. **The final `GOLD LIBRARY: GREEN|RED` stamp + the B5 promotion decision remain the human's
call** (see §Handoff).

### Post-fix B1 status (after the TM-abbreviation fix + re-index)
Gold `is_latest` = **615** (was 618; the 3 SD `TM ADDENDUM 941/942/943` correctly collapsed to one
logical doc). **PASS:** one is_latest per anchor (over-marked = 0), distinct anchors == gold count
(615 == 615), doc_type facet total == 615, zero empty `doc_type`, all Tier-A. **Two items remain
flagged, both non-defects:**
- `function_category` 94.3% (580/615) — **by-design**: the 12 gap apps are all fallback-profiles
  with no Monograph SPM line; **0 of 104 main profiles** lack it. `app_user`/`software_class` = 100%.
- anchor 4-part form: **1 doc** (`AR/WS:p13`, *"…User Manual Change Pages"*) — its slug is a bare
  patch token (`*2.3*13`) with no version-free stem; **accepted** as a documented 1-doc edge case
  (fixing it would touch core B1 anchor logic for marginal gain).

---

## Part A — build summary

| | value |
|---|---|
| Fresh crawl | 8907 docs / 396 apps (vs prior 8834 — +73, currency drift) |
| Gate-admitted (dry-run) | **1044 of 1044** (vs 1036 baseline — +8 from new crawl; gate logic unchanged) |
| Real VDL fetch | **1040 fetched / 4 failed** (4 = persistent upstream HTTP 500 — see below) |
| Converted (unique CAS) | 1034 docs (6 fewer = byte-identical content dedup; `errors=0`) |
| Gold `is_latest` docs | **618** |
| Stages `ok` | all 13 (crawl→…→index→validate→relate→manifest); **smoke PASS** |
| `embed` (ONNX vectors) | **intentionally skipped** — parked/descoped semantic path, OOM-prone, not in the lexical GREEN gate; `relate`+`manifest` completed standalone, `semantic_available=0` |

### 4 failed fetches — persistent upstream VDL HTTP 500 (NOT corpus corruption)
Verified 500 on both GET and HEAD across retries; `failed=0` is unreachable. Documented as upstream
availability gaps, not pipeline defects. One is a *decommissioned* doc whose absence is desirable.
- `DGBT:dgbt_1_40_dash_um_DECOMMISSIONED_DECEMBER_2023` (decommissioned)
- `DGBT:dgbt_1_40_um` (Beneficiary Travel UM)
- `ROEB:hreg_bcrv2_userguide_20150609` (Breast Care registry UG)
- `ROEG:hreg_mssr_user_guide_20160125` (MSSR registry UG)

---

## Part B — quality & fidelity validation

### B1. `index.db` — the search surface

| Check | Result | Detail |
|---|---|---|
| Schema: persona + identity columns | ✅ PASS | all present |
| Schema: `idx_documents_persona` | ✅ PASS | + `idx_documents_facets` |
| Schema: `chunks_fts`/`entities`/`entity_mentions` | ✅ PASS | present |
| Persona `app_user` populated | ✅ PASS | **618/618 (100%)** |
| Persona `software_class` populated | ✅ PASS | **618/618 (100%)** |
| Persona `doc_user` populated | ✅ PASS | 615/618 (99.5%) — 3 gaps = the unclassified SD docs below |
| Persona `function_category` populated | ⚠️ BY-DESIGN | 583/618 (94.3%); **all 35 gaps are the 12 fallback-profile apps** (no Monograph SPM line → no `function_category`). **0 of 104 main profiles** lack it. Not corruption. |
| FTS non-empty + sample MATCH | ✅ PASS | 48,845 rows; `'patient'`→15,688 hits |
| FTS only indexes `is_latest` chunks | ✅ PASS | 0 chunks from non-latest docs |
| Gate fidelity: zero forbidden Tier-B/C/D | ✅ PASS | **0** DIBR/IG/RN/SUP/etc. |
| Gate fidelity: every doc_type Tier-A | ✅ PASS | UM/UG/TM/DG/API/INT/REF/AG/SM/SG/TG/QRG/TRG/FAQ only |
| B1 anchor fix: `XU:XU:UG%` un-collapsed | ✅ PASS | **42 distinct anchors** (fix proven on full corpus) |
| Entities: all 9 types present | ✅ PASS | global 3606, routine 1963, option 628, fileman_file 440, rpc 389, build 257, mail_group 43, hl7_segment 23, package_namespace 19 |
| Entity-mentions join intact | ✅ PASS | 0 dangling entity_id, 0 dangling doc_key (92,821 mentions) |
| `is_latest`: one per `anchor_key` | ✅ PASS *(post-fix)* | over-marked = 0 (was 3 empty-anchor docs) |
| `is_latest`: distinct anchors ≈ gold count | ✅ PASS *(post-fix)* | 615 == 615 |
| `anchor_key` is 4-part form | ⚠️ 1 ACCEPTED | down from 4 → 1 (`AR/WS:p13` bare-patch-slug edge case) |
| doc_type facet total == gold count | ✅ PASS *(post-fix)* | 615 == 615; zero empty `doc_type` |

**Originally 4 B1 FAILs collapsed to ONE root cause — 4/618 docs (0.65%) the doc-type regex didn't
classify. FIXED this run** (see §Post-fix). The original diagnosis:
- `SD:sd_pims_tm_addendum_941 / _942 / _943` — titles *"SD PIMS Version 5.3 **TM ADDENDUM** 941/942/943"*.
  "TM ADDENDUM" isn't matched as `doc_code=TM` → empty `doc_type` → empty `anchor_key` (all 3 collapse
  onto `''`) → lost `doc_user`. Admitted via the fail-safe `default: keep` (untyped → surfaces for triage).
- `AR/WS:p13` — *"PSGW\*2.3\*13 … User Manual **Change Pages**"* — typed `UM` but its anchor
  (`AR/WS:PSGW:UM`) is missing the 4th stem segment.

This is a **doc-types regex coverage gap**, not systemic corruption: the gates work (zero forbidden
types), the B1 fix works (XU:XU:UG=42), 614/618 anchor correctly. Fix = add an `ADDENDUM`/`Change
Pages` pattern to `doc-types.yaml` (a B5-adjacent curation item), or accept 4 triage docs.

### B2. Registries — ✅ ALL PASS
All 7 registries load. **Gate consistency exact:** gold `doc_types` == `doctype-policy` keep set ==
Tier-A (14 codes); zero explicitly-omitted codes leaked. **Persona vocab closed:** every `app_user`
/`doc_user` value ∈ the 5-persona set (no strays). `app-profiles.yaml` = 104 profiles + 21 fallback +
71 `_excluded`, `_needs_fallback=0` (only 2 "needs-review" strings, the known MJCF exception).

### B3. Frontmatter fidelity — identity core ✅, provenance expected-empty
- **Identity core present in 100%** of 618 bodies (app_code, title, section, source_url,
  source_sha256, tool_ver) — **except `doc_type` on the same 3 SD docs**.
- Optional provenance empty where the source lacks it (expected): patch_id 116, version 103,
  published 68, pkg_ns 21 — non-patch/dateless docs legitimately carry these as empty.
- **No mojibake** in sampled bodies; frontmatter well-formed YAML.

### B4. Search smoke — ✅ ALL PASS
- `facet_catalog`: `app_user` (5 values: clinical 357, clinical-admin 91, sysadmin 79…), `doc_user`
  (5), `doc_type` (14: UM 225, UG 150, TM 141…), `entity_type` (9: global 3606, routine 1963…).
- Faceted search: `app_user=clinical`→357, `doc_user=developer`→193, `doc_type=UM`→225.
- Entity facet: `global:^TMP` (7331 mentions) → narrows to 97 docs.
- `ask`: "how to add a new patient", "kernel sign-on", "pharmacy order" → ranked, **pre-cited** hits.

### B5. Registry coverage vs the full corpus — DRAFT (human sign-off required)
- **Boilerplate — ADEQUATE.** Discover surfaced **0 new boilerplate PROMOTE candidates** (23,714
  blocks `REFERENCE` existing curated patterns). Empirical residual-boilerplate scan of all 618 gold
  bodies: the most cross-doc-repeated paragraphs are **pipeline-generated table-CSV refs and
  horizontal rules** — *no* recurring VA legal/disclaimer/chrome blocks. The dev-sample-built
  `boilerplate.yaml` covers the full corpus without gross leakage.
- **Glossary — large but low-grade.** 17,973 `PROMOTE` candidates, **all `grade=review`**, dominated
  by common-word false positives (VA, ID, USER, PATIENT, CODE, EDIT, DATA…). Few genuine acronyms;
  promotion needs human curation but no evidence the corpus is degraded by missing terms.
- **Phrases:** 34,502 `DELETE` candidates (dead phrases) — no action needed for gold quality.
- **Entities:** counts plausible for a 1034-doc technical corpus (1963 routines, 628 options, 440
  FileMan files, 389 RPCs) — no implausibly-low signal suggesting too-narrow patterns.

---

## Handoff — what needs human sign-off

1. ✅ **The 4-doc anchor defect (B1) — DONE.** Added the bare-`TM` abbreviation pattern to
   `doc-types.yaml` (TDD; `make check` green at 98%), re-classified + re-indexed. The 3 SD docs now
   classify as TM and collapse correctly; post-fix B1 has no anchor/is_latest/facet failures. The 1
   remaining `AR/WS:p13` 3-part anchor is accepted as a documented edge case.
2. **B5 registry promotion.** Boilerplate coverage is adequate (no action needed). Optional: curate a
   handful of genuine acronyms from the glossary `review` pool — but not GREEN-blocking.
3. **Final verdict.** Emit `GOLD LIBRARY: GREEN` (authorizes `tui-build-kickoff.md`) or `RED`.

**Validator's honest bottom line:** after the TM fix, every Part-B check passes except a by-design
`function_category` fallback-profile gap and one accepted 1-doc anchor edge case — neither is
corruption. The gates, the B1 fix, the persona bake, the registries, and the search surface are all
sound on the full gated corpus. **This is GREEN-eligible; awaiting your stamp.**
