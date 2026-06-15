# vdocs

A TDD Python pipeline that turns the VA VistA Document Library (DOCX manuals) into a clean,
human-browsable markdown corpus **and** a self-contained **lexical search index** (`index.db`,
SQLite + FTS5) that any developer can search **offline with zero ML dependencies**. Greenfield v2
rewrite of `vista-docs`.

**Source of truth:** the go-forward plan
[`docs/offline-lexical-search-plan.md`](docs/offline-lexical-search-plan.md) (*what/why*) and its
[implementation tracker](docs/offline-lexical-search-implementation-plan.md) (*how/status*). New to
the project? Start with the [user guide](docs/vdocs-user-guide.md); to **run** the pipeline, follow
the [operator runbook](docs/de-novo-run.md). The original `vdocs-design.md` is archived under
[`docs/historical/`](docs/historical/) as superseded reference (the semantic / vector / MCP surface
and the fidelity-QA framework were descoped — the project is lexical-first and offline).

## Install

```bash
make install
```

To **run the document pipeline** (not just `make check`), two system converters are also required —
they are external binaries, not pip dependencies:

```bash
sudo apt install pandoc                     # or: brew install pandoc  (required: every DOCX)
uv tool install 'docling-slim[standard]'    # Docling CLI (for the routed CPRS doc)
```

The `convert` stage preflight-checks both and fails up front with the install command if either is
missing. See [`docs/de-novo-run.md`](docs/de-novo-run.md) for the full operator runbook.

## Usage

After `make install`, the `vdocs` CLI lives in the project's `.venv` (it is **not** on your `PATH`).
Invoke it with `uv run` — or activate the venv first:

```bash
uv run vdocs --help          # or: source .venv/bin/activate  &&  vdocs --help
```

The full run is three commands (`uv run vdocs gate` → `… build --fresh --yes` → `… doctor`); see the
[operator runbook](docs/de-novo-run.md).

## Develop

```bash
make test       # pytest, stop on first failure, random order
make watch      # auto-rerun tests on file save (TDD)
make check      # lint + mypy + coverage (CI gate)
make format     # ruff format
make push       # check + git push
```

See [`CLAUDE.md`](CLAUDE.md) for the full dev workflow and project conventions.

## Layout

```
src/vdocs/   # importable package
tests/           # pytest, mirrors src/
docs/            # long-form docs
scripts/         # one-off dev helpers (optional)
```

## License

<!-- Add a LICENSE file (e.g. MIT) before publishing. -->
