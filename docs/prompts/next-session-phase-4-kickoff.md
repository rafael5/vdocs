# Implementation prompt — Phase 4: gold derive (consolidate · index · relate · manifest)

> Paste the fenced block below into a **fresh, clean session** opened in `~/projects/vdocs`.
> Everything outside the fence is for you (the human), not the model. The prompt is self-contained
> except for the repo — **read the files it points at before writing code.** This is a
> **multi-increment** task: each stage is its own TDD cycle and its own commit; keep `make check`
> green between increments. **Do NOT start Phase 5+ stages** (`fidelity`/`publish`/`validate`/`push`/
> `analyze`/`embed`/`serve-mcp`) — out of scope.

Snapshot at hand-off: branch `fix/compliance-remediation-pre-phase4`, **HEAD `9ebb68e`**, **19 commits
ahead of `master`**, **458 test functions, branch cov 99.7% (gate ≥95%), `make check` green**. Phases
1–3 (the 8 stages) are ✅; the pre-Phase-4 **hardening pass is complete on this branch** (reliability
R1–R9, redundancy D1–D5, the 7-invariant property suite, the `revisions.yaml` rename, the drift-doc
reconciliation) and **not yet merged**. **Merge this branch to `master` first**, then branch Phase 4
off the new tip.

> **Already done — do NOT redo.** The old "Phase-4 step 0" (`normalize`'s sidecar `history.yaml` →
> `revisions.yaml`) **landed in the hardening pass** (commit on this branch; `normalize` now emits
> `revisions.yaml`, confirmed in `stages/normalize/stage.py`). `history.yaml` is free for
> `consolidate` to own. The remaining `index` prerequisite — **`registries/entities/`** — does **not**
> exist yet; you create it when you build `index` (Increment 2).

---

```
I'm continuing development of `vdocs` (~/projects/vdocs), the greenfield v2 rewrite of the
`vista-docs` pipeline: it turns the VA VistA Document Library (DOCX manuals) into (1) a clean,
human-browsable markdown corpus on GitHub and (2) a machine-discoverable knowledge base served
over MCP. We are starting **Phase 4 — gold derive**. The architecture is already decided and
written down; your job is to BUILD it to the design, not redesign it.

## Phase 0 — prepare (do this first, before any stage code)

1. Read `~/claude/FILESYSTEM.md`, `~/projects/vdocs/CLAUDE.md`, and
   `~/claude/memory/MEMORY.md` (+ any vdocs-relevant memory files). Project rules: **hard TDD**
   (failing test first → confirm RED → implement → green → `make check`), pure logic in `*_pure.py`
   (zero I/O), thin I/O in `stage.py`, a primitive used by ≥2 stages lives in `kernel/` (§9.2 —
   copy-paste across stages is a build-breaking review failure), no `print()` (structlog), Makefile
   `.venv/bin/` prefixes. Commit per increment; **do NOT push unless asked.** Commits end with:
   `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
2. Confirm the starting state is clean: `make check` green, then read
   `docs/vdocs-implementation-tracker.md` (Overall status, the per-phase stage tables, **Lessons
   Learned — they encode hard-won real-data findings**, Change Log conventions = newest-first). Phase
   4 is rows ☐ 0/4; Phases 1–3 are ✅.
3. **Merge first.** `fix/compliance-remediation-pre-phase4` is 19 commits ahead of `master` (Phases
   1–3 + the full pre-Phase-4 hardening pass). Open/merge its PR (or fast-forward) so `master` is the
   clean tip, then create the Phase-4 branch off it. If you cannot merge (e.g. needs review), say so
   and branch Phase 4 off the current branch HEAD instead — note the choice.
