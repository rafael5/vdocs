# Kickoff prompt — building vdocs

Paste the block below into a **fresh session** opened in `~/projects/vdocs` to start the build.
(Everything below the line is the prompt; the rest of this file is for you, not the model.)

**Why a phased build:** the whole architecture is already decided and written down. The first
session's job is to lay the *spine* (kernel + contracts + orchestrator) so every later stage snaps
onto a frame that already enforces idempotency, gating, and lineage. Resist building stages first.

---

You are implementing **vdocs**, a greenfield v2 rewrite of the `vista-docs` pipeline. The complete
architecture is already specified and lives in this repo. **Your job is to build it, not redesign
it.**

**Read first, in this order — treat as the single source of truth:**
1. `docs/vdocs-design.md` — the authoritative architecture: medallion lake (bronze→silver→gold); an
   in-house DAG of `Stage`/`ArtifactContract` driven by a generic orchestrator; one shared `kernel/`;
   the 17-stage table (§8, authoritative); pattern-discovery `registries/`; anchor-document version
   rollup; the MCP search server. **If code and this doc disagree, the doc is the bug report.** Skim
   the Contents, then read §4 (medallion), §5 (storage), §6 (content model), §7 (stage contract),
   §8 (the 17 stages), §9 (kernel + discovery), §11 (layout), §17 (phased plan).
2. `docs/fidelity-framework.md` — the QA companion (per-document migration fidelity, currency,
   template compliance, TOC integrity, retrieval-quality).
3. `CLAUDE.md` — toolchain, conventions, the data-lake layout.

**Hard rules (from the design + CLAUDE.md):**
- **TDD, no exceptions:** write the failing test first → confirm red → implement → confirm green →
  `make check`. Pure transforms also get **Hypothesis** property tests (idempotency, round-trip).
- **Pure functions in `*_pure.py`** (zero I/O), thin I/O drivers in `stage.py`; shared primitives
  only in `kernel/` (copy-paste across stages is a build-breaking failure); **no top-level `.py`**.
- **All data in `~/data/vdocs`** (the lake, `DATA_DIR`), never in the repo. All paths derive from
  config (Pydantic Settings, ADR-005) — no hardcoded paths.
- Add dependencies **per phase** as the ADRs require (Typer, Pydantic v2, Pydantic-Settings,
  structlog, Hypothesis, sqlite-vec, MCP SDK) — `uv add … && uv lock`, commit the lock. Not all up front.
- Branch off `main`; commit only when asked.

**Build Phase 1 ONLY this session (design §17 step 1):** the spine —
`kernel/` (one each: text repair, frontmatter codec, fingerprint, CAS, lineage, db, discovery),
`config.py` (Pydantic Settings off `DATA_DIR`), `models/` (Pydantic boundary types incl.
`ArtifactContract`), `contracts/` (the artifact registry), and `orchestrator/` (the generic
preflight→run→postflight runner + `state.db` `stage_runs`). **Prove it** with a no-op **two-stage
DAG** that exercises the full `preflight → run → postflight` cycle, the completion record, and
skip/force — green end to end. Do **not** start real stages (crawl/fetch/…) until that passes.

**Deliverable for this session:**
1. First, a short written Phase-1 implementation plan (modules, the `Stage`/`ArtifactContract`
   types, the orchestrator, the no-op DAG test) — then implement it TDD.
2. `make check` green (lint + mypy + coverage ≥95%).
3. A clean commit history; end with a one-paragraph status + what Phase 2 (bronze: crawl→catalog→
   fetch) will need.

Ask me only if the design is genuinely ambiguous on something you must decide now; otherwise proceed
from the document. If the seeded `CLAUDE.md` is too thin once you've read the design, improve it.
