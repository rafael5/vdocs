# Kickoff prompts — pipeline audit remediation (P1–P7)

One kickoff prompt per phase of
[`../../proposals/pipeline-audit-remediation-implementation-plan.md`](../../proposals/pipeline-audit-remediation-implementation-plan.md)
(tracker beside it). Prompts exist for **un-executed** work only: each phase's closing step
writes the *next* phase's prompt (baking in the measured results of the phase just landed)
and retires the executed one. Do not write P3's prompt while P1 is open — the numbers it
needs don't exist yet.

| Prompt | Phase | Status |
|---|---|---|
| ~~`P1-acquisition-chain-integrity-kickoff.md`~~ → [`historical/`](../historical/) | P1 — re-key `raw/index.json`, chain-reconciliation gate, DOCX magic check (+ P1.4 WAL fix) | ✅ **complete** `6ba05eb` `38190e9` `fa66309` `6668a26` |
| ~~`P2-doctor-into-the-dag-kickoff.md`~~ → [`historical/`](../historical/) | P2 — doctor as terminal DAG stage (+ riders R‑13, R‑14) | ✅ **complete** `74b136b` |
| ~~`P3-retention-gates-kickoff.md`~~ → [`historical/`](../historical/) | P3 — retention verdicts gate via validate (+ the legacy-TOC capture-before-strip fix) | ✅ **complete** `b28fbf5` `f81dcb2` |
| [`P4-sound-sqlite-fingerprints-kickoff.md`](P4-sound-sqlite-fingerprints-kickoff.md) | P4 — content-hash SQLite fingerprints | **ready to run** |
| `P5-history-lineage-truth-kickoff.md` | P5 — history.yaml supersedes + stale-lineage check | written at P4 close |
| `P6-container-leadin-chunking-kickoff.md` | P6 — chunk substantive container lead-ins | written at P5 close |
| `P7-close-out-kickoff.md` | P7 — full rerun, strike audit register, republish constants | written at P6 close |