4. Read `docs/vdocs-design.md` — THE architectural source of truth. **If code and it disagree, the
   doc is the bug report.** For Phase 4 read closely (grep for the exact heading — line numbers
   drift):
   - **§8** the stage table (AUTHORITATIVE) rows: `consolidate`, `index`, `relate`, `manifest`, and
     the Notes beneath it ("consolidate captures the version rollup; push defers the git replay";
     "index/relate/embed are the derived machine views"; "the search corpus is anchor-only").
   - **§6.6** version lineage (one anchor document; patch history captured for later git replay) —
     the spec for `consolidate`.
   - **§5.5** the derived stores; stable IDs; no naming collisions — the spec for `index.db` and the
     ID scheme every downstream view references.
   - **§14.1–14.4** machine interface + the discovery descriptor — the spec for `manifest`'s
     `corpus-manifest.json` + `discovery.json`; **§14.6** (search corpus = anchor-only) for the
     `is_latest` / FTS5 design `index` must honor.
   - **§9.2** anti-duplication; **§9.6/§9.7** discovery-is-data + the registry index; **§12** testing
     strategy; **§17** the phased build plan (Phase 4 = step 4: "consolidate → index → relate →
     manifest").
5. Read `docs/fidelity-framework.md` (QA companion) and `docs/vdl-crawl-spec.md` (it defines
   `anchor_key`/`group_key`, which `consolidate` groups on — `catalog.enriched` already carries them
   per doc, confirmed in `stages/catalog/enrich_pure.py`).

## What's already built (Phases 1–3 ✅ + hardening, all on this branch)

- SPINE: `kernel/` (one each: text, frontmatter, fingerprint, cas, lineage, db, http, discovery,
  ids, table, csv, registry, **markdown** [the unified `HEADING_RE`/`iter_headings`/`strip_tags`
  home added in hardening]), Pydantic config + `ArtifactContract` registry, generic orchestrator
  (preflight→run→postflight + `state.db:stage_runs`; `contract_ver` gating is real, §7.3).
- INVENTORY MEDALLION: crawl → catalog → serve-inventory (gold inventory + the HARD GATE = the fetch
  gate) + acquisitions + inventory_status + CLI. `catalog.enriched` carries `group_key` +
  version-free `anchor_key` per doc (the §6.6 version-group keys `consolidate` needs).
- DOCUMENT SILVER (Phase 3): convert (DOCX-only; Pandoc + Docling-routed cprsguium) → discover
  (boilerplate / (doc_type,era)-template / phrase / glossary / structures miners → `registries/`,
  proposals only) → enrich (identity FM baked into `body.md` + `index.db:doc_meta_staged` rows) →
  normalize (heading recovery + level inference, revision-history → **`revisions.yaml`** sidecar,
  tables → `tables/*.csv`, boilerplate REFERENCE, template STRIP + `template_id` stamp, legacy-TOC
  strip incl. >6-hash headings, TOC regen with GitHub-slug anchors, `refs.yaml` anchor-map sidecar,
  `source_sha256`). Run end-to-end on the real 469-doc VA corpus.
- HARDENING (this branch): `atomic_write` content-skip + tree-level atomicity + stale-output pruning
  (so `SKIP_IF_UNCHANGED` honestly skips no-op re-runs and orphans are pruned); `build_atomic` WAL
  hardening + deterministic strong sqlite fingerprint; crawl/fetch transport-error retry;
  per-document error isolation in convert/normalize with a systemic-rate gate; `fetch` merges
  `raw/index.json`; the 7-invariant property suite + `--cov-branch`. **Reuse these — don't
  reinvent.** In particular: build `index.db`/relations with `kernel.db.build_atomic`; write tree
  outputs through the same content-skip/atomic-rename path `convert`/`normalize` use.

## Decisions already made (defaults — do NOT re-litigate; the design doc encodes them)

These were the thin/forward-referencing seams in earlier drafts; they are now resolved **in
`docs/vdocs-design.md`**. Build to them. If you genuinely disagree, **change the doc first** (doc-first),
don't diverge in code.

- **D1 — the two revision sidecars are distinct names (§6.4 / §6.6 / §5.2), and the rename is DONE.**
  `normalize` already emits each version's own revision table as **`revisions.yaml`** (per-document,
  silver). `consolidate` emits the **`history.yaml`** version-group lineage (gold anchor bundle) that
  FOLDS each member's `revisions.yaml` + a content-addressed ref to its retained body. `history.yaml`
  is reserved for the lineage (the dominant meaning across §6.6/§13/ADR-016). No carried-over rename
  to do.
