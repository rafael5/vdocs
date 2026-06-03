# `discover` miner validation — corpus ground-truth (Task 3)

**Status:** validation deliverable. **Date:** 2026-06-02. **Corpus:** the real 469-document
`text@converted` lake (`~/data/vdocs/documents/silver/text/01-converted`), `doc_type` joined from
`catalog.enriched` (§8). **Baseline:** the `vdocs-spike` reference run
(`~/projects/vdocs-spike/out/{templates,boilerplate}-by-doctype.yaml`), which used a simpler
exact-anchor method and **no `era` axis**.

This report records what the upgraded miners (`mine_templates` with the `(doc_type, era)` axis +
numbering-tolerant alignment + the enriched §9.8 schema; `mine_recurring_blocks` with the Task-1
artifact pre-filter) actually induce over the corpus, diffed against the spike. It is the
regression anchor (DIBR) plus a per-type characterization of where the era+pattern approach now
succeeds and where types remain heterogeneous.

## Corpus shape

- **469** converted bodies; **all 469** join to a catalog `doc_type` (no orphans).
- doc_type distribution: `DIBR 120 · IG 108 · RN 83 · TM 42 · UM 25 · UG 14 · DG 12 · CFG 8 ·
  API 8 · INT 6 · POM 5 · AG 4 · SG-SET 4 · QRG 4 · SG 4 · REF 3 · IG-IMP 3 · PDD 3 · SUP 3 ·
  SM 3 · APX 2 · FAQ 2 · DESC 2 · CVG 1`.
- Miners induced **17 `(doc_type, era)` template clusters**, **3,064 boilerplate** candidates,
  3,511 dead-phrase + 1,106 scaffold-line candidates, 7 structural conventions, 5,486 glossary
  acronyms.

## 1. DIBR — the regression anchor (PASS)

`(DIBR, era)` reproduces the spike's ~39-section Deployment / Installation / Back-out / Rollback
skeleton **section-for-section**, and matches the hand-curated
`registries/templates/templates.yaml`:

| template | docs | sections | notes |
|---|---|---|---|
| `DIBR:2020s:341c3495` | 48 | 40 (40 req) | **same `template_id` as the curated registry** — independent agreement |
| `DIBR:2010s:6e5f61d3` | 20 | 44 (40 req, 4 opt) | the 2010s skeleton + 4 era-specific optional subsections |

The consensus is the canonical VIP skeleton: *Purpose → Dependencies → Constraints → Timeline →
Site Readiness Assessment → Deployment Topology → … → Hardware/Software/Communications →
Pre-installation → Platform Installation → Installation Procedure/Verification → System
Configuration → Database Tuning → Back-Out Strategy/Considerations/Criteria/Risks/Authority/
Procedure/Verification → Rollback Considerations/…/Verification*. `semantic_role` is inferred
correctly across the skeleton (`orientation` on Purpose; `installation` on the platform/install
sections; `back-out` on the entire back-out/rollback tail). DIBR is the standardized, recent,
single-standard VIP template, and both methods + the curator agree on it.

Smaller `DIBR:2020s` sub-clusters (4 clusters of 3 docs each, 6–39 sections) are scaffold variants
that did not merge into the dominant cluster at the 0.6 near-dup threshold — fragmentation to watch,
but the 48-doc dominant cluster is the authoritative one.

## 2. Heterogeneous types — did the `era` axis help? (PARTIAL)

The spike found **no required skeleton** for `IG/RN/TM/UM/UG/DG` (exact-anchor alignment can't see
numbered/renamed slugs). With `(doc_type, era)` bucketing + numbering-tolerant clustering, the
picture splits into three outcomes:

| type | docs | clusters induced | outcome |
|---|---|---|---|
| **IG** | 108 | 5 | **era axis WON for 2010s**: `IG:2010s:7f77c4b2` (4 docs, **42 sections**) and `IG:2010s:eb77fa06` (3 docs, 13 sections) induce real skeletons. Older eras (1990s/2000s/unknown) cluster into the **empty-scaffold** template (`e3b0c442` = sha256 of an empty title list) — those docs carry no usable `H2+` headings in converted text. |
| **RN** | 83 | 5 | mostly the **empty-scaffold** cluster per era (1990s/2000s/2010s/unknown) — RN docs are largely flat. One real skeleton: `RN:2020s:84a70b4c` (3 docs, 6 sections). |
| **TM/UM/UG/DG** | 42/25/14/12 | **0 each** | docs spread across 4–5 eras (so per-era buckets ≥ 3 exist), but within an era the heading scaffolds do **not** near-dup cluster at threshold 0.6 — genuinely heterogeneous section structure, even after era split + numbering alignment. |

**The finding to chase.** The era axis converts part of the spike's "heterogeneous" verdict into
real per-era skeletons (clearly for `IG:2010s`, marginally for `RN:2020s`), confirming §9.6/spike §5.
But two distinct failure modes remain for the rest:

