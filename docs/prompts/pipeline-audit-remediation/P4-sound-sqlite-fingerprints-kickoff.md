# Kickoff — P4: sound SQLite fingerprints (the skip decision stops lying)

**Repo: `vdocs`.** Fresh session, `cd ~/projects/vdocs`. Read `CLAUDE.md`, then
`docs/proposals/pipeline-audit-remediation-implementation-plan.md` **§P4**, and audit register row
R‑1 + §2 in `docs/reference/pipeline-adversarial-audit.md`. Tick
`docs/proposals/pipeline-audit-remediation-tracker.md` per landed step. **Shared-lake rule:**
`pgrep -af "vdocs run"` before any command touching `~/data/vdocs`.

## Where we are

**P1, P2 and P3 are complete.** P1 fixed the acquisition chain and gated it. P2 (`74b136b`) made
`doctor` the DAG's terminal stage, so a `vdocs run` ends on the soundness verdict and RED fails the
run. P3 (`b28fbf5`, `f81dcb2`) made the content-retention verdict a typed record and wired it into
`validate` as Step 6 — QUARANTINE blocks, REVIEW needs a curated sign-off, an unscored bundle
blocks.

Live lake after the P3 acceptance run (**this is your baseline**):

| | |
|---|---|
| documents / gold anchors | **1,040 / 615** |
| `validate` | GREEN — chain 0, reconcile 0, **retention 0**, severed 0, bundle 0 |
| `doctor` (16/16) | **GREEN**, 19 pass / 0 by-design / 0 warn / 0 fail |
| low-retention docs | **3** (was 7), none of them a gold anchor — no sign-offs were needed |

## The problem — and it already bit us

The cheap SQLite fingerprint is **`rows:<count>`**. A content-only change with a stable row count is
invisible to it, so a consumer's `SKIP_IF_UNCHANGED` preflight decides "nothing changed" over a
table whose every cell may have changed.

**This is not hypothetical — it fired during P3's acceptance run, unprovoked.** The
`normalize contract_ver=2` cascade re-ran `index`, which rebuilt its tables with *identical row
counts*. `merge`'s input fingerprints were therefore unchanged, `merge` SKIPPED, and its
`entity_skl` projection stayed the empty shell `index` had just recreated — the exact
"`index --force` after `merge`" wipe the doctor SKL-projections check exists for. `doctor` went RED
and the run exited non-zero; `vdocs run --from merge --force` repaired it.

Read that twice, because it sets your acceptance bar: **the defect is upstream of a gate that
already catches its consequence.** P4 is what stops the wipe happening, not what detects it.

## Measured inputs (2026-08-01 — don't re-derive these, verify them if you want)

The plan hedges that the hashing cost is "bounded … if preflight latency ever matters, memoize".
It doesn't matter. Measured on this box, over the live lake:

| contracted table | rows | strong hash |
|---|---|---|
| `index.db:relations` | 203,272 | **0.33 s** |
| `index.db:doc_sections` | 83,745 | 0.29 s |
| `index.db:chunks` | 48,769 | 0.41 s |
| `inventory/gold.db` | 8,907 | 0.09 s |
| the other 9 contracted tables | ≤ 6,567 | ≤ 0.01 s each |

**≈ 1.1 s to strong-hash every contracted table in the lake.** Ship P4.1 without the memoization
escape hatch; if you add one anyway, say why in the tracker.

**Migration scope: 13 of 31** recorded `outputs_fp` are still `rows:N` — i.e. *every* SQLite
producer: `serve-inventory` (`inventory/gold.db`), `enrich` (`doc_meta_staged`), `index`
(documents, doc_sections, chunks, entities), `resolve` (all three `knowledge.db` tables), `merge`
(entity_skl, entity_synonyms, chunk_entities), `relate` (relations).

## Goal — two landed steps, commit subjects `P4.1:` / `P4.2:`

### P4.1 — content-hash unconditionally

`kernel/fingerprint.py: sqlite_fingerprint` drops the row-count path: always the canonical content
hash (the existing strong path — typed-cell encoding, NULL ≠ `''`, sorted rows, already
order-independent). `--verify` keeps its meaning for files and trees.
*Tests first:* a same-row-count cell mutation changes the fingerprint; row **order** does not; NULL
and `''` do not collide.

### P4.2 — migrate the recorded `rows:N` fingerprints

Old recorded values mismatch the new format, which a consumer's preflight reads as **upstream
drift → FAIL** — 13 of them, on the first run after P4.1. Handle it in code, not operator lore:
treat a recorded fingerprint matching `^rows:\d+$` as *format-migrated* (log it, accept once,
re-record in the new format), never as drift.
*Tests first:* a legacy recorded value + an unchanged table → accept + re-record, no FAIL; a legacy
value + a genuinely changed table → still a real drift FAIL. **Do not** let the migration swallow
a real change; that would trade a false alarm for a silent one.

## Acceptance — the P4 ✓ row

- `make check` green.
- **The live regression, reproduced and then fixed:** mutate one cell of a contracted table on a
  **scratch lake** (`DATA_DIR` override — never the live one) without changing the row count, and
  show the consumer stage re-running where it previously skipped. A permanent test for this is
  worth more than the demo (the P1.2/P3.3 precedent).
- Live lake: a full `vdocs run` after P4.1+P4.2 with **no spurious drift FAILs** (the 13 legacy
  fingerprints migrate silently and are re-recorded), ending GREEN at `doctor`.
- **Check whether P4 obviates the P3 repair sequence:** re-run the `normalize contract_ver`
  cascade scenario and confirm `merge` now re-runs on its own instead of needing `--force`. If it
  does, say so in the tracker — that is the finding that closes R‑1, not the unit test.
- Tick P4.1–P4.2 + P4 ✓, then **write `P5-history-lineage-truth-kickoff.md`** (plan §P5 — it needs
  P5's live inputs: how many version groups carry more than one member, and whether any
  `history.yaml` latest-member `body_sha256` already disagrees with its `body.md`), update the
  prompts README, retire this prompt to `docs/prompts/historical/`.

## Increment protocol

Commit + push per step with the trailer; update `docs/vdocs-design.md` in the same commit if the
fingerprint contract's description changes (§7.3 skip decision). If the code contradicts this
prompt, **the plan is the bug report** — reconcile the plan first. P3 is the cautionary tale: its
plan step named the wrong sink *and* the wrong direction, and only measuring first caught it.
