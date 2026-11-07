# A2 after: the lake rebuilt from `normalize` with the empty-heading repair, the preamble section and the body-coverage gate, measured 2026-11-07

Provenance: `index_db` /home/rafael/data/vdocs/index.db · documents 1040 · chunks 58240 (A1: 57,804) ·
sections 84,159 (A1: 83,738) · `corpus_content_hash` `b6e38e58…` (changed: 307 bodies changed) ·
read contract 1.8 · 347.0 MB (A1: 360.5). Rebuild `vdocs run --from normalize --to manifest --force`
(log `~/data/vdocs/reports/run-a2-preamble-coverage-2-2026-11-07.log`: 8 stages GREEN, `refs_sidecars` 1,005 as
before, `validate` 0 findings). Before: `reports/a2-before.md`. Paired ranking: `reports/a2-paired.md`.

## Success criteria (kickoff "after building")

| Criterion | Before | After | Verdict |
|---|---|---|---|
| 1 latest documents below 95% body coverage (strict measure, script) | 70 | **5** (below 99%: 147 → 72) | met: every one is a named exception or a FAIL the operator sees |
| 1 the three hand-checked documents | RMPR 10.6%, PSO 48.1%, KMPS 56.9% | **all three at or above 95%** (RMPR now has the heading `Using Surgical Implants` with its bookmark anchor; PSO and KMPS carry a `preamble`) | met |
| 2 empty-title headings in normalized bodies | 1,907 lines in 307 bodies | **3 lines in 2 bodies**, all inside what the shared fence scan reads as a code block (an HL7 `~~~` repeat separator opened an unclosed fence in `PRC/ifcp5_1tech_manual` and `VBECS/vbecs_2_3_3_admin_user_guide`) | met for the body text; the residue is a fence-tracking matter, not the repair's |
| 3 `vdocs doctor` | GREEN, nothing compared a body with its chunks | **GREEN**, 24 checks, the exception list printed (below) | met |
| 4 harness paired against A1 | — | identical on all 30 questions; no judged section lost; **no preamble section enters any top 10** | met |
| 5 `make check` in vdocs-web and vdocs-cli | — | **both green**; `vdocs section PSO/pso_7_0_iep_um_4_pt2/preamble` returns the text, `vdocs document` lists the preamble first; vdocs-web's `Preview` orders by `seq` and its `SectionText` by id, so a `preamble` row needs nothing special | met |
| 6 floor to 99? | — | **no**: 72 latest documents sit between 95 and 99%, mostly bodiless sentence headings and small hollow headings; the causes are written into the proposal | D2 says 99 once the three known causes are fixed; two are, the third (sentence headings) is a chunking rule for later |

`vdocs doctor`, as printed:

```
  ◎ BY-DESIGN body coverage            612/615 latest documents at or above 95% of body tokens indexed; 3 below the floor accepted by policy
  ◎ BY-DESIGN body coverage exceptions 3 listed: LR/labbbumf — paragraphs converted as headings with no body (48 sections); their text is the heading, which a bodiless section does not index (80.1%), EDIS/edp_2_1_1_ug — paragraphs converted as headings with no body (18 NOTE sections); same cause (92.6%), PXRM/ahobpr_registrantportal_usermanual_v3 — paragraphs converted as headings with no body (14 sections); same cause (92.1%)
615 gold documents · 22 pass · 2 by-design · 0 warn · 0 fail
GOLD LIBRARY: GREEN
```

## What the gate found that the kickoff did not know

- **The gate's measure had to exclude normalize's own text twice.** The generated `## Contents` list
  (found before building: 150 → 70 documents below 95%) and the identity header (found after: on a
  148-token change page, `PRCA/icd_10_um_tp_4_5_281`, the title, version and source lines were 20%
  of the "body" with every word of the document's text indexed). Both are set aside by the same two
  patterns the preamble section uses (`index_pure.IDENTITY_HEADER_RE`, `GENERATED_TOC_RE`), from
  one home. With them: 5 → 3 documents below the floor, all one cause.
- **The remaining cause is converter paragraphs turned into headings with nothing under them.**
  `LR/labbbumf` (80.1%: 48 such sections, e.g. `# The Laboratory Planning and Implementation Guide
  Version 5.2 … provides detailed instructions…`), `EDIS/edp_2_1_1_ug` (92.6%: 18 `### NOTE: …`
  sections), `PXRM/ahobpr_registrantportal_usermanual_v3` (92.1%: 14). A heading with no body is
  off the search surface by design (`is_searchable`: "a bare heading with nothing under it"), which
  is right for a real heading and wrong when the heading IS the paragraph. Corpus-wide: **130
  bodiless sections with headings of more than 12 words in 31 latest documents**. Out of A2's
  scope (a chunking rule); the three are named exceptions with that reason and an expiry — when a
  sentence-heading rule lands they rise above the floor and `doctor` WARNs that the entries are
  stale.
- **The empty heading was load-bearing.** Repairing it after `recover_headings` (the kickoff's
  order) cost `RMPR/rmpr_3_nppdum` its one real heading: the bare `# ` had made the body count as
  structured and had given `recover_headings_from_toc` a tree to promote into. `validate`'s
  count-drop tripwire caught it (`refs_sidecars` 1,005 → 1,004) and blocked the first rebuild — the
  gate doing exactly its job. The repair now runs first, and a title that opens with its Word
  bookmark (`<span id="_Toc…" class="anchor"></span>Using Surgical Implants`) keeps the span on
  the heading line so the anchor survives into `refs.yaml`.

## The preamble, as built

195 latest documents gained a `preamble` section (173 ok, 19 hollow, 3 stub),
395 chunks with the oversized ones split; the largest is `ACR/acr_p_pimstm/preamble` (7,863
characters). Its text is the document's own: identity header and generated TOC set aside, so a
document whose only text before its first heading is the header gets no preamble (420 documents).
45 documents gained headings from the repair (`DGJ/dgj1_0_tm` 29 → 38, `GMTS/gmts_2_7_p133_um`
63 → 69); none lost one.

## Red-proof of the gate (scratch lake, before the rebuild)

1. Today's A1 index, policy as shipped: **RED**, "545/615 latest documents at or above 95% …
   below: RMPR/rmpr_3_nppdum (10.6%), PSO/pso_7_0_iep_um_4_pt2 (48.1%), …" — the gate fires on the
   defect the review found.
2. Every chunk of `XU/krn_8_0_sm_kids_ug` deleted on the copy: **RED**, the victim listed at 0.0%.
3. An exception `GONE/never_existed` planted in a copy of the policy: **RED**, "exception(s) name
   no latest document: GONE/never_existed — remove them from registries/doctor-policy.yaml", and
   the exception list WARNs "(not in the index)".

Scripts: the session scratchpad's `a2/coverage.py` (strict measure, written to
`reports/a2-after-coverage.json` with per-document rows), `a1/paired.py`, `a1/probes.py`; the
harness section below is `scripts/baseline_golden.py --out reports/a2-after.md`.

