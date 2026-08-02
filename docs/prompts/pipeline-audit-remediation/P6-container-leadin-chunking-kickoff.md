# Kickoff — P6: container lead-in chunking (the 27% stops being unsearchable)

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

**Golden retrieval baseline: nDCG@10 = 0.5134** (MRR 0.6067, recall@10 0.6140, redundancy@10 0.04,
19 labeled of 20 queries). That is **up from the audit's 0.469** — SKL work landed in between, so
re-measure rather than comparing to the audit's number. Reproduce it exactly with:

```bash
.venv/bin/python scripts/baseline_golden.py --k 10 --out reports/<name>.md
```

Run it **before** you change anything (confirm you reproduce 0.5134 on today's lake) and again
after P6.1. "Must not regress" is against *your* pre-run, not against a number in a document.

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
- Golden nDCG@10 **≥ your pre-run** (reproduce 0.5134 first, then re-run after P6.1). A regression
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
