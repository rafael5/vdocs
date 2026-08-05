# The observatory's first real delta — VDL, 2026-06-10 → 2026-08-05

**The timeline's first two points.** A fresh crawl ran 2026-08-05 (17m51s, GREEN, 0 skipped) and
VO.2 preserved it automatically; `vdocs vdl-delta` compared it against the snapshot banked by VO.0.
This is the first change record that exists at all — before 2026-08-05 every crawl overwrote its
predecessor.

**Headline: the VDL grew, nothing was retired, and one brand-new VistA application arrived that the
pipeline currently excludes because nobody has classified it yet.**

## What changed

| | 2026-06-10 | 2026-08-05 | |
|---|---:|---:|---|
| sections | 5 | 5 | |
| applications | 396 | **398** | +2, none departed, none renamed |
| document listings | 8,907 | **8,983** | +76 net |
| distinct document URLs | 7,584 | **7,649** | +65 net — **186 arrived, 121 left** |
| lifecycle transitions | — | **0** | no `active→archive→decommissioned` movement at all |

⚠️ **Listings ≠ documents.** The crawl yields 8,983 *listings* over 7,649 distinct URLs — the same
document URL is listed under more than one application about 1,300 times. State which unit any
count is in; the delta command reports listings.

**Most of the churn is re-filing, not publication.** Of the 121 URLs that disappeared, **110 still
exist under the same filename elsewhere** and only **11 are genuinely absent** (≈6 documents in
docx+pdf pairs, including a stray `Test Document VDL` that VA appears to have cleaned up). Of the
186 arrivals, 92 carry a filename we already had.

The single largest movement: **Integrated Scheduling Solution documentation was re-filed from
Admission Discharge Transfer (appid=327) to Scheduling (appid=399)** — SD gained 80 listings.

## The two new applications

Both are named **"Prosthetics 4-Sight II (RMPV)"** — `appid=443` (`active`, 6 documents) and
`appid=444` (`archive`, 9 documents).

> **A second live confirmation that identity must be `appid`.** The one previous case was two
> different applications both called "Admission Discharge Transfer (ADT)" (appid 55 and 327). Name
> keying would have merged these two RMPV entries — an active application and its archive twin —
> into one.

**None of its 15 records is admitted.** `RMPV` appears in **no registry**, so `system_type` resolves
to `unclassified` and the gate treats unclassified as not-VistA. A genuinely new VistA application
therefore entered the library and left the corpus untouched, silently.

⚠️ **`vdocs completeness` still returns COMPLETE.** That is arguably wrong. VO.9 defines complete as
*nothing missing for a reason we did not choose*, and nobody chose to exclude RMPV — it simply
arrived after the registries were last curated. `not-vista:system-type=unclassified` is a
limitation wearing a decision's clothes, which is exactly what that gate exists to catch.
**Operator ruling needed:** is Prosthetics 4-Sight II in scope? Scope decisions belong to
`crawl-integrity`, and this effort only supplies the evidence.

## What it does to the admitted set

Both snapshots replayed through **today's** gate code, so this is one ruler (the replay reproduced
the tracker's 1,218 exactly, which also proves a preserved snapshot can be re-derived):

| | admitted targets |
|---|---:|
| 2026-06-10 crawl | 1,218 |
| 2026-08-05 crawl | **1,209** |
| | **26 arrived, 35 departed → net −9** |

The 35 departures are the ISS re-filing: **ADT 31, SD 3, PSO 1**. Their doc_id is
`<app>:<slug>`, so re-filing a document to another application **changes its identity** —
`ADT:iss_release_1_10_0_rn` becomes `SD:iss_release_1_10_0_rn`.

**14 of the 35 are already fetched and indexed.** CI.2 master-set retention protects them (a
fetched document is never dropped by a relabel), so the likely outcome of the next fetch is the
same content held under **two** doc_ids — the ADT originals retained, the SD twins acquired as new.
The other 21 were never fetched and leave cleanly (R‑10).

⚠️ **Not verified:** whether the CI.4 composition gate reds on the next `vdocs fetch`. Retention
runs before composition and may absorb these; `--dry-run` only reports the match count (1,209) and
does not exercise the deep gate. Expect to need an acknowledgement in
`registries/inventory/scope-changes.yaml` and check rather than assume.

## Two measurement traps, both caught

- **`file_date` looked like a regression and is not.** Every one of the 186 additions has an empty
  `file_date`, which reads as a broken parser. It is filled on **26 rows (0.3%) in *both*
  snapshots** — the VDL simply does not publish it. Measuring the baseline before calling it a
  break is what kept this out of the report as a false alarm.
- **Net counts hid the churn.** `+76` conceals 186 arrivals against 121 departures. See below.

## A limitation this exposed in VO.3 itself

The delta reports **per-section net counts**, so 121 document departures were invisible in its
output — they had to be dug out with an ad-hoc script. The effort's own carried-in note says:

> **Compare composition, not totals.** Losing 20 and gaining 20 nets to zero … findings are by
> document identifier.

VO.3 applies that at the **application** level (arrivals/departures/renames by `appid`) but not at
the **document** level. Table 1's DoD is met as written — but the principle behind it is not fully
honoured. A document-level arrivals/departures list, keyed on URL and reported by document
identifier, is the smallest change that would close the gap. **Not built**: it is a scope decision
for the operator, not one to make mid-report.

## Reproducing

```bash
vdocs vdl-delta                      # the two newest snapshots
vdocs vdl-delta 2026-06-10 2026-08-05
```

Snapshots: `$DATA_DIR/inventory/snapshots/{2026-06-10,2026-08-05}/catalog.raw.json`. The
2026-06-10 directory also holds the hand-banked `bronze/` + `gold/` copies and their `SHA256SUMS`.