---

# Phase 0.4 baseline — lexical retrieval quality (golden set)

- **Lake:** `/home/rafael/data/vdocs`  ·  **mode:** lexical (FTS5+BM25), keyword forms  ·  **k:** 10
- **Labeled queries:** 30 of 31
- **mean nDCG@10:** 0.453
- **mean MRR:** 0.5449
- **mean recall@10:** 0.4747
- **mean redundancy@10:** 0.0871 (all queries)

## Per-query

| query | axis | nDCG@10 | MRR | recall@10 | redundancy@10 | hits |
|---|---|---|---|---|---|---|
| kids-install-build | kids-install | 0.0 | 0.0 | 0.0 | 0.0 | 10 |
| pharmacy-api-dispense | redundancy-probe | — | — | — | 0.7 | 10 |
| fileman-add-field | fileman-dd | 0.0 | 0.0 | 0.0 | 0.0 | 10 |
| rpc-broker-client-call | rpc-broker | 0.0637 | 0.125 | 0.1111 | 0.0 | 10 |
| mailman-decnet-transmission | mailman-network | 0.783 | 1.0 | 0.5714 | 0.3 | 7 |
| radiology-cancel-exam | radiology | 0.3308 | 0.1429 | 0.6667 | 0.0 | 10 |
| pharmacy-release-signed-order | pharmacy-release | 0.8415 | 1.0 | 0.5 | 0.3 | 8 |
| tiu-unsigned-notes | tiu-notes | 0.754 | 1.0 | 0.5 | 0.2 | 8 |
| vpr-allergy-data | vpr-domains | 0.7364 | 1.0 | 1.0 | 0.1 | 9 |
| lab-file60-audit | lab-audit | 0.9329 | 1.0 | 1.0 | 0.0 | 10 |
| cprs-enter-immunization | cprs-gui | 0.554 | 1.0 | 1.0 | 0.0 | 10 |
| vbecs-accept-order | vbecs-orders | 0.7126 | 1.0 | 0.25 | 0.0 | 10 |
| hl7-security-keys | hl7-security | 0.9173 | 1.0 | 0.5 | 0.2 | 9 |
| fileman-file-200-new-person | fileman-dd | 0.2351 | 0.125 | 0.3333 | 0.0 | 10 |
| fileman-import-host-file | api-leadin | 0.2404 | 0.1429 | 0.5 | 0.0 | 10 |
| fileman-input-transform-definition | api-leadin | 0.631 | 1.0 | 1.0 | 0.3 | 10 |
| fileman-blddialog-icr-number | api-leadin | 0.9173 | 1.0 | 0.5 | 0.0 | 1 |
| quasar-package-wide-variables | short-reference | 1.0 | 1.0 | 1.0 | 0.0 | 1 |
| hl7-table-0136-values | short-reference | 1.0 | 1.0 | 1.0 | 0.0 | 10 |
| kids-backup-transport-global | kids-install | 0.301 | 0.1111 | 1.0 | 0.0 | 10 |
| hl7-start-tcpip-link | hl7-links | 0.7829 | 1.0 | 0.6667 | 0.0 | 10 |
| fileman-file-access-security | kernel-security | 0.57 | 1.0 | 0.5714 | 0.0 | 10 |
| vista-signon-credentials | kernel-auth | 0.0 | 0.0 | 0.0 | 0.0 | 10 |
| fileman-finder-api | fileman-api | 0.2652 | 0.2 | 0.2 | 0.0 | 10 |
| taskman-monitor | kernel-ops | 0.4697 | 1.0 | 0.5714 | 0.0 | 10 |
| plain-change-password | plain-english | 0.5525 | 0.5 | 0.8 | 0.1 | 10 |
| plain-create-user-account | plain-english | 0.0 | 0.0 | 0.0 | 0.3 | 10 |
| plain-background-jobs | plain-english | 0.0 | 0.0 | 0.0 | 0.1 | 10 |
| plain-set-up-printer | plain-english | 0.0 | 0.0 | 0.0 | 0.0 | 10 |
| plain-enter-patient-allergies | plain-english | 0.0 | 0.0 | 0.0 | 0.1 | 10 |
| plain-send-email | plain-english | 0.0 | 0.0 | 0.0 | 0.0 | 10 |
