# Phase 0.4 baseline — lexical retrieval quality (golden set)

- **Lake:** `/home/rafael/data/vdocs-dev`  ·  **mode:** lexical (FTS5+BM25)  ·  **k:** 10
- **Labeled queries:** 5 of 6
- **mean nDCG@10:** 0.4692
- **mean MRR:** 0.5389
- **mean recall@10:** 0.7167
- **mean redundancy@10:** 0.0333 (all queries)

## Per-query

| query | axis | nDCG@10 | MRR | recall@10 | redundancy@10 | hits |
|---|---|---|---|---|---|---|
| kids-install-build | kids-install | 0.231 | 1.0 | 0.5 | 0.1 | 9 |
| kids-delphi-components-install | kids-install | 0.4824 | 0.25 | 1.0 | 0.0 | 10 |
| hwsc-rest-from-vista-m | hwsc-rest | 0.2243 | 0.1111 | 0.3333 | 0.0 | 10 |
| hwsc-install-privileges | hwsc-rest | 0.9804 | 1.0 | 1.0 | 0.0 | 10 |
| kaajee-install-procedure | kaajee-auth | 0.4278 | 0.3333 | 0.75 | 0.0 | 10 |
| pharmacy-api-dispense | redundancy-probe | — | — | — | 0.1 | 9 |
