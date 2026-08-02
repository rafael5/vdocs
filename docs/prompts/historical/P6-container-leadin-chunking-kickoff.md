# Kickoff — P6: container lead-in chunking (the 27% stops being unsearchable)

> ## ⚠️ STATUS 2026-08-02 — most of P6 already landed, out of phase order
>
> The operator read the measurements below and asked for **P6.1b immediately**. It landed as
> `e374d9a`, and because it is a single predicate it **subsumed P6.1**; **P6.2 rode with it** (the
> numbers only exist after the rebuild, and a stale coverage rule actively misleads). Live now:
> chunk-less **26.70% → 10.49%**, `vdocs run` GREEN 16/16, `make check` green at 1,204 tests.
>
> **P6.3** (`d984f8a`) and **P6.4** also landed. So does anything remain? Only the P6 ✓ demo — a
> container-lead-in query answered from `search` where it previously needed the body.md fallback —
> and then P7.
>
> **Read this before trusting any retrieval number below or in the tracker.** The first golden
> measurement of P6.1b reported "unchanged at 0.5134, 0 of 20 queries moved", and I wrote that up as
> the golden set being *blind to the class*. It was not: `scripts/baseline_golden.py` defaulted to
> **`~/data/vdocs-dev`**, a stale 451-document lake that P6.1b never touched, and its printed rollup
> named no corpus — so three measurements in a row answered a question about the wrong lake and
> looked consistent doing it. Corrected on production: the five new P6.4 queries average **nDCG@10
> 0.751**, two of them scoring a perfect 1.000 against a single judged section that had **zero
> chunks** before P6.1b (so they were exactly 0.000 before, by construction). The harness now
> defaults to `Settings().data_dir`, refuses a missing index.db, and stamps
> `index_db`/`documents`/`chunks`/`corpus_content_hash` into every rollup. **Every pre-2026-08-02
> golden number in this repo — the audit's 0.469 included — is a dev-lake number.**
>
> Everything below is preserved as the **measured record** that drove the change — the
> decomposition, the residual analysis, and the `< 8%` argument. Read it as evidence, not as a
> to-do list; the tracker rows carry what actually landed.

> **To start the session**, `cd ~/projects/vdocs` and say:
>
> > Read `docs/prompts/pipeline-audit-remediation/P6-container-leadin-chunking-kickoff.md` and execute it.
>
> Nothing else is needed — this file is self-contained. It names every document to read
> (`CLAUDE.md`, plan §P6, the tracker, audit [S10]/R‑7/R‑11) and carries the measured post-P5
> baseline, so no prior conversation's context is required.
>
> **Two caveats to carry in**, both measured 2026-08-01 and both changing what you should expect:
> (1) the plan's **`< 8%` target is not reachable by P6.1 as specified** — the residual is ~14%; see
> "What P6.1 will actually buy" below and settle the target before you build. (2) `index` re-running
> can leave `merge` skipped and `doctor` RED — the repair is one command, and it is *not* a defect
> you introduced; see "The trap in your acceptance run".

**Repo: `vdocs`.** Fresh session, `cd ~/projects/vdocs`. Read `CLAUDE.md`, then
`docs/proposals/pipeline-audit-remediation-implementation-plan.md` **§P6**, and audit footnote
[S10] + register rows R‑7 / R‑11 in `docs/reference/pipeline-adversarial-audit.md`. Tick
`docs/proposals/pipeline-audit-remediation-tracker.md` per landed step. **Shared-lake rule:**
`pgrep -af "vdocs run"` before any command touching `~/data/vdocs`.

## Where we are

**P1–P5 are complete.** P1 fixed and gated the acquisition chain. P2 (`74b136b`) made `doctor` the
DAG's terminal stage. P3 (`b28fbf5`, `f81dcb2`) turned the content-retention verdict into a gate.
P4 (`1419d1b`) made SQLite fingerprints content hashes. P5 (`75d12e6`, `30351e9`) made
`history.yaml` supersede a re-processed member's stale facts instead of discarding them, and added
the `validate` Step‑4 check that keeps the lineage true — it went from 615 of 615 anchors
misdescribing their own body to **0 of 615**.

Live lake after the P5 acceptance run (**this is your baseline**):

| | |
|---|---|
| documents / gold anchors | **1,040 / 615** |
| `validate` | GREEN — chain 0, reconcile 0, retention 0, severed 0, **bundle 0 (incl. lineage)** |
| `doctor` (16/16) | **GREEN**, 19 pass / 0 by-design / 0 warn / 0 fail |
| `vdocs run` | GREEN end-to-end, steady state (everything skips on a second run) |

## The live inputs P6 needs — measured 2026-08-01, post-P5

