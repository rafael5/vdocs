# Kickoff — P7: close-out (strike the register, republish the numbers, archive the effort)

> **To start the session**, `cd ~/projects/vdocs` and say:
>
> > Read `docs/prompts/pipeline-audit-remediation/P7-close-out-kickoff.md` and execute it.
>
> Nothing else is needed — this file is self-contained. It names every document to read
> (`CLAUDE.md`, plan §P7, the tracker, the audit register) and carries the final measured numbers,
> so no prior conversation's context is required.
>
> **Carry one thing in above all:** ⚠️ **every golden-retrieval number recorded in this repo before
> 2026-08-02 was measured against the wrong lake** — including the audit's `nDCG@10 = 0.469`. See
> "The correction P7 must propagate" below. Do not strike a register row by comparing to one.

**Repo: `vdocs`.** Fresh session, `cd ~/projects/vdocs`. Read `CLAUDE.md`, then
`docs/proposals/pipeline-audit-remediation-implementation-plan.md` **§P7**, the tracker, and
`docs/reference/pipeline-adversarial-audit.md` (the register + the master table). **Shared-lake
rule:** `pgrep -af "vdocs run"` before any command touching `~/data/vdocs`.

## Where we are — P1–P6 are complete

| phase | landed | what closed |
|---|---|---|
| P1 | `6ba05eb` `38190e9` `fa66309` `6668a26` | `raw/index.json` re-keyed by `doc_id`; the acquisition-chain gate; DOCX magic check; a WAL corruption bug found by the live run |
| P2 | `74b136b` | `doctor` is the DAG's terminal stage — the index.db gate stopped being advisory |
| P3 | `b28fbf5` `f81dcb2` | retention verdicts gate; capture-before-strip fix for legacy TOCs |
| P4 | `1419d1b` | SQLite fingerprints are content hashes; the `rows:N` migration |
| P5 | `75d12e6` `30351e9` | `history.yaml` supersedes stale member facts; the `stale-lineage` gate — 615/615 → 0/615 |
| P6 | `e374d9a` `d984f8a` `5fa9a65` | `searchable` split from `kind`; chunk-less **26.70% → 10.49%**; three-surface warning parity; golden queries for the newly-covered class + harness provenance |

Live lake as of 2026-08-02 (**your baseline**): 1,040 documents / 615 gold anchors ·
`corpus_content_hash 6dbec1f5…` · `vdocs run` **GREEN 16/16** at doctor (**20** pass / 0 fail) ·
`validate` GREEN (chain 0, reconcile 0, retention 0, severed 0, bundle 0 incl. lineage) ·
`make check` green at **1,212 tests / 96.25%**.

## The numbers P7 republishes

| metric | audit-time | now |
|---|---|---|
| chunk-less share of live latest sections | 13,899 / 52,048 = 26.7% | **5,469 / 52,128 = 10.49%** |
| …what remains | containers + hollow, indiscriminately | 4,648 bare containers + 821 empty hollow — **provably contentless** |
| gold anchors with a stale lineage record | 615 of 615 | **0 of 615** |
| recorded fingerprints that are content hashes | 18 of 31 | **all** |
| golden nDCG@10, original 19 labeled | *(0.469 — WRONG LAKE, see below)* | **0.3072** on production |
| golden nDCG@10, the 5 P6.4 queries | *(did not exist)* | **0.751** |

## The correction P7 must propagate

`scripts/baseline_golden.py` defaulted to **`~/data/vdocs-dev`** — a stale 451-document lake — and
its printed rollup named no corpus. Three P6 measurements were quoted as evidence about the
production lake while reading that one, and they agreed with each other, which is what made it look
like confirmation. Fixed in `5fa9a65` (default = `Settings().data_dir`; refuse a missing index.db;
`index_db`/`documents`/`chunks`/`corpus_content_hash` stamped into every rollup).

**P7 owes the audit document an annotation**, not a quiet edit: `0.469` in
`pipeline-adversarial-audit.md` is a dev-lake number and is not comparable to anything measured
since. Per the audit's own correction rule, add the note; do not delete the original.

