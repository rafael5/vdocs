# Function-Domain Taxonomy — the `function` facet

> **Status:** adopted 2026-06-10. Registry: `registries/inventory/function-domains.yaml`.
> Replaces the Monograph "SPM Product Line" as the basis of `documents.function_category`.

## Why this exists

`function_category` was the VistA Monograph's **"SPM Product Line"** — VA's internal
*portfolio/ownership* taxonomy (which VA product line **owns** an application), not a
*functional* one. As a browse facet it was vague and overlapping:

- **Infrastructure landed in clinical buckets**: Kernel (`XU`), FileMan (`DI`), HL7,
  MailMan (`XM`), registration (`ADT`) were all "Health Informatics"; the RPC Broker
  (`XWB`) was "Eligibility and Enrollment".
- **"Clinical Services" (178) vs "Patient Care Services" (130)** were both just clinical
  care, split by owning office.
- **"VistA Office (VO) Technical Reference / VistA Infrastructure"** were org jargon, and
  **35 docs** had no value at all.

The SPM line is retained in `app-profiles.yaml` (`function_category`) for provenance, but
the facet now uses a curated **functional** taxonomy: *what the software does*.

## The domains

| Domain | Definition |
|---|---|
| **Clinical care** | The clinician's record — orders, notes, problems, consults, reminders, allergies, vitals, encounters, bedside documentation. |
| **Pharmacy** | Medication ordering, dispensing, bar-code administration, and drug data management. |
| **Laboratory** | Clinical laboratory, blood bank, point-of-care testing, and lab data interfaces (`LR`, `LA`, `LEDI`, `POC`, `EPI`, `VBECS`). |
| **Radiology & imaging** | Radiology, nuclear medicine, and VistA Imaging (`RA`, `MAG`). |
| **Specialty care** | Condition-/population-specific clinical programs and specialty services — surgery (`SR`, `SRA`), audiology (`ACKQ`), mental health, oncology, prosthetics, dentistry, women's health, registries, …. |
| **Registration & scheduling** | Patient registration, eligibility/enrollment, appointments, primary-care panel management. |
| **Billing & finance** | Revenue, claims, fee/travel pay, fiscal accounting, acquisition, payroll. |
| **Infrastructure** | The VistA platform — Kernel security, FileMan database, messaging (HL7/MailMan), interfaces (RPC Broker/VistALink), data exchange, system monitoring. |
| **Admin & quality** | Operations, HIM (records, release of information), quality/safety surveillance, patient advocacy, facilities/logistics. |

## How it's wired

- **`function-domains.yaml`** — `domains:` (the definitions above) + `apps:` (every
  `app_code` → one domain). Curated data (tenet #13): edit an app's domain and re-run
  `vdocs run --only index` — no code change.
- **`kernel.personas.load_profile_maps`** sources the `function_category` tag from this
  registry's `apps:` (was `app-profiles.yaml`'s SPM `function_category`). `enrich` bakes it
  into gold frontmatter; `index` lands it in `documents.function_category`; the TUI and
  `vdocs ask` read it from there.

## Maintenance

Mappings are judgment calls grounded in the app's VistA package and name; tweak in the
YAML as needed. A few deliberate placements worth noting: surgery (`SR`/`SRA`) → Diagnostics
& ancillary (procedural); HIM (`RT`/`ROI`/`DGJ`) → Admin & quality; Beneficiary Travel
(`DGBT`) and Fugitive Felon (`FFP`) → Billing & finance (benefit pay/eligibility-financial);
capacity/monitoring (`KMP*`/`RUM`/`SAGG`) and data-exchange (`VPR`/`VDEF`/`VAQ`/`MPIF`) →
Infrastructure.
