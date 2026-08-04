# SL.1 — the three measurements

Measured 2026-08-04 on the production lake (`~/data/vdocs/index.db`, 1,040 documents, 57,895
chunks). Read-only; no pipeline stage ran. Reproduce with:

```bash
.venv/bin/python scripts/sl1_ambiguity.py                          # (a)
PYTHONPATH=scripts .venv/bin/python scripts/sl1_vocab_cost.py      # (b)
.venv/bin/python scripts/sl1_candidate_quality.py                  # (c)
```

Artifacts: `reports/sl1a-ambiguity.{md,json}` · `reports/sl1b-vocab-cost.{md,json}` ·
`reports/sl1c-candidate-quality.{md,json}`.

Ground truth throughout is **`vista-meta`'s measured model** (`export/data-model/files.tsv`,
`code-model/routines.tsv`, `code-model/routine-globals.tsv`) — deliberately not the pilot's 21-file
`registries/entities/dd-seed.di.yaml`, which is the thing under evaluation. Measuring the feature
against its own input would only have shown the input is self-consistent.

---

## (a) The ambiguity is real and widespread — **233 files, 1,932 documents**

| | |
|---|---|
| FileMan files this collection mentions at all | 2,963 |
| …mentioned under two or more surface forms | 362 |
| **…with a true split — documents that name the file and never its number** | **233** |
| file×document pairs reachable by the name but not by the number | **1,932** |
| chunks behind those | 8,564 |

Both sides are anchored the same way. The number form is the production recognizer's `file #N`
match (it refuses a bare number); the name form only counts where the manual marks it as a file
reference (`NEW PERSON … file`, `file … NEW PERSON`, `NEW PERSON (#200)`). Without that anchor the
count is 303 files / 4,998 pairs, but it is inflated by prose: "PARAMETERS" alone matches 7,397
chunks that have nothing to do with file 8989.5. The anchored number is the one to quote.

The largest splits are `200 NEW PERSON` (195 documents), `8989.5 PARAMETERS` (146),
`44 HOSPITAL LOCATION` (88), `3.5 DEVICE` (81), `63 LAB DATA` (40).

**So the premise holds.** This corpus really does name the same thing two ways, at scale. The
feature is aimed at a real target.

## (b) It costs about a third of identifier-shaped questions — **28 of 80** — and the layer as built repairs **3**

80 identifier-shaped questions, stratified: the 40 largest splits plus 40 drawn at random from the
tail (seed 20260804). A question fails *for vocabulary reasons alone* when the number query returns
none of the answering passages at k=10 **and** the name query returns some — same engine, same
index, same k, only the word changed.

| | |
|---|---|
| questions scored | 80 |
| the number query already reaches the answer | 42 (53%) |
| **vocabulary failures** | **28 (35%)** |
| neither query reaches it (not a vocabulary problem) | 10 |
| **failures the synonym layer as built would repair** | **3** |
| failures the layer **cannot express at all** | **24** |
| ceiling — failures repairable by *any* expansion | **23** |
| questions the expansion would damage | 0 |

The gap between 3 and 23 is the finding. Those 24 unexpressable failures are not waiting on
curation — they are dropped by `search_pure.skl_expansion_map`'s own guards, for two reasons that
have nothing to do with the approval queue:

- **Two-digit file numbers** (`60 LABORATORY TEST`, `80 ICD DIAGNOSIS`, `42 WARD LOCATION`,
  `49`, `36`, `56`, `64`, `81`, `15`) are dropped by the `len(key) >= 3` guard, which is also
  enforced independently in `acronym_phrase_clauses`. The guard is defensible — "60" is a common
  token — but it is what is blocking, not curation.
- **Decimal file numbers** (`3.8`, `50.7`, `52.6`, `40.7`, `59.4`, `8925.1`, `409.1`, …) can never
  work: `.isalnum()` rejects the key, and even if it did not, FTS5 tokenises `50.7` into `50` and
  `7`, so a single-token key can never match it. That is structural, not a setting.

Note that this is **reachability, not answer quality** — these questions carry no relevance labels
and their numbers are not comparable to the golden nDCG in `reports/rc-final-baseline.*`.

### The handed-over case, `vista-signon-credentials`, is out of scope for this machinery