1. **Flat / heading-less docs** (older `IG`, most `RN`) collapse to the empty-scaffold cluster
   (`e3b0c442`). This is an upstream **structure-recovery** problem (no `H2+` in the converted
   text), not a template-induction one — these docs need old-gen heading recovery (§6.7) *before*
   they can yield a template. Era split cannot help a doc with no headings.
2. **Genuinely divergent structure** (`TM/UM/UG/DG`) — these docs *have* headings but share no
   common scaffold within an era at the 0.6 threshold. Candidate next steps: (a) lower
   `scaffold_threshold` for these types to admit looser clusters; (b) `title_pattern`/semantic-role
   *alignment* clustering (cluster on roles, not raw titles); (c) accept that user/technical guides
   were never poured from one skeleton and rely on the **canonical** per-`doc_type` schema (§9.8
   tier 2) for these instead of an empirical era-template.

Either way, **boilerplate subtraction pays off for all of these regardless** (§3) — it does not
require a coherent skeleton.

## 3. Boilerplate — artifact noise removed, clean head intact (PASS)

The Task-1 pre-filter removed the structural-markdown noise the spike flagged as dominant:

- **`[↑ Back to Contents](#contents)` nav lines: 0 remaining** as candidates (was the #1 "boilerplate"
  across all 120 DIBR docs).
- **Standalone images** — markdown `![](<sha>.png)` and multi-line Pandoc `<img …>` figure tags —
  no longer surface (Task-1 extension found during this validation; `![](…)` and multi-line `<img>`
  were leaking past the initial single-line filter).
- Secondary plain-text TOC lines and table-CSV markers: dropped.

The clean top-evidence head now matches the spike's report — real, curation-worthy boilerplate:

| docs | block (truncated) |
|---|---|
| 70 | "This document describes the Deployment, Installation, Back-out, and Rollback Plan for …" |
| 65/63/60/53/49/48 | KIDS install prompts ("Want KIDS to INHIBIT LOGONs…", "Want to DISABLE Scheduled Options…", "queue the install by enter a 'Q'…") |
| 54 | "The purpose of this plan is to provide a single, common document that describes how, when…" |
| 43/41 | "This manual uses several methods to highlight different aspects of the material:" + the font-convention lines |
| 41 | "Per the Veteran-focused Integrated Process (VIP) Guide, the Deployment, Installation, Back…" |

VA title-page furniture, the DIBR/CAPRI description paragraphs, KIDS prompts, and standard table
captions all surface cleanly and type-tagged — exactly the spike's clean head.

**Residual noise classes (future curation, out of Task-1 scope):**

- `**  \n**` (empty bold) recurs in **191** docs — a Pandoc empty-emphasis artifact. Not a
  link/image/CSV/nav artifact, so Task 1 does not target it; it belongs in `registries/phrases`
  (DELETE) or a `registries/structures` canonicalization. Flagged for a follow-up registry entry.
- `<img …>`-prefixed candidates that *remain* are **table rows** from the recurring symbol-legend
  table (`| <img…> | **NOTE/REF:** … |`) — these carry descriptive content and are **correctly
  retained** as legitimate boilerplate (the standard notation table), not artifact noise.

## 4. Per-doc_type verdict (induction-worthiness)

| doc_type | template verdict | boilerplate verdict |
|---|---|---|
| `DIBR` | **Promote** — validated, matches registry | **Promote** (clean, high-evidence) |
| `IG` | **2010s promotable; defer older eras** (flat docs) | **Promote** |
| `RN` | Defer (mostly flat; only 2020s skeleton) | **Promote** |
| `TM` | Defer (heterogeneous) | **Promote** |
| `DG` | Defer (no cluster) | **Promote** |
| `UM`/`UG` | Defer (heterogeneous) | candidate (lower evidence) |
| `API` | **Hold for human review** — 4-doc, 392-section heading *dump*, not a template | n/a |
| `CFG`/`POM`/`AG` | **Hold for human review** (small cohort) | n/a |

## Findings note (summary)

- **Curation-worthy templates now:** `DIBR` (both eras, validated) and **`IG:2010s`** (the era-axis
  win — a real 42-section install-guide skeleton the spike could not see).
- **Remain heterogeneous:** `TM/UM/UG/DG` (divergent structure even per-era) and the older
  `IG`/`RN` eras (flat, heading-less converted text → empty-scaffold clusters). The two are
  *different* problems: the former needs looser clustering or role-based alignment; the latter needs
  old-gen heading recovery (§6.7) upstream before a template can be induced at all.
- **Boilerplate is the broadly-useful half:** clean, high-evidence, type-tagged blocks for
  `DIBR/IG/TM/DG` (and more) regardless of whether a type has a coherent skeleton.
- **`required` policy validated:** the DIBR sections the spike measured at 60–94% are correctly
  marked required under the ≥50% ratio; the optional tier ([25%,50%)) retained 4 era-specific
  subsections in `DIBR:2010s` that "every member" would have dropped.
