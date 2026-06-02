# vdocs — Phase 4 kickoff (gold derive: consolidate · index · relate · manifest)

Paste the fenced block below into a **fresh session** opened in `~/projects/vdocs` to start Phase 4.
Everything outside the fence is for you (the human), not the model.

Snapshot at hand-off: branch `fix/compliance-remediation-pre-phase4`, **HEAD `e1e3b44`**, **414 test
functions, 100% coverage, `make check` green**. Phases 1–3 (PRs #3/#4/#5) are merged to `master`;
the two pre-Phase-4 compliance commits on this branch (`a73fcc1`, `e1e3b44`) are **not yet merged** —
**merge this branch to `master` first**, then branch Phase 4 off the new tip.

---

```
I'm continuing development of `vdocs` (~/projects/vdocs), the greenfield v2 rewrite of the
`vista-docs` pipeline: it turns the VA VistA Document Library (DOCX manuals) into (1) a clean,
human-browsable markdown corpus on GitHub and (2) a machine-discoverable knowledge base served
over MCP. We are starting **Phase 4 — gold derive**. The architecture is already decided and
written down; your job is to BUILD it, not redesign it.

## First, read these (in order)
1. ~/claude/FILESYSTEM.md and ~/projects/vdocs/CLAUDE.md (project conventions + toolchain).
2. docs/vdocs-design.md — THE architectural source of truth. If code and it disagree, the doc is
   the bug report. For Phase 4, read closely:
   - §8 (the stage table — AUTHORITATIVE) rows: consolidate, index, relate, manifest, and the
     Notes beneath the table (esp. "consolidate captures the version rollup; push defers the git
     replay"; "index/relate/embed are the derived machine views"; "the search corpus is anchor-only").
   - §6.6 (version lineage: one anchor document, patch history captured for later git replay) — the
     spec for `consolidate`.
   - §5.5 (the derived stores; stable IDs; no naming collisions) — the spec for `index.db` and the
     ID scheme every downstream view references.
   - §14.1–14.4 (machine interface; the discovery descriptor) — the spec for `manifest`'s
     corpus-manifest.json + discovery.json, and §14.6 (search corpus = anchor-only) for the
     is_latest / FTS5 design `index` must honor.
3. docs/vdocs-implementation-tracker.md — the whole-pipeline status tracker (Overall status, the
   per-phase stage tables, Lessons Learned, Change Log). READ THE LESSONS — they encode hard-won
   real-data findings. Phase 4 is rows 76–83; Phases 1–3 are ✅ and merged.
4. docs/fidelity-framework.md (QA companion) and docs/vdl-crawl-spec.md (inventory enrichment spec;
   it defines `anchor_key`/`group_key`, which `consolidate` groups on).

## What's already built (Phases 1–3, all ✅ on master)
- SPINE: kernel/ (one each: text, frontmatter, fingerprint, cas, lineage, db, http, discovery,
  ids, table, csv, registry), Pydantic config + ArtifactContract registry, generic orchestrator
  (preflight→run→postflight + state.db:stage_runs; contract_ver gating is real, §7.3).
- INVENTORY MEDALLION: crawl → catalog → serve-inventory (gold inventory + the HARD GATE = the
  fetch gate) + acquisitions + inventory_status + CLI. catalog.enriched carries `group_key` +
  version-free `anchor_key` per doc (the §6.6 version-group keys consolidate needs).
- DOCUMENT SILVER (Phase 3): convert (DOCX-only; Pandoc + Docling-routed cprsguium) → discover
  (boilerplate/(doc_type,era)-template/phrase/glossary/structures miners → registries/, proposals
  only) → enrich (identity FM baked into body.md + index.db:doc_meta_staged rows) → normalize
  (heading recovery + level inference, revision-history → history.yaml sidecar, tables → tables/*.csv,
  boilerplate REFERENCE, template STRIP + template_id stamp, legacy-TOC strip, TOC regen with
  GitHub-slug anchors, refs.yaml anchor-map sidecar, source_sha256). Run end-to-end on a real
  469-doc VA corpus.

## Phase 4 scope — build in this order (each its own increment, TDD, doc-first)
The §8 contracts are authoritative; quoting them so you build to the doc:

1. **consolidate** (🥇 DOC, §6.6) — requires `text@normalized` + `assets`; produces `consolidated`.
   Gather all members of each version group (key = `anchor_key`), order oldest→newest, collapse to
   ONE anchor document at a stable version-free path whose body is the LATEST normalized body;
   capture the ordered lineage + RETAIN every prior normalized body (content-addressed) as
   travel-with sidecars; flag the newest member. Append-only capture (a later patch appends one
   entry, retains the prior body, rewrites nothing). This is the captured replay source for the
   deferred `push --replay-history`; do NOT build the git replay now.
2. **index** (🥇 DOC, §5.5) — requires `text@normalized` + `consolidated` (for grouping); produces
   `index.db`: `documents`, `doc_sections` (ALL sections, each carrying `is_latest`) + **FTS5 over
   is_latest sections only** (the search surface, §14.6), entity tables, quality, views — every unit
   keyed by a **stable ID**. Consume the `doc_meta_staged` rows `enrich` already writes and the
   `refs.yaml` anchor maps `normalize` already emits (stable_section_id = "<doc_id>/<slug>"). Build
   the DB with `kernel/db.build_atomic` (promoted last session precisely for index/relate/embed).
3. **relate** (🥇 DOC) — requires `index.db` (documents, entities, sections); produces
   `index.db:relations` — the knowledge graph edges (doc↔entity, doc↔doc xref, entity↔entity). Adds
   only edges over already-extracted entities; cheap and re-runnable.
4. **manifest** (🥇 DOC, §14.4) — requires `consolidated` + `index.db` + `vectors.db` (**optional**,
   Phase 6) + `state.db` (lineage); produces `corpus-manifest.json` + `discovery.json` (corpus schema,
   counts, the stable-ID scheme, embedding-model id+version, MCP capabilities — the agent "front door").
   With no `vectors.db` yet, omit the embedding fields + mark semantic search unavailable (§14.4).

## Design seams — RESOLVED in the design doc (read the cited sections; don't re-litigate)
The three seams the earlier draft flagged are now decided and written into `docs/vdocs-design.md`.
Build to these; if you disagree, change the doc first (don't diverge in code):
- **The two revision sidecars are now distinct names (§6.4 / §6.6 / §5.2).** `normalize` emits each
  version's own revision-history table as **`revisions.yaml`** (per-document, silver); `consolidate`
  emits the **`history.yaml`** version-group lineage (gold anchor bundle) that FOLDS each member's
  `revisions.yaml` + a content-addressed ref to its retained body. `history.yaml` is reserved for the
  lineage (the dominant meaning across §6.6/§13/ADR-016). **PHASE-4 STEP 0 (small code task):**
  `normalize` currently still WRITES `history.yaml` (`stages/normalize/stage.py` + `revision_pure.py`
  + tests) — rename that sidecar to `revisions.yaml` first (TDD: flip the test, confirm red, rename,
  green, `make check`), so `consolidate` can read `revisions.yaml` and own `history.yaml` cleanly.
  This is the only carried-over code change; do it as the first commit of the phase.
- **Entity extraction lives in `index`, vocabulary is DATA (§8 note + §9.6/§9.7 + §5.5).** New curated
  `registries/entities` (VistA domain: package namespaces, FileMan file numbers, routines, options,
  RPCs, protocols, HL7 segments, mail groups, globals, build/patch ids — disposition **EXTRACT**,
  seeded from domain knowledge, augmentable by `discover` corpus-frequency candidates). A generic pure
  pass in `index` (`entities_pure.py`) recognizes them over normalized bodies → `index.db:entities`
  keyed by `(type, canonical-name)` (§5.5). `relate` only adds edges. No entity patterns hard-coded in
  stage code (tenet #13). Seed `registries/entities/` with a high-confidence starter set + README stub.
- **`manifest`'s `vectors.db` input is now OPTIONAL (§8 manifest row + §14.4).** Build manifest in
  Phase 4 against `consolidated` + `index.db` alone: omit the embedding-model id+version and mark
  semantic search **unavailable** in the capability manifest; a Phase-6 re-run (once `embed` writes
  `vectors.db`) fills those fields and flips the capability on. Same "optional produces don't gate"
  rule the orchestrator already applies to `convert`'s `assets` — don't fabricate the dependency.
- **Stable IDs are the contract (§5.5/§14.5) — not a seam, just hold the line.** doc_id =
  `app_code:doc_slug`; section id = `<doc_id>/<slug>` (normalize's `refs.yaml` already uses it);
  entity id = `(type, canonical-name)`. `index` OWNS ID persistence — published-markdown anchors,
  FTS5/section rows, graph nodes, and (later) vector keys all reference the SAME ids. Keep consistent
  across consolidate→index→relate.

## `consolidate` build recipe (the first stage — TDD, §9.2)
- **Pure core first** (`stages/consolidate/consolidate_pure.py`, zero I/O): grouping + ordering +
  lineage-merge over plain values — `group_by_anchor_key(bundles) -> groups`,
  `order_members(group) -> ordered` (patch number, then official revision date),
  `merge_history(existing, ordered) -> history` (APPEND-ONLY: a later run promoting a new latest body
  appends one entry + retains the prior body, rewrites nothing). Realistic multi-patch fixtures (e.g.
  one logical doc at 5.1 → 5.2 → 5.3). Failing unit test first, confirm red, implement, green.
- **Thin I/O driver** (`stages/consolidate/stage.py`): a `Stage` (`requires=[TEXT_NORMALIZED, ASSETS]`,
  `produces=[CONSOLIDATED]`, `SKIP_IF_UNCHANGED`). Reuse the kernel — `cas` for content-addressed
  prior-body retention + atomic writes, `frontmatter`, `lineage`. No copy-paste across stages (§9.2);
  if a primitive isn't in `kernel/`, add it there.
- Add the **`CONSOLIDATED` contract** to `contracts/registry.py` (a `TREE_*` over the gold anchor
  bundle) and the gold path to `config.py` if not already derived. The orchestrator derives DAG order
  from the §8 table — don't hand-wire edges.
- **Integration test through the orchestrator:** seed two normalized bundles that are patches of one
  logical doc → assert one anchor bundle at the version-free path, latest body promoted, `history.yaml`
  with both versions ordered + a CAS ref to the older retained body + each member's `revisions.yaml`,
  prior body present in CAS.
- Land it green, flip the tracker row, append a Change Log entry, THEN move to `index`.

## Real-corpus loop (IMPORTANT — don't develop in a vacuum)
The document-medallion stages are developed against REAL VA docs. The lake at ~/data/vdocs is
populated with 469 real docs seeded offline from v1's already-fetched ~/data/vista-docs/raw/ via
`python scripts/seed_from_v1.py` (no live crawl), already carried through convert→...→normalize.
v1 (~/projects/vista-docs) is the authoritative reference for any ported logic. Pattern: process
the real corpus through each new stage, see what actually breaks, fix, re-verify. Real data has
caught bugs fixtures hid every phase so far. Verify a consistent lake skips:
`vdocs run --from convert --to normalize` (no --force) should SKIP all four.

## Conventions (hard rules)
- TDD, no exceptions: write the failing test first → confirm RED → implement → confirm green →
  `make check`. Pure transforms also get Hypothesis property tests (idempotency/round-trip).
- Pure functions in *_pure.py (zero I/O); thin I/O drivers in stage.py; ONE shared kernel/
  (copy-paste across stages is a build-breaking review failure). No top-level .py under src/vdocs/.
- Discovery-is-data: recurring/curatable patterns live in version-controlled registries/, never
  hard-coded (tenet #13). The DB-build atomicity primitive is kernel/db.build_atomic — reuse it.
- make check = ruff (line 100; E,F,I) + mypy + pytest (random order) + coverage; keep it 100%.
- Add deps PER PHASE only as the design requires (`uv add … && uv lock`, commit the lock). Phase 4
  likely needs NO new deps — index/relate are sqlite stdlib + FTS5, manifest is JSON. sqlite-vec +
  MCP SDK belong to Phase 6 (embed/serve-mcp); don't add them yet.
- Update docs/vdocs-design.md in the SAME commit whenever a stage's inputs/outputs/CLI change. After
  each stage: flip its tracker row (☐→✅), append a Change Log entry, record any Lessons Learned.
- Branch Phase 4 off master (after merging the pre-Phase-4 compliance branch); commit only when
  asked. Commits end with:
  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
- Lake gotcha: run downstream stages as ONE `vdocs run --from X --to Y` pass, not separate --force
  invocations, or the cheap (size:mtime) fingerprints go stale and preflight refuses.

## Deliverable for this session
Start with `consolidate`. First read §6.6 + the §8 consolidate row, resolve the "two history.yaml"
seam in the design doc, then write a short plan (the version-group grouping, the anchor-document +
retained-prior-body capture, the append-only history.yaml layout, the contract + config + CLI) and
implement it TDD. Land consolidate green (tests + make check), flip its tracker row, append a Change
Log entry, then proceed to index. End with a one-paragraph status + what the next increment needs.

Please begin by reading the design doc + the implementation tracker, confirm current state
(`make check`), then propose the consolidate plan and proceed TDD-style.
```

---

## Notes for whoever resumes (not part of the prompt)

- **Why this file exists.** The implementation tracker's "Current focus" line and the Phase-4 row
  both point here (`docs/prompts/next-session-phase-4-kickoff.md`); this is that referenced kickoff.
- **Merge first.** `fix/compliance-remediation-pre-phase4` is 2 commits ahead of `master`
  (`a73fcc1` compliance findings, `e1e3b44` legacy-TOC-behind-oversized-heading). Open/merge its PR
  before branching Phase 4, so Phase 4 starts from a clean `master` tip.
- **Three genuine seams** are called out in the prompt because they're the spots the design is thin
  or forward-referencing: (1) the per-doc vs per-group `history.yaml` grain, (2) the entity
  vocabulary + where extraction lives, (3) manifest's `vectors.db` requirement that Phase 6 hasn't
  satisfied yet. Each is a "decide + amend the design doc first" item, consistent with how Phases
  1–3 handled input seams (e.g. discover's (doc_type, era) join seam was raised before coding).
- **Build order within the phase** mirrors the dependency spine: consolidate → index → relate →
  manifest. index consumes `doc_meta_staged` (enrich) + `refs.yaml` (normalize), both already
  produced on the real lake, so index has real inputs from day one.
- **Pipeline tally after Phase 4** would be 12 ✅ (8 + the 4 gold-derive stages). Phase 5 (gold
  deliver: fidelity·publish·validate·push·analyze) is next; the `validate` hard gate is the
  deliver-side analogue of the serve-inventory gate.
