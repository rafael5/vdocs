PYTHON     := .venv/bin/python
PYTEST     := .venv/bin/pytest
PTW        := .venv/bin/ptw
RUFF       := .venv/bin/ruff
MYPY       := .venv/bin/mypy
PRECOMMIT  := .venv/bin/pre-commit
BRANCH      = $(shell git rev-parse --abbrev-ref HEAD)

.PHONY: install test test-lf watch lint format mypy cov check push pull hooks contract-lint

install:
	uv sync --extra dev
	$(MAKE) hooks

hooks:
	$(PRECOMMIT) install --hook-type pre-commit --hook-type pre-push

test:
	$(PYTEST)

test-lf:
	$(PYTEST) --lf

watch:
	$(PTW) -- --tb=short

lint:
	$(RUFF) check src/ tests/

format:
	$(RUFF) format src/ tests/

mypy:
	$(MYPY) src/

cov:
	$(PYTEST) --cov --cov-report=term-missing

check: lint mypy cov

# read-contract semver guard (ADR-0001 P1.6): a breaking change to contracts/read/ may not ship as
# a MINOR. No-op until a v2 spec exists.
contract-lint:
	$(PYTHON) -c "import sys; from vdocs.kernel import read_contract as rc; p = rc.lint_latest(); [print('CONTRACT-LINT:', x) for x in p]; sys.exit(1 if p else 0)"

pull:
	git pull origin $(BRANCH)

push: check
	git push origin $(BRANCH)
