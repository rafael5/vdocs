# Phase 0.4 baseline — lexical retrieval quality (golden set)

- **Lake:** `/home/rafael/data/vdocs-dev`  ·  **mode:** lexical (FTS5+BM25)  ·  **k:** 10
- **Labeled queries:** 18 of 19
- **mean nDCG@10:** 0.5232
- **mean MRR:** 0.5849
- **mean recall@10:** 0.6204
- **mean redundancy@10:** 0.0421 (all queries)

## Per-query

| query | axis | nDCG@10 | MRR | recall@10 | redundancy@10 | hits |
|---|---|---|---|---|---|---|
| kids-install-build | kids-install | 0.231 | 1.0 | 0.5 | 0.1 | 9 |
| kids-delphi-components-install | kids-install | 0.4824 | 0.25 | 1.0 | 0.0 | 10 |
| hwsc-rest-from-vista-m | hwsc-rest | 0.2243 | 0.1111 | 0.3333 | 0.0 | 10 |
| hwsc-install-privileges | hwsc-rest | 0.9804 | 1.0 | 1.0 | 0.0 | 10 |
| kaajee-install-procedure | kaajee-auth | 0.4278 | 0.3333 | 0.75 | 0.0 | 10 |
| pharmacy-api-dispense | redundancy-probe | — | — | — | 0.1 | 9 |
| fileman-add-field | fileman-dd | 0.0 | 0.0 | 0.0 | 0.0 | 10 |
| rpc-broker-client-call | rpc-broker | 0.3234 | 0.3333 | 0.25 | 0.0 | 10 |
| mailman-decnet-transmission | mailman-network | 0.4835 | 0.5 | 0.5 | 0.1 | 9 |
| radiology-cancel-exam | radiology | 1.0 | 1.0 | 1.0 | 0.2 | 8 |
| pharmacy-release-signed-order | pharmacy-release | 0.9429 | 1.0 | 1.0 | 0.0 | 10 |
| tiu-unsigned-notes | tiu-notes | 0.7453 | 1.0 | 0.3333 | 0.1 | 9 |
| vpr-allergy-data | vpr-domains | 0.7142 | 1.0 | 1.0 | 0.1 | 9 |
| lab-file60-audit | lab-audit | 0.6444 | 1.0 | 0.75 | 0.0 | 10 |
| cprs-enter-immunization | cprs-gui | 0.5276 | 0.3333 | 1.0 | 0.0 | 10 |
| vbecs-accept-order | vbecs-orders | 0.0 | 0.0 | 0.0 | 0.0 | 10 |
| lexicon-lookup | lexicon | 0.417 | 0.3333 | 1.0 | 0.0 | 10 |
| hl7-security-keys | hl7-security | 0.9173 | 1.0 | 0.5 | 0.1 | 9 |
| hwsc-web-service-manager | hwsc-manage | 0.3563 | 0.3333 | 0.25 | 0.0 | 10 |
