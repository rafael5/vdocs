# Inventory browser — step 0 measurements

Every figure in §1, §3 and §4 of [the inventory browser proposal](../docs/proposals/inventory-browser-proposal.md), measured again by `scripts/inventory_measurements.py` through the pipeline's own definitions. *Proposal* is the value the proposal printed before step 0.

## What this read

| Input | Identity |
|---|---|
| Lake | `/home/rafael/data/vdocs` (read-only) |
| `inventory.json` | 9,080 records, sha256 `d7078541298b511acec160e3d429b2d57eddee3eb954ea7e9e040dcb3343470e` |
| `index.db` | read_schema_version 1.6, corpus_content_hash `1bc0d78f3ae6c2eb0b69a29ee455ccaddb64d7aa00b79095dafeda3c28463517` |
| Crawl `catalog.raw.json` | 9,080 links, sha256 `93139fcc7f3039fb4b92db23fd619a8fe96ccbc57ab5a4bc4f7ae9ce711d4f16` |
| `state.db` acquisitions | 1,045 rows, sha256 of (doc_id, status) `596fdef2db0df7927c86b4066206f8f6b59fd261dadf3ab8993e90e1879faa4e` |
| `history.yaml` | 615 files, sha256 `329113edf959ac743edff0c729331b65567017733bd15c1c5d50bedc06545adf` |
| Registries | `/home/rafael/projects/vdocs/registries`, sha256 `fd0e23ffef4fc94f5e0f293ba7eeb0815329c2952d298db114852bc941124a44` |
| vdocs | commit `722d2c2b970cb94db75fed90a776eba17ca43d6d` (src, registries, scripts clean) |
| vista-meta | commit `d0df56bfdff7fb9d7fb2388f71876827c12c81eb`; `package-namespace.tsv` sha256 `40d561c29ea576c66ccd65a5e32e9e6646dc75a286701d172c8e0381a9735f17`, last changed in `f1e9d332aaaa4185c0eb74b9feb1f37a9d552229` |
| Run date | 2026-11-05 |

## §1 Why

