# vdocs — Documentation-Discovery & Gold-Gap-Fill: Bug & Lessons-Learned Report

> **Status:** Findings report + remediation backlog. **Actionable** — every bug
> row has a proposed remedy; §16 is a prioritized backlog ready to pull into the
> remediation plan.
>
> **Date:** 2026-06-07 · **Author:** Claude (Opus 4.8) working *from the m-stdlib
> repo*, not from vdocs. · **Provenance:** surfaced while completing a real task —
> "fill the documentation gaps in the m-stdlib VistA-bridge architecture doc
> using the vdocs gold corpus, fetch what's missing, make it gold." That task
> was a textbook exercise of vdocs' two intended consumers at once: the
> **"based on vdocs gold, answer X"** path and the **"fill the gold gaps"** path.
> It worked — but only after a long chain of manual rediscovery that this report
> exists to eliminate.
>
> **Method:** read-only against the live lake at `~/data/vdocs` (figures verified
> against `inventory.json`, `state.db`, `index.db`, and the gold corpus card),
> plus one minimal mutation (a 4-doc `fetch --app VIAB`). No code changed.
>
> **Companion docs:** [`vdocs-remediation-plan.md`](vdocs-remediation-plan.md)
> (forward source of truth — this report's backlog should fold into it),
> [`vdocs-implementation-plan.md`](vdocs-implementation-plan.md). The over-
> consolidation bug is also logged in the **m-stdlib** repo at
> `docs/tracking/discoveries.md` (2026-06-07 row).

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Context — the Task That Triggered This](#2-context--the-task-that-triggered-this)
3. [The Discovery Sequence I Actually Had to Perform (the "rediscovery tax")](#3-the-discovery-sequence-i-actually-had-to-perform-the-rediscovery-tax)
4. [Master Table — Bugs & Discoveries (Problem → Remedy)](#4-master-table--bugs--discoveries-problem--remedy)
5. [B1 — Over-Consolidation Collapses Distinct Guides into One Anchor](#5-b1--over-consolidation-collapses-distinct-guides-into-one-anchor)
6. [B2 — Fetch-then-Promote Won't Reprocess a Single New Doc](#6-b2--fetch-then-promote-wont-reprocess-a-single-new-doc)
7. [B3 — `vdocs inventory --status` Has No Per-Document Query](#7-b3--vdocs-inventory---status-has-no-per-document-query)
8. [B4 — `vdocs ask` Silently Hides Fetched-but-Not-Gold Content](#8-b4--vdocs-ask-silently-hides-fetched-but-not-gold-content)
9. [B5 — No inventory ⋈ acquisitions ⋈ index "Gap-Candidate" Join](#9-b5--no-inventory--acquisitions--index-gap-candidate-join)
10. [Machine-Discovery-Surface Improvements (the gold card / ai-manifest)](#10-machine-discovery-surface-improvements-the-gold-card--ai-manifest)
11. [Inventory-Surface Improvements](#11-inventory-surface-improvements)
12. [A First-Class "Fill the Gold Gaps" Workflow/Command](#12-a-first-class-fill-the-gold-gaps-workflowcommand)
13. [Improvements to "Based on vdocs Gold, Answer Question X"](#13-improvements-to-based-on-vdocs-gold-answer-question-x)
14. [CLAUDE.md & Skill Fixes (so the rediscovery never recurs)](#14-claudemd--skill-fixes-so-the-rediscovery-never-recurs)
15. [Other Lessons Learned](#15-other-lessons-learned)
16. [Prioritized Remediation Backlog](#16-prioritized-remediation-backlog)
17. [Verified-Facts Appendix](#17-verified-facts-appendix)

---

## 1. Executive Summary

The vdocs corpus **had the answers** — six dedicated Kernel 8.0 guides (KIDS,
Device Handler, TaskMan, in Developer's + Systems-Management forms) plus full
TLS-enablement material were present, and the OAuth/IAM gap was genuinely,
verifiably absent from the entire 3,692-document VDL inventory. Those are exactly
the kinds of conclusions vdocs is built to deliver.

But reaching them required **~15 manual discovery steps** that the tool should
have answered in one or two commands. The recurring failure mode is the same in
every case: **vdocs exposes only the *gold* surface to its machine consumers, but
the two highest-value tasks — "answer X from gold" and "fill the gold gaps" —
both need visibility into the *non-gold* tiers** (what's in the VDL but unfetched;
what's fetched but not promoted; why). When that visibility is missing, an agent
falls back to hand-querying `inventory.json`, `state.db`, and `index.db` with
ad-hoc Python and SQL — slow, error-prone, and non-reproducible.

Five concrete bugs/limitations (B1–B5) and a set of surface/skill improvements
follow. The headline defect is **B1, over-consolidation**: ~41 distinct Kernel
feature guides share one anchor key and all but one get demoted to
`is_latest=0`, silently excluded from gold search. The headline *process* gap is
the absence of a **first-class gap-fill command** (§12) that joins the three
stores an agent currently joins by hand.

---

## 2. Context — the Task That Triggered This

A consumer repo (m-stdlib) had an architecture doc with a §12 "Documentation
Gaps — Proposed VDL Fetches" table listing 7 topics it believed were missing or
under-covered in the corpus:

1. Standalone KIDS guide
2. Device Handler dedicated guide
3. TaskMan dedicated guide
4. VistA TLS / IRIS-for-Health socket-TLS enablement
5. VistA IAM / OAuth 2.0 / SMART-on-FHIR
6. PARAMETER Tools full API reference
7. VIA architecture / design guide

The task: confirm each against the corpus, **fetch and make gold** anything that
exists but isn't gold, and feed the findings back. The *content* outcome (now in
m-stdlib v0.2 of the doc) was a success. The *tooling* experience is what this
report captures.

**Final content verdict, for reference:** 1–3 exist on the VDL and were fetched
(blocked from gold by B1); 4 was already gold (the doc was simply wrong that it
wasn't); 5 is absent from the entire VDL; 6 has no consolidated reference on the
VDL; 7 has a VIP User Guide (fetched, blocked by B1) but no architecture doc.

---

## 3. The Discovery Sequence I Actually Had to Perform (the "rediscovery tax")

Every step below is something I had to *figure out*, not something the tool
handed me. Steps marked **⟲** are pure rediscovery that a returning agent would
repeat from scratch.

| # | What I had to do | Why it was friction |
|---|---|---|
| 1 | Check for a live operator run (`pgrep -af "vdocs run"` + `reports/*.log`) before touching the shared lake. **⟲** | Correct and necessary, but it lives only in a global CLAUDE.md note, not in the vdocs skill; a fresh agent may not know to do it. |
| 2 | Read `ai-manifest.json` for counts — got **461 latest docs**. | Fine — but the card only describes *gold*. It gave no hint that 2,180 more genuine docs sit unfetched in the VDL, or that fetched-but-not-gold docs exist. |
| 3 | Run `vdocs ask` for each of 7 topics. | Worked for present-in-gold topics. But for the 3 Kernel guides it returned only *indirect* hits (the TM/SM summaries), giving the false impression the dedicated guides didn't exist — when in fact they were **already fetched and sitting in `index.db` at `is_latest=0`** (see B4). |
| 4 | Discover `vdocs inventory --status` exists, run it → got one summary line (`total=3692 fetched=1465 …`). **⟲** | No per-document output mode. Useless for "*which* docs about topic X are unfetched." (B3) |
| 5 | Reverse-engineer `inventory/gold/inventory.json` structure: a **dict of lists**, **8,834 rows with duplicates** (one per format/version), needing dedup by `doc_url`. **⟲** | Undocumented shape. I burned a query just learning it. |
| 6 | Hand-write Python topic filters over the deduped inventory to find candidate slugs (KIDS/Device Handler/TaskMan UGs; VIA VIP UG; IAM/OAuth = 0). **⟲** | This is the core gap-fill question and there is no command for it. (B5) |
| 7 | Query `state.db` `acquisitions` to get fetch status — keyed by `doc_id`/`source_url`, **not slug**, so slug→status needed a `LIKE '%slug%'`. **⟲** | Awkward join key; no convenience lookup. |
| 8 | Discover the 6 Kernel guides were **already fetched + converted + enriched + normalized** but not gold. **⟲** | Nothing surfaced this; I found it by `find`-ing the silver tree. |
| 9 | Read `state.db` `stage_runs` to learn a full pipeline run had completed that day, then inspect `documents/gold/consolidated/XU/` anchors. **⟲** | Manual forensics to answer "why isn't it gold?" |
| 10 | Read a gold `history.yaml` to see the `xu_dg` anchor had only 2 members — proving the granular guides were dropped. **⟲** | This is the moment B1 became visible; took deep spelunking. |
| 11 | Cross-check `index.db`: the guides **are** there but at `is_latest=0`; confirm FTS only indexes `is_latest=1` (from the skill doc). **⟲** | The exclusion is silent. |
| 12 | Try `vdocs fetch --app VIAB` (worked) then `vdocs run --from convert` → **skipped everything** as unchanged; `--force` also skipped convert. **⟲** | The single-new-doc promote path doesn't work. (B2) |
| 13 | Fall back to reading content from the normalized **silver** bodies directly. **⟲** | The only way to extract the findings, since gold search couldn't see them. |
| 14 | Grep silver bodies for the precise APIs (`CALL^%ZISTCP`, `$$PSET^%ZTLOAD`, Required Builds #11, `XPDENV`, `DEFAULT TLS SERVER CONFIG`). | Reasonable, but only because gold search was unavailable. |
| 15 | Confirm the absent topics (OAuth/SMART/FHIR/IAM) are truly absent across all 3,692 docs, not merely unfetched. **⟲** | "Confirmed absent" is a first-class answer a gap-fill tool should produce directly. |

**Net:** ~12 of 15 steps are rediscovery a returning agent repeats from zero.
The remedies below collapse this to **two commands**: a gap-candidate query (§12,
B5) and a single-doc fetch-and-promote (§6, B2).

---

## 4. Master Table — Bugs & Discoveries (Problem → Remedy)

| ID | Severity | Area | Problem | Remedy (short) |
|---|---|---|---|---|
| **B1** | **P1** | `catalog`/identity + `consolidate` | ~41 distinct Kernel-8.0 `krn_8_0_{dg,sm}_*_ug` feature guides share one `XU:XU:UG` anchor key → consolidate keeps one "winner", demotes ~40 to `is_latest=0` → excluded from gold search & anchor set. | Derive a **per-document** anchor key for granular feature guides (include `doc_subject`/slug, not just `doc_code`). Add a consolidate guardrail: warn when a version group's members have **divergent titles** (a heuristic for "these aren't versions of each other"). |
| **B2** | **P1** | `run` orchestrator / `convert` | After `fetch` adds a new bronze doc, `vdocs run --from convert` skips all stages as "unchanged"; `--force` also fails to re-run convert. New doc never promotes. | Make stage freshness key on the **bronze acquisition set**, not just prior stage outputs; make `--force` actually force the named range; add a `vdocs promote <doc_id>` one-shot (fetch→…→manifest for a single lineage). |
| **B3** | **P2** | `inventory` CLI | `inventory --status` prints only an aggregate line; no per-document, filterable, machine-readable output. | Add `--json` + dimension filters (`--app/--doc-type/--topic/--status fetched|pending|not_acquired|not_gold`). Emit rows with `doc_key, slug, fetched, is_latest, gold, body_path`. |
| **B4** | **P1** | `ask` / search surface | `vdocs ask` indexes only `is_latest=1`, so fetched-but-demoted content (B1's victims) is **silently invisible** — the agent gets "not found" when the answer is in silver. | When a query has strong hits among `is_latest=0` / silver docs, surface them under a **"non-gold matches"** section with a clear tier label, or at least a count + hint. Never let present content read as absent. |
| **B5** | **P2** | discovery surface | No command answers the gap-fill core question: "docs about topic X that exist in the VDL but aren't gold yet." Requires hand-joining inventory ⋈ acquisitions ⋈ index. | Ship `vdocs gaps "<topic>"` (and `--app/--doc-type`) that does the join and returns candidates with status + suggested action. See §12. |
| **D1** | discovery | inventory schema | `inventory.json` is an undocumented dict-of-lists with per-format/version dupes (8,834 rows for ~3,692 genuine docs). | Document the schema in the card; or expose it only via the B3 query so consumers never parse the raw file. |
| **D2** | discovery | acquisitions schema | `acquisitions` is keyed by `doc_id`/`source_url`, not slug/`doc_key`; slug lookup needs `LIKE`. | Add a `doc_key` column or a view joining acquisitions↔inventory on a stable key. |
| **D3** | docs | card scope | `CORPUS.md`/`ai-manifest.json` describe **only gold** — they have no view of "fetched-not-gold" or "in-VDL-not-fetched," the exact tiers a gap-fill task needs. | Add coverage/tier counts + a "frontier" section to the card (see §10). |
| **D4** | process | shared-lake safety | The "check for a live `vdocs run` before staging" rule lives only in a global CLAUDE.md, not the vdocs skill. | Move it into the `vdocs-pipeline` skill as a preflight step (see §14). |

---

## 5. B1 — Over-Consolidation Collapses Distinct Guides into One Anchor

**Severity: P1 (silently hides genuine, fetched content from gold search).**

### Symptom
The dedicated **KIDS / Device Handler / TaskMan** Developer's-Guide and
Systems-Management guides — real, distinct VA manuals — are absent from
`vdocs ask` and have no `documents/gold/consolidated/.../body.md` anchor, even
though they are fetched and fully processed through silver.

### Root cause
The `catalog`/identity stage assigns an **anchor key** of the form
`<app>:<ns>:<doc_code>`. For all ~41 Kernel-8.0 per-feature User Guides the
`doc_code` is the same (`UG`), so they collapse to a single version group
**`XU:XU:UG`**. `consolidate` is designed to pick one "latest" anchor per version
group and retain the rest as append-only lineage (prior *versions*). It therefore
keeps one winner and marks the other ~40 **`is_latest=0`**. Because the search
index (`index.db` FTS5) covers **only `is_latest=1`**, those ~40 distinct guides
vanish from the gold/search surface.

This is a **category error**: KIDS UG, Device Handler UG, and TaskMan UG are
*different documents*, not different *versions of one document*. The version-group
abstraction is being applied across a set whose members are siblings, not
revisions.

### Evidence (verified)
- `documents/silver/text/03-normalized/XU/` contains **41** `*_ug` guides.
- `documents/gold/consolidated/XU/xu_dg/history.yaml` → anchor `XU:XU:DG`,
  `member_count: 2` (`krn_8_0_dg` + `kdc1_0dgrm`) — the granular `*_dg_*_ug`
  guides are **not** members.
- `index.db`: `XU/krn_8_0_dg_kids_ug` … exist but every one has `is_latest=0`.
- `vdocs ask "KIDS environment check routine … XPDUTL"` → no KIDS-guide hit.

### Impact
Any "answer X from gold" or "fill the gold gaps" task touching a multi-guide
application (Kernel is the worst case, but any app that ships many same-`doc_code`
manuals is exposed) will get false negatives. The corpus *looks* thinner than it
is. The same defect blocks `VIAB/via_vip_user_guide`.

### Remedy
1. **Anchor-key fix:** for granular feature guides, derive a per-document anchor
   key (e.g. fold `doc_subject` or the slug stem into the key), so siblings get
   distinct anchors.
2. **Consolidate guardrail:** when a version group's members have **materially
   divergent titles** (cheap string-distance check), refuse to collapse and emit
   a `validate`-stage warning — silent over-collapse should be impossible.
3. **Backfill:** after the fix, re-run `catalog`→`consolidate`→`index`→`relate`→
   `manifest`; the ~40 Kernel guides + the VIA VIP UG promote to gold.

---

## 6. B2 — Fetch-then-Promote Won't Reprocess a Single New Doc

**Severity: P1 (the documented "fetch and make gold" workflow doesn't complete).**

### Symptom
`vdocs fetch --app VIAB` fetched 4 docs (1 new, `via_vip_user_guide`) into bronze
successfully. The follow-up `vdocs run --from convert` reported success but
**skipped every stage as "unchanged"** (stage `finished_at` timestamps didn't
move); the VIP UG was never converted. `vdocs run --from convert --force` also
did **not** re-run convert. Result: the new doc is stuck in bronze.

### Root cause (hypothesis — needs a code read)
Stage freshness appears to be computed from prior-stage *output* fingerprints, not
from the **bronze acquisition set**, so adding a bronze doc doesn't invalidate
convert. And `--force` is either not threaded into the convert stage's skip
decision or is scoped to the orchestrator's top-level DAG check.

### Impact
The single most common gap-fill action — "fetch this one missing doc and make it
gold" — cannot be completed with the documented commands. The operator is forced
into either a full forced rebuild (expensive, mutates the shared lake) or reading
from bronze/silver by hand.

### Remedy
1. Include the **bronze acquisition manifest** in the convert stage's freshness
   key so a new acquisition triggers reprocessing of (at least) that lineage.
2. Make `--force`/`--from` actually force the named stage range unconditionally.
3. Add a first-class **`vdocs promote <doc_id|--group …>`**: fetch (if needed) →
   convert → enrich → normalize → consolidate → index → relate → manifest for a
   **single lineage**, incrementally, without a global rebuild. This is the
   natural primitive for gap-fill.

---

## 7. B3 — `vdocs inventory --status` Has No Per-Document Query

**Severity: P2.**

`inventory --status` prints exactly one line:
`inventory status: total=3692 fetched=1465 failed=5 not_acquired=2180 out_of_scope=42`.
There is no flag for per-document rows, no filtering, no JSON. To answer "which
unfetched docs are about TaskMan?" I had to parse `inventory.json` by hand.

**Remedy:** add `--json` and dimension filters (`--app`, `--doc-type`, `--topic`,
`--status fetched|pending|not_acquired|failed|out_of_scope|not_gold`). Each row:
`{doc_key, slug, app, doc_type, fetched, is_latest, gold, body_path, doc_url}`.
This single change retires steps 4–8 of §3.

---

## 8. B4 — `vdocs ask` Silently Hides Fetched-but-Not-Gold Content

**Severity: P1 (correctness — present content reads as absent).**

`vdocs ask` searches FTS over `is_latest=1` only. That is the right *default* for
clean answers, but it means B1's ~40 demoted guides (and any fetched-but-not-
promoted doc) are **invisible with no signal**. During this task `ask` told me the
KIDS/Device Handler/TaskMan guides weren't there; they were, in silver and in
`index.db`.

**Remedy:** when a query's top non-gold hits clear a score threshold, append a
**"⚠ non-gold matches (fetched, not promoted)"** block to the `ask` output (CLI
and `--json`), each row tier-labeled (`silver` / `is_latest=0`) with its
`body_path`. At minimum, print a one-line hint: *"N fetched-but-not-gold docs also
matched — run `vdocs gaps` / `vdocs promote`."* The invariant: **vdocs must never
let present content read as absent.**

---

## 9. B5 — No inventory ⋈ acquisitions ⋈ index "Gap-Candidate" Join

**Severity: P2 (forces hand-joining 3 stores for the core gap-fill question).**

The gap-fill task's central question — *"what exists in the VDL about topic X that
isn't gold yet, and what's blocking it?"* — requires joining:
- `inventory.json` (topic → candidate docs),
- `acquisitions` (fetched? failed? not_acquired?),
- `index.db` (`is_latest`/gold?).

There is no command for this; I wrote the join by hand three times. See §12 for
the proposed `vdocs gaps` command that ships the join.

---

## 10. Machine-Discovery-Surface Improvements (the gold card / ai-manifest)

The card (`CORPUS.md` + `ai-manifest.json` + `discovery.json`) is excellent for
"what's in gold," but it is **gold-only**, which blinds the two key tasks. Add:

1. **Tier/coverage counts** in the manifest header: `gold` (latest, searchable),
   `fetched_not_gold` (the B1/B2 victims), `in_vdl_not_fetched` (the 2,180),
   `failed`, `out_of_scope`. One glance tells an agent whether a gap is a *fetch*
   problem or an *absence*.
2. **A "frontier" section** listing, per application, how many docs are gold vs.
   fetched-not-gold vs. unfetched — so "is app XU fully mined?" is answerable from
   the card.
3. **An explicit "confirmed absent" affordance.** "We searched the whole VDL and
   topic T has zero docs" is a *valuable, citable* answer (it's how I closed the
   OAuth gap). The card/`ask` should make that a clean result, not an inference
   from an empty search.
4. **Tier labels on every machine result.** Any doc reference the surface emits
   should carry its tier (`gold|silver|bronze|in-vdl-only`) so a consumer never
   assumes gold.

---

## 11. Inventory-Surface Improvements

- Implement **B3** (per-doc query) — the single highest-leverage inventory fix.
- Implement **D2** — add a `doc_key`/slug join key (or a view) to `acquisitions`.
- Publish the **`inventory.json` schema** (D1) or, better, make the raw file an
  implementation detail behind the B3 query so no consumer parses dict-of-lists
  with per-format dupes again.
- Add `inventory --topic "<text>"` doing a lexical match over
  `doc_title`/`doc_label`/`app_name_full`/`doc_subject` so topic discovery
  doesn't require custom Python.

---

## 12. A First-Class "Fill the Gold Gaps" Workflow/Command

This task is common enough to deserve a command. Proposed:

```
vdocs gaps "<topic>" [--app XU] [--doc-type UG] [--json]
```

**Behavior:** lexical match over the inventory, joined to acquisitions + index,
returning every candidate with a **status** and a **next action**:

| status | meaning | suggested action |
|---|---|---|
| `gold` | already latest + searchable | cite it |
| `fetched_not_gold` | in silver/`index.db`, `is_latest=0` | `vdocs promote <doc_id>` (and fix B1 if it's an over-collapse) |
| `not_acquired` | in the VDL, never fetched | `vdocs fetch --select` then `vdocs promote` |
| `failed` | fetch attempted, errored | inspect `acquisitions.error`, retry |
| `out_of_scope` | PDF-only etc. | note the limitation |
| *(empty result)* | **confirmed absent from the VDL** | report the gap as unfillable from the VDL |

Pair it with **`vdocs promote <doc_id>`** (B2) so the two-step gap-fill —
*discover candidates → promote one* — is two commands, not fifteen. A short
**`docs/playbooks/fill-the-gold-gaps.md`** should document the loop end-to-end.

---

## 13. Improvements to "Based on vdocs Gold, Answer Question X"

The grounded-answer path is the skill's headline. Two fixes make it trustworthy:

1. **B4** — never let fetched-but-not-gold content read as absent. An answer of
   "not in the corpus" must mean "not fetched *and* not in the VDL," not "fetched
   but demoted by B1."
2. **"Absent" as a first-class answer.** When `ask` is empty, the surface should
   distinguish *"absent from gold but present in silver"* (→ promote), *"in the
   VDL but unfetched"* (→ fetch), and *"absent from the entire VDL"* (→ genuinely
   unanswerable from VA docs). Today all three look identical (empty result), and
   the agent must do §3's forensics to tell them apart. This directly determines
   whether the correct response is "let me fetch it" vs. "the VDL doesn't cover
   this."

---

## 14. CLAUDE.md & Skill Fixes (so the rediscovery never recurs)

The knowledge an agent needed for this task is scattered or missing. Concretely:

### `vdocs-corpus` skill (the query path)
- Add a **"gap-fill / not-in-gold" section**: how to tell *absent-from-gold* from
  *absent-from-VDL*; point at `vdocs gaps` (once it exists) and the silver-tier
  fallback (`documents/silver/text/03-normalized/<APP>/<slug>/body.md`).
- Document the **`is_latest=1`-only** search caveat explicitly (it's the root of
  B4's surprise) and the B1 over-consolidation gotcha so an agent doesn't trust an
  empty `ask` for a multi-guide app.

### `vdocs-pipeline` skill (the operate path)
- Add a **preflight**: check for a live `vdocs run` (`pgrep` + `reports/*.log`)
  before any stage on the shared lake — currently only in a personal global
  CLAUDE.md, so it doesn't travel.
- Document the **single-doc fetch→promote** recipe (and its current B2 breakage +
  the full-`--force` workaround) until B2 is fixed.
- Document the **`inventory.json` / `acquisitions` / `index.db` shapes** (D1/D2)
  so nobody reverse-engineers them again.
- Document the **over-consolidation gotcha** (B1): an empty gold result for a
  known-to-exist guide ⇒ check `is_latest=0` in `index.db` before concluding it's
  missing.

### vdocs repo `CLAUDE.md`
- Add a short **"Two consumer tasks"** subsection naming the *answer-X* and
  *fill-gaps* paths and the commands each should use — so the design intent that
  these are first-class is visible to any agent that opens the repo.

---

## 15. Other Lessons Learned

- **The card's `index_fingerprint` is the right freshness handle** — but it only
  reflects gold. A consumer can't tell from the card that bronze/silver moved
  (e.g. my VIAB fetch). Tier counts (§10) fix this.
- **A minimal mutation is safe and was correct** here (a 4-doc `fetch`), but the
  *promote* couldn't complete (B2), so the lake now holds a fetched-not-gold doc
  that the card doesn't mention — exactly the invisible state §10 warns about.
- **Reading from silver is a legitimate fallback** and should be *blessed* in the
  skill, not treated as off-road. Normalized silver bodies are clean markdown; for
  a one-off extraction they're fine. The tool should make this an explicit,
  documented escape hatch rather than something each agent reinvents.
- **"Confirmed absent" deserves the same rigor as a hit.** I verified OAuth/IAM
  absence across all 3,692 docs; that negative is a load-bearing conclusion in the
  consumer doc. The surface should make producing it cheap and citable.
- **Over-collapse is probably broader than Kernel.** Any app shipping multiple
  same-`doc_code` manuals (User Guides, Technical Manuals split per feature) is a
  candidate. A `validate`-stage report of "version groups with divergent member
  titles" would quantify the blast radius in one run.

---

## 16. Prioritized Remediation Backlog

| Pri | Item | Bug(s) | Effort | Payoff |
|---|---|---|---|---|
| **P1** | Fix anchor-key derivation for granular feature guides + consolidate divergent-title guardrail; backfill. | B1 | M | Unblocks ~40 Kernel guides + VIA VIP UG; prevents silent corpus shrinkage. |
| **P1** | `vdocs promote <doc_id>` single-lineage promote + fix convert freshness/`--force`. | B2 | M | Makes "fetch & make gold" actually work. |
| **P1** | `ask` surfaces non-gold matches / never reports present content as absent. | B4 | S | Correctness of the headline query path. |
| **P2** | `vdocs gaps "<topic>"` join command. | B5, B3 | M | Collapses §3's 15 steps to 2. |
| **P2** | `inventory --json/--topic/--status` per-doc query. | B3, D1, D2 | S | Retires hand-querying inventory/acquisitions. |
| **P2** | Card tier/coverage counts + frontier + "confirmed absent" affordance. | D3, §10 | S | Agents see fetch-problem vs. absence at a glance. |
| **P3** | Skill + CLAUDE.md updates (vdocs-corpus, vdocs-pipeline, repo CLAUDE.md). | D4, §14 | S | Stops the rediscovery from recurring. |
| **P3** | `validate`-stage "divergent-title version groups" report. | B1 (detection) | S | Quantifies over-collapse blast radius. |

---

## 17. Verified-Facts Appendix

All figures observed directly from the live lake at `~/data/vdocs` on 2026-06-07.

- **Inventory status:** `total=3692 fetched=1465 failed=5 not_acquired=2180 out_of_scope=42`.
- **Gold card counts:** `documents_latest=461`, `version_groups=461`,
  `sections=89800`, `sections_searchable=24320`, entities 4,792.
- **Over-collapse:** `documents/silver/text/03-normalized/XU/` holds **41**
  `*_ug` guides; `index.db` shows them present but `is_latest=0`;
  `gold/consolidated/XU/xu_dg/history.yaml` anchor `XU:XU:DG` has `member_count: 2`
  (the granular guides are not members).
- **Search scope:** FTS5 indexes `is_latest=1` rows only (per the corpus card /
  skill contract) — the mechanism by which B1's victims are hidden (B4).
- **Fetch-promote breakage:** `fetch --app VIAB` → `4 fetched`; subsequent
  `run --from convert` and `run --from convert --force` left `stage_runs.convert
  finished_at` unchanged and produced no `converted/VIAB/via_vip_user_guide`
  bundle.
- **Content actually present (read from silver, now grounding m-stdlib doc v0.2):**
  `CALL^%ZISTCP` (ICR #2118), `OPEN/USE/CLOSE^%ZISUTL`, `$$PSET^%ZTLOAD`
  (ICR #10063), Required Builds `#11` Multiple + 3 install actions, env-check
  `XPDENV`, and `XU*8*787` → `DEFAULT TLS SERVER CONFIG` → IRIS
  `Security.SSLConfigs` (the latter in gold `xu_tm`).
- **Confirmed absent from the entire 3,692-doc VDL:** `oauth`, `smart on fhir`,
  `token introspection`, `fhir`, `identity and access`, `ssoi` — zero documents.

---

*End report. Fold the §16 backlog into
[`vdocs-remediation-plan.md`](vdocs-remediation-plan.md); B1, B2, and B4 are the
P1s. A returning session should start from
[`docs/prompts/discovery-surface-bugfix-kickoff.md`](prompts/discovery-surface-bugfix-kickoff.md).*
