# Identity and classification, measured end to end

**Measured 2026-08-05** against the live lake: inventory 8,983 records (crawl of 2026-08-05), built
corpus `index.db` 1,040 documents (build of 2026-08-04), both banked snapshots, and the registries.
Extends [`vo-document-identity-and-rmpv.md`](vo-document-identity-and-rmpv.md), which found the
problem; this measures its size.

---

# Part A — the identity problem is wider than `doc_id`

## A1. All four identity keys embed the application

The earlier finding named `doc_id`. In fact **every** key in the identity vocabulary begins with the
application code:

```
doc_id      = ACKQ:ackq3_0_p12tm
doc_key     = ACKQ/ackq3_0_p12tm          ← the FK the whole search layer joins on
anchor_key  = ACKQ:ACKQ:TM:ackq3_p12tm    ← the version-group key
group_key   = ACKQ:ACKQ:3
```

| key | documents whose key starts with their own `app_code` |
|---|---|
| `anchor_key` | **1,040 / 1,040** |
| `group_key` | **931 / 1,040** |

So VA re-filing a document does not only change its `doc_id` — it changes the key that decides
**which version family it belongs to**. Two releases of one manual, one of them re-filed, land in
different version groups.

## A2. Everything downstream is keyed on it

| store | table | keyed on | rows |
|---|---|---|---:|
| `state.db` | `acquisitions` | `doc_id` | 1,044 |
| `index.db` | `documents` | `doc_id` + `doc_key` | 1,040 |
| `index.db` | `doc_meta_staged` | `doc_id` | 1,040 |
| `index.db` | `doc_sections` | `doc_key` (FK) | 83,745 |
| `index.db` | `chunks` | `doc_key` (FK) | 57,895 |
| `index.db` | `entity_mentions` | `doc_key` (FK) | 90,506 |
| `index.db` | `relations` | `doc_key` | 203,272 |
| `inventory.db` | `inventory` | `doc_id` | 8,983 |
| | | **total** | **447,525** |

Plus the **filesystem layout itself** — `documents/silver/text/03-normalized/<app>/<slug>/` and
`gold/consolidated/<app>/<slug>/`, 109 application directories over 1,040 (silver) and 615 (gold)
documents. The application code is not merely a column; it is a **path component**, so a re-filing
physically moves bundles.

## A3. Blast radius of the re-filing that actually happened

75 filenames changed owning application between the two crawls. 14 of them were already fetched and
built:

| what would be re-keyed | rows |
|---|---:|
| `doc_sections` | 1,424 |
| `chunks` | 92 |
| `documents` | 14 |
| `acquisitions` | 14 |
| `entity_mentions` | 6 |

≈**1,550 rows** for **14 documents** VA merely re-filed — nothing about their content changed.

> ⚠️ The 1,424-sections-to-92-chunks ratio on these documents is lopsided even by the corpus's known
> chunk-less rate. Noted, not diagnosed — it is a separate question from identity.

## A4. The app component splits one document into several

Of 7,641 genuine records over 3,721 distinct slugs, **42 slugs are carried by more than one
application**, creating **63 surplus identities**:

| applications sharing one slug | documents |
|---|---:|
| 2 | 25 |
| 3 | 14 |
| 4 | 2 |
| 5 | 1 (`phar_1_api_r0520`) |

This is not corruption. VA publishes a multi-package document **once per package folder**, titled
from each package's perspective. The pipeline then mints one identity per copy.

## A5. The cross-listed copies, finally measured — and the recommendation narrows

A4 called the 63 extra ids "surplus" on the strength of same-filename-different-folder. That was an
inference, and it was flagged unproven: the fetch gate admits one copy per document, so we had never
held two to compare. **Measured 2026-08-05** by fetching every copy of the six most widely
cross-listed slugs (21 files) and comparing both bytes and extracted text:

