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

- **Proposed (2026-11-07), decisions D1–D5 taken as recommended; A1 and A2 built and adopted 2026-11-07 (`reports/a1-*.md`, `reports/a2-*.md`), A3–A5 open:** [`proposals/end-to-end-search-architecture-review.md`](proposals/end-to-end-search-architecture-review.md)
  — adversarial end-to-end review of capture, storage, indexing and search: 10% of indexed tokens
  are markup, text before the first heading is never indexed, 6.3% of chunks are template copies,
  13 near-duplicate latest-document pairs, the text stored twice with no `ANALYZE`; ranked A/B/C
  recommendations (clean-text projection, preamble + coverage gate, section-collapsed MCP results
  and a read tool, database hygiene, a document-unit option, generated synonym classes) and the
  preconditions for a `sqlite-vec` trial. Re-ranks the open items of the MCP review (Appendix B).
- **Proposed (2026-11-06), decisions taken; all five fixes built (2026-11-07):** [`proposals/keyword-search-five-fixes.md`](proposals/keyword-search-five-fixes.md)
  — good-enough keyword search: the web console sorts by relevance, scoring each manual by its
  three best passages (right manual on page 1 for 12 → 24 of 24 keyword searches), one query reader obeys quotes, AND/OR/NOT and identifiers in
  every front door, a synonym list whose core is plain-English package names ("blood bank" finds
  VBECS; 91 → 242 of 242 drafted names find their application on page 1), keyword-form test
  questions, and search-box suggestions. Summary cards searched first, pseudo-relevance feedback
  and a link-count prior were measured and rejected. Measurements: `scripts/mcp_review/` →
  `../reports/mcp-review-*.json`.
- **Proposed (2026-11-06), for review, nothing built:** [`proposals/vdocs-mcp-interface-design.md`](proposals/vdocs-mcp-interface-design.md)
  — the MCP server and the other machine front doors (Go CLI, vdocs-web API) measured against the
  code and against a machine-consumer metric set: nine drifted claims, identifier and paraphrase
  weak spots, no way to read a cited passage, and fourteen ranked recommendations. Its
  search-syntax and vocabulary parts (R9, R10, R12, R14) are superseded by the five-fixes proposal
  above. Measurements: `scripts/mcp_review/` → `../reports/mcp-review-*.json`.
- **Proposed (2026-11-05); producer and web mode built, identity continuity next:** [`proposals/inventory-browser-proposal.md`](proposals/inventory-browser-proposal.md)
  — the whole VDL catalog (9,080 records) as an Inventory mode in vdocs-web, with Library facets
  plus gold / disposition / reason and each document's own last-updated date, carried in `index.db`.
  All decisions taken 2026-11-05. Step 0 (2026-11-05) committed the measurements:
  `scripts/inventory_measurements.py` → [`../reports/inventory-browser-measurements.md`](../reports/inventory-browser-measurements.md)
  (kickoff in [`prompts/historical/`](prompts/historical/inventory-browser-step0-kickoff.md)). Step 1,
  the producer, landed 2026-11-05 (kickoff in
  [`prompts/historical/`](prompts/historical/inventory-browser-step1-kickoff.md)): `index.db` carries
  `v_inventory` (one row per listing, with disposition and reason), each document's
  `last_updated`, read contract 1.7, and a doctor freshness check; the lake was rebuilt and every
  step 0 figure held. Step 2 closed the same day: the operator took the web mode's go (D5)
  without the planned month of use (its unrun kickoff is in
  [`prompts/historical/`](prompts/historical/inventory-browser-step2-kickoff.md)). Step 4, the
  Inventory mode in vdocs-web, landed the same day, before identity continuity at the operator's
  call (D1): until that lands, the 14 re-filed ISS guides show twice, labelled. Step 3 — a short
  proposal for identity continuity across re-filing — is next:
  [`prompts/inventory-browser-step3-kickoff.md`](prompts/inventory-browser-step3-kickoff.md).
- ~~**Active workstream:** SKL~~ — **the search-facing half is RULED AGAINST (2026-08-04)**, see
  [`proposals/vdocs-quality-synonym-layer/`](proposals/vdocs-quality-synonym-layer/) §10. S0–S3
  landed and the termbase + glossary projections are live and keep working; S4/S5 are **not** to be
  started as written. [`proposals/skl-implementation-plan.md`](proposals/skl-implementation-plan.md)
  is now read-for-history on the equivalence question.
- **Active workstream — the `vdocs-quality-*` family** (five efforts, each with its own proposal,
  plan, tracker and prompts; [programme rationale + ordering](proposals/search-quality-and-scope-integrity-implementation-plan.md),
  [rollup](proposals/search-quality-and-scope-integrity-tracker.md)):
  1. [`vdocs-quality-crawl-integrity/`](proposals/vdocs-quality-crawl-integrity/) — nothing watches
     the front door, and a fetched document can be lost to a VA relabel (**blocks all others**)
  2. [`vdocs-quality-report-card/`](proposals/vdocs-quality-report-card/) — the answer key we grade
     search with is stale (**blocks 3–5**)
  3. [`vdocs-quality-response-ranking/`](proposals/vdocs-quality-response-ranking/) — the right
     answer is found, then shown below the fold (**the user-visible win**)
  4. [`vdocs-quality-synonym-layer/`](proposals/vdocs-quality-synonym-layer/) — the synonym feature
     knows one synonym (R‑12). **RULED 2026-08-04: stop** — the queue was 307 candidates, not 4,415,
     and approving all of it buys one equivalence; the bottleneck is the projection, not curation
  5. [`vdocs-quality-pattern-miner/`](proposals/vdocs-quality-pattern-miner/) — ~81,500 suggestions
     per rebuild, 29 accepted
  6. [`vdocs-quality-vdl-observatory/`](proposals/vdocs-quality-vdl-observatory/) — the source is
     copied but never recorded: no timeline, no lifecycle signal (**snapshots can't be backdated**)
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
