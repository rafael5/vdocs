# RR.2 — bm25 field-weight sweep on the production collection

- **Lake:** `/home/rafael/data/vdocs/index.db` · **k:** 10 · **grid points:** 120
- **Shipped weights** {'doc_title': 2.5, 'title': 2.0, 'section_path': 1.5, 'body': 1.0} → mean nDCG@10 **0.6386**
- **Candidates beating it on the mean AND regressing no question:** 0

A candidate is adoptable only if it regresses **no** question. The mean is reported first because it is what a sweep optimises, and second because it is not the rule.

| rank | doc_title | title | section_path | mean nDCG@10 | Δmean | improved | regressed | worst regression |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 3.0 | 3.0 | 0.5 | 0.6693 | +0.0307 | 9 | 5 | -0.1131 |
| 2 | 4.0 | 3.0 | 0.5 | 0.6691 | +0.0305 | 9 | 6 | -0.1131 |
| 3 | 2.0 | 3.0 | 0.5 | 0.6682 | +0.0296 | 7 | 5 | -0.1131 |
| 4 | 1.5 | 3.0 | 0.5 | 0.6629 | +0.0243 | 6 | 8 | -0.1131 |
| 5 | 2.5 | 3.0 | 0.5 | 0.6620 | +0.0234 | 8 | 5 | -0.1438 |
| 6 | 3.0 | 3.0 | 1.0 | 0.6571 | +0.0185 | 8 | 3 | -0.0334 |
| 7 | 2.5 | 3.0 | 1.0 | 0.6563 | +0.0177 | 9 | 2 | -0.0045 |
| 8 | 1.5 | 2.5 | 0.5 | 0.6561 | +0.0175 | 6 | 7 | -0.1131 |
| 9 | 4.0 | 3.0 | 1.0 | 0.6556 | +0.0170 | 10 | 5 | -0.0558 |
| 10 | 1.5 | 3.0 | 2.0 | 0.6550 | +0.0164 | 6 | 7 | -0.0923 |
