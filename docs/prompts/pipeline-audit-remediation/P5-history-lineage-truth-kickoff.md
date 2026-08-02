# Kickoff — P5: history lineage truth (the replay source stops misdescribing the bundle)

> **To start the session**, `cd ~/projects/vdocs` and say:
>
> > Read `docs/prompts/pipeline-audit-remediation/P5-history-lineage-truth-kickoff.md` and execute it.
>
> Nothing else is needed — this file is self-contained. It names every document to read
> (`CLAUDE.md`, plan §P5, the tracker, audit [S9]/R‑9) and carries the measured post-P4 baseline,
> so no prior conversation's context is required.
>
> **One caveat to carry in:** the 615/615 figure below was measured by comparing each latest
> member's `body_sha256` against the **gold anchor's** `body.md`, which is the comparison P5.2
> specifies. On the document inspected, that gold body was byte-identical to its silver normalized
> source, so the comparison holds — but confirm which of the two `consolidate` intends to be
> authoritative before hard-wiring the check.

**Repo: `vdocs`.** Fresh session, `cd ~/projects/vdocs`. Read `CLAUDE.md`, then
`docs/proposals/pipeline-audit-remediation-implementation-plan.md` **§P5**, and audit footnote
[S9] + register row R‑9 in `docs/reference/pipeline-adversarial-audit.md`. Tick
`docs/proposals/pipeline-audit-remediation-tracker.md` per landed step. **Shared-lake rule:**
`pgrep -af "vdocs run"` before any command touching `~/data/vdocs`.

## Where we are

**P1–P4 are complete.** P1 fixed and gated the acquisition chain. P2 (`74b136b`) made `doctor` the
DAG's terminal stage. P3 (`b28fbf5`, `f81dcb2`) turned the content-retention verdict into a gate —
and fixed a capture-before-strip violation that was deleting paper TOCs with no record. P4
(`1419d1b`) made SQLite fingerprints content hashes, so a consumer can no longer skip over a table
whose content changed under a stable row count.

Live lake after the P4 acceptance run (**this is your baseline**):

| | |
|---|---|
| documents / gold anchors | **1,040 / 615** |
| `validate` | GREEN — chain 0, reconcile 0, retention 0, severed 0, bundle 0 |
| `doctor` (16/16) | **GREEN**, 19 pass / 0 by-design / 0 warn / 0 fail |
| recorded fingerprints | **113, all content hashes** (0 legacy `rows:N` left) |

## The problem — measured at 100% prevalence

`merge_history` appends only unseen `doc_id`s. A member that is re-processed keeps its **original**
recorded facts (`body_sha256`, `revisions`, `official_date`) while its bundle moves on, so
`history.yaml` — the artifact §6.6 designates as the **replay source** — can describe a body that is
no longer there. Undetectable today: `bundle.yaml` is recomputed from the parts on disk, so the
integrity gate passes happily over a stale lineage.

**Measured on the live lake 2026-08-01 — every single anchor is affected:**

| | |
|---|---|
| gold anchors whose latest-member `body_sha256` ≠ `sha256(body.md)` | **615 of 615** |
| …differing only in frontmatter (a `function_category` profile change via `enrich`) | 531 |
| …differing in the **body** | **84** |
| retained bodies missing from the `_shared/history` CAS | **0** |
| version groups carrying more than one member (the supersede path) | **92** (523 are single-member) |

Read those two rows together, because they set the tone for the phase: **nothing has been lost** —
every retained body is still in the CAS, exactly as §6.6 promises — but **every** lineage record
misdescribes its bundle. This is a truthfulness defect in an audit artifact, not a data-loss one.
Do not let the 615 panic you into a migration script; P5.1 is a code fix and the next
`consolidate` run is the migration.

## Goal — two landed steps, commit subjects `P5.1:` / `P5.2:`

### P5.1 — supersede, don't discard

`consolidate_pure.merge_history`: when a fresh member shares a `doc_id` with a captured entry but
differs in `body_sha256`, **adopt the fresh facts** and push the prior fact-dict onto that entry's
`superseded: [...]` list. Append-only *preserved*: no recorded fact is ever deleted, it is demoted
with its capture intact, and the prior bodies remain in the CAS by construction. Unchanged members
are untouched; an identical re-run stays a no-op (assert that — a lineage record that grows on
every run is its own kind of lie). **consolidate `contract_ver = 4`.**
*Tests first:* changed `body_sha256` → fresh facts adopted + one `superseded` entry carrying the old
ones; unchanged member → byte-identical output; a *third* change → two `superseded` entries in
order, oldest last (or first — pick one, document it, test it).

### P5.2 — the check that keeps it true (validate Step 4 extension)

For every gold bundle: the history member with `is_latest: true` must satisfy
`body_sha256 == sha256(<bundle>/body.md)`, else a blocking `stale-lineage` finding naming the
`doc_id`. This is the gate that would have caught all 615 the moment they drifted.
*Tests first:* a hand-staled `history.yaml` reds; a fresh one passes. Same fixture lesson as
P1.2/P3.3 — seed the broken state **before** blessing the upstream, or you trip the drift preflight
instead of the gate under test.

**Sequencing that matters:** P5.2 reds 615/615 until P5.1 has re-run `consolidate`. Land P5.1,
re-run, confirm zero, *then* land P5.2 — and say in the tracker that you verified the zero rather
than assuming the re-run fixed it. (P3's lesson: a zero-finding gate is a claim about coverage
until you count positively. Here the positive count is 615 anchors each carrying a latest member
whose sha matches.)

## Acceptance — the P5 ✓ row

- `make check` green.
- Live lake: `consolidate` re-run under `contract_ver=4` → **0 of 615** stale latest members
  (re-measure with the same comparison this prompt used, and record the number); `vdocs run` GREEN
  through `doctor`.
- Spot-check one of the **92** multi-member groups and confirm its `superseded:` list carries the
  prior facts rather than having replaced them — the whole point is that nothing is discarded.
- A hand-staled `history.yaml` reds `validate` as a permanent test, not a one-off demo.
- Tick P5.1–P5.2 + P5 ✓, then **write `P6-container-leadin-chunking-kickoff.md`** (plan §P6 — the
  largest behavioural change in the programme; it needs P6's live inputs: the current chunk-less
  share of latest sections, which was 27.2% of 52,048 at audit time and has moved since P3 changed
  what normalize keeps, plus the current golden nDCG@10 baseline, 0.469 at audit time), update the
  prompts README, retire this prompt to `docs/prompts/historical/`.

## Increment protocol

Commit + push per step with the trailer; update `docs/vdocs-design.md` in the same commit (§6.6's
`history.yaml` description gains `superseded`; §8's `validate` row gains the Step-4 extension). If
the code contradicts this prompt, **the plan is the bug report** — reconcile the plan first. Two
phases running have now hit that: P3's plan step named the wrong sink *and* the wrong direction,
and P4's "accept once" migration would have been permanent leniency as literally specified. Measure
before you implement.
