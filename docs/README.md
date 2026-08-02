# docs/ — index and filing rules

## The lifecycle rule

Documentation here is classified by **lifecycle state, not topic**:

1. A workstream is born as a **committed** proposal (+ implementation-plan/tracker) in
   [`proposals/`](proposals/). Never leave a proposal untracked on disk.
2. Its session kickoff prompts live in [`prompts/`](prompts/); each moves to
   `prompts/historical/` **in the commit that lands its work**.
3. When the last phase ships — or the workstream is formally dropped — the proposal/tracker
   moves to [`historical/`](historical/) in the closing commit, *after* promoting anything an
   operator still needs into [`reference/`](reference/) or the root docs.
4. Decisions that must outlive their workstream become ADRs in [`adr/`](adr/).

## What lives where

| Location | Contents | Lifetime |
|---|---|---|
| `docs/` root | The canonical four: this index, [`vdocs-design.md`](vdocs-design.md) (architecture), [`vdocs-user-guide.md`](vdocs-user-guide.md) (onboarding/operator guide), [`de-novo-run.md`](de-novo-run.md) (from-scratch runbook) | evergreen, kept current |
| [`reference/`](reference/) | Durable lookups: gate reference, inventory/crawl column spec, classification & persona model, function-domain taxonomy, discovery-UX research, [pipeline adversarial audit](reference/pipeline-adversarial-audit.md) (per-stage logic/IO/gates table + risk register, 2026-08-01) | evergreen, consult as needed |
| [`proposals/`](proposals/) | Live or parked-unfinished workstreams (proposal + tracker pairs) | until the workstream closes |
| [`prompts/`](prompts/) | Kickoff prompts for **un-executed** work only | until the work lands |
| [`adr/`](adr/) | Numbered architecture decision records | permanent |
| [`releases/`](releases/) | Release manifests/records for shipped data bundles | permanent |
| [`session-summaries/`](session-summaries/) | The narrative record of Claude working sessions — what was attempted, what happened, what was got wrong; **frozen** (corrections go in later entries) | append-only |
| [`historical/`](historical/) | Closed workstreams, dated snapshots, superseded designs — kept for the *why*, never updated | archive |

## Current state (2026-07-04)

- **Active workstream:** SKL — [`proposals/skl-implementation-plan.md`](proposals/skl-implementation-plan.md)
  (S0–S3 landed; S4 semantic-fidelity gates and S5 generalize-to-Kernel open).
- **✅ Complete (2026-08-02):** pipeline audit remediation, P1–P7 — [`historical/pipeline-audit-remediation-implementation-plan.md`](historical/pipeline-audit-remediation-implementation-plan.md)
  (+ [tracker](historical/pipeline-audit-remediation-tracker.md)). Fixed 13 of the audit's register
  rows and added one; the living record is the struck register in
  [`reference/pipeline-adversarial-audit.md`](reference/pipeline-adversarial-audit.md). Chunk-less
  sections 26.7% → 10.5%, stale lineage 615/615 → 0/615, retrieval +44%. **Open hand-off:**
  [`guides/updating-out-of-repo-surfaces.md`](guides/updating-out-of-repo-surfaces.md).
- **Paused:** FileMan docs-as-code pilot at L1.4
  ([`prompts/L1.4-export-fileman-driver-kickoff.md`](prompts/L1.4-export-fileman-driver-kickoff.md));
  manifest query-recipe staleness fix
  ([`prompts/historical/manifest-query-recipe-staleness-fix-kickoff.md`](prompts/historical/manifest-query-recipe-staleness-fix-kickoff.md)).
- **Direction:** lexical-first, offline, human-consumer (vectors/MCP parked) — rationale in
  [`proposals/offline-lexical-search-plan.md`](proposals/offline-lexical-search-plan.md).
