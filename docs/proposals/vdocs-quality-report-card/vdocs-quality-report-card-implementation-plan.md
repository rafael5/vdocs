# vdocs-quality-report-card — implementation plan

Proposal: [`vdocs-quality-report-card.md`](vdocs-quality-report-card.md) ·
Tracker: [`vdocs-quality-report-card-tracker.md`](vdocs-quality-report-card-tracker.md) ·
Prompts: [`prompts/`](prompts/)

🥈 **This effort runs second, after [`vdocs-quality-crawl-integrity`](../vdocs-quality-crawl-integrity/) (`CI ✓` — ticked 2026-08-03, `801f48c`)** — ordering revised 2026-08-03: RC.1's retire/re-point decision depended on the scope ruling, which the operator has now made (retire; XOBW/KAAJEE/LEX stay excluded). Every later effort is blocked on this tracker's `RC ✓` row.
📏 **Measure before you act:** RC.1 opens by *confirming* the exclusions are real rather than assuming them.

Three steps, commit subjects `RC.1:` / `RC.2:` / `RC.3:`. House rules apply: `make check` green before commit, tick the tracker in the same commit, and every claim of improvement measured on the production collection with a provenance-stamped report.

## RC.1 — Retire the six unanswerable questions, and author six replacements

> **Operator ruling, 2026-08-03 (the scope input this step waited on):** XOBW, KAAJEE and LEX
> **stay excluded** — the 102 never-acquired documents are not admitted. Therefore all six
> questions **retire**; none is re-pointed at excluded material. Six **different** questions are
> authored to replace them, each gated on documents that actually exist in the fetched corpus.

For each of `kids-delphi-components-install`, `hwsc-rest-from-vista-m`, `hwsc-install-privileges`,
`kaajee-install-procedure`, `lexicon-lookup`, `hwsc-web-service-manager`:

1. Confirm the exclusion is real and deliberate — the application is in the gold inventory but not
   admitted (`system_type` is *Integration middleware* or *Data patch*, not *VistA*). Do not assume;
   re-check, because "the document is missing" and "the document is out of scope" look identical
   from the answer key's side and mean opposite things. This confirmation still runs: the ruling
   decides what to *do* about an exclusion, not whether the exclusion is what we think it is.
2. **Retire** each one into a `retired:` block in the same file with a one-line reason naming the
   application and why it is out of scope. Neither delete the question nor leave it labelled — a
   silently deleted question loses the evidence that scope changed.
3. **Author six replacement questions** so the key keeps its size and topical spread. Each must be
   **existence-gated before it is written down**: every marked answer resolves to a section that is
   present, `ok`, latest and searchable in the production collection — check, do not assume, and
   record the check. Prefer replacements covering the same information needs (installation
   procedure, privileges, client/server call, lookup) from admitted VistA manuals, so the key's
   shape is preserved rather than drifting toward whatever is easy to answer.
4. Grade every replacement by **reading the passage**, never the title — the key already carries one
   title-assigned label that was wrong when read.

**Measure of done:** the harness reports `unscoreable_queries == 0`, the key holds 24 labelled
questions again, and no marked answer in it points outside the fetched corpus.

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

Growing the key beyond its current size, re-judging below rank ten, and any change to search
behaviour. All three would either contaminate the baseline or invite optimising for positions no
user reads. RC.1's six replacements are a **one-for-one swap**, not growth: the key ends the effort
with the same 24 labelled questions it started with.
