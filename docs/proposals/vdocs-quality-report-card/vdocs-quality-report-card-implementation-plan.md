# vdocs-quality-report-card — implementation plan

Proposal: [`vdocs-quality-report-card.md`](vdocs-quality-report-card.md) ·
Tracker: [`vdocs-quality-report-card-tracker.md`](vdocs-quality-report-card-tracker.md) ·
Prompts: [`prompts/`](prompts/)

🥈 **This effort runs second, after [`vdocs-quality-crawl-integrity`](../vdocs-quality-crawl-integrity/) (`CI ✓`)** — ordering revised 2026-08-03: RC.1's retire/re-point decision depends on the scope ruling. Every later effort is blocked on this tracker's `RC ✓` row.
📏 **Measure before you act:** RC.1 opens by *confirming* the exclusions are real rather than assuming them.

Three steps, commit subjects `RC.1:` / `RC.2:` / `RC.3:`. House rules apply: `make check` green before commit, tick the tracker in the same commit, and every claim of improvement measured on the production collection with a provenance-stamped report.

## RC.1 — Resolve the six unanswerable questions

For each of `kids-delphi-components-install`, `hwsc-rest-from-vista-m`, `hwsc-install-privileges`,
`kaajee-install-procedure`, `lexicon-lookup`, `hwsc-web-service-manager`:

1. Confirm the exclusion is real and deliberate — the application is in the gold inventory but not
   admitted (`system_type` is *Integration middleware* or *Data patch*, not *VistA*). Do not assume;
   re-check, because "the document is missing" and "the document is out of scope" look identical
   from the answer key's side and mean opposite things.
2. **Re-point** if the same information need is answerable from an in-scope manual — search the
   collection for it and grade what you find by reading. **Retire** if it is not, moving the question
   to a `retired:` block in the same file with a one-line reason naming the application and why it is
   out of scope.
3. Neither delete the question nor leave it labelled. A silently deleted question loses the evidence
   that scope changed.

**Measure of done:** the harness reports `unscoreable_queries == 0`.
**Operator decision required:** retiring narrows what the key claims to cover. Surface the
retire/re-point split for sign-off rather than deciding it silently.

## RC.2 — Re-judge the key against the current collection

For every remaining question, read the current top ten and grade what is there.

- Add grade 2/3 for passages that genuinely answer the question but are currently unlabelled. The two
  known cases: `kids-install-build` (search returns `XU/krn_8_0_sm_kids_ug/running-installations` —
  the actual KIDS User Guide — and is scored 0) and `fileman-add-field` (search returns
  `DI/scrn_tut/adding-ssn-field`, a tutorial on adding a field, and is scored 0).
- Record a one-line reason for each new or changed grade. A later reader must be able to disagree
  with the reasoning, not guess at it.
- Leave the deliberate discriminators alone: several questions have near-miss lexical decoys
  unlabelled *on purpose* (e.g. the identically-titled "Package-wide Variables" sections belonging to
  other packages). Do not "fix" those into relevance.

**Measure of done:** every question scoring 0.000 has been checked by reading its top ten and is
annotated as *search's fault* or *the key's fault*. The count of the former is the real input to the
ranking effort.

## RC.3 — Make staleness fail, not score zero

The harness already detects an unanswerable question and excludes it from the means
(`unscoreable_queries`). Turn the report into a gate: the harness exits non-zero when any labelled
question has no answerable target on the collection it just measured.

*Tests first:* a fixture key with one out-of-scope question reds; an all-answerable key passes.
Keep the exclusion behaviour — a failing gate that still reports honest means is more useful than
one that refuses to produce a number.

**Measure of done:** the gate reds on a hand-staled key and passes on the live one.

## Sequencing and dependencies

RC.1 → RC.2 → RC.3, strictly. RC.2's output (how many zeros are genuinely search's fault) is the
input to `vdocs-quality-response-ranking`, which must not start until this lands — tuning ranking
against an unrepaired key would optimise toward measurably worse answers.

## Out of scope

Expanding the key, re-judging below rank ten, and any change to search behaviour. All three would
either contaminate the baseline or invite optimising for positions no user reads.
