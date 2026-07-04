# Kickoff — Resume the Read-Contract System + vdocs-web build

**For a fresh session.** This continues an in-flight, multi-repo build (ADR-0001). The contract
system is **complete** (P0–P4); the new `vdocs-web` consumer is **partway** (P5.1/P5.2/P5.5 done,
P5.3/P5.4/P5.6 remain). Execute the remaining phases TDD-first, updating the tracker as work lands.
**Do not redesign** — if you think the design is wrong, edit the ADR and stop for operator sign-off.

> **Why this exists.** `vdocs` (the pipeline) produces `index.db`; multiple clients read it
> (`vdocs-tui`, `vdocs-web`, a future MCP endpoint). A **published read contract** (versioned views
> + vocab-as-data + drift gates) insulates consumers from physical-schema change, so the gold
> library can grow and the pipeline can be refined without silently breaking consumers.

## Read first (in this order)

1. **`docs/adr/0001-read-contract-and-drift-prevention.md`** — the *what/why* (authoritative).
2. **`docs/read-contract-implementation-plan.md`** — ⭐ the *how/status* tracker (phases P0–P6,
   per-phase changelog/**discoveries D7–D20**/risks). **This is the live state — read its tracker
   table + the P5 section before doing anything.**
3. Project memory `read-contract-and-vdocs-web` (in the vdocs memory dir) — the condensed running log.
4. **`~/.claude/CLAUDE.md`** — the house **Node** + **Go** dev standards (added this work; they
   govern vdocs-web).

## State snapshot (2026-06-11)

| Phase | Repo | Status |
|---|---|---|
| P0 meta/version axes · P1 contract+views · P2 vocab+enum-gate+manifest | **vdocs** (master) | ✅ |
| P3 `pkg/index` extract + contract binding + drift check | **vdocs-tui** | ✅ |
| P4 consume views + vocab; delete `explain.go` maps | **vdocs-tui** | ✅ |
| P5.1 scaffold · P5.2 API spine · P5.5 SvelteKit SPA | **vdocs-web** | ✅ |
| **P5.3** preview/TOC/fuzzy/FTS5 endpoints + Svelte panes | vdocs-web | ⬜ **next** |
| **P5.4** 294 MB DB auto-download + manifest validation | vdocs-web | ⬜ |
| **P5.6** cross-compile matrix | vdocs-web | ⬜ |
| P6 MCP endpoint + `make check-consumers` | — | ⛔ deferred |

**Read contract is at v1.2** (`vdocs/contracts/read/v1.json`), vendored into
`vdocs-tui/pkg/index/contract/v1.json` (and transitively used by vdocs-web).

## The three repos + cross-repo rules

- **vdocs** — `~/projects/vdocs` (Python pipeline). Commits docs+code **directly to `master`**.
- **vdocs-tui** — `~/vista-cloud-dev/vdocs-tui` (Go). **branch → PR → squash-merge** (org protocol).
  Owns `pkg/index` (the shared read-contract query core).
- **vdocs-web** — `~/vista-cloud-dev/vdocs-web` (Go server + SvelteKit). branch → PR. Imports
  `pkg/index` via `replace github.com/vista-cloud-dev/vdocs-tui => ../vdocs-tui` (the two are
  siblings under `~/vista-cloud-dev/`).
- **Leaf-first:** a producer (vdocs) contract change lands **before** consumers re-vendor. Re-vendor
  = `command cp ~/projects/vdocs/contracts/read/v1.json vdocs-tui/pkg/index/contract/v1.json`, then
  bump the version assertions + `make contract-check`. **One session ↔ one repo ↔ one branch.**

## Toolchain quickstart (airgapped; verified working)

- **Go (both Go repos):** `export GOPROXY="file://$HOME/go/pkg/mod/cache/download" GOSUMDB=off
  GOFLAGS=-mod=mod`. Gate: `golangci-lint run ./...` + `go test ./...` (+ `make contract-check` in
  vdocs-tui). vdocs-web also has `make check`.