## Goal — four steps, commit subjects `P7.1:` … `P7.4:`

### P7.1 — the full forced end-to-end run
`vdocs run --force` (every stage, not a slice), ending GREEN at `doctor`. This is the acceptance
that no phase's `contract_ver` bump or skip-decision left the lake internally inconsistent.
(The `merge`/`entity_skl` trap that used to make this painful is fixed — see below — so a plain
`vdocs run` afterwards should reach doctor GREEN with no manual repair.)

### P7.2 — strike the register rows, refresh the master table
Rows to strike **with their landing commit**, per the audit's correction rule: R‑1, R‑2, R‑3, R‑5,
R‑6, R‑7, R‑8, R‑9, R‑11, plus the R‑13/R‑14 riders that landed with P2. Refresh the
Status/Credibility cells in the master table that these fixes change. **R‑1 is now strikeable in
full** — cite P4 for the input half and R1.1 for the output half. Consider adding **one new row for
the pattern itself** (see below); a register that only lists fixed instances loses the shape.

### P7.3 — flag the out-of-repo surfaces (do NOT edit silently)
The `vdocs-corpus` skill and the mounted vdocs MCP server instructions still quote the retired
26.7% / ~73% rule. They live outside this repo. Write the operator a short, exact diff-ready note
(old text → new text) and stop there; `.github`-style silent edits to another surface are how the
five in-repo sites drifted apart in the first place.

### P7.4 — archive the effort
`git mv` the plan **and** the tracker to `docs/historical/`, repointing inbound links, per the
docs lifecycle (Tier D: a completed plan/tracker is history). Retire this prompt to
`docs/prompts/historical/` and mark the prompts README complete.

## Both of P6's open items were closed before P7 (2026-08-02) — verify, don't redo

They were listed here as open when this prompt was written; the operator asked for them first.

1. **R‑1's output half is CLOSED** (tracker R1.1). The skip decision now verifies that each of a
   stage's **own** produced artifacts still fingerprints to what its last run recorded; a clobbered
   output yields `PROCEED` naming the artifact, not `SKIP`. Red-proven on a fixture, then live:
   forcing an `index` rebuild empties `entity_skl`, and a plain `vdocs run` re-ran `merge` by itself
   and ended doctor GREEN. `--from merge --force` is no longer needed — **if you see that advice in
   an older note, it is stale.** So R‑1 *can* be struck in P7.2, citing P4 (input half) and this
   (output half). Confirm steady state yourself: two consecutive `vdocs run`s, the second one all
   SKIPPED except `validate`/`doctor`.
2. **The third way is CLOSED too** (tracker R1.2). Output text that lives in *code*
   (`manifest_pure.USAGE` → `CORPUS.md`) moves no input fingerprint, so `manifest` skips and ships a
   stale card. `doctor` now compares the published usage rule to the code that renders it — **20
   checks, not 19**. The pattern is still worth a register row *as a pattern*: three distinct
   mechanisms (weak fingerprint · another stage wiped it · the text is code) all produce "stale
   output, unchanged inputs", and a fourth is likelier than not.

## Acceptance — the P7 ✓ row

- `vdocs run --force` GREEN end-to-end at `doctor`; `make check` green.
- Every struck register row carries its landing commit; the master table agrees with the numbers in
  this prompt; the `0.469` annotation is in place.
- R‑1 struck citing BOTH halves; the stale-output pattern captured as its own row.
- The operator note for the out-of-repo surfaces exists and says exactly what to change.
- Plan + tracker under `docs/historical/`, inbound links repointed, prompts README closed out.
- A session summary in `docs/session-summaries/` — this one closes a seven-phase effort, so write
  the arc, not just the last step.

## Increment protocol

Commit + push per step with the trailer. If the code contradicts this prompt, **the plan is the bug
report** — reconcile the plan first. Four phases have now hit that: P3's step named the wrong sink
*and* direction, P4's "accept once" would have been permanent leniency as specified, P6's `< 8%`
target was unreachable by its own prescribed mechanism, and P6's first retrieval measurement was
taken against a lake the change never touched. **Measure before you implement — and check what your
measurement actually read.**
