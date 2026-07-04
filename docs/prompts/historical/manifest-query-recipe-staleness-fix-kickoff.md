# Kickoff — fix the stale `vdocs ask` / `body_path` query recipe baked into the manifest

**Type:** small, self-contained bug fix (generator + tests + regen artifacts).
**Repo:** `~/projects/vdocs` (this repo). **Stack:** Python (uv/ruff/mypy/pytest) — load the
`python-project` skill, TDD is a hard rule here.

## Problem (what's wrong, and why it matters)

The **read/query CLI** shipped and renamed its commands a while back:

- query command is now **`vdocs search "<q>" --k N --json`** (was `vdocs ask …`)
- read-a-section is **`vdocs section "<section_id>" --json`** (returns the full `text` + citation)
- search **hits no longer carry `body_path`**; each hit is
  `{section_id, doc_key, doc_title, section_title, app_code, doc_type, score, snippet, uri, source_url}`

But the **manifest generator still emits the OLD recipe** into the agent front-door artifacts
(`ai-manifest.json` → `query` and `citation` blocks, and the rendered `CORPUS.md` card). So an agent
that trusts the manifest's self-described recipe runs a command that no longer exists. This already
bit a downstream consumer (the `~/.claude/skills/vdocs-corpus` skill was written from the old
recipe). The skill has since been hand-corrected to match the real CLI; **this task fixes the
upstream source so the generated artifacts stop emitting the stale recipe.**

Confirm the live CLI yourself before editing (don't trust this doc blindly):

```bash
vdocs search --help          # query CLI on $PATH (Go binary): search/section/document/facets
vdocs search "KAAJEE" --k 2 --json
vdocs section "EDIS/edp_2_1_1_tm/kaajee" --json
```

(Two binaries exist — the **query CLI** `vdocs` on `$PATH`, and this repo's **pipeline CLI**
`.venv/bin/vdocs` with `crawl…manifest/run/build`. This fix is to the pipeline side that *generates*
the manifest.)

## Exact location of the stale strings

`src/vdocs/stages/manifest/manifest_pure.py`:

- **`QUERY_RECIPE`** (~lines 113–115): `"command": 'vdocs ask "<your question>" --k 8 --json'` and a
  `"returns": …` string that lists `body_path` as a hit field.
- **`CITATION`** (~lines 119–121): `"format"` / `"resolve"` strings that reference `(<body_path>)` as
  the per-hit citation path.
- Module docstring (~line 242) mentions "the `vdocs ask` query recipe".
- The CORPUS.md card renderer (~lines 285–306) interpolates the same `QUERY_RECIPE`/`CITATION`
  strings, so fixing the constants fixes the card too.

## What to change

1. **`QUERY_RECIPE.command`** → `'vdocs search "<your question>" --k 8 --json'`.
2. **`QUERY_RECIPE.returns`** → the real search-hit shape:
   `ranked hits: {section_id, doc_key, doc_title, section_title, app_code, doc_type, snippet, score, uri, source_url}`.
3. **`CITATION`** → describe the citation an agent actually has from `search`/`section` output.
   Recommended format: `<doc_title> — §<section_title>  [vdocs://section/<section_id>]  (<source_url>)`,
   and a `resolve` line that says: to read a section's text, run `vdocs section "<section_id>"`
   (returns `text` + `source_url` + `uri`). Drop `body_path` from the **hit/citation** recipe.
4. **Docstring** "vdocs ask" → "vdocs search".

## What NOT to change (important)

- **Do NOT remove the `body_path` field from the `documents` *catalog*.** That field is legitimate —
  it's the on-disk gold anchor (`documents/gold/consolidated/<app>/<slug>/body.md`) recorded per
  document, resolved by `_body_path()` / `server.ids`. Only the *query/citation recipe* (which
  described body_path as a per-search-hit field) is wrong. Tests like
  `test_build_catalog_resolves_gold_body_path` must keep passing unchanged.

## TDD workflow (hard rule)

Tests already pin the OLD recipe — update them first, watch them fail, then fix the generator:

- `tests/unit/stages/test_manifest_pure.py` ~line 192: `assert "vdocs ask" in m["query"]["command"]`
  → assert `"vdocs search"`. ~line 207: `assert "vdocs ask" in md` (rendered card) → `"vdocs search"`.
- Add/adjust an assertion that the recipe does **not** advertise `body_path` as a hit field and that
  `source_url` is present in `returns`.
- Run `pytest tests/unit/stages/test_manifest_pure.py` → red → implement → green.

Then sweep for any other stale emitters (server/MCP recipe text, docs):

```bash
grep -rnE "vdocs ask" src/ docs/ --include='*.py' --include='*.md'
```

Fix the same `ask→search` / hit-field drift anywhere a recipe is *advertised* (e.g.
`src/vdocs/server/__init__.py` if it surfaces a query recipe; `docs/vdocs-user-guide.md`). Use
judgement — historical/proposal docs describing past design are fine to leave; user-facing "how to
query" guidance is not.

## Regenerate + verify the artifacts

The manifest stage writes into the **data lake** (`~/data/vdocs`), shared with the operator. **First
check no live run is in progress** (house rule):

```bash
pgrep -af "vdocs run" ; ls -lt ~/data/vdocs/reports/*.log 2>/dev/null | head
```

If clear, regenerate (reads derived stores only, cheap) and verify:

```bash
cd ~/projects/vdocs && .venv/bin/vdocs manifest --force
python3 -c "import json; m=json.load(open('/home/rafael/data/vdocs/documents/gold/ai-manifest.json')); print(m['query']); print(m['citation'])"
grep -n "vdocs search" ~/data/vdocs/documents/gold/CORPUS.md | head
```

Confirm `query.command` now says `vdocs search`, the `returns`/`citation` no longer list `body_path`
as a hit field, and the CORPUS.md card renders the new recipe.

## Gates + close-out

- `make check` (ruff + mypy + pytest) must be green before committing — TDD red→green complete.
- Commit per this repo's conventions (current branch is a feature branch, not `main`; follow the
  `python-project` skill + the `Co-Authored-By: Claude …` trailer). The generated lake artifacts
  under `~/data/vdocs/` are **not** committed (data lake, not the repo) — only the `src/` + `tests/`
  changes ride in the commit.
- Optional: drop a one-line note in `~/.claude/skills/vdocs-corpus/SKILL.md`'s caveat that the
  upstream manifest recipe is now fixed (the caveat currently warns the manifest recipe is stale).

## Acceptance

- `manifest_pure.py` emits `vdocs search` / `vdocs section` and a hit-shape recipe with `source_url`
  and no `body_path`-as-hit-field.
- `documents` catalog still carries `body_path` per doc (unchanged).
- Regenerated `ai-manifest.json` + `CORPUS.md` reflect the new recipe.
- `make check` green.
