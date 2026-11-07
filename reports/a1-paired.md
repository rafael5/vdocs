# A1 paired comparison: the pre-A1 index vs the rebuilt one, per golden question

Both indexes through the production engine (`server.search.lexical_search`, synonym table on,
k=10, unique sections), 2026-11-07. Machine-readable: `reports/a1-paired.json` (per-query top-10
lists on both sides).

| | Before | After |
|---|---|---|
| `index_db` | scratchpad copy of `~/data/vdocs/index.db` as built 2026-11-06 23:23 | `~/data/vdocs/index.db` rebuilt 2026-11-07 |
| documents / chunks | 1040 / 57804 | 1040 / 57804 |
| `corpus_content_hash` | `5b118189…` | `5b118189…` (same document set) |

## Adoption rule: no question loses a judged section from its top 10 — **passed**

Judged sections lost from a top 10: **none**. Gained: `DI/fm22_2um2/new-person-file-for-standalone-va-fileman` (grade 3) enters
`fileman-file-200-new-person` at rank 8 — a grade-3 answer that was unreachable before.

## Means over the 30 keyword questions, bootstrap 95% interval on the paired delta (4,000 resamples, seed 7)

| Metric | Before | After | Δ | 95% CI | Wins / losses / ties |
|---|---|---|---|---|---|
| nDCG@10 | 0.4437 | **0.453** | +0.0094 | [-0.0017, +0.0271] | 4 / 4 / 22 |
| MRR | 0.5426 | **0.5449** | +0.0023 | [-0.0051, +0.0125] | 2 / 2 / 26 |
| recall@10 | 0.4636 | **0.4747** | +0.0111 | [+0.0000, +0.0333] | 1 / 0 / 29 |
| nDCG@10, the 24 originals | 0.5316 | **0.5433** | | | |

The intervals include zero for nDCG@10 and MRR: A1 is a hygiene change whose ranking effect is
small and non-negative in aggregate, as the review expected. The four nDCG losses are rank shifts of
one judged section by one or two places within the top 10, never out of it (the recall@10 row has
no losses).

## The 8 questions that moved

| Question | Axis | nDCG@10 | MRR | recall@10 |
|---|---|---|---|---|
| rpc-broker-client-call | rpc-broker | 0.0673 → 0.0637 (-0.0036) | 0.1429 → 0.1250 (-0.0179) | 0.1111 → 0.1111 |
| tiu-unsigned-notes | tiu-notes | 0.7661 → 0.7540 (-0.0121) | 1.0000 → 1.0000 | 0.5000 → 0.5000 |
| fileman-file-200-new-person | fileman-dd | 0.0000 → 0.2351 (+0.2351) | 0.0000 → 0.1250 (+0.1250) | 0.0000 → 0.3333 (+0.3333) |
| fileman-input-transform-definition | api-leadin | 0.5714 → 0.6310 (+0.0596) | 1.0000 → 1.0000 | 1.0000 → 1.0000 |
| kids-backup-transport-global | kids-install | 0.2891 → 0.3010 (+0.0119) | 0.1000 → 0.1111 (+0.0111) | 1.0000 → 1.0000 |
| fileman-file-access-security | kernel-security | 0.5483 → 0.5700 (+0.0217) | 1.0000 → 1.0000 | 0.5714 → 0.5714 |
| fileman-finder-api | fileman-api | 0.2953 → 0.2652 (-0.0301) | 0.2500 → 0.2000 (-0.0500) | 0.2000 → 0.2000 |
| taskman-monitor | kernel-ops | 0.4715 → 0.4697 (-0.0018) | 1.0000 → 1.0000 | 0.5714 → 0.5714 |

The other 22 questions returned identical judged rankings.

## Identifier probes (synonym table on, top 5)

| Probe | Before | After |
|---|---|---|
| patch ids found | 216/256 | **223/256** |
| `file #N` found | 25/30 | **25/30** (the same five missed: 1, 101, 2, 4, 405) |