| slug | copies | byte-identical? | text |
|---|---:|---|---|
| `phar_1_api_r0520` | 5 | no (265,658–265,879 B) | 56,819–56,843 words — **Δ 24 (0.04%)** |
| `icd_10_ptf_modifications_ig` | 4 | no | 10,450–10,455 words — **Δ 5** |
| `psj_5_pso_7_psu_4_dg_5_3_pss_1_rn` | 4 | no (23,139–38,178 B) | **618 words, byte-for-byte identical text** |
| `ecme_hipaa_ncpdp_1_rn` | 3 | no (**78 KB vs 497 KB**) | 5,619–5,620 words — **Δ 1** |
| `pss_1_dosing_ord_ck_um_r0918` | 3 | no | 69,131 words in all three |
| `m1e1_pso_7_psj_5_pss_1_rn` | 3 | no | 2,526–2,527 words — **Δ 1** |

**No copy is byte-identical to another, and the text is 99.96%+ identical.** The largest word
difference anywhere is 24 words in 56,843; three of the six differ by a single word. The byte
divergence is embedded images and Word re-export metadata — `ecme_hipaa_ncpdp_1_rn` is 78 KB under
ECME and 497 KB under PSS, for **one word** of text difference.

That one word is the point: each package's copy carries **its own patch reference in the title**
(`BPS*1*1 ECME HIPAA NCPDP Release Notes` vs `PSS*1*90 Release Notes — HIPAA NCPDP Connection for
EDI Pharmacy`). So the copies are the same document, published once per package and labelled from
that package's side.

**What this changes.** Two conclusions, and they point in opposite directions:

- **Cross-listing is not a defect.** Collapsing these to one `doc_slug` identity would merge
  documents that are the same in substance but differ in exactly the field a reader searches by —
  the package's own patch number. Keeping them distinct is a defensible modelling choice, not an
  accident. ~~63 surplus ids~~ → **63 deliberate variants**. The word "surplus" in A4 is withdrawn.
- **Re-filing remains a real defect.** When VA moved the ISS documents from ADT to Scheduling,
  nothing about them changed — same file, same content, new id. That is identity churn with no
  informational content, and it is the case worth fixing.

**Revised recommendation.** The earlier three-layer proposal (document = `doc_slug`) is
**withdrawn** — the measurement does not support it. What survives is much narrower:

> Identity should be **continuous across re-filing**: when a document that has already been
> acquired reappears under a different application, it should keep the identity it had, rather than
> departing and being re-born. This is the identity analogue of CI.2 master-set retention, which
> already protects the *set* but not the *key*. The precedent for the mechanism is
> `registries/anchor-aliases.yaml`.

**Not a contract change.** That reframing removes the case for v1.6 → v2: `doc_id` keeps its shape,
and the fix is continuity of assignment, not a new key. Scope, cost and risk all drop by an order of
magnitude — which is the whole reason the measurement was worth running before building anything.

---

# Part B — every attribute a document carries

## B1. The eight classification axes (8,983 records)

| axis | distinct | shape |
|---|---:|---|
| `system_type` | 11 | VistA 68.5% · Web client 10.3% · VA enterprise service 5.9% · Integration middleware 4.1% · **VistA + GUI 3.7%** · **VistA + COTS 3.5%** · VBA system 1.6% · COTS product 1.1% · Data patch 0.7% · **VistA + middleware 0.4%** · Program documentation 0.2% |
| `app_status` | 3 | active 60.3% · archive 38.3% · decommissioned 1.4% |
| `noise_type` | 4 | (none) 85.1% · vba_form 13.3% · va_ref 1.7% · test_document 1 record |
| `doc_format` | 3 | pdf 57.6% · docx 42.3% · doc 7 records |
| `out_of_scope_reason` | 3 | mirrors `doc_format` exactly — it *is* the non-DOCX format |
| `doc_code` | 32 | RN 18.1% · DIBR 15.6% · FORM 13.3% · UG 10.0% · UM 9.8% · IG 9.2% · TM 8.3% · … |
| `section_name` | 5 | Clinical 65.4% · Financial-Administrative 16.8% · GUI Hybrids 9.1% · Infrastructure 8.7% · Monograph 2 records |
| `cots_dependent` | 2 | True on 404 records (4.5%) |

