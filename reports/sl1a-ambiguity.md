# SL.1(a) — how common is the number/name vocabulary split?

- **index_db:** `/home/rafael/data/vdocs/index.db` · **documents:** 1040 · **chunks:** 57895 · **doc_key hash:** `cd3b3cbb299ea86d`
- **ground truth:** `/home/rafael/projects/vista-meta/vista/export/data-model/files.tsv` (8255 FileMan files, measured from a live VistA)

## Rollup

| | |
|---|---|
| FileMan files this collection mentions at all (distinctive names only) | 2963 |
| …of those, mentioned under **two or more** surface forms | 362 |
| …with a split on a **bare** name match (upper bound, over-counts prose) | 303 |
| **…with a split on a *file-referring* name match (the defensible number)** | **233** |
| documents reachable by the anchored name but not by the number (file×doc pairs) | **1932** |
| chunks behind those anchored name matches | 8564 |
| (same, unanchored) | 4998 |
| files the collection names **only** by number | 8 |
| files the collection names **only** by name (bare match; mostly prose noise) | 2611 |
| file names suppressed as ordinary English (guard) | 28 |

## The anchored split, largest first

| file | name | docs by number | docs by anchored name | anchored name-only docs | chunks |
|---|---|---|---|---|---|
| 200 | NEW PERSON | 26 | 219 | 195 | 986 |
| 8989.5 | PARAMETERS | 4 | 147 | 146 | 590 |
| 44 | HOSPITAL LOCATION | 11 | 98 | 88 | 309 |
| 3.5 | DEVICE | 3 | 83 | 81 | 248 |
| 63 | LAB DATA | 8 | 47 | 40 | 230 |
| 45 | PTF | 4 | 35 | 33 | 76 |
| 60 | LABORATORY TEST | 18 | 50 | 32 | 226 |
| 55 | PHARMACY PATIENT | 4 | 33 | 31 | 128 |
| 80 | ICD DIAGNOSIS | 2 | 32 | 31 | 61 |
| 50.68 | VA PRODUCT | 2 | 32 | 30 | 235 |
| 59 | OUTPATIENT SITE | 1 | 30 | 29 | 109 |
| 81 | CPT | 5 | 29 | 26 | 60 |
| 42 | WARD LOCATION | 7 | 30 | 25 | 59 |
| 771 | HL7 APPLICATION PARAMETER | 3 | 26 | 25 | 80 |
| 870 | HL LOGICAL LINK | 9 | 33 | 25 | 124 |
| 8989.3 | KERNEL SYSTEM PARAMETERS | 2 | 27 | 25 | 93 |
| 50.7 | PHARMACY ORDERABLE ITEM | 1 | 25 | 24 | 147 |
| 441 | ITEM MASTER | 5 | 27 | 22 | 174 |
| 49 | SERVICE/SECTION | 2 | 22 | 21 | 38 |
| 50.605 | VA DRUG CLASS | 2 | 22 | 21 | 97 |
| 51.2 | MEDICATION ROUTES | 2 | 23 | 21 | 107 |
| 8989.51 | PARAMETER DEFINITION | 6 | 23 | 21 | 51 |
| 52.6 | IV ADDITIVES | 1 | 21 | 20 | 127 |
| 3.8 | MAIL GROUP | 3 | 20 | 19 | 42 |
| 52.7 | IV SOLUTIONS | 1 | 20 | 19 | 102 |
| 19.2 | OPTION SCHEDULING | 2 | 19 | 18 | 47 |
| 50.6 | VA GENERIC | 2 | 20 | 18 | 107 |
| 61 | TOPOGRAPHY FIELD | 8 | 23 | 18 | 66 |
| 64 | WKLD CODE | 5 | 23 | 18 | 50 |
| 50.416 | DRUG INGREDIENTS | 1 | 16 | 16 | 77 |
| 62.06 | ANTIMICROBIAL SUSCEPTIBILITY | 1 | 16 | 15 | 47 |
| 36 | INSURANCE COMPANY | 1 | 14 | 14 | 46 |
| 40.7 | CLINIC STOP | 1 | 15 | 14 | 28 |
| 69.9 | LABORATORY SITE | 2 | 15 | 14 | 67 |
| 8925 | TIU DOCUMENT | 3 | 16 | 14 | 74 |
| 2005.2 | NETWORK LOCATION | 2 | 14 | 12 | 59 |
| 772 | HL7 MESSAGE TEXT | 7 | 18 | 12 | 34 |
| 101.43 | ORDERABLE ITEMS | 2 | 13 | 11 | 35 |
| 120.8 | PATIENT ALLERGIES | 3 | 14 | 11 | 54 |
| 405 | PATIENT MOVEMENT | 5 | 11 | 11 | 18 |

## Dropped by the anchor — a bare name match with no file-referring occurrence

| file | name | bare name-only docs | bare chunks |
|---|---|---|---|
| 410.1 | TRANSACTION NUMBER | 54 | 419 |
| 442.6 | PAT NUMBER | 23 | 74 |
| 801.41 | REMINDER DIALOG | 21 | 172 |
| 410.2 | CLASSIFICATION OF REQUEST | 20 | 117 |
| 6920 | WORK ORDER # | 12 | 214 |
| 100.9 | OE/RR NOTIFICATIONS | 7 | 18 |
| 417 | FMS TRANSACTIONS | 7 | 23 |
| 771.6 | HL7 MESSAGE STATUS | 7 | 17 |
| 413.1 | TURN-IN REQUEST | 6 | 247 |
| 22 | POW PERIOD | 5 | 6 |
| 579.3 | VDEF REQUEST QUEUE | 5 | 22 |
| 601.71 | MH TESTS AND SURVEYS | 5 | 15 |
| 421 | FUND DISTRIBUTION | 4 | 32 |
| 440.6 | PURCHASE CARD ORDER RECONCILE | 4 | 10 |
| 442.5 | PAT TYPE | 4 | 14 |
| 446.6 | SPECIALTY COMMANDS | 4 | 26 |
| 631.6 | HBHC CLINIC | 4 | 14 |
| 100.23 | OE/RR PRINT FORMATS | 3 | 4 |
| 347 | AR FMS DOCUMENT | 3 | 5 |
| 62.6 | ACCESSION TEST GROUP | 3 | 14 |

## Names the English guard suppressed (largest number-form presence first)

These files *are* referenced by number in the collection, but their names are ordinary
English words, so no name-form measurement is trustworthy for them.

| file | name | docs by number |
|---|---|---|
| 2 | PATIENT | 27 |
| 1 | FILE | 23 |
| 4 | INSTITUTION | 14 |
| 19 | OPTION | 10 |
| 100 | ORDER | 9 |
| 5 | STATE | 8 |
| 50 | DRUG | 8 |
| 10 | RACE | 5 |
| 101 | PROTOCOL | 4 |
| 13 | RELIGION | 4 |
| 4.2 | DOMAIN | 4 |
| 68 | ACCESSION | 4 |
| 0 | ATTRIBUTE | 3 |
| 440 | VENDOR | 3 |
| 12 | OCCUPATION | 2 |
| 2005 | IMAGE | 2 |
| 52 | PRESCRIPTION | 2 |
| 9000010 | VISIT | 2 |
| 9000011 | PROBLEM | 2 |
| 130 | SURGERY | 1 |
