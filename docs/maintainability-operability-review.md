# vdocs — maintainability & zero-AI-operability review

**Date:** 2026-06-14 · **Scope:** the whole `vdocs` Python pipeline (`src/`, `tests/`, `docs/`,
`Makefile`, `pyproject.toml`). **Goal:** (1) how easily a new human could take over maintenance,
and (2) whether a competent operator can run the pipeline end-to-end **with zero AI** "looking over
the shoulder" to decode errors. **Method:** five parallel grounded code audits (architecture,
cross-stage consistency, operability, clarity, tests/reproducibility), each citing `file:line`,
plus direct verification of the two load-bearing claims.

> This is a review/proposal doc (no code claims here are aspirational — they cite the tree as of
> 2026-06-14). The P0 fixes below are being landed in the same branch (`ops-zero-ai-p0`); P1/P2 are
> proposed follow-ups.

## Verdict

`vdocs` is a **genuinely well-architected pipeline** — internal quality is high enough that a
competent dev can read and own the *code* comfortably. The gap is **cold-start operability**: a
fresh-clone human following only the docs, with no AI, is stranded today by a handful of specific,
fixable things. **It is not yet zero-AI-runnable — but it is one small punch list away.**

| Dimension | Score | One-line |
|---|---|---|
| Modularity | 4.5/5 | Generic topo-sort DAG, single-definition contracts, strictly-honored pure/IO split; adding a stage touches ~4 files and nothing else. |
| Consistency | 4/5 | Uniform `Stage` skeleton, one gate path, one error-isolation pattern; a few un-promoted helpers + two ghost packages. |
| Non-redundancy | 3.5/5 | §9.2 mostly upheld, but 3 real copy-paste sites. |
| Clarity / self-doc | 4/5 | Best dimension — dense *why*-focused docstrings, intent-revealing names, an exemplary user guide; undercut by a stale README. |
| Tests / reproducibility | 4/5 | Real CI, fully-pinned toolchain, 927 tests / ~98% cov, no mocks, property tests — but the gate is RED right now. |
| **Zero-AI operability** | 3/5 | Excellent run/gate/doctor UX, honest resume — but a fresh human won't get past `convert`, or even launch `vdocs`. |

## What is genuinely well-built (so a maintainer doesn't "fix" it)

- **Generic orchestrator.** `orchestrator/engine.py` derives execution order by Kahn topo-sort over
  each stage's `requires`/`produces` contracts — there is **no hand-maintained ordered stage
  list**. Cycle/duplicate/unknown-stage errors are explicit.
- **Gating logic lives exactly once.** `orchestrator/stage.py` owns preflight/postflight/skip/
  fingerprint-diff/error-rate gating on the `Stage` base class; concrete stages override only
  `run()` (and optionally `deep_gate`). No stage re-implements gating.
- **Principled resume/idempotency.** `state.db:stage_runs` keyed `(stage, scope)`; skip is decided
  by comparing `inputs_fp` + `contract_ver`. The `contract_ver` bump folds into downstream
  `inputs_fp` so a producer shape-change forces consumers to re-run.
- **The purity rule holds.** No `*_pure.py` file does I/O (verified); stage drivers are thin.
- **Tests are honest.** Real CI (`.github/workflows/ci.yml`, `uv sync --frozen`), pinned toolchain
  (`uv.lock`, `.python-version`), 927 tests / 97.95% branch coverage, **no mocks** (only
  `monkeypatch` seams), deterministic (no clock/random/network), 13 Hypothesis property-test files
  on the pure transforms.
- **The 2026-06-10 operability hardening was real:** `gate → build --fresh --yes → doctor` is one
  consistent model across docs; GREEN/WARN/ERROR + exit codes are first-class; the orchestrated
  path is traceback-free; `fetch` resume is idempotent and bakes in the "don't thrash the VDL-500s"
  gotcha (`permanent_missing`); the shared-lake guard prevents the two-orchestrator race.

## The zero-AI operability gap (the crux)

Ranked by how likely each is to strand a no-AI human.

1. **[P0] `make check` is RED out of the box (verified).**
   `tests/integration/test_cli.py::test_build_fresh_refuses_without_yes` invokes `vdocs build
   --fresh` in-process, which reaches the real `_other_vdocs_running()` (`cli/app.py:434`, shells
   `pgrep -af vdocs`). That self-matches — the `.venv` lives under `…/projects/vdocs/`, so the
   pytest interpreter's own path contains "vdocs" — so the test fails **deterministically, even
   with no other vdocs process running** (confirmed: `pgrep` returns nothing, the test still
   fails). A human's first health check is RED and they cannot tell regression from environment.
   **Fix:** `monkeypatch.setattr("vdocs.cli.app._other_vdocs_running", lambda: False)` in that test
   (its sibling already does this). One line.