## B2. `system_type` is the axis that decides admission

The fetch gate admits on the **`"VistA"` prefix** of `system_type` plus a non-denied `app_status`
(`registries/inventory/scope-policy.yaml`). Measured:

| `system_type` | records | admitted | rate |
|---|---:|---:|---:|
| VistA | 6,155 | 2,242 | 36.4% |
| **VistA + GUI** | 332 | 174 | 52.4% |
| **VistA + COTS** | 311 | 62 | 19.9% |
| **VistA + middleware** | 35 | 12 | 34.3% |
| Web client | 922 | 0 | 0% |
| VA enterprise service | 534 | 0 | 0% |
| Integration middleware | 371 | 0 | 0% |
| VBA system | 145 | 0 | 0% |
| COTS product | 97 | 0 | 0% |
| Data patch | 64 | 0 | 0% |
| Program documentation | 17 | 0 | 0% |

Everything not prefixed `VistA` is admitted at **exactly 0%**. This single registry value is the
most consequential attribute in the pipeline — which is why an *unclassified* application
disappearing silently (the RMPV case) matters as much as it does.

## B3. `cots_dependent` is a second, independent axis — and it disagrees with the first

The flag is set on six applications, and it does **not** line up with `system_type`:

| app | `system_type` | `cots_dependent` |
|---|---|---|
| MD, ROI, YS | VistA + COTS | True |
| CPT, DRG | Data patch | True |
| PREM | Integration middleware | True |

So "depends on a commercial product" is expressed **twice**, in two vocabularies that do not agree:
`VistA + COTS` says it in `system_type`, `cots_dependent` says it as a boolean, and three
applications carry the boolean while their `system_type` says something else entirely. Meanwhile
`system_type` alone drives admission and `cots_dependent` drives nothing.

**Recommendation (not built):** treat `system_type` as two orthogonal facts — a **platform** (is it
VistA/M?) and **companions** (what else does it need: GUI, COTS, middleware, ObjectScript?) — and
derive `cots_dependent` from the companion list rather than maintaining it separately. That removes
a class of contradiction rather than documenting it.

---

# Part C — where "hybrid VistA" fits

## C1. The taxonomy already anticipated hybrids

Three compound values exist (`VistA + GUI` — CPRS, MAG; `VistA + COTS` — MD, ROI, YS;
`VistA + middleware` — XOBV), and `scope-policy.yaml` says so explicitly:

> "VistA hybrids (VistA + GUI / + COTS / + middleware) stay IN — they are VistA-based."

Because the gate matches a **prefix**, any new `VistA + …` value is admitted exactly like plain
`VistA`. Verified: no code compares `system_type` to a literal, and it is not exposed in the read
contract — so the vocabulary can grow without a contract change.

## C2. RMPV is a new *kind* of hybrid, not another instance of an old one

| existing value | second artifact | where it runs |
|---|---|---|
| `VistA + GUI` | Delphi client executable | on the **workstation** |
| `VistA + COTS` | commercial product | a **separate system** |
| `VistA + middleware` | VistALink / middleware tier | a **separate tier** |
| **`VistA + ObjectScript`** | IRIS ObjectScript classes | **inside the same instance as the M code** |

RMPV installs **two** artifacts: the KIDS build `RMPV*1*6` *and*
`4Sight-II_Deployment_1_2_20260528.xml`, a set of ObjectScript classes providing a FileMan-to-Class
REST service into VALIP. That second artifact is server-side — the application's logic is split
across two languages **in one instance**. None of the three existing hybrids describes that.

