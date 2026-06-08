# Kickoff prompt — vdocs-spike (doc_type template & boilerplate discovery)

Paste the block **below the line** into a **fresh session** opened in `~/projects` (the project dir
`~/projects/vdocs-spike` does not exist yet — the prompt creates it). Everything above the line is
for you, not the model.

**Why a separate repo:** this is an exploratory, out-of-band *spike* whose only job is to look at the
already-normalized corpus and characterize, per `doc_type` (RN, UM, IG, DIBR, TM, …), the structural
**template** (recurring section skeleton) and the **boilerplate** (recurring verbatim blocks) each
type was poured into. It must **not** contaminate the `vdocs` repo or its registries — findings get
hand-curated back into `vdocs` later, by you, deliberately. So it lives in its own git repo built
from the standard Python template.

**Path correction worth knowing:** the normalized corpus is at
`~/data/vdocs/documents/silver/text/03-normalized/` (note the `text/` segment), **not**
`~/data/vdocs/documents/silver/03-normalized/`. 469 documents, laid out as
`<PKG>/<doc_slug>/body.md` (+ a sibling `refs.yaml`). Each `body.md` opens with YAML frontmatter
carrying `doc_type`, `app_code`, `version`, `source_url`, etc., then a `## Contents` TOC, then the
body. doc_type distribution (so you know which types have enough evidence to induce a template):
DIBR 120 · IG 108 · RN 83 · TM 42 · UM 25 · UG 14 · DG 12 · CFG 8 · API 8 · INT 6 · POM 5 ·
SG-SET/SG/QRG/AG 4 · SUP/SM/REF/PDD/IG-IMP 3 · FAQ/DESC/APX 2 · CVG 1.

**`vdocs` is reference-only.** The spike may *read* `~/projects/vdocs` for prior art but imports
nothing from it. The most relevant prior art to study before writing your own:
- `registries/templates/templates.yaml` + `README.md` — the **target shape** for induced templates:
  `template_id`, `doc_type`, `era`, ordered `sections[]` with `section_id`/`title`/`level`/`required`/
  `toc_level`, `evidence_docs`. Your spike output should be schema-compatible so curation is trivial.
- `registries/boilerplate/boilerplate.yaml` + `README.md` — target shape for boilerplate:
  `id`, `label`, `key` (whitespace-collapsed match identity), `text` (canonical copy), `evidence_docs`.
- `src/vdocs/stages/discover/discover_pure.py` — already contains `mine_templates()` (§396),
  `mine_recurring_blocks()` / `_cluster_boilerplate()` (§158/§225), `mine_structures()`. This is the
  algorithm prior art; the spike's contribution is to run it **partitioned by doc_type** and report.