| Figure | Proposal | Measured |  |
|---|---|---|---|
| `vdocs inventory --status` total: distinct non-noise `doc_id`s, any system type | 3,834 | 3,834 | same |
| … of which VistA (the gate's `app_in_scope`) | 2,941 | 2,886 | **differs** |
| … of which on a VistA system type, decommissioned applications included (the first measurement's definition) | — | 2,941 |  |
| `vdocs completeness` records | 9,080 | 9,080 | same |
| Records held with no gold document | 219 | 216 | **differs** |
| … archived sole survivors, never fetched | 152 | 152 | same |
| … DOCX the policy keeps, never fetched | 52 | 52 | same |
| … PDF records held as the only format (`sole-format`), never fetched | 9 | 6 | **differs** |
| … … of which the PDF twin of a DOCX with the same `doc_id` (none since `classify()` pairs by `doc_id` too) | — | 0 |  |
| … fetch failed | 5 | 5 | same |
| … rejected as bad content | 1 | 1 | same |
| … fetched, yet not in gold | — | 0 |  |
| … largest applications | SD 40, VBECS 27, CPRS 25, ROR 24, PSO 17 | SD 39, VBECS 27, CPRS 25, ROR 24, PSO 16 | **differs** |
| Gold documents whose `doc_id` no record carries | 15 | 15 | same |
| … whose slug the inventory lists under another app code (re-filed) | 14 | 14 | same |
| … whose slug is gone from the inventory | 1 | 1 | same |
| Records of the re-filed slugs, under the new app code, held but not in gold | 14 | 14 | same |

## §3 What a record is, and the facets

| Figure | Proposal | Measured |  |
|---|---|---|---|
| Records (listings) | 9,080 | 9,080 | same |
| Distinct `doc_id` | 5,032 | 5,032 | same |
| Records sharing one `doc_id`, at most | 6 | 6 | same |
| Links listed on more than one application page (the proposal: 18 benefits-form links) | 18 | 9 | **differs** |
| … records listing them | 1,334 | 1,332 | **differs** |
| Links listed more than once anywhere | — | 18 |  |
| … listings beyond the first of each | — | 1,334 |  |
| Records classified `not-vista:vba-form` (restated in D2) | 1,184 | 1,184 | same |
| … distinct files (D2: 18) | 18 | 8 | **differs** |
| Records with a gold match on `doc_id` | 2,120 | 2,120 | same |
| Distinct (application page, section, file URL, patch id) | 9,073 | 9,073 | same |
| … surplus records | 7 | 7 | same |
| … links listed more than once on one page | 5 | 5 | same |
| … … with every field identical | 3 | 3 | same |
| App codes on more than one application page | 171 | 171 | same |
| … the most pages | LR 12 | LR 12 | same |
| Distinct row keys | — | 9,080 |  |
| Gold-matched records whose computed Domain differs from `index.db` | 0 | 0 | same |
| Gold-matched records whose computed Audience differs from `index.db` | 0 | 0 | same |
| Gold-matched records whose computed App user differs from `index.db` | 0 | 0 | same |
| Gold-matched records whose computed Type differs from `index.db` | 0 | 0 | same |
| … whose Namespace differs (documents) | 2 | 2 | same |
| Records with no application profile (no app user, software class or domain) | 2,300 | 2,305 | same |
| … of which not VistA | 2,298 | 2,298 | same |
| Inventory namespaces (distinct non-empty `pkg_ns`) | 162 | 161 | **differs** |
| … named by the PACKAGE file (#9.4) | 102 | 102 | same |
| … … records | 6,710 | 6,710 | same |
| … not in the PACKAGE file but an application code | 56 | 56 | same |
| … … records | 1,717 | 1,717 | same |
| … named nowhere | PREC, PREN, XUSC | PREC, PREN, XUSC | same |
| … … records | 92 | 92 | same |
| Records with no namespace | 561 | 561 | same |
| Namespaces named by both the PACKAGE file and a same-code application | 94 | 94 | same |
| … whose two names are equal after folding case and punctuation | 73 | 37 | **differs** |
| Inventory namespaces with no same-code application name in `app-profiles.yaml` (restated in D4) | 60 | 64 | **differs** |
| Library namespaces (latest documents) | 96 | 96 | same |
| … named today (same-code application) | 92 | 92 | same |
| … named with the PACKAGE file first, else the same-code application | 96 | 96 | same |
| … named for the first time | BPS, DG, PSGW, USR | BPS, DG, PSGW, USR | same |
| … whose name would change (folded comparison; the proposal read 15 substantive + 32 reworded) | 47 | 46 | **differs** |

## §4 Dates

| Figure | Proposal | Measured |  |
|---|---|---|---|
| Crawled links that carry a VDL posting date | 28 | 28 | same |
| … of crawled links | 9,080 | 9,080 | same |
| Gold documents (`v_documents`) | 1,040 | 1,040 | same |
| … dated by `official_date` | 990 | 990 | same |
| … … from Revision History | 856 | 856 | same |
| … … from the title page | 134 | 134 | same |
| … carrying no date | 50 | 50 | same |
| … with no `history.yaml` member | — | 0 |  |
| `doc_id`s in more than one `history.yaml` member | — | 0 |  |
| `superseded` entries naming another `doc_id` | — | 0 |  |
| Gold documents whose newest revision is later than the title page | 332 | 332 | same |
| … median years later | 14 | 14.1 | same |
| `xwb1_1p44um` title page | 2005-01 | 2005-01 | same |
| `xwb1_1p44um` newest revision | 2022-08 | 2022-08 | same |
| Records dated through `doc_id` | 2,018 | 2,018 | same |
| Records a title-page date (`v_documents.published`) alone would date | — | 1,864 |  |
| Records undated | 7,062 | 7,062 | same |
| … not VistA | 3,228 | 3,228 | same |
| … VistA (measured directly) | 3,834 | 3,834 | same |
| … … records of gold documents that carry no date | 100 | 102 | same |
| … … … those gold documents | 50 | 50 | same |
| … … records with no gold document | 3,732 | 3,732 | same |
| … … … never fetched (no acquisition row) | 3,732 | 3,721 | **differs** |
| … … … distinct `doc_id`s | 1,861 | 1,861 | same |
| … … … distinct slugs | — | 1,809 |  |
| Distinct `doc_id`s among undated VistA records (D6's 1,911 documents) | 1,911 | 1,911 | same |
| … with a DOCX record (D6: a Word version) | 1,903 | 1,882 | **differs** |
| Share of records dated (%) | 22 | 22.2 | same |
| Share dated if every undated VistA record were dated (%, D6) | 64 | 64.4 | same |
| Share of records undated (%, D6) | 78 | 77.8 | same |

## Details

### Held records with no gold document, by reason and fetch outcome

| Reason | `inventory --status` | Acquisition | Records |
|---|---|---|---|
| (kept DOCX) | failed | failed | 5 |
| (kept DOCX) | not_acquired | never-attempted | 52 |
| sole-format | out_of_scope | bad_content | 1 |
| sole-format | out_of_scope | never-attempted | 6 |
| sole-survivor | not_acquired | never-attempted | 152 |

### Gold documents no record carries

| `doc_id` | Slug listed under |
|---|---|
| ADT:iss_release_1_11_11_user_guide | SD |
| ADT:iss_release_1_12_0_user_guide | SD |
| ADT:iss_release_1_13_3_user_guide | SD |
| ADT:iss_release_1_14_1_user_guide | SD |
| ADT:iss_release_1_15_4_user_guide | SD |
| ADT:iss_release_1_16_1_user_guide | SD |
| ADT:iss_release_1_17_2_user_guide | SD |
| ADT:iss_release_1_18_10_user_guide | SD |
| ADT:iss_release_1_19_1_user_guide | SD |
| ADT:iss_release_1_21_2_user_guide | SD |
| ADT:iss_release_1_22_3_user_guide | SD |
| ADT:iss_release_1_5_4_0_user_guide | SD |
| ADT:iss_release_1_7_1_0_user_guide | SD |
| ADT:iss_release_1_8_6_0_user_guide | SD |
| PSS:pss_1_dosing_ord_ck_um_r0918 | (none) |

### Links listed on more than one application page

| Link | Pages | Records | Noise type |
|---|---|---|---|
| http://www.benefits.va.gov/milwaukee/docs/SF1199A_Direct_Deposit_Sign_Up_Form.pdf | 148 | 148 | vba_form |
| http://www.vba.va.gov/pubs/forms/VBA-21-2680-ARE.pdf | 148 | 148 | vba_form |
| http://www.vba.va.gov/pubs/forms/VBA-21-4138-ARE.pdf | 148 | 148 | vba_form |
| http://www.vba.va.gov/pubs/forms/VBA-21-526-ARE.pdf | 148 | 148 | vba_form |
| http://www.vba.va.gov/pubs/forms/VBA-21-534-ARE.pdf | 148 | 148 | vba_form |
| http://www.vba.va.gov/pubs/forms/VBA-22-1990-ARE.pdf | 148 | 148 | vba_form |
| http://www.vba.va.gov/pubs/forms/VBA-22-1995-ARE.pdf | 148 | 148 | vba_form |
| http://www.vba.va.gov/pubs/forms/vba-24-0296-are.pdf | 148 | 148 | vba_form |
| https://www.va.gov/op3/docs/StrategicPlanning/VA2014-2020strategicPlan.pdf | 148 | 148 | va_ref |

### Links listed more than once on one page

| Link | Listings | Every field identical | Titles | Doc codes |
|---|---|---|---|---|
| https://www.va.gov/vdl/documents/Financial_Admin/CAPRI/DVBA_UM.docx | 3 | no | 3 | 2 |
| https://www.va.gov/vdl/documents/Financial_Admin/CAPRI/DVBA_UM.pdf | 3 | no | 3 | 2 |
| https://www.va.gov/vdl/documents/Financial_Admin/Accounts_Receivable_(AR)/prca_4_5_p455_dibr.docx | 2 | yes | 1 | 1 |
| https://www.va.gov/vdl/documents/Clinical/Scheduling_Archive/VSE_GUI_2_0_0_14_Action_Item_Install.docx | 2 | yes | 1 | 1 |
| https://www.va.gov/vdl/documents/Clinical/Scheduling_Archive/VSE_GUI_2_0_0_14_Action_Item_Install.pdf | 2 | yes | 1 | 1 |

### Gold-matched documents whose namespace differs

| `doc_id` | Inventory | Gold | Records |
|---|---|---|---|
| CPRS:cprslmtm | CPRS | OR | 2 |
| POC:lab_poc_iug | POC | LA | 2 |

### Library namespace names that would change

Every Library namespace whose current name (the same-code application's) is not equal to its PACKAGE-file name after folding case and punctuation. Which of them change in substance and which are rewordings is a reading of this list, not a measurement.

| Namespace | Library today | PACKAGE file (#9.4) |
|---|---|---|
| ACKQ | Quality Audiology and Speech Analysis and Reporting (QUASAR) | QUASAR |
| ANRV | Visual Impairment Service Team (VIST) | VISUAL IMPAIRMENT SERVICE TEAM |
| DGJ | Incomplete Records Tracking (IRT) | INCOMPLETE RECORDS TRACKING |
| DI | FileMan | VA FILEMAN |
| DVBA | Automated Medical Information Exchange (AMIE) | AUTOMATED MED INFO EXCHANGE |
| EC | Event Capture System (ECS) | EVENT CAPTURE |
| ECX | Decision Support System (DSS) Extracts | DSS EXTRACTS |
| EN | Engineering (AEMS / MERS) | ENGINEERING |
| FH | Nutrition and Food Service | DIETETICS |
| GMPL | CPRS: Problem List | PROBLEM LIST |
| GMRA | CPRS: Adverse Reaction Tracking (ART) | ADVERSE REACTION TRACKING |
| GMRC | CPRS: Consult/Request Tracking | CONSULT/REQUEST TRACKING |
| GMRV | Vitals/Measurements | GEN. MED. REC. - VITALS |
| GMTS | CPRS: Health Summary | HEALTH SUMMARY |
| IBD | Automated Information Collection System (AICS) | AUTOMATED INFO COLLECTION SYS |
| LA | Laboratory: Universal Interface | AUTOMATED LAB INSTRUMENTS |
| LR | Laboratory | LAB SERVICE |
| MAG | VistA Imaging System | IMAGING |
| MMRS | Methicillin Resistant Staph Aureus (MRSA) | MRSA INITIATIVE REPORTS |
| MPIF | Master Patient Index | MASTER PATIENT INDEX VISTA |
| NUPA | Patient Assessment Documentation Package (PADP) | PATIENT ASSESSMENT DOCUMENTATION |
| NUR | Nursing | NURSING SERVICE |
| ONC | Registry: Oncology | ONCOLOGY |
| OOPS | Automated Safety Incident Surveillance Tracking System | ASISTS |
| OR | Order Entry / CPRS | ORDER ENTRY/RESULTS REPORTING |
| PRCA | Accounts Receivable (AR) | ACCOUNTS RECEIVABLE |
| PRCN | Equipment / Turn-In Request | EQUIPMENT/TURN-IN REQUIEST |
| PREA | Pharmacy: Advanced Medication Platform | ADVANCED MEDICATION PLATFORM |
| PRS | Personnel and Accounting Integrated Data (PAID) | PAID |
| PSA | Pharmacy: Drug Accountability | DRUG ACCOUNTABILITY |
| PSB | Pharmacy: Bar Code Medication Administration (BCMA) | BAR CODE MED ADMIN |
| PSD | Pharmacy: Controlled Substances | CONTROLLED SUBSTANCES |
| PSJ | Pharmacy: Inpatient Medications | INPATIENT MEDICATIONS |
| PSN | Pharmacy: National Drug File (NDF) | NATIONAL DRUG FILE |
| PSO | Pharmacy: Outpatient Pharmacy | OUTPATIENT PHARMACY |
| PSX | Pharmacy: Consolidated Mail Outpatient Pharmacy | CMOP |
| PX | Patient Care Encounter (PCE) | PCE PATIENT CARE ENCOUNTER |
| QAC | Patient Advocate Tracking System (PATS) | PATIENT REPRESENTATIVE |
| ROR | Registry: Clinical Case (CCR) | CLINICAL CASE REGISTRIES |
| SPN | Spinal Cord Injury and Disorders Outcomes (SCIDO) | SPINAL CORD DYSFUNCTION |
| TIU | CPRS: Text Integration Utility | TEXT INTEGRATION UTILITIES |
| VAQ | Patient Data Exchange (PDX) | PATIENT DATA EXCHANGE |
| VDEF | VistA Data Extraction Framework | VDEF |
| WII | Wounded Ill and Injured Warriors | WOUNDED INJURED & ILL WARRIORS |
| XT | Kernel Toolkit | TOOLKIT |
| XWB | Remote Procedure Call (RPC) Broker | RPC BROKER |

### Inventory namespaces whose two names differ

| Namespace | PACKAGE file (#9.4) | Application |
|---|---|---|
| ACKQ | QUASAR | Quality Audiology and Speech Analysis and Reporting (QUASAR) |
| AFJX | NETWORK HEALTH EXCHANGE | Network Health Exchange (NHE) |
| ANRV | VISUAL IMPAIRMENT SERVICE TEAM | Visual Impairment Service Team (VIST) |
| DGJ | INCOMPLETE RECORDS TRACKING | Incomplete Records Tracking (IRT) |
| DI | VA FILEMAN | FileMan |
| DVBA | AUTOMATED MED INFO EXCHANGE | Automated Medical Information Exchange (AMIE) |
| EC | EVENT CAPTURE | Event Capture System (ECS) |
| ECX | DSS EXTRACTS | Decision Support System (DSS) Extracts |
| EN | ENGINEERING | Engineering (AEMS / MERS) |
| ES | POLICE & SECURITY | Police and Security |
| ETS | ENTERPRISE TERMINOLOGY SERVICES | Enterprise Terminology Service |
| FH | DIETETICS | Nutrition and Food Service |
| GMPL | PROBLEM LIST | CPRS: Problem List |
| GMRA | ADVERSE REACTION TRACKING | CPRS: Adverse Reaction Tracking (ART) |
| GMRC | CONSULT/REQUEST TRACKING | CPRS: Consult/Request Tracking |
| GMRV | GEN. MED. REC. - VITALS | Vitals/Measurements |
| GMTS | HEALTH SUMMARY | CPRS: Health Summary |
| IBD | AUTOMATED INFO COLLECTION SYS | Automated Information Collection System (AICS) |
| ICD | DRG GROUPER | ICD-9-CM |
| JLV | JOINT LEGACY VIEWER | Joint Longitudinal Viewer |
| LA | AUTOMATED LAB INSTRUMENTS | Laboratory: Universal Interface |
| LR | LAB SERVICE | Laboratory |
| MAG | IMAGING | VistA Imaging System |
| MMRS | MRSA INITIATIVE REPORTS | Methicillin Resistant Staph Aureus (MRSA) |
| MPIF | MASTER PATIENT INDEX VISTA | Master Patient Index |
| NHIN | NATIONAL HEALTH INFORMATION NETWORK | Nationwide Health Information Network Adapter |
| NUPA | PATIENT ASSESSMENT DOCUMENTATION | Patient Assessment Documentation Package (PADP) |
| NUR | NURSING SERVICE | Nursing |
| ONC | ONCOLOGY | Registry: Oncology |
| OOPS | ASISTS | Automated Safety Incident Surveillance Tracking System |
| OR | ORDER ENTRY/RESULTS REPORTING | Order Entry / CPRS |
| PRCA | ACCOUNTS RECEIVABLE | Accounts Receivable (AR) |
| PRCN | EQUIPMENT/TURN-IN REQUIEST | Equipment / Turn-In Request |
| PREA | ADVANCED MEDICATION PLATFORM | Pharmacy: Advanced Medication Platform |
| PRS | PAID | Personnel and Accounting Integrated Data (PAID) |
| PSA | DRUG ACCOUNTABILITY | Pharmacy: Drug Accountability |
| PSB | BAR CODE MED ADMIN | Pharmacy: Bar Code Medication Administration (BCMA) |
| PSD | CONTROLLED SUBSTANCES | Pharmacy: Controlled Substances |
| PSJ | INPATIENT MEDICATIONS | Pharmacy: Inpatient Medications |
| PSN | NATIONAL DRUG FILE | Pharmacy: National Drug File (NDF) |
| PSO | OUTPATIENT PHARMACY | Pharmacy: Outpatient Pharmacy |
| PSX | CMOP | Pharmacy: Consolidated Mail Outpatient Pharmacy |
| PX | PCE PATIENT CARE ENCOUNTER | Patient Care Encounter (PCE) |
| QAC | PATIENT REPRESENTATIVE | Patient Advocate Tracking System (PATS) |
| ROR | CLINICAL CASE REGISTRIES | Registry: Clinical Case (CCR) |
| SPN | SPINAL CORD DYSFUNCTION | Spinal Cord Injury and Disorders Outcomes (SCIDO) |
| TIU | TEXT INTEGRATION UTILITIES | CPRS: Text Integration Utility |
| VAQ | PATIENT DATA EXCHANGE | Patient Data Exchange (PDX) |
| VDEF | VDEF | VistA Data Extraction Framework |
| VIAB | VISTA INTEGRATION ADAPTER | VistA Integration Adapter (VIA) |
| VPS | VA POINT OF SERVICE | VHA Point of Service (Kiosks) |
| WEBG | WEBVRAM | Web VistA Remote Access Mgmt (WEBVRAM) |
| WII | WOUNDED INJURED & ILL WARRIORS | Wounded Ill and Injured Warriors |
| XOBE | ELECTRONIC SIGNATURE | Electronic Signature (ESig) |
| XOBW | WEB SERVICES CLIENT | HealtheVet Web Services Client (HWSC) |
| XT | TOOLKIT | Kernel Toolkit |
| XWB | RPC BROKER | Remote Procedure Call (RPC) Broker |

### Undated VistA records with no gold document

| By acquisition | Records |
|---|---|
| bad_content | 1 |
| failed | 10 |
| never-attempted | 3,721 |

| By `inventory --status` | Records |
|---|---|
| failed | 10 |
| not_acquired | 3,690 |
| out_of_scope | 32 |

| By disposition | Records |
|---|---|
| covered-by-other-format | 1,860 |
| excluded | 1,656 |
| held | 216 |

## Notes

- The undated VistA records (§4) and the `inventory --status` total (§1) are both 3,834, measured independently. They count different things — records, against distinct non-noise `doc_id`s of any system type — so the match is a coincidence.
- `inventory_status` labels every PDF-only `doc_id` *out_of_scope* without reading its acquisition, although the gate admits sole-format PDFs and fetch attempts them: 1 held record(s) with acquisition *bad_content*. The acquisition column is the fetch outcome.
