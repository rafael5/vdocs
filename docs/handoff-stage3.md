# vdocs — fresh-session handoff (end of Phase 3 silver)

Paste the block below into a new session to continue this work. Snapshot: **HEAD `565b697`,
275 tests, 100% coverage, `make check` green.**

---

```
I'm continuing development of `vdocs` (~/projects/vdocs), the greenfield v2 rewrite of the
`vista-docs` pipeline: it turns the VA VistA Document Library (DOCX manuals) into a clean
markdown corpus + a machine-discoverable knowledge base served over MCP.

## First, read these (in order)
1. ~/claude/FILESYSTEM.md and ~/projects/vdocs/CLAUDE.md (project conventions)
2. docs/vdocs-design.md — THE architectural source of truth. If code and it disagree, the
   doc is the bug report. Key sections: §4 (two medallions), §5 (lake layout + bundles),
   §6 (frontmatter/TOC/lineage), §7 (stage contracts/preflight/postflight), §8 (the 18-stage
   table — authoritative), §9.6 (discovery-is-data / registries), §17 (phased build plan).
3. docs/vdocs-implementation-tracker.md — the whole-pipeline status tracker (Overall status
   table + per-stage rows + Lessons Learned + Change Log). Read the Lessons — they encode
   hard-won real-data findings. docs/vdl-crawl-tracker.md is the inventory-medallion detail.
4. docs/vdl-crawl-spec.md (inventory enrichment spec) and docs/fidelity-framework.md (QA).

## What's done (HEAD 565b697, 275 tests, 100% coverage, make check green)
- Spine: kernel/ (one each: text, frontmatter, fingerprint, cas, lineage, db, discovery, http),
  Pydantic config + ArtifactContract registry, generic orchestrator (preflight→run→postflight,
  state.db).
- INVENTORY MEDALLION (complete): crawl → catalog → serve-inventory (gold inventory + the HARD
  GATE = the fetch gate) + acquisitions + inventory_status + CLI. The enrichment reproduces the
  v1 §7 distributions EXACTLY on the full 8,834-row corpus.
- DOCUMENT SILVER (Phase 3): convert (DOCX-only; Pandoc default + Docling routing for cprsguium),
  discover (boilerplate/phrase/glossary miners + a convert-quality probe), enrich (identity FM +
  index.db:doc_meta_staged), normalize (heading-recovery from _Toc bookmarks, revision-history →
  history.yaml sidecar, artifact-strip, curated registries/phrases subtraction, TOC regen with
  GitHub-slug anchors, source_sha256).

## Real-corpus loop (IMPORTANT — don't develop in a vacuum)
The document-medallion stages are developed against REAL VA documents, not just fixtures. The
lake at ~/data/vdocs is populated with 469 real docs seeded offline from v1's already-fetched
~/data/vista-docs/raw/ via `python scripts/seed_from_v1.py` (no live crawl). v1 (~/projects/
vista-docs) is the authoritative reference for ported logic and a comparison target
(~/data/vista-docs/normalized/). Pattern: process the real corpus through a stage, see what
actually breaks, fix, re-verify. This caught real bugs fixtures hid (convert image-ref
rewriting; discover measuring headings instead of bare markers).

## Conventions (hard rules)
- TDD: write the test, confirm it fails, implement, confirm green, `make check` before commit.
- Pure functions in *_pure.py (zero I/O); thin I/O in stage.py drivers; ONE shared kernel/
  (copy-paste across stages is a review failure). No top-level .py modules under src/vdocs/.
- Discovery-is-data: recurring patterns live in version-controlled registries/, never hard-coded.
- make check = ruff (line 100; E,F,I) + mypy + pytest (random order) + coverage; keep it 100%.
- Update docs/vdocs-design.md in the same commit when a stage's inputs/outputs/CLI change.
- After each stage/feature: flip its tracker row, append a Change Log entry, record any Lessons.
- Commits end with: Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
- Heavy/conflicting deps (e.g. Docling — pins typer<0.22 vs our >=0.26.5) run OUT-OF-PROCESS
  via an isolated `uv tool` CLI, like Pandoc. Docling is routed ONLY for cprsguium (the bare-
  marker `[[…]](#_Toc…)` explosion); the registries/converter-routing allowlist is that signal.
- Lake gotcha: run downstream stages as ONE `vdocs run --from X --to Y` pass, not separate
  `--force` invocations, or the cheap (size:mtime) fingerprints go stale and preflight refuses.

## What to do next — pick up the deferred normalize F-steps OR start Phase 4
Deferred normalize F-steps (tracker-listed): tables → tables/*.csv sidecars (data-dictionary
HTML <table> blocks → CSV + a body stub; small inline tables stay), boilerplate REFERENCE +
gold/_shared, template STRIP+STAMP, refs.yaml + back-links + bookmark rewrite, heading-level
inference. OR start Phase 4 (gold derive): consolidate → index (consumes the doc_meta_staged
rows enrich already writes; FTS5 + stable IDs) → relate → manifest.

Please start by reading the design doc + the implementation tracker, confirm the current state
(`make check`), then propose a short plan for the next increment and proceed TDD-style.
```

---

## Notes for whoever resumes

- **Pipeline tally (tracker):** 6 ✅ · 2 ◐ · 11 ☐. `convert`/`discover`/`enrich` ✅, `normalize`
  ◐ (more F-steps deferred), `fetch` ◐ (explicit selection flags pending).
- **Housekeeping:** there is no `~/claude/memory/project_vdocs.md` (the status-line hook keeps
  asking — ignore unless you want to create one). An unrelated mermaid-diagram diff in
  `docs/vdocs-design.md` has been left unstaged across the whole session — it isn't ours.
- **Verify a stage on real data**, e.g.: `vdocs run --from convert --to normalize` (no `--force`)
  should SKIP all four if the lake is consistent. The gold inventory + 469-doc silver are populated.
