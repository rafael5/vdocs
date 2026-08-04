# 2026-08-03 (evening) — report-card lands whole; the ruler is now honest

One session, three commits, `RC ✓`. The report-card effort repaired the **answer key** — search
was not touched, by design — and turned key rot from a footnote into a red gate.

## What landed

- **RC.1** (`c0a3931`): the operator's scope rulings (both "keep excluded") executed — six
  scope-rotted queries retired into the key's `retired:` block with reasons, six replacements
  authored on admitted manuals, every label existence-gated against production (present,
  is_latest, searchable, **non-zero chunk text**) before being written. The confirmation step
  corrected R‑19: `XU/kdc1_0ig` is doctype-omitted (IG, Tier B), not system_type-excluded. The
  sweep also found the same artefact inside an answerable query — `kids-install-build` carried
  two structurally-unretrievable XOBW labels.
- **RC.2** (`0b5fecf`): top-10 of all 24 queries read (~50 passages); 34 labels added, 2
  downgraded, every change with its reason. Both kickoff suspicions resolved, one each way:
  `kids-install-build` WAS a key defect (and its two *original* labels were about installing
  Kernel itself — title-assigned, wrong when read); `fileman-add-field` was NOT (the ScreenMan
  tutorial places fields on forms, not the DD — its zero belongs to search).
- **RC.3** (this commit): TDD'd `gate_exit_code` — the harness exits 1 with "GOLDEN KEY: RED"
  when any labelled query is unscoreable, after writing the full report. Hand-staled fixture
  reds; live lake passes exit 0.

## The numbers

Published corrected baseline (`reports/rc-final-baseline.*`): **nDCG@10 0.6386 · MRR 0.7535 ·
recall@10 0.7134** — 24 labelled, 109 labels, 0 unscoreable, hash `726d22a4…` / 57,895 chunks.
The 0.5305→0.6386 move is *mislabelling reclaimed, not search improved*: rankings were identical
throughout; three queries even dipped microscopically because honest new labels raise the IDCG
denominator. Post-CI hash `726d22a4…` ≠ pre-RC `6dbec1f5…` is metadata-only (CI.3 lifecycle
labels): verified **0 per-query drift** on untouched queries before comparing anything.

## Attribution handed to response-ranking (now unblocked)

1 zero (`fileman-add-field`, lexical trap; real answers below rank 10) + 2 low
(`vbecs-accept-order` 0.05 — the Q2.3 container/leaf twins; `vista-signon-credentials` 0.17 —
vocabulary gap). **All search-owned; zero key-owned.** RR-kickoff rewritten with the post-RC
position table: 69.7% of judged answers visible @10, near band (11–100) 16.5%.

## Durable lessons

- **A title is a hypothesis** — bidirectionally. Reading refuted one suspected key defect
  (`fileman-add-field`) and confirmed another nobody suspected (`kids-install-build`'s original
  grade-3 was title-assigned and wrong).
- **An existence-gate needs a text check, not just a row check**: `HL7/hl71_6p56_p66/link-setup`
  exists, is latest, is "searchable" — and has zero chunk text. A label on it would have
  recreated the defect the effort removed.
- **Repairing the ruler changes the reading, so re-derive every number that used it** — the RR
  sizing table shrank from "23.5% unseen" to 16.5% because RC.2 credited answers search was
  already returning.
