# Phase 0.4 baseline — lexical retrieval quality (golden set)

- **Lake:** `/home/rafael/data/vdocs`  ·  **mode:** lexical (FTS5+BM25)  ·  **k:** 10
- **Labeled queries:** 24 of 25
- **mean nDCG@10:** 0.6386
- **mean MRR:** 0.7535
- **mean recall@10:** 0.7134
- **mean redundancy@10:** 0.048 (all queries)

## Per-query

| query | axis | nDCG@10 | MRR | recall@10 | redundancy@10 | hits |
|---|---|---|---|---|---|---|
| kids-install-build | kids-install | 0.8109 | 1.0 | 0.5714 | 0.0 | 10 |
| pharmacy-api-dispense | redundancy-probe | — | — | — | 0.3 | 10 |
| fileman-add-field | fileman-dd | 0.0 | 0.0 | 0.0 | 0.0 | 10 |
| rpc-broker-client-call | rpc-broker | 0.4319 | 1.0 | 0.5556 | 0.0 | 10 |
| mailman-decnet-transmission | mailman-network | 0.5861 | 0.5 | 0.7143 | 0.1 | 9 |
| radiology-cancel-exam | radiology | 0.924 | 1.0 | 1.0 | 0.0 | 10 |
| pharmacy-release-signed-order | pharmacy-release | 0.7265 | 0.5 | 0.8333 | 0.2 | 9 |
| tiu-unsigned-notes | tiu-notes | 0.7391 | 1.0 | 0.5 | 0.1 | 9 |
| vpr-allergy-data | vpr-domains | 0.669 | 1.0 | 1.0 | 0.0 | 10 |
| lab-file60-audit | lab-audit | 0.7068 | 1.0 | 0.8333 | 0.0 | 10 |
| cprs-enter-immunization | cprs-gui | 0.5842 | 0.3333 | 1.0 | 0.0 | 10 |
| vbecs-accept-order | vbecs-orders | 0.0509 | 0.3333 | 0.25 | 0.1 | 9 |
| hl7-security-keys | hl7-security | 0.9173 | 1.0 | 0.5 | 0.1 | 10 |
| fileman-file-200-new-person | fileman-dd | 0.4327 | 0.3333 | 1.0 | 0.1 | 9 |
| fileman-import-host-file | api-leadin | 0.72 | 1.0 | 0.6667 | 0.0 | 10 |
| fileman-input-transform-definition | api-leadin | 0.9795 | 1.0 | 1.0 | 0.0 | 10 |
| fileman-blddialog-icr-number | api-leadin | 0.3951 | 0.25 | 0.5 | 0.0 | 10 |
| quasar-package-wide-variables | short-reference | 1.0 | 1.0 | 1.0 | 0.1 | 10 |
| hl7-table-0136-values | short-reference | 0.9469 | 1.0 | 1.0 | 0.0 | 10 |
| kids-backup-transport-global | kids-install | 0.5 | 0.3333 | 1.0 | 0.0 | 10 |
| hl7-start-tcpip-link | hl7-links | 0.9247 | 1.0 | 0.8333 | 0.0 | 10 |
| fileman-file-access-security | kernel-security | 0.7575 | 1.0 | 0.8571 | 0.0 | 10 |
| vista-signon-credentials | kernel-auth | 0.1749 | 0.5 | 0.25 | 0.1 | 9 |
| fileman-finder-api | fileman-api | 0.7139 | 1.0 | 0.4 | 0.0 | 10 |
| taskman-monitor | kernel-ops | 0.6344 | 1.0 | 0.8571 | 0.0 | 10 |
