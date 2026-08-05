# Two investigations from the first delta — document identity, and whether RMPV is VistA

Follows [`vo-first-delta-2026-08-05.md`](vo-first-delta-2026-08-05.md), which raised both questions.
Measured on the 2026-08-05 inventory (8,983 records, 7,641 genuine) and the two banked snapshots.

---

# 1. Document identity — we need one authoritative id, and today we do not have one

## The problem, restated from evidence

`doc_id` is `<app_name_abbrev>:<doc_slug>` (`kernel/ids.py`). The application component is supplied
by **whichever VDL page lists the document**, and that is not a property of the document. Two
measured consequences:

**It changes when VA re-files.** 35 admitted documents "departed" on 2026-08-05 purely because VA
moved Integrated Scheduling Solution documentation from Admission Discharge Transfer to Scheduling.
`ADT:iss_release_1_10_0_rn` became `SD:iss_release_1_10_0_rn`. Nothing about the document changed.

**It splits one document into several ids.** VA publishes a multi-package document **once per
package folder**, and titles each copy from that package's perspective. 42 slugs are listed under
more than one application; the extreme case is a Pharmacy API guide carried under five:

```
PSA  .../Clinical/Pharm_api/phar_1_api_r0520.docx
PSJ  .../Clinical/Pharm-Inpatient_Med/phar_1_api_r0520.docx
PSN  .../Clinical/Pharm-National_Drug_File_(NDF)/phar_1_api_r0520.docx
PSO  .../Clinical/Pharm-Outpatient_Pharmacy/phar_1_api_r0520.docx
PSS  .../Clinical/Pharm-Data_Mgmnt_(PDM)/phar_1_api_r0520.docx
```

All 42 are this pattern — joint patches and combined builds (`PSB*3*47/PSS*1*141`,
`IB*2*276/PRCA*4.5*230`, the MOCHA combined builds across PSJ/PSO/PSS). The titles differ *because*
each package's page names the same file from its own side; that is a labelling difference, not a
document difference.

**And the slug alone over-splits in the other direction.** Six fetched documents are byte-identical
pairs under two slugs — `PSN:psn_4_um` / `PSN:psn_4_um_r`, `PSJ:psj_5_tm` / `PSJ:psj_5_0_tm` (1,040
fetched, 1,034 distinct payloads).

## What each candidate key actually survives

| candidate | survives re-filing | survives cross-listing | one id per document | notes |
|---|:--:|:--:|:--:|---|
| `app:doc_slug` (today) | ❌ 35 churned | ❌ up to 5 ids | ❌ | app is not a document property |
| VDL URL | ❌ path holds the app folder | ❌ one URL per copy | ❌ | 110 URLs changed between snapshots |
| `doc_slug` | ✅ | ✅ | ⚠️ 6 known over-splits | already format-agnostic: 3,725 of 3,784 pairs carry docx+pdf under one slug |
| content `sha256` | ✅ | ✅ | ❌ by design | identifies *bytes*; a revision is a new document |

## Recommendation — three layers, each answering a different question

There is no single field that answers everything, because "the same document" means three different
things in this pipeline. What we need is one **authoritative** key per question, and to stop using
the wrong one as a join key:

1. **Document identity → `doc_slug`, app-free.** It is the only candidate stable under both
   re-filing and cross-listing. `app_code` becomes an *attribute* — and a **multi-valued** one:
   `phar_1_api_r0520` is served by five packages, which is a fact worth keeping, not a reason for
   five identities.
2. **Payload identity → `sha256`.** Already the CAS key. Answers "are these the same bytes",
   which is what collapses VA's duplicate copies.
3. **Version-family identity → `anchor_key`.** Already exists and already app-free of version
   noise. Answers "the same document across releases".

**Do not adopt this blind.** Two things must be measured first, and neither is expensive:

- **The 6 payload-identical slug pairs** (`psn_4_um` / `psn_4_um_r`) are the one place `doc_slug`
  over-splits. Either fold them with a curated alias (the `anchor-aliases.yaml` precedent) or
  accept them as distinct VDL publications; decide explicitly.
- **Slug collisions between genuinely different documents are unproven.** All 42 observed cases
  look like one file cross-listed, but the fetch gate admits only one copy per document, so we have
  never held two copies to compare. The cheap test: fetch both copies of ~5 colliding slugs and
  compare sha256. If any pair differs, `doc_slug` alone is insufficient and needs a namespace.

**Blast radius, so this is not underestimated.** `doc_id` is the join key across `state.db`
(`acquisitions`), the fetch raw index, `index.db`, `knowledge.db`, the read contract consumed by
vdocs-web/vdocs-tui, and the golden answer key. Changing it is a contract change (`v1.6` → `v2`),
not a refactor. **Not built** — this records the finding and the recommendation; the change itself
needs a decision.

