# reports/ — measurement artifacts, and the one rule for reading them

## A report without `index_db` in its rollup predates 2026-08-02. You do not know what corpus it measured.

`scripts/baseline_golden.py` used to default to `~/data/vdocs-dev` while every other command
defaulted to `~/data/vdocs`, and its printed rollup named **no corpus at all**. Three P6
measurements were quoted as evidence about the production lake while reading a stale 451-document
dev copy — and they agreed with each other, which is exactly what made it read as confirmation
rather than as a bug. It was caught only by a contradiction: the engine ranked a section #1 for a
query the harness had scored 0.000.

Since then every rollup carries `index_db`, `documents`, `chunks` and `corpus_content_hash`.

## The current baseline is `rc-final-baseline.*` (2026-08-03, post-report-card key)

The report-card effort (RC.1–RC.3) repaired the ANSWER KEY, not search: six scope-rotted queries
retired and replaced, 34 labels added / 2 downgraded by reading, and the harness now **exits
non-zero** when any labelled query is unscoreable. The number to measure ranking work against is
**nDCG@10 0.6386 · MRR 0.7535 · recall@10 0.7134** (24 labelled, 109 labels,
`corpus_content_hash 726d22a4…`, 57,895 chunks). Anything quoting **0.5305 / 18 answerable**
is the pre-RC key — same engine, different ruler; do not compare across the key change. The
intermediate steps are `rc1-key-repair.*` (retire+replace only) and `rc2-key-rejudged.*`
(full re-judge; identical numbers to rc-final, kept as the per-step record).
⚠️ The post-CI lake's `corpus_content_hash` is `726d22a4…`, not the `6dbec1f5…` in pre-RC
reports — a metadata-only change (CI.3 lifecycle labels); verified 0 per-query drift on the
unchanged queries, `documents`/`chunks` identical.

**So:**

- **Compare `index_db` + `documents` + `chunks`, not `corpus_content_hash` alone.**
  ⚠️ `corpus_content_hash` fingerprints the **document set**, not the index build — two indexes over
  the same documents with *different chunking* carry the **same hash**. Measured: the pre-P6.1
  rebuild (48,769 chunks) and the shipped one (57,895) both hash to `6dbec1f5…`. So the hash tells
  you the corpus is the same; only `chunks` tells you the index is. That is why the rollup records
  both.
- Comparing an nDCG from one corpus to an nDCG from another is not a regression test, it is a
  category error — a 2.3×-larger corpus scores *lower* on the same queries purely from competition
  (the original 19 golden queries: 0.5134 on the 451-doc dev lake, 0.3072 on the 1,040-doc
  production lake, same code, same day).
- **A filtered ranking is not a rebuilt index.** Estimating "before" by removing the new sections
  from the current results was accurate in the mean (−0.0050 vs a true −0.0059) and wrong per
  query: it missed two queries dropping to 0.000 and one gaining +0.286, because BM25 scores shift
  with corpus statistics. If the question is worth answering, rebuild — it costs ~45 s per index
  build here, and `p6-golden-PROD-before-p61.*` is what that buys.
- **A file here with no `index_db` field is a historical record, not a baseline.** Read it for what
  changed within its own run, never as a number to measure today against.

The two P6 reports that were measured on the wrong lake were **deleted** rather than annotated
(commit `ae87ef6`+): they had been committed as evidence for a claim they could not support, and a
machine-readable file that quietly lies is worse than an absent one. The corrected run is
`p6-golden-PROD-with-p64.*`, which carries its provenance.
