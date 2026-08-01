# Kickoff — P3: retention gates (the verdict that fires but never blocks)

**Repo: `vdocs`.** Fresh session, `cd ~/projects/vdocs`. Read `CLAUDE.md`, then
`docs/proposals/pipeline-audit-remediation-implementation-plan.md` **§P3**, and audit footnote
[S8] + register row R‑5 in `docs/reference/pipeline-adversarial-audit.md`. Tick
`docs/proposals/pipeline-audit-remediation-tracker.md` per landed step. **Shared-lake rule:**
`pgrep -af "vdocs run"` before any command touching `~/data/vdocs`.

## Where we are

**P1 and P2 are complete.** P1 (`6ba05eb`, `38190e9`, `fa66309`, `6668a26`) made `raw/index.json`
a derived, `doc_id`-keyed projection, joined the acquisition chain in `validate` Step 5, refused
non-DOCX payloads at the CAS door, and swept the replaced database's stale WAL. P2 (`74b136b`)
made `doctor` the DAG's terminal stage: a `vdocs run` now ends on the soundness gate, RED fails
the run, and the verdict is a computable artifact at `reports/doctor/doctor.json`.

Live lake after the P2 acceptance run (**this is your baseline**):

| | |
|---|---|
| documents | **1,040** |
| gold anchors / version groups | **615** |
| `validate` | GREEN — `chain_findings=0`, `severed_refs=0`, `bundle_findings=0`, `blocking=0` |
| `doctor` (now stage 16/16) | **GREEN**, 19 pass / 0 by-design / 0 warn / 0 fail |
| **low-retention docs** | **7 — unchanged by P1's six restored documents** |

The 7, **re-measured 2026-08-01 on the post-P1 lake** (`normalize` counts `low_retention: 7`;
`flags.yaml` scan agrees). This is your P3.1 input — the exact docs whose scores must move:

| bundle | verdict | retention |
|---|---|---|
| `PRCA/icd_10_um_tp_4_5_281` | **QUARANTINE** | 0.14 |
| `PSD/psd_3_p69_um_supv_cp` | **QUARANTINE** | 0.05 |
| `PSO/pso_7_0_p581_um_42` | REVIEW | 0.53 |
| `PSD/psd_3_p71_tm_cp` | REVIEW | 0.76 |
| `PSJ/psj_5_p254_tm_cp` | REVIEW | 0.76 |
| `PSD/psd_3_p69_tm_cp` | REVIEW | 0.77 |
| `PSS/pss_1_p129_tm_cp` | REVIEW | 0.80 |

Two things that shape the work. **The distribution is bimodal**: five sit just under the 0.8
PASS floor (`pss_1_p129_tm_cp` is *at* 0.80 before rounding — it will flip on the smallest credit),
while two are catastrophic (0.14, 0.05) and will not be rescued by crediting table words. Expect
P3.1 to clear most of the REVIEW band and expose the two QUARANTINEs as the real question.
**Four of the seven are `_cp` "Change Pages" documents** — partial-update docs that are legitimately
mostly tables. That is the R‑5 fairness claim (relocated table words uncredited) showing up in the
data, and it is exactly what P3.1 fixes; do not sign off what the score should have credited.

P2 also carried both riders: **R‑13** (`_index_fingerprint` now checkpoints the WAL before hashing —
it could stamp a stale view) and **R‑14** (`build --fresh` now spares `reports/validation/`, the
cross-run drop baseline). Neither is open.

## The problem P3 fixes

`score_retention` **fires and is then ignored.** Its verdict lands in `flags.yaml` as a string;
`blocks_publish()` — the rule that says QUARANTINE always blocks and REVIEW blocks without
sign-off — is called by **nothing but its own unit test**. A document whose body was 95% deleted
ships into gold, and every gate downstream reports green, because no gate ever asks. This is the
same finding class P2 just closed one instance of: the check exists, passes review, and is wired
to nothing.

## Goal — three landed steps, commit subjects `P3.1:` / `P3.2:` / `P3.3:`

Take them in order; each is independently gate-green and committable.

### P3.1 — credit relocated words (`normalize/stage.py`)

`score_retention` already takes `relocated_words`; `normalize` passes 0. Sum the word counts of
the `tables/*.csv` sidecars the same run extracted and pass them in. Words that moved to a
referent the body still points at were never lost.
*Tests first:* a doc whose table words move out scores PASS where it previously scored REVIEW;
a doc with no tables is unaffected. **Re-measure the 7 on the live lake and record the new
counts in the tracker** — the plan's expectation is that "some flip to PASS", not all.

### P3.2 — record retention in `capture.yaml`

Add a `retention` block (`{retention, verdict, enriched_words, kept_words}`) to
`capture_pure.build_manifest`, so the verdict is a **typed, dense record on every bundle** rather
than a sparse flag string a consumer must parse. **`normalize` `contract_ver = 2`** (sidecar
shape change → downstream re-runs). Note `capture.yaml` travels to the gold anchor bundle at
`consolidate` and is covered by `bundle.yaml`'s signed manifest — the P3.3 gate reads a *verified*
record, which is the point of putting it there rather than beside it.

### P3.3 — gate it in `validate` (Step 6)

`blocks_publish` finally goes live. Any bundle whose `capture.yaml` verdict is **QUARANTINE** →
blocking finding. **REVIEW** blocks unless its `doc_id` is signed off in a new curated
`registries/retention-signoff.yaml` (`signoffs: [{doc_id, reason, date}]`) — the human in the loop
is a registry entry (tenet #13), reviewable in a diff, and already a fingerprinted `validate`
input (P1.2 added the `REGISTRIES` edge, so that note in the plan is already satisfied — verify
rather than re-add).
*Tests first:* QUARANTINE fixture blocks; REVIEW blocks; REVIEW + signoff passes; PASS never
blocks; a signoff for a `doc_id` that is no longer low-retention should not silently rot — decide
whether that is a WARN and say so in the tracker.

**Judgment call this phase forces (do not sidestep it):** for each doc still QUARANTINE after
P3.1, the honest options are *fix `normalize`* (if the strip over-ran — check
`PRCA/icd_10_um_tp_4_5_281` and `PSD/psd_3_p69_um_supv_cp` against their enriched bodies before
anything else), *sign off with a real reason* (the upstream document genuinely is a stub), or
*let it block*. A sign-off written to make the gate green is the failure mode this whole
remediation exists to prevent.

## Acceptance — the P3 ✓ row

- `make check` green.
- Live lake: `vdocs run` (which now ends on `doctor`) GREEN, with every remaining low-retention
  doc either PASS after P3.1, signed off with a stated reason, or genuinely blocked — and the
  final count recorded in the tracker.
- A synthetic over-strip (drop ~60% of a fixture body) reds `validate` — a permanent test, not a
  one-off demo (the P1.2 precedent: four permanent red-path integration tests beat a scratch-lake
  demonstration that cannot rot).
- Tick P3.1–P3.3 + P3 ✓, then **write `P4-sound-sqlite-fingerprints-kickoff.md`** (plan §P4 —
  it needs the live measurement P4 turns on: the largest contracted table's row count and the
  hashing cost on this box, plus how many recorded `outputs_fp` are still in the legacy `rows:N`
  format), update the prompts README, retire this prompt to `docs/prompts/historical/`.

## Increment protocol

Commit + push per step with the trailer; update `docs/vdocs-design.md` in the same commit (§8's
`normalize` row gains the `retention` block in `capture.yaml`; the `validate` row gains Step 6).
If the code contradicts this prompt, **the plan is the bug report** — reconcile the plan first.
