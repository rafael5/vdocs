# SL.1(b) — what the vocabulary split costs, in questions

- **index_db:** `/home/rafael/data/vdocs/index.db` · **k:** 10
- **sample:** 40 largest splits + 40 drawn from the tail (seed 20260804), from `reports/sl1a-ambiguity.json`
- **not** the golden set: these questions carry no relevance labels. The measure is reachability of the answering passage, and its numbers do not compare to golden nDCG.

## Rollup

| | |
|---|---|
| identifier-shaped questions scored | 80 |
| the number query already reaches the answer | 42 (52%) |
| **vocabulary failures** — the name query reaches it, the number query does not | **28** (35%) |
| neither query reaches it (not a vocabulary problem) | 10 |
| **failures the synonym layer would repair** | **3** |
| failures the layer *cannot express* (guards drop the expansion) | 24 |
| questions the expansion would damage | 0 |
| **ceiling — failures repairable by *any* expansion** (both vocabularies in one query) | **23** |

## Per question

| file | name | stratum | verdict | expansion | repaired |
|---|---|---|---|---|---|
| 200 | NEW PERSON | head | reached | `200 → NEW PERSON` | — |
| 8989.5 | PARAMETERS | head | reached | — | — |
| 44 | HOSPITAL LOCATION | head | reached | — | — |
| 3.5 | DEVICE | head | reached | — | — |
| 63 | LAB DATA | head | reached | — | — |
| 45 | PTF | head | reached | — | — |
| 60 | LABORATORY TEST | head | vocabulary_failure | — | no |
| 55 | PHARMACY PATIENT | head | reached | — | — |
| 80 | ICD DIAGNOSIS | head | vocabulary_failure | — | no |
| 50.68 | VA PRODUCT | head | reached | — | — |
| 59 | OUTPATIENT SITE | head | reached | — | — |
| 81 | CPT | head | vocabulary_failure | — | no |
| 42 | WARD LOCATION | head | vocabulary_failure | — | no |
| 771 | HL7 APPLICATION PARAMETER | head | reached | `771 → HL7 APPLICATION PARAMETER` | — |
| 870 | HL LOGICAL LINK | head | reached | `870 → HL LOGICAL LINK` | — |
| 8989.3 | KERNEL SYSTEM PARAMETERS | head | reached | — | — |
| 50.7 | PHARMACY ORDERABLE ITEM | head | vocabulary_failure | — | no |
| 441 | ITEM MASTER | head | reached | `441 → ITEM MASTER` | — |
| 49 | SERVICE/SECTION | head | vocabulary_failure | — | no |
| 50.605 | VA DRUG CLASS | head | reached | — | — |
| 51.2 | MEDICATION ROUTES | head | reached | — | — |
| 8989.51 | PARAMETER DEFINITION | head | reached | — | — |
| 52.6 | IV ADDITIVES | head | vocabulary_failure | — | no |
| 3.8 | MAIL GROUP | head | vocabulary_failure | — | no |
| 52.7 | IV SOLUTIONS | head | vocabulary_failure | — | no |
| 19.2 | OPTION SCHEDULING | head | reached | — | — |
| 50.6 | VA GENERIC | head | vocabulary_failure | — | no |
| 61 | TOPOGRAPHY FIELD | head | reached | — | — |
| 64 | WKLD CODE | head | vocabulary_failure | — | no |
| 50.416 | DRUG INGREDIENTS | head | reached | — | — |
| 62.06 | ANTIMICROBIAL SUSCEPTIBILITY | head | reached | — | — |
| 36 | INSURANCE COMPANY | head | vocabulary_failure | — | no |
| 40.7 | CLINIC STOP | head | vocabulary_failure | — | no |
| 69.9 | LABORATORY SITE | head | reached | — | — |
| 8925 | TIU DOCUMENT | head | vocabulary_failure | `8925 → TIU DOCUMENT` | yes |
| 2005.2 | NETWORK LOCATION | head | reached | — | — |
| 772 | HL7 MESSAGE TEXT | head | reached | `772 → HL7 MESSAGE TEXT` | — |
| 101.43 | ORDERABLE ITEMS | head | reached | — | — |
| 120.8 | PATIENT ALLERGIES | head | unreached_either_way | — | — |
| 405 | PATIENT MOVEMENT | head | reached | `405 → PATIENT MOVEMENT` | — |
| 59.4 | INPATIENT SITE | tail | vocabulary_failure | — | no |
| 779.2 | HLO APPLICATION REGISTRY | tail | reached | — | — |
| 66.2 | BLOOD BANK VALIDATION | tail | vocabulary_failure | — | no |
| 6912 | MANUFACTURER LIST FILE | tail | unreached_either_way | `6912 → MANUFACTURER LIST FILE` | — |
| 195.4 | RECORD TRACKING SYSTEM PARAMETERS | tail | reached | — | — |
| 8925.7 | TIU MULTIPLE SIGNATURE | tail | vocabulary_failure | — | no |
| 56 | DRUG INTERACTION | tail | vocabulary_failure | — | no |
| 340 | AR DEBTOR | tail | reached | `340 → AR DEBTOR` | — |
| 740 | QUALITY ASSURANCE SITE PARAMETERS | tail | reached | `740 → QUALITY ASSURANCE SITE PARAMETERS` | — |
| 58.1 | PHARMACY AOU STOCK | tail | vocabulary_failure | — | no |
| 78.3 | DIAGNOSTIC CODES | tail | reached | — | — |
| 59.5 | IV ROOM | tail | vocabulary_failure | — | no |
| 15 | DUPLICATE RECORD | tail | vocabulary_failure | — | no |
| 839.7 | PCE DATA SOURCE | tail | reached | — | — |
| 62.1 | DELTA CHECKS | tail | vocabulary_failure | — | no |
| 62.485 | LA7 MESSAGE LOG BULLETINS | tail | reached | — | — |
| 142.5 | HEALTH SUMMARY OBJECTS | tail | unreached_either_way | — | — |
| 195.1 | RECORD TRACKING APPLICATION | tail | reached | — | — |
| 100.98 | DISPLAY GROUP | tail | unreached_either_way | — | — |
| 8973.1 | CM HL7 DATA | tail | reached | — | — |
| 120.51 | GMRV VITAL TYPE | tail | reached | — | — |
| 54 | RX CONSULT | tail | reached | — | — |
| 6925 | CONSTRUCTION PROJECT | tail | vocabulary_failure | `6925 → CONSTRUCTION PROJECT` | no |
| 120.83 | SIGN/SYMPTOMS | tail | reached | — | — |
| 660 | RECORD OF PROS APPLIANCE/REPAIR | tail | vocabulary_failure | `660 → RECORD OF PROS APPLIANCE/REPAIR` | yes |
| 8925.1 | TIU DOCUMENT DEFINITION | tail | vocabulary_failure | — | no |
| 123.5 | REQUEST SERVICES | tail | unreached_either_way | — | — |
| 14.6 | UCI ASSOCIATION | tail | unreached_either_way | — | — |
| 27.11 | PATIENT ENROLLMENT | tail | reached | — | — |
| 632 | HBHC VISIT | tail | reached | `632 → HBHC VISIT` | — |
| 509850.9 | AUDIOMETRIC EXAM DATA | tail | unreached_either_way | — | — |
| 409.1 | APPOINTMENT TYPE | tail | vocabulary_failure | — | no |
| 341.1 | AR EVENT TYPE | tail | reached | — | — |
| 230 | ED LOG | tail | vocabulary_failure | `230 → ED LOG` | yes |
| 2101.2 | GENERIC CODE SHEET TRANSACTION TYPE/SEGMENT | tail | unreached_either_way | — | — |
| 213.9 | NURS PARAMETERS | tail | vocabulary_failure | — | no |
| 452 | PRSE STUDENT EDUCATION TRACKING | tail | reached | `452 → PRSE STUDENT EDUCATION TRACKING` | — |
| 120.86 | ADVERSE REACTION ASSESSMENT | tail | reached | — | — |
| 433 | AR TRANSACTION | tail | unreached_either_way | `433 → AR TRANSACTION` | — |
| 409.2 | CANCELLATION REASONS | tail | unreached_either_way | — | — |
