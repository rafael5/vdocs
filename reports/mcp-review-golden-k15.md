# Phase 0.4 baseline — lexical retrieval quality (golden set)

- **Lake:** `/home/rafael/data/vdocs`  ·  **mode:** lexical (FTS5+BM25)  ·  **k:** 15
- **Labeled queries:** 24 of 25
- **mean nDCG@15:** 0.6682
- **mean MRR:** 0.7951
- **mean recall@15:** 0.7761
- **mean redundancy@15:** 0.0693 (all queries)

## Per-query

| query | axis | nDCG@15 | MRR | recall@15 | redundancy@15 | hits |
|---|---|---|---|---|---|---|
| kids-install-build | kids-install | 0.8101 | 1.0 | 0.5714 | 0.0667 | 14 |
| pharmacy-api-dispense | redundancy-probe | — | — | — | 0.4667 | 14 |
| fileman-add-field | fileman-dd | 0.0 | 0.0 | 0.0 | 0.0 | 15 |
| rpc-broker-client-call | rpc-broker | 0.5592 | 1.0 | 0.6667 | 0.0 | 15 |
| mailman-decnet-transmission | mailman-network | 0.5861 | 0.5 | 0.7143 | 0.2 | 12 |
| radiology-cancel-exam | radiology | 0.924 | 1.0 | 1.0 | 0.0 | 15 |
| pharmacy-release-signed-order | pharmacy-release | 0.9309 | 1.0 | 0.8333 | 0.2 | 13 |
| tiu-unsigned-notes | tiu-notes | 0.7342 | 1.0 | 0.5 | 0.2 | 12 |
| vpr-allergy-data | vpr-domains | 0.7142 | 1.0 | 1.0 | 0.0667 | 15 |
| lab-file60-audit | lab-audit | 0.7289 | 1.0 | 1.0 | 0.0 | 15 |
| cprs-enter-immunization | cprs-gui | 0.5842 | 0.3333 | 1.0 | 0.0 | 15 |
| vbecs-accept-order | vbecs-orders | 0.1965 | 0.3333 | 0.5 | 0.0 | 15 |
| hl7-security-keys | hl7-security | 0.9173 | 1.0 | 0.5 | 0.1333 | 15 |
| fileman-file-200-new-person | fileman-dd | 0.422 | 0.3333 | 1.0 | 0.0667 | 14 |
| fileman-import-host-file | api-leadin | 0.7347 | 1.0 | 1.0 | 0.0 | 15 |
| fileman-input-transform-definition | api-leadin | 0.9795 | 1.0 | 1.0 | 0.0667 | 15 |
| fileman-blddialog-icr-number | api-leadin | 0.4305 | 0.25 | 1.0 | 0.0 | 15 |
| quasar-package-wide-variables | short-reference | 1.0 | 1.0 | 1.0 | 0.0667 | 15 |
| hl7-table-0136-values | short-reference | 0.9469 | 1.0 | 1.0 | 0.0667 | 15 |
| kids-backup-transport-global | kids-install | 0.5 | 0.3333 | 1.0 | 0.0 | 15 |
| hl7-start-tcpip-link | hl7-links | 0.8924 | 1.0 | 0.8333 | 0.0 | 15 |
| fileman-file-access-security | kernel-security | 0.8193 | 1.0 | 1.0 | 0.0 | 15 |
| vista-signon-credentials | kernel-auth | 0.2772 | 1.0 | 0.25 | 0.1333 | 13 |
| fileman-finder-api | fileman-api | 0.7139 | 1.0 | 0.4 | 0.0 | 15 |
| taskman-monitor | kernel-ops | 0.6344 | 1.0 | 0.8571 | 0.0 | 15 |
