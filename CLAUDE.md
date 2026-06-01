# Claude Project Context — vdocs

## What this project is

`vdocs` is the **greenfield v2 rewrite** of the `vista-docs` pipeline: it turns the VA VistA
Document Library (DOCX/PDF manuals) into (1) a clean, human-browsable markdown corpus on GitHub
and (2) a machine-discoverable knowledge base served over MCP (hybrid semantic + lexical +
structured + graph search). Repo, import package, and CLI are all `vdocs`.

## THE SOURCE OF TRUTH

- **[`docs/vdocs-design.md`](docs/vdocs-design.md)** is the single source of architectural truth.
  **If the code and that document disagree, the document is the bug report.** Read it before
  changing anything structural.
- **[`docs/fidelity-framework.md`](docs/fidelity-framework.md)** is the QA companion (per-document
  migration fidelity, currency, template compliance, TOC integrity, retrieval-quality).

Do not redesign in code. Propose design changes by editing the design doc first.

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
· **structlog** · SQLite (`state.db`, `index.db`) + **sqlite-vec** (`vectors.db`) · **MCP Python SDK**.
Add deps **per phase** as the design requires (`uv add … && uv lock`, commit the lock) — not all up front.

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
~/data/vdocs/                # $DATA_DIR
  bronze/{catalog,raw}       # crawl·catalog·fetch (raw is content-addressed)
  assets/<sha256>.<ext>      # convert (CAS image store)
  silver/text/{01-converted,02-enriched,03-normalized}/...
  gold/{consolidated,_shared,publish, corpus-manifest.json, discovery.json, glossary.md}
  state.db · index.db · vectors.db
  reports/{survey,headings,lexicon,patterns,fidelity}
```

The curated **`registries/`** (boilerplate · templates · phrases · glossary · structures ·
converter-routing) is version-controlled **in this repo** (§9.7), not in the lake.

## Claude guidelines

- Prefer editing existing files; keep functions small and independently testable.
- Pure functions take/return plain values — no side effects. `logging`/`structlog`, never `print()`.
- No mocks unless unavoidable — prefer real objects and fakes.
- Update `docs/vdocs-design.md` in the same commit whenever a stage's inputs/outputs/CLI change.