- **Node (vdocs-web/web):** Node **is** installed via nvm (v22.22.2 + v24.14.1). The tool's
  non-login shell doesn't source nvm, so **prepend it to PATH**:
  `export PATH="$HOME/.nvm/versions/node/v22.22.2/bin:$PATH"` (npm's shebang needs `node` on PATH).
  **npm registry network works.** Front-end: `make web-install` (npm ci), `make web-build` (vite →
  `internal/web/static`, embedded via `//go:embed all:static`), `make web-dev`.
- **Python (vdocs):** `make check` (ruff+mypy+pytest ≥95%); `.venv/bin/` prefixes.

## Working protocol (per increment, non-negotiable)

TDD (write failing test → implement → green) → gate (`make check` / Go gate) → **update the tracker**
(flip status, fill Changelog/Discoveries/Lessons; mark ⚠️ + edit the ADR if a discovery changes the
design) → commit (stage **explicit paths**, never `git add -A`/`.`; `Co-Authored-By: Claude …`) →
update the project memory. Stop and report at each phase boundary. Additive-first; fixtures, not the
live lake.

## Immediate next: P5.3 (vdocs-web, Node-independent)

Add API endpoints over `pkg/index` (which already has the methods) + Svelte panes:
- `GET /api/doc/{docKey}/toc` → `ix.DocTOC` · `GET /api/section/{id}` → `ix.SectionText` ·
  `GET /api/preview/{docKey}` → `ix.Preview` · full-text via the existing `?q=` (FTS) on
  `/api/candidates` (already wired in `filterFromQuery`) — surface it in the UI.
- Svelte: a results→preview pane (click a doc → TOC → section body) + a search box. httptest the new
  handlers (fixture pattern in `internal/api/server_test.go`); add Svelte to `+page.svelte`.
- Then P5.4 (DB auto-download: zstd + sha256 + `read_schema_version` from the publish manifest;
  honor `--db`/`$VDOCS_DB`/`$DATA_DIR` first), P5.6 (cross-compile: `make dist` matrix).

## Current caveats / operator TODOs

- **The live 294 MB `~/data/vdocs/index.db` is pre-contract** (built before P0/P1 → no `meta`/`v_*`
  views). Until the operator **rebuilds `index` at v1.2**, `vdocs doctor` reports RED, the TUI
  degrades, and `vdocs-web` **refuses** the DB by design (`HasContractViews`). Rebuild =
  `vdocs index` (or `vdocs build`) on the shared lake — **check `pgrep -af "vdocs run"` first**
  (shared-lake guard), it's an operator action. Test against fresh fixtures, not the live lake.
- **CI for vdocs-web is deferred (D18):** the cross-*private*-repo `replace` dep needs a
  dual-checkout+PAT or `go mod vendor`. Local `make check` is the gate.
- **SvelteKit deviates** from the house npm/Biome/`node:test` standard only on the build tool (Vite)
  — that's intended (it's an app, not a lib). Everything else is house-standard (npm, `.node-version`,
  committed `package-lock.json`).

## Gotchas already paid for (don't repeat)

- `//go:embed static` silently excludes `_`-prefixed dirs → SvelteKit `_app/` needs **`all:static`**.
- `git add -A` once swept untracked `docs/*.draft.yaml` into a commit → **stage explicit paths**.
- Backticks inside a double-quoted `git commit -m` run as shell substitution → use `-F` / a file.
- `cp`/`mv` are aliased to `-i` (prompt) in this env → use `command cp -f`; `git mv` needs the dest
  parent dir (`mkdir -p` first). Sandbox **denies** `rm`, force-push, and some `curl`.

## First action

`cd ~/vista-cloud-dev/vdocs-web`, re-read the tracker's P5 section, branch, and begin **P5.3** —
TDD a `/api/doc/{key}/toc` handler test first (fixture per `server_test.go`), implement, green, then
the section/preview endpoints and the Svelte preview pane. Gate, update the tracker, PR, report.
