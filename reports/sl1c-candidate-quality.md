# SL.1(c) — how sound are the waiting candidates?

- **queue:** `/home/rafael/data/vdocs/reports/knowledge/proposals.json`
- **ground truth:** `/home/rafael/projects/vista-meta/vista/export` (vista-meta measured model)

## The queue is smaller than reported, and differently shaped

| | |
|---|---|
| mentions (`resolve`'s `proposals` count — what the tracker records) | 4415 |
| **distinct candidates a curator would actually review** | **307** |

By type: `global` 174, `routine` 105, `fileman_file` 18, `package_namespace` 5, `build` 4, `hl7_segment` 1.

## What approving them would buy

| | |
|---|---|
| candidates of a type the seed can represent (`fileman_file`) | 18 |
| **structurally inert** — recognised, but no landing place in the seed and nothing the expansion map keys on | **289** |
| **would reach search if approved** | **1** |

Recognition quality (is the surface a real thing in the measured VistA?): unknown-to-the-measured-model 180, valid 111, unchecked 10, not-a-file 6.

## Strata

- **head** (seen more than once): 191 candidates — recognised unknown-to-the-measured-model 102, valid 80, unchecked 6, not-a-file 3.
- **tail** (seen exactly once): 116 candidates, 40 sampled — recognised unknown-to-the-measured-model 26, valid 11, unchecked 2, not-a-file 1.

## Every `fileman_file` candidate — the only type that could reach search

| surface | occurrences | docs | real file? | canonical name | reach |
|---|---|---|---|---|---|
| 16200 | 5 | 1 | not-a-file | — | inert-not-a-real-file |
| 05 | 4 | 1 | not-a-file | — | inert-not-a-real-file |
| 16000 | 2 | 1 | not-a-file | — | inert-not-a-real-file |
| 10 | 1 | 1 | valid | RACE | inert-guards-drop-it |
| 120.8 | 1 | 1 | valid | PATIENT ALLERGIES | inert-guards-drop-it |
| 120.85 | 1 | 1 | valid | ADVERSE REACTION REPORTING | inert-guards-drop-it |
| 120.86 | 1 | 1 | valid | ADVERSE REACTION ASSESSMENT | inert-guards-drop-it |
| 16201 | 1 | 1 | not-a-file | — | inert-not-a-real-file |
| 3 | 1 | 1 | not-a-file | — | inert-not-a-real-file |
| 301.7 | 1 | 1 | valid | IVM ADDRESS CHANGE LOG | inert-guards-drop-it |
| 391.71 | 1 | 1 | valid | ADT/HL7 PIVOT | inert-guards-drop-it |
| 405 | 1 | 1 | valid | PATIENT MOVEMENT | would-expand |
| 45 | 1 | 1 | valid | PTF | inert-guards-drop-it |
| 5 | 1 | 1 | valid | STATE | inert-guards-drop-it |
| 59.9 | 1 | 1 | valid | PBM PATIENT DEMOGRAPHICS | inert-guards-drop-it |
| 7 | 1 | 1 | valid | PROVIDER CLASS | inert-guards-drop-it |
| 798.3 | 1 | 1 | valid | ROR PATIENT EVENTS | inert-guards-drop-it |
| 999000 | 1 | 1 | not-a-file | — | inert-not-a-real-file |
