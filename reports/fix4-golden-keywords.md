# Phase 0.4 baseline — lexical retrieval quality (golden set)

- **Lake:** `/home/rafael/data/vdocs`  ·  **mode:** lexical (FTS5+BM25), keyword forms  ·  **k:** 10
- **Labeled queries:** 30 of 31
- **mean nDCG@10:** 0.4248
- **mean MRR:** 0.4954
- **mean recall@10:** 0.4436
- **mean redundancy@10:** 0.0871 (all queries)

## Per-query

| query | axis | nDCG@10 | MRR | recall@10 | redundancy@10 | hits |
|---|---|---|---|---|---|---|
| kids-install-build | kids-install | 0.0 | 0.0 | 0.0 | 0.0 | 10 |
| pharmacy-api-dispense | redundancy-probe | — | — | — | 0.7 | 10 |
| fileman-add-field | fileman-dd | 0.0 | 0.0 | 0.0 | 0.0 | 10 |
| rpc-broker-client-call | rpc-broker | 0.0673 | 0.1429 | 0.1111 | 0.0 | 10 |
| mailman-decnet-transmission | mailman-network | 0.783 | 1.0 | 0.5714 | 0.3 | 7 |
| radiology-cancel-exam | radiology | 0.3308 | 0.1429 | 0.6667 | 0.0 | 10 |
| pharmacy-release-signed-order | pharmacy-release | 0.8415 | 1.0 | 0.5 | 0.3 | 8 |
| tiu-unsigned-notes | tiu-notes | 0.7661 | 1.0 | 0.5 | 0.1 | 9 |
| vpr-allergy-data | vpr-domains | 0.5757 | 0.5 | 1.0 | 0.0 | 10 |
| lab-file60-audit | lab-audit | 0.9329 | 1.0 | 1.0 | 0.0 | 10 |
| cprs-enter-immunization | cprs-gui | 0.5269 | 0.3333 | 1.0 | 0.0 | 10 |
| vbecs-accept-order | vbecs-orders | 0.7126 | 1.0 | 0.25 | 0.0 | 10 |
| hl7-security-keys | hl7-security | 0.9173 | 1.0 | 0.5 | 0.2 | 9 |
| fileman-file-200-new-person | fileman-dd | 0.0 | 0.0 | 0.0 | 0.0 | 10 |
| fileman-import-host-file | api-leadin | 0.2404 | 0.1429 | 0.5 | 0.0 | 10 |
| fileman-input-transform-definition | api-leadin | 0.5714 | 1.0 | 1.0 | 0.3 | 10 |
| fileman-blddialog-icr-number | api-leadin | 0.9173 | 1.0 | 0.5 | 0.0 | 1 |
| quasar-package-wide-variables | short-reference | 1.0 | 1.0 | 1.0 | 0.0 | 1 |
| hl7-table-0136-values | short-reference | 1.0 | 1.0 | 1.0 | 0.0 | 10 |
| kids-backup-transport-global | kids-install | 0.2891 | 0.1 | 1.0 | 0.0 | 10 |
| hl7-start-tcpip-link | hl7-links | 0.7829 | 1.0 | 0.6667 | 0.0 | 10 |
| fileman-file-access-security | kernel-security | 0.5483 | 1.0 | 0.5714 | 0.0 | 10 |
| vista-signon-credentials | kernel-auth | 0.0 | 0.0 | 0.0 | 0.0 | 10 |
| fileman-finder-api | fileman-api | 0.2953 | 0.25 | 0.2 | 0.0 | 10 |
| taskman-monitor | kernel-ops | 0.4715 | 1.0 | 0.5714 | 0.0 | 10 |
| plain-change-password | plain-english | 0.0 | 0.0 | 0.0 | 0.1 | 10 |
| plain-create-user-account | plain-english | 0.0 | 0.0 | 0.0 | 0.4 | 9 |
| plain-background-jobs | plain-english | 0.0 | 0.0 | 0.0 | 0.2 | 10 |
| plain-set-up-printer | plain-english | 0.0 | 0.0 | 0.0 | 0.0 | 10 |
| plain-enter-patient-allergies | plain-english | 0.1736 | 0.25 | 0.2 | 0.1 | 9 |
| plain-send-email | plain-english | 0.0 | 0.0 | 0.0 | 0.0 | 10 |
