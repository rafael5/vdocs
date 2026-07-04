# Kickoff — Implement the Read Contract & Drift-Prevention System (vdocs → consumers)

**For a fresh session.** This is a **feature build** with a finished design. Your job is to execute
the staged implementation plan, TDD-first, phase by phase, updating the tracker as work lands. The
design is already decided and signed off — **do not redesign it.** If you believe the design is
wrong, edit the ADR first and stop for operator sign-off; do not diverge in code.

> **Why this exists.** `vdocs` (the pipeline) produces `index.db`; multiple clients read it
> (`vdocs-tui`, the planned `vdocs-web`, a future MCP endpoint). Today that relationship is an
> **implicit, unversioned contract** — no schema version is stamped, consumers bind to physical
> tables, vocabularies are hardcoded in consumer code. As the gold library grows and the pipeline is
> refined, consumers drift and break silently. This system makes every class of drift trip a
> specific, actionable alarm at the moment it originates.

---

## Read first (in this order)

1. **`docs/adr/0001-read-contract-and-drift-prevention.md`** — ⭐ the *what/why*. Authoritative for
   the contract design (two version axes, views as interface, vocab-as-data, four guardrails,
   capability negotiation, expand/contract migration). **If the ADR and code disagree, the ADR is the
   bug report.**
2. **`docs/read-contract-implementation-plan.md`** — ⭐ the *how/status*. The phase tracker (P0–P6)
   you will execute and keep updated. Read the **Pre-implementation discoveries (D1–D6)** and the
   **Cross-phase risk register** before touching anything.
3. **`CLAUDE.md`** (project + global) — architecture rules (medallion lake; pure `*_pure.py` vs I/O
   `stage.py`; shared `kernel/`; no top-level modules; **discovery-is-data** registries), the **TDD
   hard rule**, and the toolchain (`uv`/`ruff`/`mypy`/`pytest`, `make check` ≥95%).

## The three repos (and the cross-repo rule)

- **vdocs** (producer) — `~/projects/vdocs`. Python pipeline. Commits docs+code **directly to
  `master`** (repo convention). Phases P0–P2, P6.2 land here.
- **vdocs-tui** (consumer) — `~/vista-cloud-dev/vdocs-tui`. Go. **branch → PR → squash-merge** (org
  Increment Protocol). Phases P3–P4 land here.
- **vdocs-web** (new consumer) — to be created in the `vista-cloud-dev` org. Go server + SvelteKit.
  Phase P5.

**Hard ordering (leaf-first):** producer changes land **before** consumer changes; the
`internal/index → pkg/index` extraction (P3.1) lands **before** any vdocs-web work. Do not start a
phase whose upstream dependency is not yet green. **One session ↔ one repo ↔ one branch** — `cd`
into the target repo before working; never `git init` a workspace root.

## Working protocol (per step, non-negotiable)

1. **TDD:** write the test first; confirm it fails (ImportError / assertion / missing column);
   implement; confirm green.
2. **Gate:** vdocs → `make check` (lint + mypy + coverage ≥95%); Go → `golangci-lint run` clean +
   `go test -race`. (Go is airgapped: `GOPROXY=file://$HOME/go/pkg/mod/cache/download GOSUMDB=off
   GOFLAGS=-mod=mod`.)
3. **Update the tracker:** fill the phase's **Changelog** (what landed), **Discoveries** (anything
   non-obvious you learned — promote surprises to the risk register), and **Lessons learned**. Flip
   the step's status (⬜→🟡→✅). If a discovery warrants a design change, mark ⚠️ and update the ADR.
4. **Commit:** stage only files you touched (never `git add -A`/`.`); `Co-Authored-By: Claude …`
   trailer; push. vdocs → master; vdocs-tui/vdocs-web → PR.
5. **Increment memory:** record non-obvious findings to project memory (the
   `read-contract-and-vdocs-web` memory is the workstream file — update it, don't duplicate).

**Additive-first discipline:** every contract change is additive (new view/column/capability, MINOR
version bump) unless a deliberate expand/contract MAJOR migration is scheduled. **Never delete a
consumer's input in the same step that introduces its replacement** — e.g. ship the `vocab` table
(P2.1) *before* deleting `explain.go`'s maps (P4.4).

**Fixtures, not the live lake:** contract/characterization tests run against tiny fixture DBs built
from the spec. **Never** run them against `~/data/vdocs/index.db` (294 MB; a live operator run may
hold it — check `pgrep -af "vdocs run"` first). Do not rebuild the lake to test the contract.

## Execution order

Start at **P0** and proceed in order. Each phase is shippable on its own.

- **P0 — Contract baseline (vdocs):** `meta(key,value)` table; stamp `read_schema_version="1.0"` +
  `corpus_snapshot` (hash a *sorted, content-only* projection — exclude build timestamps from the
  hash per RR/P0 risk); drop the leaked `doc_meta_staged`. No behavior change. **Smallest increment —
  do this first and fully.**
- **P1 — Read contract + views (vdocs):** `contracts/read/v1.json` describing today's schema
  verbatim; `v_*` views from the spec; document `chunks_fts`; `doctor` asserts emitted DB == spec;
  `contract-lint` enforces semver bump-type.
- **P2 — Vocab-as-data + drift gates (vdocs):** `vocab(kind,code,label,description)` from
  `registries/`; `doctor` enum-coverage gate; coverage stats + `capabilities` in `manifest.json`;
  corpus characterization (approval) test.
- **P3 — Shared Go core (vdocs-tui):** `internal/index → pkg/index` (isolated mechanical PR, API
  unchanged, gate green) **then** codegen + `RequiredSchemaVersion` runtime check + `make
  contract-check` drift alarm + contract-fixture test.
- **P4 — vdocs-tui consumes contract:** query `v_*` views; defensive optional columns; read all
  vocab from the `vocab` table; **delete** `explain.go`'s `personaDef`/`sectionDef`/`domainDef`.
- **P5 — vdocs-web (new repo):** scaffold → spine (`/api/facets` + `/api/candidates` over
  `pkg/index`, prove it green before anything else) → preview/TOC/fuzzy/FTS → DB auto-download +
  manifest validation → capabilities + `go:embed` → cross-compile.
- **P6 — Multi-consumer hardening (future/⛔ until MCP returns):** MCP endpoint; `make
  check-consumers` compatibility matrix.

## Definition of done (per phase)

The tracker row(s) are ✅, the gate is green, the phase's Changelog/Discoveries/Lessons are filled,
the work is committed+pushed, and (consumer phases) the downstream still builds against the new
contract. **Stop and report** at the end of each phase rather than steamrolling P0→P5 in one session
— let the operator review between phases.

## Open questions to confirm with the operator before P1

- **Contract distribution model:** ADR recommends *vendored copy + `make contract-check` against the
  local vdocs sibling*. Confirm, or choose `go.work`/submodule (tighter coupling).
- **`v1` vs `v2` naming:** the ADR text used `v2.json` illustratively; the tracker starts the stamped
  version at `1.0`. Confirm the first published contract is **v1** (recommended — it's the first).
- **vdocs-web repo creation:** confirm org (`vista-cloud-dev`) + private, and that creating the repo
  is authorized when P5 begins.

## First action

`cd ~/projects/vdocs`, re-read the ADR + tracker, then begin **P0.1** TDD-first: a test asserting the
published `index.db` has a `meta` table carrying `read_schema_version` and `corpus_snapshot` and that
`doc_meta_staged` is absent. Confirm it fails, implement in the index stage, confirm green, run `make
check`, update the P0 tracker section, commit to `master`, and report before starting P1.