---

# 2. Prosthetics 4-Sight II (RMPV) — it IS VistA. Classified.

## The rule, applied

**Rule: it is VistA if it is KIDS-installed.** RMPV's own `RMPV*1*6 Technical Manual` settles it:

> "This VistA software includes **Kernel Installation and Distribution System (KIDS)** software and
> an InterSystems IRIS ObjectScript xml file release."
> Patch: **RMPV\*1\*6**

Corroborating, from the same manual:

- **18 M routines in the RMPV namespace** — `RMPVORMPRDIS`, `RMPVORMPROP`, `RMPVORMPRPAT`,
  `RMPVORMPRPAT5`, `RMPVORMPRPIYE/F/I/J/S`, `RMPVORMPRSIT`, `RMPVORMPRUTIL`, `RMPVDRV`, `RMPVFM`,
  `RMPVIO`, `RMPVRT`, `RMPVS633`, `RMPVS925`, `RMPVWALM`.
- "The VistA system should be operating the latest versions of **Kernel and VA FileMan**" and
  "must be installed on a **VistA facility server** with VA FileMan".
- **Integration Control Registrations** into measured VistA: **ICR #6540 → Prosthetics file #668**
  (`PROSTHETIC SUSPENSE`, `^RMPR(668,` — *measured:* vista-meta data-v1 · data-model/files.tsv ·
  file_number=668) and **ICR #2980 → `CMT^GMRCGUIB`/`SFILE^GMRCGUIB`** (Consults).

**It is a hybrid**, and worth stating plainly: alongside the KIDS patch it ships an InterSystems
IRIS ObjectScript XML (`4Sight-II_Deployment_1_2_20260528.xml`) providing a REST API via a
FileMan-to-Class utility, so 4-Sight II can call the VA Logistics Integration Platform (VALIP). The
IRIS half is not KIDS — but the KIDS half is real, and the rule decides on that.

⚠️ **Measured vs documented, not reconciled.** vista-meta data-v1 (extracted 2026-07-03) has
**0 RMPV routines, 0 RMPV files, 0 RMPV entries in file #9.8**, while RMPR has 433 routines and 93
files. That is consistent with RMPV being newer than the extract — *documented:* it is KIDS-installed;
*measured:* not present in our model. Re-check on the next vista-meta refresh rather than assuming
either side is wrong.

## What was wrong, and what changed

RMPV appeared in **no registry**, so `classify_system` returned `unclassified`
(`enrich_pure.py:290`), which the gate treats as not-VistA — **0 of its 15 records admitted**. A
genuinely new VistA application entered the library and the corpus ignored it.

**Fixed as data, not code** (tenet #13): one line in `registries/inventory/system-types.yaml`,
`RMPV: VistA`, with the evidence in a comment. Effects, measured:

| | before | after |
|---|---:|---:|
| admitted fetch targets | 1,209 | **1,212** |
| `inventory-unclassified-apps` warning | 15 | **gone** |

The three admitted documents are the Administrative Guide, Technical Manual and User Guide. The
`archive` twin (appid=444) contributes **nothing, correctly** — see below.

## Two things the investigation cleared up on the way

**The archive twin has no documents at all.** `appid=444` "Prosthetics 4-Sight II (RMPV) - ARCHIVE"
lists 9 "documents" that are all VA/VBA page furniture (benefits forms, the VA Strategic Plan). It
is an empty archive page wearing boilerplate.

**That boilerplate explains the entire duplicate-listing population.** Exactly **9 URLs are each
listed under 149 applications**, accounting for **1,341 listings** — and the noise classifier
already catches every one (`vba_form` 1,192 + `va_ref` 149 = 1,341). So "8,983 listings over 7,649
distinct URLs" is not messy data: it is 8 VBA forms and one strategic plan repeated as page
furniture, correctly excluded.

⚠️ **Say which unit you counted.** Listings (8,983) ≠ distinct URLs (7,649) ≠ genuine records
(7,641) ≠ admitted targets (1,212).

## The general lesson

`unclassified` is not a decision. `vdocs completeness` counted RMPV under
`not-vista:system-type=unclassified` and still returned **COMPLETE**, but nobody ever decided
RMPV was out of scope — it simply arrived after the registries were curated. VO.9 defines complete
as *nothing missing for a reason we chose*, so an unclassified application should not be able to
pass silently.

**Recommendation (not built):** make `system-type=unclassified` a *reportable* state in
`completeness` rather than a clean exclusion — a WARN naming the applications, so the next new VDL
application forces a deliberate ruling instead of vanishing. The registry-size test in
`test_registries.py` already acts as the tripwire for the reverse direction and caught this change.