- **D2 — entity extraction lives in `index`; the vocabulary is DATA (§8 note + §9.6/§9.7 + §5.5).**
  Create curated **`registries/entities/`** (VistA domain: package namespaces, FileMan file numbers,
  routines, options, RPCs, protocols, HL7 segments, mail groups, globals, build/patch ids —
  disposition **EXTRACT**, seeded from domain knowledge, augmentable by `discover` corpus-frequency
  candidates). A generic pure pass in `index` (`entities_pure.py`) recognizes them over normalized
  bodies → `index.db:entities` keyed by `(type, canonical-name)` (§5.5). `relate` only adds edges.
  **No entity patterns hard-coded in stage code** (tenet #13). Seed `registries/entities/` with a
  high-confidence starter set + a README stub when you build `index`.
- **D3 — `manifest`'s `vectors.db` input is OPTIONAL (§8 manifest row + §14.4).** Build `manifest`
  in Phase 4 against `consolidated` + `index.db` alone: omit the embedding-model id+version and mark
  semantic search **unavailable** in the capability manifest; a Phase-6 re-run (once `embed` writes
  `vectors.db`) fills those fields and flips the capability on. Same "optional produces don't gate"
  rule the orchestrator already applies to `convert`'s `assets` — don't fabricate the dependency.
- **D4 — stable IDs are the contract (§5.5/§14.5); hold the line, don't redesign.**
  `doc_id = app_code:doc_slug`; section id = `<doc_id>/<slug>` (normalize's `refs.yaml` already uses
  it); entity id = `(type, canonical-name)`. **`index` OWNS ID persistence** — published-markdown
  anchors, FTS5/section rows, graph nodes, and (later) vector keys all reference the SAME ids. Keep
  consistent across consolidate→index→relate→manifest.

## Phase 4 scope — build in this dependency order (each its own increment: TDD, doc-first, own commit)

The §8 contracts are authoritative; quoting them so you build to the doc.

### Increment 1 — `consolidate` (🥇 DOC, §6.6) — requires `text@normalized` + `assets`; produces `consolidated`

Gather all members of each version group (key = `anchor_key`), order oldest→newest, collapse to ONE
anchor document at a stable **version-free** path whose body is the LATEST normalized body; capture
the ordered lineage + RETAIN every prior normalized body (content-addressed, via `kernel.cas`) as
travel-with sidecars; flag the newest member. **Append-only capture**: a later patch appends one
entry + retains the prior body, rewrites nothing. This is the captured replay source for the deferred
`push --replay-history`; do NOT build the git replay now.

Build recipe (§9.2):
- **Pure core first** (`stages/consolidate/consolidate_pure.py`, zero I/O): `group_by_anchor_key`,
  `order_members` (patch number, then official revision date), `merge_history(existing, ordered)`
  (APPEND-ONLY). Realistic multi-patch fixtures (one logical doc at 5.1 → 5.2 → 5.3). Failing unit
  test first → RED → implement → green.
- **Thin I/O driver** (`stages/consolidate/stage.py`): a `Stage`
  (`requires=[TEXT_NORMALIZED, ASSETS]`, `produces=[CONSOLIDATED]`, `SKIP_IF_UNCHANGED`). Reuse the
  kernel — `cas` for content-addressed prior-body retention + the hardened atomic/content-skip tree
  write, `frontmatter`, `lineage`. Fold each member's `revisions.yaml`. No copy-paste; if a primitive
  isn't in `kernel/`, add it there.
- Add the **`CONSOLIDATED` contract** to `contracts/registry.py` (a `TREE_*` over the gold anchor
  bundle) and the gold path to `config.py` if not derived. The orchestrator derives DAG order from
  the §8 table — **don't hand-wire edges.** Add the `consolidate` CLI command.
- **Integration test through the orchestrator:** seed two normalized bundles that are patches of one
  logical doc → assert one anchor bundle at the version-free path, latest body promoted, `history.yaml`
  with both versions ordered + a CAS ref to the older retained body + each member's `revisions.yaml`,
  prior body present in CAS. Idempotent re-run skips.
- Land green, flip the tracker row (☐→✅), append a Change Log entry, record any Lessons. THEN `index`.

### Increment 2 — `index` (🥇 DOC, §5.5/§14.6) — requires `text@normalized` + `consolidated`; produces `index.db`

`index.db`: `documents`, `doc_sections` (ALL sections, each carrying `is_latest`) + **FTS5 over
`is_latest` sections only** (the search surface, §14.6), `entities` tables, quality, views — every
unit keyed by a **stable ID** (D4). Consume the `doc_meta_staged` rows `enrich` already writes and
the `refs.yaml` anchor maps `normalize` already emits (`stable_section_id = "<doc_id>/<slug>"`).
Build the DB with `kernel.db.build_atomic` (hardened for WAL + deterministic strong fingerprint —
promoted precisely for index/relate/embed).

- First create **`registries/entities/`** (D2): a high-confidence starter set across the VistA entity
  types + a README stub describing the schema and the EXTRACT disposition.
- **Pure core** (`stages/index/entities_pure.py` + section/doc shredding pures, zero I/O): generic
  recognizers driven by the registry vocabulary (no hard-coded patterns), section/doc row builders.
  Failing unit test first.
- **Thin I/O driver** builds `index.db` via `build_atomic`; the `INDEX_DB` contract + config path +
  CLI. Integration test: build over the seeded bundles, assert `documents`/`doc_sections` row counts,
  `is_latest` flagging, FTS5 returns only is_latest sections, entities keyed by `(type, canonical)`,
  stable ids match `refs.yaml`.

### Increment 3 — `relate` (🥇 DOC, §8) — requires `index.db` (documents, entities, sections); produces `index.db:relations`

The knowledge-graph edges (doc↔entity, doc↔doc xref, entity↔entity). Adds ONLY edges over
already-extracted entities; cheap and re-runnable. Pure edge-derivation core + thin driver appending
the `relations` table (+ contract/CLI). Integration test asserts the expected edges over the seeded
graph; re-run is idempotent.

### Increment 4 — `manifest` (🥇 DOC, §14.4) — requires `consolidated` + `index.db` + `state.db`; `vectors.db` OPTIONAL (D3)

Produces `corpus-manifest.json` + `discovery.json` (corpus schema, counts, the stable-ID scheme,
embedding-model id+version, MCP capabilities — the agent "front door"). With no `vectors.db` yet,
omit the embedding fields + mark semantic search **unavailable** (§14.4). Pure assembler core + thin
driver + contract/CLI. Integration test asserts the JSON schema, counts match `index.db`, and the
semantic-search-unavailable flag.

## Real-corpus loop (IMPORTANT — don't develop in a vacuum)

The document-medallion stages are developed against REAL VA docs. The lake at `~/data/vdocs` is the
canonical `documents/{bronze,assets,silver}` + `inventory/{bronze,silver,gold}` layout, populated
with 469 real docs carried through convert→…→normalize. v1 (`~/projects/vista-docs`) is the
authoritative reference for any ported logic. Pattern: process the real corpus through each new stage,
see what actually breaks, fix, re-verify — real data has caught bugs fixtures hid every phase so far.

After all four stages are green, regenerate the gold-derive layer from the existing silver (the lake
is deterministic from bronze; **do NOT re-crawl or re-fetch** — network stages, immutable inputs):

    .venv/bin/vdocs run --from consolidate --to manifest --force

Verify (report counts): consolidated anchor bundles == number of version groups; each carries
`history.yaml` folding its members' `revisions.yaml` + CAS refs to retained prior bodies; `index.db`
has the expected `documents`/`doc_sections`/`entities`/`relations` row counts and FTS5 over is_latest
only; `corpus-manifest.json` + `discovery.json` present with semantic search marked unavailable. Then
confirm a clean re-run skips: `.venv/bin/vdocs run --from consolidate --to manifest` (no `--force`)
should SKIP all four (the hardened content-skip fingerprints make this honest).

## Conventions (hard rules)

- TDD, no exceptions: failing test first → RED → implement → green → `make check`. Pure transforms
  also get Hypothesis property tests (idempotency/round-trip) under `tests/property/`.
- Pure functions in `*_pure.py` (zero I/O); thin I/O drivers in `stage.py`; ONE shared `kernel/`
  (copy-paste across stages is a build-breaking review failure). No top-level `.py` under
  `src/vdocs/`.
- Discovery-is-data: recurring/curatable patterns live in version-controlled `registries/`, never
  hard-coded (tenet #13). DB-build atomicity primitive is `kernel.db.build_atomic` — reuse it.
- `make check` = ruff (line 100; E,F,I) + mypy + pytest (random order) + coverage (≥95%, branch).
- Add deps PER PHASE only as the design requires (`uv add … && uv lock`, commit the lock). **Phase 4
  needs NO new deps** — index/relate are sqlite stdlib + FTS5, manifest is JSON. sqlite-vec + MCP SDK
  belong to Phase 6; don't add them.
- Update `docs/vdocs-design.md` in the SAME commit whenever a stage's inputs/outputs/CLI change.
  After each stage: flip its tracker row (☐→✅), append a newest-first Change Log entry, refresh the
  test-count line, record any Lessons Learned.
- Lake gotcha: run downstream stages as ONE `vdocs run --from X --to Y` pass, not separate `--force`
  invocations, or the cheap (size:mtime) fingerprints go stale and preflight refuses.

## Definition of done (Phase 4)

- 4 stages built (consolidate · index · relate · manifest), each TDD (RED→green) with unit +
  orchestrator-integration tests, each its own commit + tracker row flipped ☐→✅ + Change Log entry.
- `registries/entities/` seeded (starter set + README); no entity pattern hard-coded in stage code.
- Stable-ID scheme (D4) consistent across all four stages and matching `normalize`'s `refs.yaml`.
- `consolidate` owns `history.yaml` (version-group lineage, append-only, retained prior bodies in
  CAS); `manifest` marks semantic search unavailable (no `vectors.db` yet).
- Gold-derive layer regenerated on the real 469-doc lake (no re-fetch); a no-`--force` re-run SKIPs
  all four; verification counts reported.
- `make check` green throughout (ruff · mypy · pytest random-order · branch cov ≥95%). **Do NOT push
  unless asked.** Pipeline tally after Phase 4 = 12 ✅ (8 + the 4 gold-derive stages).
- **No Phase 5+ work.** Where a fix and the design disagree, **fix the design doc first** (doc-first)
  and say so in the commit.

Please begin with Phase 0: read the design doc + tracker, confirm `make check` is green, handle the
merge, then propose the `consolidate` plan and proceed TDD-style.
```

---

## Notes for whoever resumes (not part of the prompt)

- **Why this file exists.** The implementation tracker's "Current focus" line and the Phase-4 row
  both point here (`docs/prompts/next-session-phase-4-kickoff.md`). This is that referenced kickoff,
  **refreshed after the pre-Phase-4 hardening pass** (HEAD `9ebb68e`, 458 tests). The earlier draft's
  "Phase-4 STEP 0" (the `history.yaml`→`revisions.yaml` rename) is **obsolete** — it landed during
  hardening; the prompt above reflects that.
- **Merge first.** `fix/compliance-remediation-pre-phase4` is 19 commits ahead of `master` (Phases
  1–3 + the whole hardening pass). Merge its PR before branching Phase 4 so Phase 4 starts from a
  clean `master` tip.
- **The three design seams are RESOLVED** in `docs/vdocs-design.md` and restated as D1–D3 in the
  prompt (the two-sidecar names, the entity vocabulary + where extraction lives, manifest's optional
  `vectors.db`). They are "build to the doc; change the doc first if you disagree" items, not open
  questions. D4 (stable IDs) is the cross-stage contract to hold.
- **Build order mirrors the dependency spine:** consolidate → index → relate → manifest. `index`
  consumes `doc_meta_staged` (enrich) + `refs.yaml` (normalize), both already on the real lake, so it
  has real inputs from day one. Reuse the hardened kernel — `build_atomic` for the DBs, the
  content-skip/atomic-rename tree writer for `consolidated`.
- **Pipeline tally after Phase 4** would be 12 ✅. Phase 5 (gold deliver: fidelity·publish·validate·
  push·analyze) is next; the `validate` hard gate is the deliver-side analogue of the serve-inventory
  gate.
</content>
</invoke>
