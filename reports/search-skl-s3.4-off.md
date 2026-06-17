# Phase 0.4 baseline — lexical retrieval quality (golden set)

- **Lake:** `/home/rafael/data/vdocs`  ·  **mode:** lexical (FTS5+BM25)  ·  **k:** 10
- **Labeled queries:** 19 of 20
- **mean nDCG@10:** 0.3131
- **mean MRR:** 0.3557
- **mean recall@10:** 0.3596
- **mean redundancy@10:** 0.065 (all queries)

## Per-query

| query | axis | nDCG@10 | MRR | recall@10 | redundancy@10 | hits |
|---|---|---|---|---|---|---|
| kids-install-build | kids-install | 0.0 | 0.0 | 0.0 | 0.0 | 10 |
| kids-delphi-components-install | kids-install | 0.0 | 0.0 | 0.0 | 0.0 | 10 |
| hwsc-rest-from-vista-m | hwsc-rest | 0.0 | 0.0 | 0.0 | 0.1 | 10 |
| hwsc-install-privileges | hwsc-rest | 0.0 | 0.0 | 0.0 | 0.1 | 10 |
| kaajee-install-procedure | kaajee-auth | 0.0 | 0.0 | 0.0 | 0.2 | 10 |
| pharmacy-api-dispense | redundancy-probe | — | — | — | 0.3 | 10 |
| fileman-add-field | fileman-dd | 0.0 | 0.0 | 0.0 | 0.0 | 10 |
| rpc-broker-client-call | rpc-broker | 0.204 | 0.125 | 0.25 | 0.0 | 10 |
| mailman-decnet-transmission | mailman-network | 0.4817 | 0.5 | 0.5 | 0.1 | 9 |
| radiology-cancel-exam | radiology | 0.9558 | 1.0 | 1.0 | 0.0 | 10 |
| pharmacy-release-signed-order | pharmacy-release | 0.584 | 0.5 | 0.6667 | 0.1 | 10 |
| tiu-unsigned-notes | tiu-notes | 0.7453 | 1.0 | 0.3333 | 0.1 | 9 |
| vpr-allergy-data | vpr-domains | 0.6728 | 1.0 | 1.0 | 0.0 | 10 |
| lab-file60-audit | lab-audit | 0.6444 | 1.0 | 0.75 | 0.0 | 10 |
| cprs-enter-immunization | cprs-gui | 0.5203 | 0.3333 | 1.0 | 0.0 | 10 |
| vbecs-accept-order | vbecs-orders | 0.0923 | 0.1 | 0.3333 | 0.0 | 10 |
| lexicon-lookup | lexicon | 0.0 | 0.0 | 0.0 | 0.0 | 10 |
| hl7-security-keys | hl7-security | 0.9173 | 1.0 | 0.5 | 0.0 | 10 |
| hwsc-web-service-manager | hwsc-manage | 0.0 | 0.0 | 0.0 | 0.3 | 9 |
| fileman-file-200-new-person | fileman-dd | 0.1305 | 0.2 | 0.5 | 0.0 | 10 |
