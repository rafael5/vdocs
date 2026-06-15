# vdocs

A TDD Python pipeline that turns the VA VistA Document Library (DOCX/PDF manuals) into a clean,
GitHub-native markdown corpus **and** a self-contained, offline knowledge base
(lexical + structured + graph search over `index.db`, zero ML dependencies). Greenfield v2 rewrite
of `vista-docs`.

**Architecture is fully specified in [`docs/vdocs-design.md`](docs/vdocs-design.md)** (the single
source of truth) with the QA companion [`docs/fidelity-framework.md`](docs/fidelity-framework.md).
To start building, see [`docs/kickoff-prompt.md`](docs/kickoff-prompt.md).

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

```bash
vdocs --help
```

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