**Chunk-less share.** Two measures; know which one you are quoting, because the shipped constants
use the second.

| measure | count | share |
|---|---|---|
| kind-based: latest sections of kind `container` or `hollow` | 11,543 + 2,627 = **14,170** of 52,128 | **27.18%** |
| empirical: latest sections with **no row in `chunks`** ← *this is what the `26.7%` constants mean* | **13,916** of 52,128 | **26.70%** |

The two differ by the **254 `container` sections that already carry chunks** (table chunks land
under a container's own section id) — the fact `mcp._has_chunks` exists to respect: `kind` is a
predictor, not a fact. Both numbers are within 0.1 pp of the audit's (13,899 / 52,048 / 26.7%): **P3
did not move this**, so don't expect the re-measure to be interesting *before* P6.1.

**Golden retrieval baseline — ⚠️ CORRECTED 2026-08-02.** The `nDCG@10 = 0.5134` originally
recorded here (and the audit's `0.469`) came from **`~/data/vdocs-dev`**, a stale 451-document lake
the harness defaulted to. Both are dev-lake numbers and are **not** comparable to a production run.
On the production lake (1,040 docs) with the P6.4 queries added, the set reads **mean nDCG@10
0.3997** overall — 0.307 over the original 19, **0.751** over the five new ones. The harness now
defaults to `Settings().data_dir`, refuses a missing index.db, and stamps the corpus it read into
every rollup, so this class of error announces itself. Reproduce with:

```bash
.venv/bin/python scripts/baseline_golden.py --k 10 --out reports/<name>.md
```

Run it **before** you change anything and again after — and check the `corpus_content_hash`
in the rollup matches between the two, because "must not regress" is only meaningful against the
same corpus. Compare against *your own* pre-run, never against a number in a document.

## What P6.1 will actually buy — measure before you commit to the target

I ran the **shipped** shredder + token floor (`index_pure.shred_sections` /
`kernel.markdown.substantive_tokens`, `MIN_SUBSTANTIVE_TOKENS = 8`) over all 615 gold bodies. For a
container, `tokens` is *already* exactly its own lead-in — `shred_sections` slices
`lines[idx+1:end]` where `end` is the next heading — so P6.1's predicate can be evaluated today
without writing any code:

| | |
|---|---|
| `container` sections | **11,543** |
| …whose own lead-in clears the 8-token floor (→ would become searchable) | **6,779 (58.7%)** |
| …bare containers (heading, then straight into a child) | 4,764 |
| `hollow` (nothing to index, stays unsearchable by design) | 2,627 |
| **predicted residual chunk-less after P6.1** | **7,391 of 52,100 ≈ 14.2%** |

(52,100 vs the index's 52,128: my re-shred skipped the generated `## Contents`/bookmark-heading
handling and the heading-less-body fallback. A ~0.05% discrepancy, irrelevant to the ratio.)

### What the unsearchable 14,170 actually hold — measured 2026-08-02

Before accepting any residual, I decomposed the whole unsearchable population by **what is in the
section**, and cross-checked each class against `chunks`/`chunks_fts` in the live `index.db`:

| what the section holds | container | hollow | total | verdict |
|---|---|---|---|---|
| ≥8 tokens of its own lead-in prose | 6,779 | — | **6,779** | P6.1 fixes this |
| **1–7 tokens of real prose** (below the floor) | 90 | 1,806 | **1,896** | ⚠️ **dark — see below** |
| a `tables/*.csv` sidecar referent | 24 | 0 | 24 | **already covered** — 24 of 24 carry a table chunk |
| a `_shared/` boilerplate referent | 2 | 0 | 2 | by design (indexed once, canonically) |
| 0 tokens, no referent | 4,648 | 821 | **5,469** | correctly dark — nothing to index |
| | 11,543 | 2,627 | 14,170 | |

**The table-sidecar worry is closed.** A section whose content was lifted to a CSV *does* look
empty to `substantive_tokens` (a referent line contributes zero tokens by design) — but the B3b
table-chunk path in `index/stage.py:294` is `for s in secs:`, **ungated by `searchable`**, so every
extracted table is re-introduced as an FTS chunk citing its section whatever its kind. Measured:
24 of 24 such containers carry a table chunk. This is the mechanism behind the 254 containers that
already have chunks. Don't "fix" it.

**The floor is the real second defect, and it is the same conflation as `container`.** 1,896
sections carry genuine prose that falls under `MIN_SUBSTANTIVE_TOKENS = 8`, so they get **no chunk
— and therefore no `chunks_fts` row at all**, which means neither their text *nor their heading* is
on the search surface. Verified end-to-end on `ACKQ/ackq3_0tm/package-wide-variables` (kind
`hollow`): `chunks`=0, `chunks_fts`=0, and the phrase *"There are no QUASAR package-wide
variables"* returns **0 FTS hits** while sitting in the shipped `body.md`. The same heading in
`LR/lr5_2tm`, `XWB/xwb_1_1_tm_r`, `AMT/am_oramtm` classifies `ok` and is searchable — so the corpus
answers the identical reference question for some packages and silently not for others, decided by
whether the sentence ran to eight words. Real examples now dark: *"There are no QUASAR
package-wide variables."* · *"The Audiogram Module requires no global variables."* ·
`TABLE 0136 - YES/NO INDICATOR` → *"VALUE DESCRIPTION / Y YES / N NO"* (an HL7 table definition) ·
`GETDATA^ACKQAG02` → *"Provides the data for START^ACKQAG02."*

The 8-token floor is an **over-strip detector** — it answers "did `normalize` gut this section?",
where a thin section is legitimately not evidence of damage. Reusing it as a **retrieval** gate says
"under eight words is not worth finding", which is false for exactly the short reference entries a
technical manual is full of. `searchable = kind in ("ok","stub")` is one line making both mistakes
at once.

**Decision to settle at session start (it is a scope change, so put it in §P6 before building):**
add **P6.1b** — separate the retrieval predicate from the QA floor. `kind` keeps the 8-token floor
untouched (over-strip scoring and the nav map are unaffected); `searchable` becomes "has anything
to index at all": `tokens > 0 or has_referent`, for leaves *and* containers. Then:

| | chunk-less share |
|---|---|
| today | 26.70% |
| after P6.1 alone | ~14.2% |
| after P6.1 + P6.1b | **5,495 / 52,128 ≈ 10.5%** — and every section left is genuinely contentless |

Still not `< 8%`, but now the residual is *provably* empty rather than merely assumed to be. Prove
P6.1b on the golden set like P6.1: it adds standalone chunks under their own anchors (not merges,
so the merge-small-leaves precision collapse shouldn't apply) — but the tiny-chunk BM25 dilution
risk is real and is exactly what the nDCG re-run is for. If it regresses, ship P6.1 and record
P6.1b as measured-and-rejected with the number.

**Is the residual real, or an upstream artifact?** Fair question, since `normalize` rewrites heading
levels (`infer_heading_levels`) and a mis-levelled sibling would *manufacture* a container that
never was one. Measured 2026-08-02, and the answer is **real**:

| | |
|---|---|
| containers created by re-leveling alone (enriched body, before vs after `infer_heading_levels`) | **7** across 612 docs (4 created, 3 dissolved) |
| containers created by **all** of normalize (enriched → shipped gold body, aligned by heading title) | **173** created, 481 dissolved |
| …of the 173, the ones that are **bare** (no lead-in, i.e. would still be unsearchable after P6.1) | **72** |

So at most **72 of the 4,764** bare containers (1.5%, ≈0.14 pp of the corpus) are artifacts of our
own processing. Fixing every one of them moves the residual from 14.19% to ~14.05%. The floor is
the documents, not the pipeline — **don't spend P6 on it.**

*(The 7 flips have a real cause worth one line: `infer_heading_levels` counts **empty-titled**
headings — pandoc's rendering of Word bookmark-only heading paragraphs, 1,932 of 85,829 enriched
headings across 320 docs — as genuine ancestors, while `shred_sections`/`parse_headings` discard
them. Re-leveling therefore bakes an invisible heading's hierarchy into the visible ones, and a leaf
can come out a container. Its docstring's "slugs depend on heading text, not level, so the anchor
map is unaffected" is true and beside the point: the **container predicate** depends on level. Two
components disagreeing about what counts as a heading — the same shape as the P6 defect itself. A
footnote for P7's register, not P6 work.)*

**So P6.1 roughly halves the chunk-less share — 27% → ~14% — and does not reach the plan's `< 8%`
target.** The gap is 4,764 bare containers plus 2,627 hollow sections, and neither has lead-in prose
to chunk: for them "unsearchable" is *correct*, not a defect. Decide this explicitly and record it:
either (a) restate the measure of done as the measured residual with the target struck (my
recommendation — the remaining 14% is the honest floor of this mechanism, and the residual
disclosure in the constants is what covers it), or (b) widen the scope, which is a **plan change,
not a step** — write it into §P6 first. What you must not do is ship ~14% against a `< 8%` row and
call it done.

## Goal — three landed steps, commit subjects `P6.1:` / `P6.2:` / `P6.3:`

### P6.1 — searchable containers

A `container` whose **own body** clears the substantive-token floor becomes `searchable=True`; the
`kind` stays `container` (nav-map semantics and `section_path` derivation untouched), and `hollow`
stays unsearchable. In `index_pure.shred_sections` the whole change is the `searchable=` expression
— `tokens` is already in scope and already means the right thing. **index `contract_ver = 15`.**
Confirm `contracts/read/v1.json` documents `searchable` loosely enough to be a column-semantics
change; if it pins it to "kind ∈ {ok, stub}", that is a MINOR bump, and the read-contract lint
(`make check` runs `kernel.read_contract.lint_latest`) is what will tell you.
*Tests first:* a container with a substantive lead-in → chunked under its own anchor; a bare
container (heading straight into a child) → not; hollow → not; `section_path` and the nav rows for
all of them unchanged. Then the golden re-run.

### P6.2 — re-measure and republish the numbers

The `26.7%` / `13,899` / `52,048` / `~73%` rule is hardcoded in **five** places that must move
together — verified present today:

1. `src/vdocs/server/mcp.py:37` — the measured-constant comment
2. `src/vdocs/server/mcp.py:45` `NOT_INDEXED_RULE`
3. `src/vdocs/server/mcp.py:309` + `:355` — orientation + `initialize` instructions (two strings,
   one rule — the audit's R‑11 seam)
4. `src/vdocs/server/mcp.py:180` `_has_chunks` docstring (quotes `254 of the 11,526`)
5. `src/vdocs/stages/manifest/manifest_pure.py:174` — the AI corpus card's reading rule

Re-measure both shares post-P6.1 (the empirical one is the one the constants mean), update all five,
and record before/after in the tracker. **The residual disclosure stays** — the rule is right even
when the number shrinks, and after P6.1 it is *more* important, not less: what remains unsearchable
is genuinely contentless, so an agent that stops reading `body.md` will be wrong less often but in
exactly the same way.

### P6.3 — warning parity on the CLI (audit R‑11)

The `ask` CLI's empty result and its `--json` output emit the same not-indexed warning object as the
MCP `search` tool — one shared constant, three surfaces. Note the constant lives in `server/mcp.py`
today, not `server/search.py` as §P6 says; moving it to the shared module is part of the step.

## The trap in your acceptance run

P6.1 re-runs `index`. When `index` rebuilds with **content-identical** `chunks`/`entities`, `merge`
correctly sees unchanged inputs and SKIPS — but `index` has already recreated `entity_skl` as an
empty shell, so `doctor` goes **RED** on the SKL-projections check. This happened again during P5's
acceptance run, *after* P4 (the tracker's P4 ✓ row claims R‑1 "cannot recur by construction" —
that claim is about content-keyed **inputs** and does not cover a stage's **output** being
destroyed by another stage). The repair is `vdocs run --from merge --force`, and it is recorded in
the P5 ✓ row. Expect it, don't debug it, and don't let it eat your session. Whether the real fix
(merge verifying its own outputs exist, or `index` not owning `entity_skl`) belongs in P7 or a new
register row is a judgement call worth making in the tracker.

## Acceptance — the P6 ✓ row

- `make check` green.
- Golden nDCG@10 **≥ your pre-run** on the SAME `corpus_content_hash`. A regression
  here outweighs the coverage win — the merge-small-leaves experiment is the precedent.
- Live lake: full `vdocs run` GREEN through `doctor`; chunk-less share re-measured and **stated as
  the actual number**, with the `< 8%` row either struck or met.
- A known container-lead-in query — the FileMan "Input Parameters" class the audit cites — returns
  the section from `search` where it previously required the `body.md` fallback. Show the query and
  both results; this is the user-visible point of the whole phase.
- All five constant sites agree with the new measurement (grep for the old numbers and get zero
  hits outside `docs/reference/`, the tracker, and this prompt).
- Tick P6.1–P6.3 + P6 ✓, then **write `P7-close-out-kickoff.md`** (plan §P7 — it needs P7's live
  inputs: the final chunk-less/nDCG numbers, the full list of register rows now strikeable with
  their landing commits, and whether the `merge`/`entity_skl` residual above became a register row
  or a P7 step), update the prompts README, retire this prompt to `docs/prompts/historical/`.

## Increment protocol

Commit + push per step with the trailer; update `docs/vdocs-design.md` in the same commit (§8's
`index` row and the §14.6 `container`/`searchable` semantics both change). If the code contradicts
this prompt, **the plan is the bug report** — reconcile the plan first. Three phases have now hit
that: P3's plan step named the wrong sink *and* the wrong direction, P4's "accept once" migration
would have been permanent leniency as literally specified, and P6's own `< 8%` target is
unreachable by the mechanism §P6 prescribes. Measure before you implement.
