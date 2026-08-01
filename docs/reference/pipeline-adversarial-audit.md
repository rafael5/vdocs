# vdocs pipeline — end-to-end adversarial logic audit

**Basis: the executed code, not the documentation.** Every claim below was derived by reading the
wired stage implementations (`src/vdocs/…` at the audit commit) and cross-checked against the
**live lake** (`~/data/vdocs`, audited 2026-08-01, `corpus_content_hash 3ce0872e32ec…`,
1,034 documents / 615 gold anchors, `vdocs doctor` = **GOLD LIBRARY: GREEN**, `validate`
blocking = 0). Where the design docs and the code disagree, the code wins here and the
disagreement is called out.

**Why this document exists (the four uses):**

1. **Human audit** — a person can read §3 + §4 and verify each stage's logic, inputs, outputs,
   and its measure of "done and accurate", stage by stage, against the code cited by
   `file:line`.
2. **Re-implementation reference** — §6 separates *normative* logic (must be replicated in a Go
   port) from *incidental* Python behavior (must NOT be replicated blindly).
3. **Traceability / reliability under drift** — §5 is the artifact ledger: every stage emits a
   written, computable artifact the next stage reads, so the whole chain is re-derivable and
   diffable when the VDL source or a format changes (§8).
4. **An accurate MCP service** — §7 is the method for serving this corpus over MCP without
   manufacturing false negatives, including the CSV sidecars and the container/hollow retrieval
   gap.

---

## Table of contents