**Classified as `VistA + ObjectScript`.** Admission is unchanged (1,212 targets, RMPV's 3 documents
still admitted) because the prefix rule handles it.

## C3. Is it a population or a one-off? Measured: a one-off, so far

Searching all 57,895 chunks of the built corpus for non-M runtimes:

| runtime named | applications |
|---|---:|
| Delphi | 31 |
| Java | 25 |
| InterSystems | 13 |
| .NET/C# | 9 |
| SQL Server | 8 |
| IRIS | 6 |
| **ObjectScript** | **0** |

⚠️ **A mention is not a dependency, and this is exactly where that bites.** VistA *runs on*
InterSystems, so its documentation naturally names it. Sampling the 12 applications that mention
both KIDS and InterSystems:

- **XU (Kernel)** — "use the TLS configuration name as defined in InterSystems IRIS": a **platform
  facility**.
- **DGBT** — a **glossary entry**: "InterSystems | The 3rd party vendor that provides a product
  known as InterSystems Cache".
- **TIU** — a glossary entry for HealthConnect.
- **VPR** — interfaces *to* InterSystems Health Connect / the SDA model: an **integration**, not a
  shipped artifact.

None of them ships second-language code. **`ObjectScript` appears in zero applications**, which is
the cleanest signal available: RMPV is the **first server-side-polyglot VistA application in the
corpus**. Treat the count as a floor, not a census — the corpus is the pre-RMPV build, and this is a
lexical search.

## C4. Why the category matters beyond bookkeeping

**vista-meta cannot see the ObjectScript half.** The measured model is built from M routines,
globals and FileMan (`routines`, `files`, `vista_file_9_8`). RMPV's 18 M routines will appear there
once the extract catches up; its ObjectScript classes never will. So for this class of application
the measured model is **structurally incomplete**, and "not measured in vista-meta" stops meaning
"not present in VistA".

That is a reason to name the category rather than fold it into plain `VistA`: it marks exactly the
applications where the code model and the documentation will disagree, by construction.

> *documented:* RMPV is KIDS-installed and ships ObjectScript (its own `RMPV*1*6` Technical Manual).
> *measured:* vista-meta data-v1 (extract 2026-07-03) has 0 RMPV routines, 0 files, 0 entries in
> #9.8. **Not reconciled** — the extract predates the documents. Re-check on the next refresh.

---

## What changed in this pass, and what did not

**Changed** (data only, gate verified): `RMPV: VistA` → `RMPV: VistA + ObjectScript` in
`registries/inventory/system-types.yaml`, with the evidence in a comment; the registry-count test
updated to assert the compound value *and* that it still starts with `VistA`. Admitted targets
1,212, unchanged. 1,488 tests, coverage 96.39%, `make check` exit 0.

## Follow-ups — resolved 2026-08-05

1. **Identity rework — investigated and WITHDRAWN as specified.** The measurement in A5 disproved
   its premise. What replaces it is the much smaller "identity continuity across re-filing", and it
   is *not* a contract change. Not built; it now needs a short proposal, not a migration.
2. **`cots_dependent` vs `VistA + COTS` — DONE.** `split_system_type` separates a platform from its
   companions, and `classify_system` derives `cots_dependent` from **both** sources, so a
   `"VistA + COTS"` application is COTS-dependent whether or not anyone remembered the second list.
   Two registry-wide invariants now assert it for all 197 applications, plus a closed vocabulary for
   platforms (8) and companions (GUI, COTS, middleware, ObjectScript) so a typo cannot quietly
   become a new category admitted at 0%.
3. **`system-type=unclassified` — DONE.** It is now its own disposition, `undecided`, not
   `not-vista`: an absence of a decision rather than a decision. It counts against `complete`
   (exit 1) and the report **names the applications to classify** and where to do it. The live lake
   is still COMPLETE — RMPV is classified, so nothing is undecided — so the gate is armed without
   firing today.