2. **[P0] Pandoc is an undocumented hard dependency, and its absence is mis-reported as a corpus
   defect.** `convert/stage.py` shells `pandoc` for every doc (the default converter). It is not in
   `pyproject.toml` (it can't be — it's a system binary), not in any prereq doc, and there was no
   `shutil.which` preflight. With no pandoc, every doc raised `FileNotFoundError`, each swallowed by
   `DocLoop` → `doc_error_gate` fails the stage as "systemic," and the operator saw *"N documents
   failed to convert: …"* — **never "pandoc is not installed."** **Fix:** a `convert` preflight
   that fails with remediation, + list pandoc (and docling for routed bundles) in the prereqs.

3. **[P1] `vdocs` isn't on `PATH` after `make install`, and no doc says how to invoke it.**
   `make install` → `uv sync` puts the binary at `.venv/bin/vdocs`; every doc says `vdocs gate`. A
   fresh human gets `command not found`. **Fix:** document `uv run vdocs …` (or activation) once.

4. **[P1] README misdirects to the wrong source of truth.** `README.md:8-10` calls
   `docs/vdocs-design.md` the SSOT and cites `fidelity-framework.md` + `kickoff-prompt.md` — all
   three gone from `docs/` (moved to `historical/` or nonexistent), and still markets the descoped
   "semantic" product. The first file anyone opens sends them to vanished/frozen docs. **Fix:**
   repoint to `offline-lexical-search-plan.md` (active plan) + `vdocs-user-guide.md` (onboarding).

5. **[P2] No volume/time expectations** (~1000+ DOCX, multi-GB, ~6-min fetch, VDL bulk-500s), and
   **aux commands** (`gate`/`fetch`/`doctor`/`ask`) aren't routed through the clean reporter, so a
   malformed registry YAML surfaces as a raw traceback rather than an ERROR+remediation line.

## Internal-quality findings (real, mostly small)

**Redundancy (§9.2 violations):**
- `blocks_publish` triplicated byte-for-byte across `fidelity/{retention,compliance,overstrip}_pure.py`
  → extract one `_verdict.py`.
- The `(safe_component(app), safe_component(slug)) → record` bundle-path join hand-rolled 3× with
  drifting rules (`enrich/stage.py:74`, `discover/stage.py:74`, `normalize/stage.py:316`) → one
  `kernel/bundle.index_records_by_path()`.
- `tables/*.csv` reader duplicated (`index/stage.py:311` vs `manifest/stage.py:113`); `kernel/csv.py`
  only *writes* → add `read_rows()`.

**Ghost / dead code (a maintainer trips on these):**
- `src/vdocs/stages/embed/` is an **empty phantom dir** (only stale `__pycache__`) that 3 docs say
  is "gone" → `rm -rf`.
- `fidelity/` has pure modules but **no `stage.py`** and isn't in the DAG; only `retention_pure` is
  consumed — `compliance_pure`/`overstrip_pure` (~275 LOC) are dead → wire a `FidelityStage` or move
  to a clearly-marked `parked/`.
- `kernel/lineage.py` has zero importers → delete or wire.

**Consistency snags:** `catalog/enrich_pure.py` is misnamed (collides with the real `enrich` stage,
same `ep` alias) → rename `catalog_pure.py`; `build_stages()` lives in `cli/app.py` and stages get
`selection` via `# type: ignore` attribute injection → move to a `pipeline.py`, pass via context.

**Docs-vs-code drift (erodes trust):** `CLAUDE.md` Toolchain still lists `sqlite-vec`/`MCP` (not in
`pyproject`); the lean plan's tracker shows L1 ⬜ while the impl tracker shows it ✅-done;
`CHANGELOG.md:9` points at a nonexistent `CHANGES.md`; `TODO.md` is an empty skeleton.

## Prioritized punch list

- **P0 — unblock zero-AI run (~½ day):** (1) monkeypatch the pgrep test → gate green; (2) pandoc
  preflight + prereq docs. These two alone move operability 3 → ~4.5. *(Landing in this branch.)*
- **P1 — takeover hygiene (~1 day):** `uv run vdocs` everywhere; rewrite README to the real SSOT;
  `rm` the `embed/` ghost; sync `CLAUDE.md` toolchain + the two trackers.
- **P2 — durability (~1–2 days):** de-dup the 3 copy-paste sites into the kernel; decide
  `fidelity/`'s fate; route aux commands through the reporter; add volume/time expectations to
  `de-novo-run.md`; delete dead `lineage.py`/`TODO.md`.

## Future-development recommendations

- **`vdocs preflight` command** — a single up-front check of pandoc/docling/disk/network/data-dir
  that fails with remediation. The highest-leverage zero-AI investment (most stranding happens
  before stage 1).
- **Smoke-test a real conversion in CI** — convert one tiny DOCX with pandoc so a green gate proves
  the pipeline *runs*, not just that code lints. Today `make check` green does not exercise pandoc.
- **Promote `contract_ver` discipline** to the other derived-store producers (`inventory.db`,
  `doc_meta_staged`, `relations`) so a schema change there also forces downstream re-runs (only
  `index` uses it today).
