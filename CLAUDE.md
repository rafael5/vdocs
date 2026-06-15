# Claude Project Context — vdocs

## What this project is

`vdocs` turns the VA VistA Document Library (DOCX/PDF manuals) into a clean, human-browsable
markdown corpus **and** a self-contained lexical search index (`index.db`, SQLite + FTS5) that any
developer can search **offline with zero ML dependencies**. Repo, import package, and CLI are all
`vdocs`.

> **Direction reset (2026-06-08).** The original twin goal included a **semantic/vector + MCP agent**
> surface. A spike proved the all-or-nothing embedding/vector path is **not worth its cost** on this
> upstream-uncontrolled corpus (OOM via ONNX fan-out; full re-embed on every doc change). The project
> is now **lexical-first, offline, human-consumer**. Semantic search is parked; the MCP/agent surface
> is descoped.

## THE SOURCE OF TRUTH

Driven by the **go-forward plan** (with two frozen predecessors kept as record/background):

- **[`docs/offline-lexical-search-plan.md`](docs/offline-lexical-search-plan.md)** — ⭐ **the active
  plan** (*what/why*). Go-forward scope: lexical-search quality, the zero-dependency distributable
  search tool, the human `publish`/`push` deliverable, and the quality gate.
- **[`docs/offline-lexical-search-implementation-plan.md`](docs/offline-lexical-search-implementation-plan.md)**
  — the *how/status* tracker (detailed L0–L4 steps, per-phase changelog/discoveries/risks). **Update
  it as work lands** (TDD → `make check` → update tracker → commit, per step).
- **[`docs/historical/vdocs-implementation-plan.md`](docs/historical/vdocs-implementation-plan.md)** — **frozen** spike
  execution record (per-phase status, discoveries, risks). See its 🏁 Closure section for the
  decisive embed-vs-lexical finding. Read for *why*; do not execute its C/D phases.
- **[`docs/historical/vdocs-remediation-plan.md`](docs/historical/vdocs-remediation-plan.md)** — the original *what/why*
  audit. Background; superseded where it assumes a semantic/MCP finish.

**If the code and the active plan disagree, the plan is the bug report.** Read it before changing
anything structural; propose design changes by editing the plan first, not in code.

The original design docs — `vdocs-design.md` (architecture) and `fidelity-framework.md` (QA
companion: per-document migration fidelity, currency, template compliance, TOC integrity,
retrieval-quality) — are now archived under [`docs/historical/`](docs/historical/) as **reference
only** (superseded by the plans above where they disagree).

## How to build

Follow the **§17 phased build plan — build the spine before the stages.** Phase 1 = kernel +
config + models + contracts + orchestrator, proven by a no-op two-stage DAG. Nothing downstream
until that is green.

## Architecture rules (from the design)

- **Medallion lake** bronze → silver → gold (§4). Data lives in `~/data/vdocs` (`DATA_DIR`),
  **never in this repo**.
- **17-stage DAG** of `Stage`/`ArtifactContract` driven by a generic in-house orchestrator (§7–§8).
  The §8 table is authoritative; the orchestrator derives order from it.
- **Pure functions in `*_pure.py`** (zero I/O); thin I/O **`stage.py`** drivers. Every pure
  function has a unit test written first.
- **One shared `kernel/`** for cross-cutting primitives (text, frontmatter, fingerprint, cas,
  lineage, db, discovery). Copy-paste across stages is a build-breaking review failure (§9.2).
- **No top-level `.py` modules.** Everything under `src/vdocs/` is a stage, the kernel, the
  orchestrator, models, contracts, or the server (§11).
- **Discovery is data, not code** (tenet #13): recurring patterns live in version-controlled
  `registries/`, subtracted by generic stages — never hard-coded.

## Toolchain (ADRs §10)

Python 3.12 + `uv` · `ruff` (line 100; E,F,I) · `mypy` · `pytest` + **Hypothesis** (property tests
for pure transforms) · **Typer** CLI · **Pydantic v2** boundary types + **Pydantic Settings** config
· **structlog** · SQLite (`state.db`, `index.db`, both FTS5). Document conversion shells out to
**Pandoc** (and **Docling** for the routed CPRS doc) — system binaries, not pip deps (see
`de-novo-run.md §0`). Add deps **per phase** as the design requires (`uv add … && uv lock`, commit
the lock) — not all up front.
> **Descoped (direction reset 2026-06-08):** `sqlite-vec`/`vectors.db` and the **MCP Python SDK** —
> the semantic/vector + agent surface is parked. They are **not** dependencies; ignore older
> references to them.

## TDD — hard rule

Write the test first, confirm it fails, implement, confirm green, `make check` before commit. No
skipping to implementation.

## Dev workflow

```bash
make install   # .venv + deps + pre-commit hooks
make test      # pytest (fast, -x, random order)
make watch     # TDD auto-rerun
make check     # lint + mypy + coverage (CI gate; ≥95%)
make format    # ruff format
make push      # check + git push
```

Makefiles must use `.venv/bin/` prefixes (parent direnv hijacks bare tool names).

## Data lake (NOT in this repo)

```
~/data/vdocs/                          # $DATA_DIR — two medallion subtrees (§4, §5.3)
  inventory/{bronze,silver,gold}/...   # INVENTORY medallion: crawl·catalog·serve-inventory
  documents/                           # DOCUMENT medallion (data plane)
    bronze/raw/<sha256>.docx           #   fetch (content-addressed) + raw/index.json
    assets/<sha256>.<ext>              #   convert (CAS image store)
    silver/text/{01-converted,02-enriched,03-normalized}/...
    gold/{consolidated,_shared,publish, corpus-manifest.json, discovery.json, glossary.md}
  state.db · index.db · vectors.db     # cross-cutting (at the lake root, not per-track)
  reports/{survey,headings,lexicon,patterns,fidelity}
```

The curated **`registries/`** (boilerplate · templates · phrases · glossary · structures ·
converter-routing) is version-controlled **in this repo** (§9.7), not in the lake.

## Claude guidelines

- Prefer editing existing files; keep functions small and independently testable.
- Pure functions take/return plain values — no side effects. `logging`/`structlog`, never `print()`.
- No mocks unless unavoidable — prefer real objects and fakes.
- Update `docs/vdocs-design.md` in the same commit whenever a stage's inputs/outputs/CLI change.
