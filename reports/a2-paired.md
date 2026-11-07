# A2 paired comparison: the A1 index vs the A2 rebuild, per golden question

Both indexes through the production engine (`server.search.lexical_search`, synonym table on,
k=10, unique sections), 2026-11-07. Machine-readable: `reports/a2-paired.json`.

| | Before (A1, `ccc184b`) | After (A2) |
|---|---|---|
| `index_db` | scratchpad copy of `~/data/vdocs/index.db` as rebuilt by A1 | `~/data/vdocs/index.db` rebuilt from `normalize` |
| documents / chunks | 1040 / 57804 | 1040 / 58240 |
| `corpus_content_hash` | `5b118189…` | `b6e38e58…` (307 bodies changed) |

## Adoption rule: no question loses a judged section from its top 10 — **passed**

Every one of the 30 questions returned the identical judged ranking: nDCG@10 0.453 → 0.453,
MRR 0.5449 → 0.5449, recall@10 0.4747 → 0.4747; 0 wins, 0 losses, 30 ties on each; the 24 originals
0.5433 → 0.5433. No judged section lost or gained; **no `preamble` section enters any top-10 list** —
the 436 new chunks (195 preamble sections, split where oversized) hold front-matter prose
(revision histories, orientation, introductions) that none of the 30 questions targets, which is
what the harness can say about them. Redundancy@10 0.0903 → 0.0871 (harness).

## Identifier probes (synonym table on, top 5)

| Probe | Before | After |
|---|---|---|
| patch ids found | 223 of 256 | **272 of 306** — the build-entity list itself grew by 50 with the newly indexed text (87.1% → 88.9%) |
| `file #N` found | 25 of 30 | **25 of 30** (the same five missed) |
| snippets with `<` | 6 of 428 | 6 of 428 (keystroke notation, unchanged) |