- [1. Scope and method](#1-scope-and-method)
- [2. The execution substrate (orchestrator, contracts, state)](#2-the-execution-substrate-orchestrator-contracts-state)
- [3. Master stage table](#3-master-stage-table)
- [4. Per-stage audit notes (the footnotes)](#4-per-stage-audit-notes-the-footnotes)
- [5. The auditable artifact chain (ledger)](#5-the-auditable-artifact-chain-ledger)
- [6. Re-implementation (Go) reference notes](#6-re-implementation-go-reference-notes)
- [7. The MCP server & search-accuracy method](#7-the-mcp-server--search-accuracy-method)
- [8. Traceability when the source or formats change](#8-traceability-when-the-source-or-formats-change)
- [9. Risks & mitigations register](#9-risks--mitigations-register)

---

## 1. Scope and method

The pipeline is 15 wired stages (`cli/app.py:build_stages`, the authoritative list) executed by a
generic DAG orchestrator, plus a serving layer (`ask` CLI, MCP server, doctor, release) that is
not in the DAG. The derived topological order (Kahn, ties by name —
`orchestrator/engine.py:57`) is:

```
crawl → catalog → serve-inventory → fetch → convert → {discover, enrich} → normalize
      → consolidate → {index, resolve, validate} → {merge, relate} → manifest
```

Note two audit-relevant order facts the docs do not state: **`validate` runs *before*
`merge`/`relate`/`manifest`** (it gates only normalize/consolidate sidecars — nothing in the DAG
gates `index.db` content; that is `doctor`'s job, and `doctor` is a CLI command, not a stage);
and `discover` is on-path but produces proposals only (nothing downstream `requires` its
output).

Adversarial method: for each stage I asked (a) what is the *measurable* input and output, (b)
what written computable artifact does the next stage actually read, (c) what is the coded
measure of "done and accurate", and (d) **what failure would this measure fail to see** (the
omission test). Findings are graded in §3 and consolidated into §9.

## 2. The execution substrate (orchestrator, contracts, state)

**Logic as coded.** Every stage subclasses `Stage` (`orchestrator/stage.py`) and inherits one
preflight/postflight algorithm — there is no second execution path. Preflight: (1) every
`requires` contract must `validate()` (exist + be structurally usable); (2) each internal
upstream must have an `ok` record in `state.db:stage_runs` **and** its recorded output
fingerprint must equal the artifact's current fingerprint (out-of-band drift check); (3) skip
if `force` is off, the prior run was `ok`, `contract_ver` matches, `inputs_fp` matches, and
required outputs validate. Postflight: required outputs must validate, the stage's `deep_gate`
must pass, then one `(stage, scope)` record is upserted with input/output fingerprints and
counts. Fingerprints (`kernel/fingerprint.py`): cheap = `size:mtime_ns` for files, tree hash of
those for trees, **`rows:<count>` for SQLite tables**; strong (`--verify`) = sha256 of content.
All artifact writes are atomic (`kernel/cas.py:atomic_write` temp+rename with byte-identical
content-skip; `kernel/db.py:build_atomic` / `replace_table_atomic` for SQLite).

**Measure of done:** each stage's `stage_runs` row (`status=ok`, `outputs_fp`, `counts`) — a
written, computable record; the next stage *reads it* in preflight. This is the spine that makes
the chain auditable.

**Adversarial findings on the substrate:**

- **A cheap SQLite fingerprint is a row count** — content changes that preserve the row count
  are invisible to `SKIP_IF_UNCHANGED`. Concretely: a registry edit that changes labels in
  `doc_meta_staged` (same 1,034 rows) while leaving normalized bodies byte-identical lets
  `index` skip with stale metadata. `contract_ver` folding covers *shape* changes only;
  `--verify` covers content but is opt-in. (R‑1)
- **`stage_runs` is last-write-only** (`INSERT OR REPLACE`, keyed `(stage, scope)`,
  `scope` always `""`). The docstring calls it "the pipeline's history"; it is actually only
  the pipeline's *latest state* — there is no append-only run journal for audit. (R‑2)
- **`DOC_ERROR_RATE_LIMIT = 0.5`**: a per-document stage (convert/normalize/consolidate) passes
  with up to half the corpus failing — failures are WARNs + counts, and nothing downstream
  gates on `counts["errors"]`. (R‑3)
- The upstream-drift check is real and good (a hand-edited artifact is caught), and `F4`
  (`requires_upstream_record=False` on `catalog`) is a deliberate, documented trust hole for
  surviving `catalog.raw.json` after a `state.db` wipe — acceptable, but note the 1:1 gate
  weakening it causes (see [S3]).

## 3. Master stage table

Grades: **Done** = ran `ok` on the live lake 2026‑07‑04 (all 15 did). **Credibility** =
does the coded "measure of done" actually prove the stage's output is *complete and accurate*
(High = gated on an independent measure; Medium = self-consistent / spot-gated; Low = ungated
or self-referential). Footnotes ([S1]…) are in §4.

| # | Stage | Core logic (as coded) | Measurable input | Computable output (next stage reads) | Measure of done/accurate (coded) | Live status (2026‑08‑01) | Credibility | FN |
|---|-------|----------------------|------------------|--------------------------------------|----------------------------------|--------------------------|-------------|----|
| 1 | `crawl` | 3-level HTML walk (index→sections→apps→doc links), BeautifulSoup + regex heuristics; polite client (UA, 5xx/429 backoff, redirects≤5) | The live VDL site (external, unfingerprintable) | `inventory/bronze/catalog.raw.{json,csv}` + `stage_runs[crawl].counts` | Postflight: file exists; per-page non-200 → WARN+skip, never abort | ok: 5 sections, 396 apps, 8,907 docs, 0 skipped | **Low** — no completeness floor; a partial crawl blesses a smaller world | [S1] |
| 2 | `catalog` | Pure 5-pass enrichment (mojibake/typos → patch-identity regexes → doc-type classify → corpus-global noise/companion/groups → peer inference → manual overrides → canonical labels → anchor_key) from registries | `catalog.raw.json` + `registries/` (fingerprinted) | `inventory/silver/catalog.enriched.{json,csv,schema.json}` | Deterministic pure function; postflight = file exists | ok: 8,907 records (7,573 clean, 1,184 vba_form, 148 va_ref, 2 test) | **Medium** — deterministic + registry-driven, but classification accuracy itself is unmeasured | [S2] |
| 3 | `serve-inventory` | Promote silver→gold JSON/CSV/SQLite; **deep_gate HARD GATE**: non-empty, 1:1 with crawl count, all noise_type/system_type/section_code/doc_format valid, ≥1 genuine doc | `catalog.enriched.json` | `inventory/gold/inventory.{json,csv,db}` + blessed `ok` (the fetch gate) | The deep_gate verdict (first hard failure wins) | ok: 8,907 records, 7,573 genuine | **Medium** — the 1:1 check is *self*-consistency vs crawl's own count; it cannot see crawl omissions, and is skipped entirely when the crawl record is absent | [S3] |
| 4 | `fetch` | Selection predicate (AND across dims) + always-on admission gate (scope-policy + doctype-policy YAML) + anchor-completeness + DOCX-dedup; CAS store `<sha256>.docx`; per-doc `acquisitions` rows; 3-attempt permanent cap | `inventory.json` + gate registries + selection fp + gate fp (both in `inputs_fp`) | `documents/bronze/raw/<sha>.docx` (CAS), `raw/index.json` (sha→provenance), `acquisitions` table | Per-doc `acquisitions` status; counts + WARN lists; no byte-level content check | ok (2026‑07‑04 top-up run): acquisitions 1,040 fetched / 4 failed | **Medium** — resilient + resumable, but **`raw/index.json` is sha-keyed: 6 doc_ids measurably collapsed** (last-writer-wins), and a 200 HTML error page would enter the CAS as a `.docx` | [S4] |
| 5 | `convert` | Pandoc→GFM (`--extract-media`), Docling for a curated allowlist (1 doc); images → asset CAS, refs rewritten by basename; per-doc error isolation | CAS tree + `raw/index.json` | `silver/text/01-converted/<app>/<slug>/body.md` + `documents/assets/` | Preflight: converter binaries present; deep_gate: error rate ≤ 50% | ok: 1,034 docs, 27,241 assets, 1 docling, 0 errors | **Low/Medium** — no per-doc output floor: an empty/garbage markdown from a corrupt DOCX passes; conversion loss is invisible until normalize's retention flag (which doesn't gate either) | [S5] |
| 6 | `discover` | Corpus-wide pure miners (recurring blocks, glossary, converter-routing, structures, (doc_type, era) templates) → **proposals only** | converted tree + `catalog.enriched` | `reports/patterns/patterns.json` | None (diagnostic-by-design; humans curate into `registries/`) | ok: 17,973 glossary cands, 4,638 scaffold blocks, 35 templates | **High for its role** — it asserts nothing into the corpus | [S6] |
| 7 | `enrich` | Join bundle ↔ inventory record by `(safe app, doc_slug)` (DOCX preferred); bake identity+persona frontmatter; stage computed metadata | converted tree + `catalog.enriched` + persona registries | `silver/text/02-enriched/**/body.md` (FM) + `index.db:doc_meta_staged` (atomic table swap) | `missing_record` counted (WARN only), no floor | ok: 1,034 docs, 0 missing, 0 pruned | **Medium** — deterministic join, but an unmatched bundle silently drops out of `doc_meta_staged` with no gate | [S7] |
| 8 | `normalize` | The F-steps: capture-before-strip (published date, revision tables→`revisions.yaml`, big tables→`tables/*.csv`, legacy TOC→`toc.yaml`), template strip (inert: 0 matched), title standardize, heading recovery/leveling, bookmark→GitHub-slug rewrite, TOC regen, back-links; per-bundle `capture.yaml` (typed outcomes + independent residue re-scan), `refs.yaml`, `flags.yaml`, retention scoring | enriched tree + `raw/index.json` + registries | `silver/text/03-normalized/**` = body + 6 sidecar types — the densest computable audit surface in the pipeline | `capture.yaml` for **every** bundle (absence typed, never ambiguous); retention verdict **flagged but not gated**; deep_gate = error rate only | ok: 1,034 docs; 852 revisions, 6,563 table CSVs, 998 refs, 801 tocs, 0 absent-unexpected, 7 low-retention | **High on capture honesty, Low on retention enforcement** — QUARANTINE-level docs still flow to gold; `blocks_publish()` is dead code | [S8] |
| 9 | `consolidate` | Reconstruct `anchor_key` from FM (same kernel formula as catalog + alias map); group, order (base→patch_num→official_date→slug), collapse to one version-free anchor bundle; retain every body in CAS; append-only `history.yaml`; **signed `bundle.yaml`** (part hashes + digest) written last; stale-part prune | normalized tree + assets | `gold/consolidated/<app>/<stem>/{body.md, history.yaml, bundle.yaml, sidecars, tables/}` + `_shared/history` CAS | `bundle.yaml` is recomputable from disk (validate Step 4 does); deep_gate = error rate | ok: 615 groups from 1,034 docs, 1,034 retained bodies | **High for integrity, Medium for lineage truth** — append-only `merge_history` never refreshes a captured member's facts, so `history.yaml` can carry a stale `body_sha256` for a re-normalized member | [S9] |
| 10 | `index` | Shred bodies into heading-aligned sections (fence-aware, slugs identical to `refs.yaml`); classify container/ok/stub/hollow; chunk only searchable latest sections (split >8k chars); re-inject `tables/*.csv` as searchable chunks; regex/vocab entity extraction (registry-driven); rebuild `index.db` atomically, carrying `doc_meta_staged` forward; stamp `meta` (read_schema_version + deterministic corpus_content_hash) | normalized tree + consolidated tree + `doc_meta_staged` + registries | `index.db`: documents, doc_sections, chunks, chunks_fts, entities, entity_mentions, vocab, meta + v_* views | contract_ver = 14 (shape bumps recorded); no in-DAG content gate (doctor is external) | ok: 1,034 docs, 81,149 sections, 48,707 chunks (5,225 table chunks), 6,572 entities, 90,456 mentions | **Medium** — structurally excellent, but by construction **27.2% of live sections (11,526 containers + 2,627 hollow of 52,048) yield no searchable text**, incl. container lead-in prose that in reference manuals is the API contract | [S10] |
| 11 | `resolve` | SKL build, **DI pilot only** (`PILOT_APP="DI"` hardcoded): shared recognizer + DD-seed resolution index (number/name/global→`fileman_file/N`); unresolved → propose-only queue; closed edge-type set; every node stamped `asserted` | consolidated gold (DI subtree) + registries | `gold/knowledge.db` (entities/terms/relationships) + `knowledge-proposals.json` | deep_gate: every node carries an `asserted` verification block | ok: 21 entities, 483 terms, 111 edges, **4,415 unresolved proposals** | **High governance, tiny coverage** — the queue is 200× the asserted set | [S11] |
| 12 | `validate` | HARD GATE over normalize/consolidate: (1) any `absent-unexpected` capture outcome; (2) count reconciliation vs `stage_runs[normalize].counts` + prior report (zero-class & drop detection, corpus ≥ 50); (3) severed cross-refs = hard floor 0 (unmapped = metric only, ~92% expected); (4) bundle.yaml hash/digest recomputation for every gold bundle | normalized + consolidated trees + state + prior report | `reports/validation/verification.json` (findings + next run's baseline) | deep_gate fails on any blocking class | ok: 0 reconcile findings, 0 severed, 575 unmapped, 919 expected-unmapped, 0 bundle findings | **High for what it covers** — but it runs *before* merge/relate/manifest and never looks at `index.db`, retention flags, or the acquisitions↔raw-index join | [S12] |
| 13 | `merge` | Fold SKL into index.db: id reconcile on `(type, canonical)` (`fileman_file:200` ↔ `fileman_file/200`), synonym catalog, distinctive-surface chunk tags; atomic single-table swaps into shells `index` owns | index.db entities/chunks + knowledge.db | `index.db`: entity_skl, entity_synonyms, chunk_entities | counts only | ok: **6 of 21** SKL entities reconciled, 56 synonyms, 5,786 chunk tags | **Medium** — 15/21 entities silently fail reconciliation with no finding (counts show it; nothing gates it) | [S13] |
| 14 | `relate` | Derive edges from existing mentions only: doc→entity (weight=count), entity↔entity per-section co-occurrence, doc↔doc via shared significant entity (`XREF_TYPES` **hardcoded** frozenset) | index.db mentions/entities | `index.db:relations` (atomic swap) | counts only | ok: 203,143 edges (14,117 mentions, 159,632 cooccurs, 29,394 xref) | **Medium** — mechanically sound; graph quality is entirely inherited from entity extraction; xref-type policy is code, not registry (tenet #13 violation) | [S14] |
| 15 | `manifest` | Assemble corpus-manifest / discovery / contract-manifest (meta axes verbatim) / AI card (+ sha256 fingerprint of index.db file) / shared boilerplate copies / SKL-projected glossary | index.db + knowledge.db + consolidated + registries | `gold/corpus-manifest.json`, `discovery.json`, `contract-manifest.json`, `ai-manifest.json`, `corpus-card.md`, `_shared/boilerplate/*.md`, `glossary.md` | Deterministic JSON (sorted keys, content-skip) | ok: 615 catalog docs, 89 boilerplate, 2,380 glossary terms | **Medium** — nothing in the DAG validates these files post-write; the index.db fingerprint streams the main DB file while the live lake sits in WAL mode (`index.db-wal` present) so it can hash a stale view | [S15] |

**Serving layer (not DAG stages, graded for the same goals):**

| Surface | Logic | Measure of accuracy | Credibility | FN |
|---|---|---|---|---|
| `vdocs ask` / `server/search.py` | Safe FTS5 MATCH (quoted tokens, OR-joined), field-weighted BM25 (doc_title 2.5 / title 2.0 / path 1.5 / body 1.0), SKL number→name expansion | Golden-set nDCG sweeps recorded in code comments | **Medium** — empty result prints "no matches in the gold corpus." with **none** of the MCP not-indexed warnings | [S16] |
| `vdocs serve-mcp` / `server/mcp.py` | JSON-RPC stdio; tools search/lookup/query/orientation; measured 26.7% rule stated on every surface; `has_indexed_text` answered by probing `chunks`, not trusting `kind` | The NOT_INDEXED_RULE contract; read-only SQL | **High honesty, incomplete capability** — it tells the client to read `body.md` + `tables/*.csv` but cannot serve those bytes itself (see §7) | [S17] |
| `doctor` / `release` / `entity-quality` | 19 soundness checks (coverage floors, anchor integrity, gate fidelity, latest-only FTS, vocab closure, read-contract verbatim); release adds quiescence, clean-tree, floors, bundle+sums | GREEN/RED verdict; exit 1 on RED | **High** — the strongest independent gate in the system, but *advisory* (not in the DAG; `build` runs it, `run` does not) | [S18] |

## 4. Per-stage audit notes (the footnotes)

[S1]: **crawl — gaps.** (a) A non-200 index page yields `sections=[]` and the stage still
writes `catalog.raw.json` — overwriting the previous crawl's bronze evidence with an empty
catalog (`stages/crawl/stage.py:61-64`); downstream the serve-inventory gate then fails on
"empty", but the good bronze is already gone (atomic-write protects against partial writes, not
against *complete-but-wrong* ones). (b) Skipped sections/apps (non-200) only WARN; the
document count the 1:1 gate later checks is the count of what the crawl *did* see — a
self-consistency gate that cannot see omission. (c) Parsing is heuristic: first date-like cell
wins (`crawl_pure.py:130`), format-label vs title guessing, and a header-less
broad-link fallback that loses type/date. **Improvements:** a crawl deep_gate with a floor vs
the prior catalog (e.g. document count ≥ 90% of last run, per-section non-zero), refuse to
overwrite bronze on an empty/shrunken result without `--force`, and persist per-page HTTP
outcomes as a computable sidecar (`crawl-report.json`) rather than log lines.

[S2]: **catalog — gaps.** Pure and reproducible (High determinism), but *accuracy* is
registry-trust: doc-type patterns are ordered regexes with filename-suffix fallback; pass-3
infers a missing doc_code only when all typed group peers agree; `doc_labelling` records
manual-vs-code provenance (good). There is no measured classification accuracy (no labeled
sample, no confusion count). **Improvement:** a small curated golden set of (title →
doc_code) with a drift check, so a registry edit that regresses classification is caught the
way search quality is (golden nDCG).

[S3]: **serve-inventory — gaps.** The gate's strongest check (1:1 with crawl) silently
degrades: `crawl_documents` is `None` when the crawl record is absent (wiped `state.db` + the
F4 trust path), and `evaluate_gate` skips the check entirely (`serve_pure.py:43`). Noise
classes and required fields are genuinely hard-gated (good). `system_type="unclassified"`
passes as a soft signal. **Improvement:** when the crawl record is missing, fall back to
comparing against the *persisted* `catalog.raw.json` row count instead of skipping.

[S4]: **fetch — gaps (one measured).** (a) **Measured on the live lake:** `raw/index.json`
is keyed by content sha; 1,040 fetched acquisitions → 1,034 index entries. Six doc_ids
(`CPRS:cprsguitm_0_636`, `PSJ:psj_5_{nurse,supr}_um`, `PSJ:psj_5_tm`, `PSN:psn_4_{um,tm}`)
share bytes with a sibling and were silently collapsed — last writer's provenance wins, the
loser gets no bundle, yet `inventory --status` reports it `fetched`. These six happen to be
duplicate listings of the same manual, but the mechanism is content-blind and would equally
eat a genuinely distinct doc republished byte-identically under a new identity. (b) No
content validation: `get_bytes` returns any 2xx body; a WAF/error HTML page becomes
`<sha>.docx` in the write-once CAS and fails later in convert as an isolated per-doc error —
the corpus is then quietly one document smaller. (c) The index merge is add/refresh-only
(R1): withdrawn or renamed documents are never removed, so `convert`'s `kept` set never
shrinks and the documented ghost-bundle pruning cannot actually fire outside `build --fresh`;
a re-fetched changed document leaves both shas in the index, converting the same bundle twice
per run with dict-insertion order deciding the winner. **Improvements:** key the index by
`doc_id` with sha as a value (one entry per logical doc, dedup preserved via CAS); magic-byte
check (`PK\x03\x04` for DOCX) before `store.put`; reconcile the index against the current
gate-admitted target set each run (drop rows whose doc_id vanished, with a report line).

[S5]: **convert — gaps.** No output floor: `pandoc` returning near-empty markdown (corrupt
DOCX, image-only scan) still writes the bundle; nothing measures converted words vs source
document size. Image join is by basename — safe per Pandoc's per-doc `image1.png…` naming, but
an incidental invariant, not a checked one. Docling routing is a curated allowlist of 1;
`bare-marker explosion` docs outside the list are silently Pandoc-shredded. **Improvements:**
per-doc conversion record (`convert.yaml`: source sha, converter, markdown bytes, image count,
non-empty floor) — the same typed-capture discipline normalize already has; it would also give
`raw → converted` retention, which today has no measure at all (normalize's retention starts
at *enriched*).

[S6]: **discover — gaps.** None structural (proposals only). The curation loop itself is
un-instrumented: nothing records which proposals were reviewed/adopted, so registry provenance
is git history only.

[S7]: **enrich — gaps.** `missing_record` bundles (converted docs with no inventory row) are
skipped with a WARN and vanish from `doc_meta_staged` — downstream `index` will still index the
*normalized* bundle if normalize processed it, deriving `doc_id` from a fallback
(`index/stage.py:211-213`), so a join failure produces a half-identified document rather than a
loud stop. Live count is 0, so this is latent. **Improvement:** gate `missing_record == 0` (or
a floor), since the join keys are supposed to be constructed to always match.

[S8]: **normalize — gaps.** The capture honesty architecture is the best in the pipeline
(typed `capture.yaml` everywhere; residue re-scan deliberately broader than the detectors;
`absent-unexpected` live count 0). Two enforcement holes: (a) **retention verdicts do not
gate** — `score_retention` is computed with `relocated_words=0` (table words already lifted are
not credited, slightly harsh) and the verdict only lands in `flags.yaml`;
`retention_pure.blocks_publish` is referenced **only by its unit test** — 7 live low-retention
docs (incl. any QUARANTINE) flow to gold uninhibited. (b) Phrase subtraction's ≥4-word
prefix rule (`normalize_pure.py:181`) can delete a *content* block that merely opens with a
curated phrase — bounded by the tiny curated list (13 live), but unbounded in principle as the
registry grows. (c) The template F-step is live code but inert data: `templates_stamped: 0`
across 1,034 docs — the `(doc_type, era)` registry has never been populated, so the scaffold
strip + `template_id` provenance the design leans on is not actually exercised.
**Improvements:** wire QUARANTINE into the validate gate (the function already exists);
credit relocated table words in the retention denominator; either populate
`registries/templates` from discover's 35 induced templates or mark the F-step dormant.

[S9]: **consolidate — gaps.** (a) `merge_history` treats member identity (`doc_id`) as the
append key and *never updates a captured member's facts* — if a member's normalized body
changes (registry fix, converter upgrade), the anchor `body.md` is refreshed but that member's
`history.yaml` entry keeps the old `body_sha256`/`revisions` (a lineage record that no longer
matches any retained-body read path for "current"). `bundle.yaml` stays truthful (recomputed
from parts), so validate can't see it; the lie is *internal to* history.yaml. (b) Ordering
falls back to `doc_slug` when patch numbers and dates are absent — "latest" for undated,
unpatched groups is alphabetical, i.e. arbitrary but deterministic. (c) The retained-body CAS
(`_shared/history`) grows monotonically by design (write-once) — fine, but nothing garbage-
collects bodies whose member was pruned upstream. **Improvement:** on merge, when an existing
member's fresh `body_sha256` differs, append a *supersedes* entry (append-only preserved,
truth restored) rather than silently keeping the stale fact.

[S10]: **index — the 27% problem, mechanism confirmed.** `shred_sections` classifies a
section as `container` purely structurally — *the next heading is deeper*
(`index_pure.py:399`) — regardless of how much lead-in prose the section itself carries; and
`chunk_units` only emits units for `searchable` sections (`kind in ("ok","stub")`). Live:
11,526 containers + 2,627 hollow = 14,153 of 52,048 latest sections (27.2%) contribute zero
chunks; in reference manuals the container lead-in (Format, Input Parameters, flag tables) *is*
the contract text. The MCP layer mitigates by disclosure (S17); the *fix* belongs here: *(the
single highest-leverage search-quality improvement in this audit)* emit a chunk for a
container's **own lead-in text** (the lines between its heading and its first child) whenever
that lead-in passes the substantive-token floor — the section row already exists, so this adds
recall with no identity churn. Also note: `doc_meta_staged` is carried forward *verbatim* into
the rebuilt DB (good), and `index --force` after `merge` wipes merge's tables — caught by
doctor's "SKL projections" check but by nothing in the DAG.

[S11]: **resolve — gaps.** Governance is exemplary (propose-don't-assert; closed edge set;
provenance on every node). Coverage is a pilot: hardcoded `PILOT_APP="DI"`, 21 entities vs
4,415 unresolved proposals. The unresolved queue has no curation loop instrumentation (same
gap as [S6]). **Improvement:** the DD seed exists for one package; generalize the seed schema
and drive `PILOT_APP` from a registry list.

[S12]: **validate — scope gaps.** What it covers, it covers well (typed absence, drop
detection with a prior-report baseline, severed-ref floor 0, full bundle hash recomputation).
What it structurally cannot see: (a) anything in `index.db` (chunk/section/FTS consistency,
is_latest discipline) — that lives only in `doctor`, which no `vdocs run` invocation executes;
(b) retention/QUARANTINE flags ([S8]); (c) the fetch-side acquisitions↔raw-index↔bundle join
([S4] — the six collapsed docs raise no finding anywhere); (d) manifest outputs (it runs
before `manifest`). The count-reconciliation baseline is the *prior verification.json* — a
`--fresh` build deletes it (reports/ wiped), so the drop-detection net is absent exactly on
the runs that rebuild everything. **Improvements:** add an inventory-reconciliation check
(gate-admitted targets = acquisitions fetched = raw-index doc_ids = converted bundles =
indexed docs — one COUNT chain, five seams, all currently unjoined); move doctor into the DAG
as a terminal stage or make `run --to manifest` finish with it.

[S13]: **merge — gaps.** Reconciliation joins on `(type, canonical)` string equality; live
result 6/21. The 15 unreconciled SKL entities (and therefore most SKL synonyms/expansions)
silently don't reach the search surface — visible only as a count. **Improvement:** emit the
unreconciled remainder as a computable sidecar (like resolve's proposals) and WARN above a
floor.

[S14]: **relate — gaps.** `XREF_TYPES` is a code constant (violates "discovery is data",
tenet #13 — same class of thing as the gate policies that *did* move to YAML). Co-occurrence
weight = shared-section count with no significance floor; 159,632 cooccur edges on 6,572
entities suggests a dense, low-signal graph nothing currently consumes critically.

[S15]: **manifest — gaps.** (a) `_index_fingerprint` streams `index.db` while the lake runs
WAL (`index.db-wal` was present and non-empty at audit time): un-checkpointed pages make the
AI-card fingerprint potentially stale vs what readers see through SQLite. Checkpoint (or
`VACUUM INTO`) before hashing — `release.strip_staged` sidesteps this for the shipped copy,
the AI card does not. (b) The manifests are written but nothing recomputes/validates them
later (no gate reads them back). (c) `generated_at` makes corpus-manifest.json
non-reproducible byte-wise (deliberate, but note it when diffing runs).

[S16]: **ask CLI — gap.** The MCP server states the not-indexed rule on five surfaces; the
CLI's empty result prints exactly the sentence ("no matches in the gold corpus.") the MCP
docs call a false-negative generator. The Go `vdocs` reader and any script over `--json` (empty
list, no warning field) inherit the same trap. **Improvement:** emit the same warning object
in the CLI/JSON empty path — one shared constant.

[S17]: **serve-mcp — capability gap.** The honesty layer is measured and thorough
(26.7% rule everywhere, `has_indexed_text` probed against `chunks` not guessed from `kind` —
254 chunked containers prove that choice right). But the remedy it prescribes ("read the gold
body.md / tables CSVs") assumes the client shares the lake filesystem; a remote MCP client
cannot follow it. The server holds everything needed to serve those bytes. See §7.

[S18]: **doctor/release — placement gap.** 19 checks, all PASS live, including read-contract
verbatim-view verification and quarantine-cascade residue — but it is invoked only by `build`
and by hand. A pipeline driven via `vdocs run` can end green with a RED-able index.db and no
one asked. (Same finding class as the org's CI-audit F-27: a gate that *works* is not a gate
that is *enforced*.)

## 5. The auditable artifact chain (ledger)

Every arrow is a written, computable artifact — the complete inter-stage data plane. A human
(or a re-implementation test harness) can diff any node; the chain is what makes end-to-end
replay auditable.

| Artifact (lake-relative) | Format | Producer → Consumers | Identity / audit key |
|---|---|---|---|
| `inventory/bronze/catalog.raw.{json,csv}` | Pydantic JSON + CSV | crawl → catalog | crawl counts in `state.db` |
| `inventory/silver/catalog.enriched.{json,csv,schema.json}` | JSON + CSV + field manifest | catalog → serve-inventory, enrich, discover, fetch-CLI | row set 1:1 with raw |
| `inventory/gold/inventory.{json,csv,db}` | JSON + CSV + SQLite | serve-inventory → fetch (+ CLI) | `doc_id = app_code:doc_slug` |
| `state.db:stage_runs` | SQLite | every postflight → every preflight | `(stage, scope)`, fingerprints |
| `state.db:acquisitions` | SQLite | fetch → `inventory --status` | `doc_id`, sha256, attempts |
| `documents/bronze/raw/<sha>.docx` + `raw/index.json` | CAS + JSON | fetch → convert, normalize (sha stamp) | **sha-keyed (see [S4])** |
| `silver/text/01-converted/**/body.md` + `documents/assets/<sha>.<ext>` | Markdown + CAS | convert → enrich, discover | bundle path `<app>/<slug>` |
| `silver/text/02-enriched/**/body.md` | Markdown+FM | enrich → normalize | identity FM keys |
| `index.db:doc_meta_staged` | SQLite | enrich → index | `doc_id` PK |
| `silver/text/03-normalized/**/`: `body.md`, `revisions.yaml`, `tables/*.csv`, `refs.yaml`, `toc.yaml`, `flags.yaml`, `capture.yaml` | MD + YAML + CSV | normalize → consolidate, index, validate, manifest(glossary) | `capture.yaml` present for **every** bundle; `refs.yaml` stable_id = `<doc_key>/<slug>` |
| `gold/consolidated/<app>/<stem>/`: `body.md`, `history.yaml`, `bundle.yaml`, sidecars, `tables/` + `gold/_shared/history/<sha>.md` | MD + YAML + CAS | consolidate → index (is_latest), resolve, validate, serving | `bundle.yaml` = signed part-hash manifest; `anchor_key` |
| `index.db` (documents…meta, v_* views) | SQLite (+FTS5) | index → relate, merge, manifest, search/MCP/doctor | `meta.read_schema_version` + `meta.corpus_content_hash` |
| `gold/knowledge.db` + `knowledge-proposals.json` | SQLite + JSON | resolve → merge, manifest | node_id `type/canonical`; every node `asserted` |
| `reports/validation/verification.json` | JSON | validate → next validate (baseline) + humans | blocking + counts baseline |
| `gold/{corpus,contract,ai}-manifest.json`, `discovery.json`, `corpus-card.md`, `glossary.md`, `_shared/boilerplate/` | JSON/MD | manifest → agents/consumers | contract axes verbatim from `meta` |
| `rich-tables/<app>/<stem>/tables/*.csv` (4,246 live) + `rich-assets/` | CSV / CAS | publish-rich-* CLIs → vdocs-web, MCP fallback path | same `anchor_relpath` derivation as body |

Chain gaps for full auditability (feed §9): the **acquisitions↔raw-index↔bundle↔index count
chain is never joined by any gate** ([S12]); `stage_runs` holds only the last run ([R‑2]);
crawl per-page outcomes are logs, not data ([S1]); the discover→registry curation step is
undocumented in data ([S6]).

## 6. Re-implementation (Go) reference notes

For a faithful port, the **normative** logic is: the contract/fingerprint/skip algorithm of §2;
the pure functions in every `*_pure.py` (these are the spec — they are deliberately I/O-free
and unit-tested first); the kernel identity formulas (`doc_id`, `slug_stem`, `anchor_key`,
`bundle_key`, `github_slug_base` + GitHub `-N` dedup, `anchor_relpath`); the registry schemas
under `registries/`; the SQLite schemas embedded in `index/stage.py`, `state.py`,
`knowledge_db.py`; and the read contract (`contracts/read/v1.json`) whose v_* views are
*generated* from the spec. Stable IDs are the compatibility surface: `doc_id`
(`app:doc_slug`), `doc_key` (`<app>/<slug>` bundle path), `section_id` (`<doc_key>/<slug>`),
`chunk_id` (`section_id[#pN | #table-NN.csv[#pN]]`), `anchor_key` (`app:pkg:code:stem`),
entity ids (`type:canonical` index-side, `type/canonical` SKL-side — yes, both; `merge`
exists to bridge them).

**Incidental behaviors a port must NOT replicate blindly (and should fix):**

1. `raw/index.json` insertion-order tie-breaking (dict order decides which entry wins a bundle)
   and its sha-keying ([S4]) — key by doc_id in the port.
2. Python `re` semantics: the patch/TOC/heading regexes use Python-specific constructs
   (lookbehinds, `re.IGNORECASE` over ASCII classes); Go `regexp` (RE2) has no lookbehind —
   several recognizers (`entities` terms alternation boundaries, `_LOOSE_TOC_ENTRY_RE`)
   need re-expression, and the port needs a **cross-language golden corpus test** (same input
   bundle → byte-identical normalized output) before trusting any of them.
3. BeautifulSoup's lenient HTML parsing and PyYAML's scalar coercions (dates, `y/n`) — port
   against serialized fixtures, not against the libraries' quirks.
4. FTS5 defaults: the `unicode61` tokenizer and bm25 column-weight order are load-bearing
   (`search_pure.FTS_COLUMNS` must match declaration order); a port using bleve/tantivy must
   re-derive weights on the golden query set, not copy the numbers.
5. External converters: Pandoc's GFM emission and `--extract-media` naming (`image1.png…`) are
   an implicit contract; pin converter versions and treat converter output as a fixture
   boundary (the port re-implements *from* converted markdown, not the DOCX parsing).
6. `size:mtime_ns` fingerprints are filesystem-semantics-dependent; a port should go
   content-hash-first (cheap = xxhash) and drop the mtime cache entirely ([R‑1] disappears).
7. `sorted()` on mixed tuples (`corpus_content_hash` sorts `repr(row)` bytes) — define a
   canonical row serialization instead of Python `repr`.

**Porting order that preserves auditability:** kernel (ids/text/markdown/fingerprint/cas) →
orchestrator + contracts → one stage at a time *consuming the Python lake* (each Go stage must
reproduce the Python artifact byte-for-byte or with a documented canonical diff) → serving
layer last. The §5 ledger is the conformance test plan: 16 artifact classes, each a fixture.

## 7. The MCP server & search-accuracy method

The goal: an MCP service over vdocs that **cannot** manufacture a false "not documented",
and that searches the *whole* corpus — body text, container lead-ins, and the CSV sidecars.

**What the code already does right (keep):** the measured NOT_INDEXED_RULE on every client
surface; `has_indexed_text` decided by probing `chunks` (254 containers *do* have chunks —
kind is a predictor, not a fact); zero-hit responses carrying an explicit warning; lookup
misses phrased as statements about the key; read-only SELECT/WITH-only SQL; provenance pins
(corpus_content_hash / doc_count / read_schema_version) in orientation; table CSVs already
re-injected as 5,225 searchable chunks citing their section (B3b) and shipped as the 4,246-file
`rich-tables/` distribution keyed by the *same* `anchor_relpath` derivation as the body path
(so body and tables can never name different bundles).

**The method to make it fully accurate (ordered by leverage):**

1. **Close the 27% at the index, not the prompt** ([S10]): chunk container lead-in prose.
   This converts the disclosure problem into a solved retrieval problem; the MCP warnings then
   describe a residual (true hollow sections) instead of a quarter of the corpus.
2. **Serve the fallback sources over MCP.** Add a `read` tool: `read(kind=body|table,
   key=doc_key|section_id|table path) → the gold body.md slice (by section anchor) or the CSV
   text`, so the "read sources 2 and 3" instruction is executable by a *remote* client — today
   it assumes lake filesystem access ([S17]). The server already computes `body_path` and
   `tables_dir`; it needs only the lake root (it has `index_db.parent`).
3. **Warning parity everywhere** ([S16]): the ask CLI and `--json` consumers must emit the same
   zero-hit warning object as the MCP tool — one constant, three surfaces.
4. **Citation contract:** every answer cites `vdocs://section/<section_id>` + `body_path` +
   the provenance pins; a client that cannot produce a pin is answering from memory, not the
   corpus. (Already the orientation contract — enforce it in the tool descriptions of any new
   tool too.)
5. **Sidecar completeness check:** a doctor check that every in-body
   `_[… (extracted to CSV)](tables/table-NN.csv)_` reference resolves to (a) a CSV in the gold
   bundle, (b) a table chunk in `chunks`, and (c) a file in `rich-tables/` — three
   representations of one fact that currently nothing reconciles.
6. **Search-quality loop:** keep the golden query set (the nDCG@10 sweeps that set
   `doc_title=2.5`) as a *gated* measure — re-run it in `make check` whenever FTS weights,
   expansions (`entity_skl` — currently only 6 rows live, [S13]), or chunking rules change, so
   retrieval quality regressions red a gate instead of a vibe.

## 8. Traceability when the source or formats change

What actually happens, per drift class, as coded:

- **VDL adds/updates a document:** re-crawl (FORCE_ONLY) → catalog re-derives → gold inventory
  fingerprint changes → fetch re-runs (selection + gate fp in `inputs_fp`) → new sha enters
  CAS; downstream stages re-run off tree fingerprints. **Sound**, with two caveats: the
  updated document's *old* sha stays in `raw/index.json` forever ([S4]c) and history.yaml
  facts for re-processed members go stale ([S9]a).
- **VDL withdraws a document:** nothing removes it — raw-index merge is add-only, so `convert`
  keeps regenerating its bundle and it remains in gold until a `--fresh` rebuild. Traceability
  is preserved (nothing lost) but *currency* is not (the corpus silently over-states the live
  library). Needs the reconciliation gate ([S12] improvement).
- **VDL page-format change:** crawl heuristics degrade silently into WARN-skips and a smaller
  catalog; the only tripwire today is the human noticing counts. The §9 R‑4 mitigation (floor
  vs prior crawl) is the fix.
- **DOCX-format/converter change:** pandoc version is unpinned system state; a pandoc upgrade
  changes converted markdown corpus-wide, tree fingerprints trip, everything re-runs — but
  nothing *records* the converter version per bundle (only `tool_ver` of vdocs itself). Add
  converter identity to the proposed `convert.yaml` ([S5]).
- **Registry change:** first-class and well-handled — registries are a fingerprinted
  `requires` contract; edits re-run consumers. One hole: row-count SQLite fingerprints can
  mask a metadata-only change from `index` ([R‑1]).
- **Schema change:** `contract_ver` bumps + read-contract semver + doctor's verbatim-view
  check + contract-manifest.json — the strongest drift discipline in the project.

## 9. Risks & mitigations register

Ordered by (impact × likelihood). "Live evidence" = observed on the 2026‑08‑01 lake.

| ID | Risk | Where | Live evidence | Impact | Mitigation |
|----|------|-------|---------------|--------|------------|
| R‑1 | Row-count SQLite fingerprints let content-only changes skip consumers (stale index metadata) | §2, fingerprint.py | latent | Wrong published metadata that no gate reds | Content-hash cheap fingerprints (xxhash) or fold a `max(rowid), sum-of-hash` digest; interim: document `--verify` as the post-registry-edit norm |
| R‑2 | Six documents measurably collapsed out of `raw/index.json` (sha-keyed, last-writer-wins); mechanism content-blind | fetch, [S4] | **1,040 fetched vs 1,034 entries; 6 doc_id pairs listed** | Silent corpus omission + provenance loss; `inventory --status` claims fetched | Re-key index by `doc_id`; add validate check: fetched doc_ids ⊆ raw-index doc_ids ⊆ bundles |
| R‑3 | No gate joins the acquisition→bundle→index count chain; each seam self-reports | validate scope, [S12] | the R‑2 six raised zero findings anywhere | An entire silent-loss *class*, not one bug | One reconciliation check across the five counts (gate-admitted = fetched = indexed-raw = converted = indexed docs), in `validate` |
| R‑4 | Crawl has no completeness floor; a degraded VDL page yields a quietly smaller blessed world; empty crawl overwrites bronze | crawl, [S1] | 0 skipped this run (healthy) | Losing whole sections of the library invisibly | Crawl deep_gate vs prior catalog (≥90% floor, per-section non-zero); refuse shrunken overwrite without force |
| R‑5 | Retention verdicts don't gate; `blocks_publish` is dead code; QUARANTINE docs ship | normalize, [S8] | 7 low-retention docs in gold | Over-stripped documents presented as gold | Wire QUARANTINE (and un-signed-off REVIEW) into `validate`; credit relocated table words |
| R‑6 | Doctor (the only index.db gate) is advisory — `vdocs run` never executes it | [S18] | doctor GREEN, but only because it was run by hand/build | A RED-able corpus can sit under a green pipeline | Make doctor a terminal DAG stage (or auto-append to any run reaching `manifest`) |
| R‑7 | 27.2% of live sections unsearchable by construction (container lead-ins + hollow) | index, [S10] | 14,153 / 52,048 sections chunk-less | Systematic false negatives; mitigated today only by prompt discipline | Chunk container lead-in text passing the substantive floor (highest-leverage fix in this audit) |
| R‑8 | Fetched bytes never validated (no magic check) — an HTML error page enters the write-once CAS as `.docx` | fetch, [S4]b | latent (0 convert errors live) | Doc silently missing; CAS pollution is permanent | `PK\x03\x04` magic check before `put`; record a typed `bad_content` acquisition status |
| R‑9 | `history.yaml` append-only merge never refreshes changed member facts (stale `body_sha256`) | consolidate, [S9] | latent (no member reprocessed since capture) | The lineage record — the replay source — lies about current bodies | Supersedes-entry pattern on sha change; validate check: latest member's recorded sha == sha(body.md) |
| R‑10 | Withdrawn/renamed VDL docs are never removed (add-only raw index) → stale gold + double-convert of re-fetched docs | fetch/convert, [S4]c, §8 | latent | Corpus over-statement; wasted work; order-dependent winner | Reconcile raw index against current admitted targets each run |
| R‑11 | CLI `ask` empty result asserts "no matches in the gold corpus" — the exact false-negative the MCP layer documents against | [S16] | code-confirmed | Agents/scripts on the CLI/JSON path inherit the trap | Emit the shared NOT_INDEXED warning on all three surfaces |
| R‑12 | SKL reach: 6/21 entities reconciled, expansions nearly empty; 4,415 unresolved proposals uncurated | merge/resolve, [S11][S13] | counts live | The semantic layer's promised search lift mostly isn't happening | Unreconciled-remainder sidecar + floor WARN; curation-loop instrumentation; generalize past DI |
| R‑13 | AI-card fingerprint hashes `index.db` main file under WAL — may not reflect reader-visible state | manifest, [S15] | `index.db-wal` present at audit | Staleness detector that can itself be stale | `PRAGMA wal_checkpoint(TRUNCATE)` (or `VACUUM INTO`) before hashing |
| R‑14 | `--fresh` wipes `reports/`, deleting the validate drop-detection baseline exactly when everything is rebuilt | validate, [S12] | code-confirmed | The cross-run net is absent on de-novo builds | Exempt `reports/validation/` from the wipe (it is evidence, not derived state — same argument that spared `catalog.raw.json`) |
| R‑15 | Per-doc error budget of 50% is generous and unconsumed downstream; `stage_runs` keeps only the last run | §2, [R‑2] | 0 errors live | A degrading corpus can trend toward 50% invisibly | Tighten to ~5% for convert/normalize; append-only `stage_run_history` table |
| R‑16 | Heuristic-classification accuracy (crawl parse, doc-type, entity extraction) has no measured baseline outside search nDCG | catalog/index, [S2] | n/a | Registry edits can regress classification silently | Small labeled golden sets with drift checks in `make check`, mirroring the search golden set |

---

*Method note: all live numbers were read from `~/data/vdocs` (`index.db`, `state.db`,
`raw/index.json`) read-only on 2026‑08‑01 with no pipeline process active; the code citations
refer to the working tree at the audit commit. Corrections to this audit should land as
edits here with a dated note, and any fix that lands should strike its register row with the
commit hash.*
