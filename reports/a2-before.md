# A2 before: body coverage of the index as built after A1, measured 2026-11-07

Provenance: `index_db` /home/rafael/data/vdocs/index.db · documents 1040 · chunks 57804 ·
`corpus_content_hash` `5b118189…` · read contract 1.8 (the A1 rebuild, `ccc184b`).
Kickoff: `docs/prompts/a2-preamble-and-coverage-gate-kickoff.md`; the finding is review §3.2.

## Step 1: coverage per latest document — three instruments, one answer

For each of the 615 `is_latest` documents: body word tokens (`\w+`) of the gold `body.md` with the
frontmatter dropped (gold == the normalized body for all 615, checked byte for byte), against the
tokens of the text the index actually chunked (the searchable sections of `index_pure.shred_sections`
over the same body, which is what `chunks` holds minus the `#pN` overlap and the table chunks).

| Instrument | Below 95% | Below 99% | Note |
|---|---|---|---|
| raw body, nothing excluded | 150 | 338 | counts the generated `## Contents` list as body text |
| **body minus the generated TOC list** (the gate's measure) | **70** | **147** | the `## Contents` heading and its link lines are navigation `normalize` regenerates, not document text |
| the MCP review's bag-of-words (`reports/mcp-review-coverage.json`) | 78 | 222 | per term, min(body count, index count) over ALL chunks incl. table chunks and section titles: a body token is "covered" when the same word occurs anywhere in the document's index |

The kickoff expected about 78 and said to stop if the count was far off. It is not: once the
generated TOC is excluded the strict sequence measure gives 70, and the review's 78 was a
looser instrument (a word in a table chunk or a title covers the same word in the body). The
difference is what a token is credited against, not what the index holds. The gate uses the strict
measure: a document's body text, minus our own TOC, against the text of its non-table chunks.

Distribution (strict): 0-50%: 2, 50-80%: 9, 80-90%: 19, 90-95%: 40, 95-99%: 77, 99-100%: 123.

## Step 2: the cause, per document below 95%

| Cause | Documents |
|---|---|
| (a) empty-title heading `^#+\s*$` in the body | 10 |
| (b) first retained heading after more than 5% of the body | 50 |
| (c) something else | 10 |

(a) and (b) explain 60 of 70: the preamble section and the heading repair are the fix.
The three hand-checked documents are the worst three of cause (a)/(b): `RMPR/rmpr_3_nppdum` 10.6%
(88% of its body precedes `# Appendix B`), `PSO/pso_7_0_iep_um_4_pt2` 48.1%, `KMPS/kmps2_0um` 56.9%.

The 10 of cause (c), none below 80%:

| Document | Coverage | Body | Indexed | Headings | Preamble | First 200 characters |
|---|---|---|---|---|---|---|
| `LR/labbbumf` | 80.06% | 17,996 | 14,408 | 88 | 0.02% | ## Contents  - [The Laboratory Planning and Implementation Guide Version 5.2 of the Laboratory software application prov… |
| `EDIS/edp_2_1_1_ug` | 90.34% | 25,537 | 23,069 | 314 | 2.27% | **Emergency Dept Integration Software (EDIS) Version 2.1.1 Increment 3 User Guide**  _Version 2.1.1 · Patch EDIS*2.1.1 ·… |
| `PXRM/ahobpr_registrantportal_usermanual_v3` | 91.27% | 4,319 | 3,942 | 40 | 0.81% | ## Contents  - [Overview](#overview)   - [As required by Public Law 112-260, Dignified Burial and Other Veterans’ Benefi… |
| `AR_WS/wstech` | 92.42% | 12,970 | 11,987 | 30 | 4.9% | **Automatic Replenishment/Ward Stock Version 2.3 Technical Manual**  _Version 2.3 · Patch AR/WS*2.3 · Published 1994-01_… |
| `XU/krn_8_0_dg_lock_manager_ug` | 94.03% | 1,590 | 1,495 | 18 | 4.97% | **Kernel 8.0 Developer's Guide: Lock Manager User Guide**  _Version 8.0 · Patch XU*8.0 · Published 2025-08_  Source: <ht… |
| `XU/krn_8_0_dg_tls` | 94.6% | 1,835 | 1,736 | 23 | 4.31% | **Kernel 8.0 Developer's Guide:Transport Layer Security (TLS)**  _Version 8.0 · Patch XU*8.0 · Published 2026-03_  Sourc… |
| `XU/krn_8_0_dg_error_processing_ug` | 94.82% | 1,621 | 1,537 | 17 | 4.87% | **Kernel 8.0 Developer's Guide: Error Processing User Guide**  _Version 8.0 · Patch XU*8.0 · Published 2025-08_  Source:… |
| `PSS/pss_1_p136_and_p117_um_cp` | 94.9% | 7,829 | 7,430 | 39 | 3.64% | **PSS*1*117/136 User Manual Change Pages**  _Version 1 · Patch PSS*1*117 · Published 1997-09_  Source: <https://www.va.g… |
| `XWB/xwb_1_1_dg_r` | 94.9% | 62,804 | 59,600 | 774 | 3.7% | **XWB*1.1*73 Developer's Guide**  _Version 1.1 · Patch XWB*1.1*73 · Published 2021-09_  Source: <https://www.va.gov/vdl/… |
| `LEDI/lab_ledi_iv_um_update` | 94.92% | 38,124 | 36,189 | 108 | 4.92% | **LA*5.2*80/LR*5.2*427 LDSI/LEDI IV Update User Manual**  _Version 5.2 · Patch LA*5.2*80 · Published 2013-08_  Source: <… |

Two of them (`LR/labbbumf`, `PXRM/ahobpr_registrantportal_usermanual_v3`) have whole paragraphs as
heading text, so their generated TOC entries wrap onto lines the TOC recogniser does not strip and
the "missing" tokens are TOC text; the Kernel developer guides and the rest sit at 94–95% and are
looked at after the rebuild. (c) does not dominate; the plan stands.

All 70 documents below 95%, worst first:

| Document | Coverage | Body | Indexed | Headings | Preamble | Cause |
|---|---|---|---|---|---|---|
| `RMPR/rmpr_3_nppdum` | 10.56% | 11,340 | 1,198 | 2 | 88.28% | a: empty-title heading |
| `PSO/pso_7_0_iep_um_4_pt2` | 48.14% | 3,436 | 1,654 | 3 | 51.86% | b: first retained heading after >5% of body |
| `PSN/psn_4_p296_um_cp` | 56.56% | 2,242 | 1,268 | 18 | 43.18% | b: first retained heading after >5% of body |
| `KMPS/kmps2_0um` | 56.89% | 3,851 | 2,191 | 15 | 0.65% | a: empty-title heading |
| `PSO/pso_7_0_iep_um_5` | 58.07% | 5,912 | 3,433 | 5 | 41.93% | b: first retained heading after >5% of body |
| `SD/sd_pims_tm_addendum_943` | 61.4% | 614 | 377 | 4 | 38.6% | b: first retained heading after >5% of body |
| `KMPV/kmp_um` | 66.04% | 4,956 | 3,273 | 29 | 33.35% | b: first retained heading after >5% of body |
| `DI/fm22_krn8_file_security` | 67.08% | 4,250 | 2,851 | 9 | 32.92% | b: first retained heading after >5% of body |
| `VPR/vpr_tm` | 68.02% | 5,312 | 3,613 | 45 | 31.74% | b: first retained heading after >5% of body |
| `XT/xtvs_vpsrt_tm_r` | 70.01% | 5,082 | 3,558 | 46 | 29.54% | b: first retained heading after >5% of body |
| `DI/fm22_2tm` | 75.95% | 11,674 | 8,866 | 62 | 23.9% | b: first retained heading after >5% of body |
| `LR/labbbumf` | 80.06% | 17,996 | 14,408 | 88 | 0.02% | c: other |
| `PRCA/icd_10_um_tp_4_5_281` | 80.41% | 148 | 119 | 1 | 21.62% | b: first retained heading after >5% of body |
| `PSB/psb_3_p2_chui_um_cp` | 81.87% | 2,162 | 1,770 | 12 | 17.76% | b: first retained heading after >5% of body |
| `KMPV/kmp_tm` | 81.88% | 10,326 | 8,455 | 116 | 16.04% | b: first retained heading after >5% of body |
| `XWB/xwb1_1p44um` | 81.9% | 6,387 | 5,231 | 24 | 18.1% | a: empty-title heading |
| `RMPR/rmpr_3_tm` | 82.17% | 7,304 | 6,002 | 1 | 17.83% | b: first retained heading after >5% of body |
| `XWB/xwb_1_1_sm_r` | 84.14% | 11,741 | 9,879 | 51 | 15.45% | b: first retained heading after >5% of body |
| `MPIF/mpif_1_0is` | 84.94% | 53,553 | 45,488 | 234 | 15.06% | b: first retained heading after >5% of body |
| `PRF/dg_53_650_ug` | 86.13% | 6,871 | 5,918 | 22 | 13.58% | b: first retained heading after >5% of body |
| `KMPD/kmpd3_0tm_r` | 86.79% | 12,191 | 10,581 | 73 | 12.8% | b: first retained heading after >5% of body |
| `RA/ra5_0hl7is` | 87.03% | 20,456 | 17,802 | 267 | 12.69% | a: empty-title heading |
| `MAG/imgsecgd` | 87.63% | 7,896 | 6,919 | 66 | 11.73% | b: first retained heading after >5% of body |
| `PRC/ifcp5_1gip` | 87.9% | 35,144 | 30,890 | 175 | 11.89% | b: first retained heading after >5% of body |
| `VALM/valm_1_0_dg` | 88.08% | 19,240 | 16,946 | 136 | 11.48% | b: first retained heading after >5% of body |
| `OOPS/oops2_0security_guide` | 88.24% | 2,193 | 1,935 | 29 | 1.14% | a: empty-title heading |
| `PSJ/psj_5_p113_nurse_cp` | 88.44% | 8,481 | 7,501 | 54 | 11.32% | b: first retained heading after >5% of body |
| `XWB/xwb_1_1_ug_r` | 88.47% | 16,319 | 14,438 | 80 | 10.93% | b: first retained heading after >5% of body |
| `ADT/adt_cnhr_um` | 88.77% | 3,412 | 3,029 | 26 | 10.87% | b: first retained heading after >5% of body |
| `LR/lr_5_2_425_ps_ug` | 89.77% | 17,014 | 15,274 | 50 | 9.83% | b: first retained heading after >5% of body |
| `XU/krn_8_0_dg_server_options_ug` | 90.0% | 910 | 819 | 7 | 9.34% | b: first retained heading after >5% of body |
| `XU/krn_8_0_dg_spooling_ug` | 90.01% | 781 | 703 | 6 | 9.99% | b: first retained heading after >5% of body |
| `XU/krn_8_0_dg_help_processor_ug` | 90.08% | 796 | 717 | 7 | 9.92% | b: first retained heading after >5% of body |
| `LR/labbbumg` | 90.12% | 1,124 | 1,013 | 8 | 8.45% | b: first retained heading after >5% of body |
| `EDIS/edp_2_1_1_ug` | 90.34% | 25,537 | 23,069 | 314 | 2.27% | c: other |
| `PRS/paid_tm` | 90.6% | 10,970 | 9,939 | 7 | 9.4% | b: first retained heading after >5% of body |
| `MPIF/rg1_0_tm` | 91.03% | 16,437 | 14,963 | 71 | 8.62% | b: first retained heading after >5% of body |
| `PXRM/ahobpr_registrantportal_usermanual_v3` | 91.27% | 4,319 | 3,942 | 40 | 0.81% | c: other |
| `GMRC/constm` | 91.54% | 54,158 | 49,574 | 158 | 8.2% | b: first retained heading after >5% of body |
| `DI/scrn_tut` | 91.58% | 22,949 | 21,016 | 151 | 7.39% | b: first retained heading after >5% of body |
| `MPIF/rg1_0_pm` | 91.69% | 17,681 | 16,211 | 56 | 8.09% | a: empty-title heading |
| `ADT/adt_mcsm` | 91.7% | 518 | 475 | 5 | 6.37% | b: first retained heading after >5% of body |
| `WII/wii_1_1_um` | 91.78% | 3,700 | 3,396 | 22 | 7.24% | b: first retained heading after >5% of body |
| `GEN/gcs2sec` | 91.85% | 847 | 778 | 14 | 7.44% | a: empty-title heading |
| `CPRS/or_3_p529_qr` | 91.91% | 1,187 | 1,091 | 1 | 8.09% | b: first retained heading after >5% of body |
| `XU/krn_8_0_dg_unwinder_ug` | 92.1% | 987 | 909 | 9 | 7.9% | b: first retained heading after >5% of body |
| `XU/krn_8_0_tm` | 92.24% | 18,875 | 17,410 | 106 | 7.48% | b: first retained heading after >5% of body |
| `XU/krn_8_0_dg_common_services_ug` | 92.37% | 1,036 | 957 | 6 | 7.63% | b: first retained heading after >5% of body |
| `AR_WS/wstech` | 92.42% | 12,970 | 11,987 | 30 | 4.9% | c: other |
| `XU/krn_8_0_dg_xtmp_global_ug` | 92.43% | 1,044 | 965 | 5 | 7.57% | b: first retained heading after >5% of body |
| `VAQ/pdx1_5um` | 92.56% | 26,516 | 24,544 | 125 | 6.28% | b: first retained heading after >5% of body |
| `XU/krn_8_0_dg_security_keys_ug` | 92.59% | 1,133 | 1,049 | 15 | 6.97% | b: first retained heading after >5% of body |
| `KMPD/kmpd3_0um_r` | 92.65% | 21,769 | 20,168 | 37 | 7.29% | b: first retained heading after >5% of body |
| `XU/krn_8_0_dg_dns_ug` | 92.69% | 1,204 | 1,116 | 12 | 6.48% | b: first retained heading after >5% of body |
| `XU/krn_8_0_dg_field_monitoring_ug` | 92.96% | 1,122 | 1,043 | 8 | 7.04% | b: first retained heading after >5% of body |
| `OR/gnum` | 93.28% | 3,468 | 3,235 | 20 | 6.37% | a: empty-title heading |
| `MAG/vista_pacs_hl7_profile_1_2` | 93.56% | 47,827 | 44,748 | 503 | 5.7% | b: first retained heading after >5% of body |
| `VPR/vpr_dg` | 93.57% | 26,792 | 25,069 | 160 | 6.34% | b: first retained heading after >5% of body |
| `DI/fm22_2um1` | 93.69% | 37,587 | 35,215 | 206 | 6.01% | b: first retained heading after >5% of body |
| `XM/xm_8_0_sysmgmtguide` | 93.7% | 37,878 | 35,493 | 176 | 6.01% | b: first retained heading after >5% of body |
| `XU/krn_8_0_dg_address_hygiene_ug` | 93.87% | 1,451 | 1,362 | 17 | 5.44% | b: first retained heading after >5% of body |
| `XU/krn_8_0_dg_lock_manager_ug` | 94.03% | 1,590 | 1,495 | 18 | 4.97% | c: other |
| `XU/krn_8_0_dg_tls` | 94.6% | 1,835 | 1,736 | 23 | 4.31% | c: other |
| `XU/krn_8_0_dg_esig_ug` | 94.63% | 1,471 | 1,392 | 13 | 5.37% | b: first retained heading after >5% of body |
| `RA/ra5_0um` | 94.72% | 118,779 | 112,502 | 225 | 5.24% | a: empty-title heading |
| `OOPS/oops2_0um` | 94.76% | 11,673 | 11,061 | 96 | 5.2% | a: empty-title heading |
| `XU/krn_8_0_dg_error_processing_ug` | 94.82% | 1,621 | 1,537 | 17 | 4.87% | c: other |
| `PSS/pss_1_p136_and_p117_um_cp` | 94.9% | 7,829 | 7,430 | 39 | 3.64% | c: other |
| `XWB/xwb_1_1_dg_r` | 94.9% | 62,804 | 59,600 | 774 | 3.7% | c: other |
| `LEDI/lab_ledi_iv_um_update` | 94.92% | 38,124 | 36,189 | 108 | 4.92% | c: other |

## Step 3: empty-title headings corpus-wide

`^#+\s*$` matches **1,907 lines in 307 of the 1,040 normalized bodies** (`silver/text/03-normalized`),
far more than the three documents of the review. What follows each (next non-blank line):

| Next line | Count |
|---|---|
| another heading | 1,618 |
| a short plain line (≤ 12 words) — a title Pandoc rendered as a paragraph, e.g. `**Enhancements in Patch 18**` | 169 |
| a long paragraph | 63 |
| a table row | 17 |
| a list item | 15 |
| HTML (`<img>`, `<span>`, `<table>`) | 13 |
| end of document | 12 |

**Amendment to work-plan step 1.** The kickoff's rule — take the next non-blank line as the heading
text unless it is a heading, fence, list item or table row — would promote 63 paragraphs to headings.
The repair takes the next line as the title only when it is a short plain line (at most 12 words,
not a nav line, table marker, HTML tag or image), with one addition found on the first rebuild: the
title may open with its Word bookmark (`<span id="_Toc…" class="anchor"></span>Using Surgical
Implants`, the RMPR shape), which rides along onto the heading line so the anchor survives. In every
other case the bare `# ` line is removed. The repair runs **before** `recover_headings`, not after:
the first rebuild showed the empty heading was load-bearing in two places — it made
`recover_headings` read a body as structured, and it gave `recover_headings_from_toc` a tree to
promote into — so repairing it afterwards cost `RMPR/rmpr_3_nppdum` its one real heading and its
`refs.yaml`, which `validate`'s count-drop tripwire (1,005 → 1,004 sidecars) caught and blocked.
The first 40 documents: `ACKQ/ackq3_0tm`, `ADT/adtbe_um`, `ADT/adt_mts_um`, `ACKQ/ackq3_0_p12tm`, `ACKQ/ackq3_0um`, `ACR/acr_p_pimstm`, `ADT/adt_pimsschoutput`, `ADT/pims_user_manual_menus_intros_orientation`, `ASU/asutm`, `ANRV/br_technical_manual_security_guide`, `AMT/am_oramum`, `ASCD/ascd_sd_53_495_um`, `ADT/sadt_um`, `ANRV/br_user_manual`, `ASCD/ascd_sd_53_495_tm`, `AMT/am_oramtm`, `ASCD/ascd_px_10_p184_um`, `ANRV/vist_4_um`, `CPRS/cprsguium`, `AR_WS/wsuser`, `CPRS/cprsguitm_0_636`, `DGBT/dgbt_1_41_tm`, `CPRS/cprslmtm`, `CPRS/cprslmtm_0_636`, `ASU/asuum`, `ECME/bps_1_tm`, `CPRS/cprslmum`, `CPRS/cprsguitm`, `ECX/ecx_3_178_tm`, `DGJ/dgj1_0_tm`, `DGJ/dgj1_0_um`, `DGBT/dgbt_1_41_um`, `DVBA/dvba_27_215_amie_tm`, `DVBA/amie_2_7_238_tm`, `EDIS/edp_um`, `DVBA/rous`, `DI/fm22_tutorial`, `EPI/lab_epi_searchextract_tm_ug`, `FB/fb_3_5_tm_r1217`, `EPI/lab_epi_tech_user_guide`, … (the list is the
scratchpad's `a2-empty-title-docs.txt`; it is reproduced by the grep in the kickoff).

## Step 4: harness baseline

Nothing has changed since A1's after-report (`reports/a1-after.json`: nDCG@10 0.4530, MRR 0.5449,
recall@10 0.4747 on the same `index_db`, documents and chunks), so it is the paired baseline for A2.

## Decision

The plan stands with two amendments recorded above: the gate's measure excludes the generated TOC
list (the kickoff's raw count overstates by 80 documents), and the empty-heading repair joins only
a short title line. Chunk windows: 5,961 non-table `#pN` parts over 1,214 sections carry a one-block
overlap, 371 of them line-split without one; the gate's indexed count drops the first block of every
later part, which undercounts those 371 by one line each — the safe direction for a floor.

Script: the session scratchpad's `a2/coverage.py` (strict measure; also reports the raw measure).