The question asks for "credentials" where Kernel's prose says *Access and Verify codes* / *2FA*.
Appending the manual's vocabulary moves it **0.1749 → 0.2772 nDCG@10**, still reaching only 1 of its
4 judged sections. But the SKL cannot express it under any amount of curation: its entities are
FileMan files with number/name/global surfaces, its `terms` are product abbreviations, and the only
thing search consumes is a *file-number → file-name* map. A prose-synonym capability would be a
different build, not this one finished. That is worth knowing precisely because the case was offered
as the fairer test.

## (c) The queue is 307 candidates, not 4,415 — and approving **all** of them adds **one** equivalence

**First, the number in the tracker is wrong in kind.** `resolve` reports `proposals: len(unresolved)`
— every *mention*. The artifact it writes, `reports/knowledge/proposals.json`, aggregates those to
one row per `(type, surface)`. 4,415 is a mention count; the queue a curator would face is **307
rows**. The plan's worry about "never 4,415 individual decisions" was addressing a backlog that does
not exist at that size.

| by type | | judged |
|---|---|---|
| `global` | 174 | inert |
| `routine` | 105 | inert |
| `fileman_file` | 18 | the only projectable type |
| `package_namespace` | 5 | inert |
| `build` | 4 | inert |
| `hl7_segment` | 1 | inert |

| | |
|---|---|
| candidates of a type the seed can represent | 18 |
| **structurally inert — recognised, but with no landing place** | **289 (94%)** |
| **would reach search if approved** | **1** |

The 289 are not wrong and not uncurated. They are a category mismatch: the DD seed represents
FileMan **files**, and the expansion map keys on file **numbers**, so a proposal for a routine, a
global, a namespace, a build or an HL7 segment has nowhere to land no matter who approves it. They
are the recognizer's leftovers, not a backlog.

Of the 18 file-number candidates: 6 are not real files at all (`16200`, `16201`, `16000`, `05`, …
— misrecognitions), 11 are real but dropped by the same guards as in (b), and **1** would produce a
working expansion: `405 → PATIENT MOVEMENT`, which occurs **once**, in **one** document.

Recognition quality, stratified as the plan required: of the 307, 111 surfaces are valid in the
measured VistA, 180 are unknown to it, 10 unchecked, 6 provably not files. The tail behaves exactly
as the plan predicted it would — the single-occurrence stratum is dominated by misrecognitions
picked out of prose and tables (`^AD`, `^C2`, `^CENTRAL`, `^FEB`, `^GROUP`, `^MA`, `^P13`, `^SX`).
A flat sample would have flattered this; the head stratum is much cleaner.

---

## What the three numbers say together

The ambiguity is real (233 files, 1,932 documents). It costs real questions (28 of 80). And the
approval queue — the thing this effort was scoped to finish — is worth **one** equivalence for a
file mentioned once.

Those findings do not point the same way, which is why the ruling in
[`vdocs-quality-synonym-layer.md §10`](vdocs-quality-synonym-layer.md#10-ruling-sl2) is neither a
plain *finish* nor a plain *stop*.

## Two corrections to the record

1. **"4,415 candidates awaiting approval" is a mention count.** The reviewable queue is 307 rows.
   Stated in the proposal, the plan, the tracker, the kickoff and register row R‑12.
2. **The bottleneck was never the approval step.** The proposal says "the gap is not the extraction
   — it is the approval step between extraction and use". Measured, the gap is the **projection**:
   `skl_expansion_map`'s guards and FTS tokenisation drop 24 of 28 repairable failures, and 94% of
   the queue names entity types the seed cannot hold.

## What else consumes the SKL (so "stop" cannot mean "delete")

Search is not `knowledge.db`'s only reader, and a ruling that ignored the others would break working
things:

- `manifest` projects the **Entities section of `gold/glossary.md`** (21 entities with
  documented-in cross-links) — reader-facing, and unaffected by the equivalence question.
- `kernel/termbase.termbase_artifacts` projects the **483 Term nodes** that `build-termbase` emits.
- `doctor` checks `entity_skl` is non-empty to catch `index` clobbering `merge`'s output (R‑18b).
- `index.db:entity_synonyms` (56 rows) and `chunk_entities` (6,311 rows) are projected by `merge`
  and read by **nothing** — the only genuinely dead output in the chain.
