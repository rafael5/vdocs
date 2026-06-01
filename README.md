# vdocs

A TDD Python pipeline that turns the VA VistA Document Library (DOCX/PDF manuals) into a clean,
GitHub-native markdown corpus **and** a machine-discoverable knowledge base served over MCP
(hybrid semantic + lexical + structured + graph search). Greenfield v2 rewrite of `vista-docs`.

**Architecture is fully specified in [`docs/vdocs-design.md`](docs/vdocs-design.md)** (the single
source of truth) with the QA companion [`docs/fidelity-framework.md`](docs/fidelity-framework.md).
To start building, see [`docs/kickoff-prompt.md`](docs/kickoff-prompt.md).

## Install

```bash
make install
```

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