- `src/vdocs/kernel/text.py:block_key` (block identity) and `kernel/discovery.py:shingles` (near-dup).
  Reimplement equivalents in the spike (don't import) — it keeps the spike standalone.

---

You are building **`vdocs-spike`**, a throwaway-quality but well-tested exploratory analysis tool in
its own repo at `~/projects/vdocs-spike`. Its single purpose: read the already-normalized VistA
document corpus and, **per `doc_type`**, induce and report two things — (1) the recurring section
**template** each doc_type was built from, and (2) the recurring verbatim **boilerplate** blocks
shared across documents of that type. Output is a curation-ready registry plus a human-readable
report. This is research, not production — but the Python toolchain hard-rules below still apply.

**This is a separate repo. Do not touch `~/projects/vdocs` except to read it for reference.**

## Set up the project from the template (first thing, before any code)

```bash
cp -r ~/claude/templates/python ~/projects/vdocs-spike
cd ~/projects/vdocs-spike
mv src/myproject src/vdocs_spike
sed -i 's/myproject/vdocs_spike/g' pyproject.toml tests/conftest.py tests/test_myproject.py README.md
mv tests/test_myproject.py tests/test_vdocs_spike.py
make install && make test     # confirm the scaffold is green before you add anything
git init && git add -A && git commit -m "chore: scaffold vdocs-spike from python template"
```

## The data (read-only input)

- Root: `~/data/vdocs/documents/silver/text/03-normalized/`
- Per document: `<PKG>/<doc_slug>/body.md` — YAML frontmatter (has `doc_type`, `app_code`, `version`,
  `source_url`, `source_sha256`, `patch_id`) followed by a `## Contents` TOC and the markdown body.
- Treat `~/data/vdocs` as **read-only**; never write into the lake. The spike writes only inside its
  own repo (or a `~/data/vdocs-spike/` output dir of your choosing — your call; if you create one,
  `mkdir -p ~/data/vdocs-spike` and keep it out of git).

## What to build (TDD, pure-first)

Mirror the `vdocs` discipline at small scale:
- **Pure functions in `*_pure.py`** (zero I/O), thin I/O drivers separately. Write the failing test
  first → red → implement → green → `make check`. Pure transforms get a **Hypothesis** property test
  where it makes sense (e.g. `block_key` idempotence, parser round-trips).
- Suggested shape (adjust as the data teaches you — don't over-design up front):
  1. **`corpus.py`** — discover the 469 `body.md` files, split frontmatter from body, parse the
     `## Contents` TOC and the `##/###` heading tree. Group documents by `doc_type`.
  2. **`templates_pure.py`** — given all docs of one doc_type, induce the section skeleton:
     align heading sequences, score each candidate section by `evidence_docs` (how many docs of that
     type contain it), mark `required` (appears in ≥ some threshold) vs optional, preserve order and
     `level`. Emit a `template_id`-keyed record shaped like `vdocs` `registries/templates`.
  3. **`boilerplate_pure.py`** — split each body into blocks, compute a `block_key` (whitespace-
     collapsed, lowercased) and shingle set, cluster near-duplicates **within each doc_type**, keep
     blocks recurring across ≥ N docs of the type. Emit records shaped like `vdocs`
     `registries/boilerplate` (`id`/`label`/`key`/`text`/`evidence_docs`), tagged with their doc_type.
  4. A **Typer CLI** (`vdocs-spike analyze [--doc-type RN] [--min-docs 3]`) that runs the analysis and
     writes outputs.
- **Outputs:**
  - `out/templates-by-doctype.yaml` and `out/boilerplate-by-doctype.yaml` — curation-ready, schema-
    compatible with the `vdocs` registries so findings can be hand-merged later.
  - `out/report.md` — per doc_type: how many docs, the induced template skeleton (with evidence
    counts), the top boilerplate blocks, and notes on which doc_types are too sparse (e.g. CVG=1) to
    induce anything. This report is the real deliverable — it's what a human reads to decide what to
    curate into `vdocs`.

## Toolchain hard-rules (same as the home server defaults)

- Python 3.12 · `uv` (not pip) · `ruff` · `mypy` · `pytest` + **Hypothesis**. Makefile uses
  `.venv/bin/` prefixes (parent direnv hijacks bare tool names). Add deps per need: `uv add typer
  pyyaml hypothesis && uv lock`, commit the lock.
- `logging`/`structlog`, never `print()` in library code (CLI user-facing output is fine).
- No mocks unless unavoidable — run against the real corpus; for unit tests use small inline fixtures.
- `make check` green (lint + mypy + coverage) before each commit. Commit only when asked.

## Deliverable for this session

1. First, a short written plan (modules, the doc_type-partitioned template-induction and
   boilerplate-clustering approach, output schemas) — then implement it TDD.
2. A working `analyze` run over the real 469-doc corpus that produces `out/report.md` and the two
   registry YAMLs.
3. `make check` green; a clean commit history in the new repo. End with a one-paragraph findings
   summary: which doc_types have strong, curation-worthy templates/boilerplate vs which are too
   sparse or noisy — i.e. what's worth promoting back into `vdocs/registries` by hand.

Ask me only if something is genuinely ambiguous and blocks you now; otherwise proceed and let the
corpus guide the thresholds.
