# Kickoff — P1: acquisition-chain integrity (re-key raw/index.json + reconciliation gate)

**Repo: `vdocs`.** Start a fresh session, `cd ~/projects/vdocs` (one session ↔ one repo). Read
`CLAUDE.md`, then `docs/proposals/pipeline-audit-remediation-implementation-plan.md` **§P1**,
and skim audit sections [S4]/[S12] + register rows R‑2/R‑3/R‑8 in
`docs/reference/pipeline-adversarial-audit.md`. Tick
`docs/proposals/pipeline-audit-remediation-tracker.md` per landed step. **Shared-lake rule:**
before any command that touches `~/data/vdocs`, confirm no other pipeline process is live
(`pgrep -af "vdocs run"`).

## Where we are (measured 2026-08-01)

The audit found — and verified against the live lake — that `fetch` writes `raw/index.json`
keyed by **content sha256**, so two doc_ids whose DOCX bytes are identical collapse into one
entry (last writer wins). Live damage: **1,040 `fetched` acquisitions → 1,034 index entries**;
the six losers (`CPRS:cprsguitm_0_636`, `PSJ:psj_5_nurse_um`, `PSJ:psj_5_supr_um`,
`PSJ:psj_5_tm`, `PSN:psn_4_um`, `PSN:psn_4_tm`) have **no bundle anywhere downstream** yet
report `fetched` in `inventory --status`. Three aggravators in the current code
(`stages/fetch/stage.py:96-105, 148-156`):

1. the index is **merge-only** — withdrawn/renamed docs never leave it, so `convert`'s
   `prune_bundles` can never fire outside `--fresh`, and a re-fetched changed doc leaves TWO
   shas converting into the same bundle with dict-insertion order picking the winner;
2. a re-run **cannot self-heal** a lost entry: `SKIP_PRESENT` (`decide_fetch_action`)
   short-circuits *before* the index write, so already-`fetched` docs never re-emit entries;
3. **no gate anywhere joins the chain** — the six raised zero findings in `validate`,
   `doctor`, or anywhere else. That absent join is the systemic hole; the six docs are just
   its first observable.

## Goal

Three landed steps, one commit each (subject prefixed `P1.1:` / `P1.2:` / `P1.3:`):

1. **P1.1** — `raw/index.json` **format 2**: keyed by `doc_id`, *derived* each fetch run from
   acquisitions ⋈ gold inventory (not merged from the prior file).
2. **P1.2** — `validate` **Step 5, chain reconciliation**: blocking findings whenever
   fetched/raw-index/converted/normalized disagree, reported by doc_id.
3. **P1.3** — DOCX **magic check** before CAS admission; typed `bad_content` acquisition
   status (audit R‑8 — same seam, small).

TDD is the hard rule: every behavior below gets its failing test first.

## P1.1 — derive the v2 index (fetch)

**New pure function** `stages/fetch/fetch_pure.py::build_raw_index(targets, acquisitions) ->
dict`:

- `targets` = the **currently gate-admitted** fetch-target records —
  `select_fetch_targets(records, Selection(all_=True), policy)` — i.e. one DOCX
  representative per logical doc (this is what defines membership; the operator's narrower
  per-run selection must NOT narrow the index).
- `acquisitions` = `ctx.state.all_acquisitions()` (duck-type: needs `.status`, `.sha256`).
- Emit `{"format": 2, "docs": {doc_id: {sha256, app_code, doc_slug, title, source_url,
  ext}}}` for every target whose acquisition is `status == "fetched"` — identity fields from
  the target record (`app_name_abbrev`, `doc_slug`, `doc_title`, `doc_url`,
  `url_ext(doc_url) or doc_format`), sha from the acquisition. Deterministic: sort keys.

**Driver change** (`stages/fetch/stage.py`): delete the read-merge of the old file and the
per-download `index[sha] = …` write; after the download loop, derive via `build_raw_index`
and `atomic_write` the result. Set **`contract_ver = 2`** on `FetchStage` with a comment
(v2 = doc_id-keyed raw index) — this is what cascades: convert/normalize fold
`bronze/raw/index.json#contract_ver` into their `inputs_fp`, so a plain `vdocs run` re-runs
them without `--force`.

**Shared reader** so v1 files fail loud instead of half-working: a small
`fetch_pure.parse_raw_index(data: dict) -> dict[str, dict]` that returns `docs` when
`format == 2` and raises `ValueError("raw/index.json is format 1 (sha-keyed) — run: vdocs
fetch")` otherwise. Adapt both consumers to it:

- `stages/convert/stage.py`: iterate `parse_raw_index(json.loads(...)).items()` as
  `(doc_id, entry)`; the CAS read becomes `raw.get(entry["sha256"], ext=entry["ext"])`;
  bundle `key` derivation unchanged (`safe_component(entry["app_code"]) / …`). Two doc_ids
  sharing one sha now produce **two bundles from one CAS blob — intended**.
- `stages/normalize/stage.py::_sha_by_bundle_path`: value becomes `e["sha256"]`.

**Behaviors to pin with tests (write first, watch them fail):**

- duplicate-content pair → two entries with the same `sha256` (the live six);
- a doc_id absent from current admitted targets → absent from the index (withdrawn docs
  leave; also assert this makes a prior-run entry disappear, i.e. derivation ≠ merge);
- a `failed`/`permanent_missing`/never-attempted target → no entry;
- format marker present; `parse_raw_index` on a v1-shaped dict raises with the remediation;
- consumer adaptations against a v2 fixture (convert bundle set, normalize sha map).

**Gotcha:** don't "optimize" back to writing entries only for docs downloaded this run — the
whole point of derivation-over-merge is that entries for `SKIP_PRESENT` docs are (re)emitted
every run, which is what heals the six without any network.

## P1.2 — chain-reconciliation gate (validate Step 5)

**New pure module** `stages/validate/chain_pure.py`:

```python
@dataclass(frozen=True)
class ChainFinding: kind: str; doc_id: str; detail: str

def reconcile_chain(*, admitted: set[str], fetched: set[str], raw_index: set[str],
                    converted: set[str], normalized: set[str]) -> list[ChainFinding]
```

Blocking finding kinds (each lists offending doc_ids, so `verification.json` carries a
computable set difference, not a bare count):

- `fetched-not-admitted` — fetched ⊄ admitted (a doc the gate no longer admits still in the
  corpus: the R‑10 staleness class);
- `fetched-not-indexed` / `indexed-not-fetched` — raw_index ≠ fetched (P1.1's derivation
  verified **independently from the on-disk artifact**, not trusted);
- `indexed-not-converted` — a raw-index doc_id whose `<app>/<slug>` bundle is missing under
  `01-converted` (compare on `bundle_path`, via `kernel.ids.bundle_path` — doc_ids with
  distinct slugs never collide there);
- `converted-not-normalized` / `normalized-not-converted` — the silver trees disagree.

**Driver wiring** (`stages/validate/stage.py`): add `requires` GOLD_INVENTORY + RAW_INDEX +
TEXT_CONVERTED + REGISTRIES (real contract edges — the admitted set needs the inventory *and*
the gate policy, which lives in registries). Build the five sets: admitted from
`select_fetch_targets(records, Selection(all_=True), load_gate_policy(...))` mapped through
`doc_id()`; fetched from `ctx.state.all_acquisitions()`; raw_index via
`fetch_pure.parse_raw_index`; converted/normalized from `rglob("body.md")` bundle paths
mapped back through the raw-index entries' `bundle_path`. Chain findings join `blocked_by`
(same pattern as `reconcile_findings`) and land in the report under `"chain_findings"`.

**Preflight ripple to check, not assume:** validate now `requires` fetch-produced artifacts —
on a lake with a wiped `state.db` this makes validate FAIL wanting a fetch record. That is
correct behavior (the gate refuses to bless an unverifiable chain); confirm the existing F4
carve-outs don't apply and note it in the commit message.

**Tests first:** healthy fixture lake → zero findings; then one test per finding kind with
exactly one seam broken (delete an index entry / drop a bundle / add an orphan acquisition);
plus report-shape (doc_ids listed) and blocking behavior (`deep_gate` fails).

## P1.3 — content admission at the CAS door

In the fetch download loop, before `store.put`: a 2xx body that does not start with
`PK\x03\x04` (DOCX = ZIP container) is **not stored**; record the acquisition with new status
`bad_content` (+ `error="not a DOCX (magic mismatch)"`, attempts accrue like `failed`, and it
retries like a transient — a WAF hiccup shouldn't permanently blacklist a URL). Check the
`Acquisition.status` typing in `models/stage.py` (extend the Literal if it is one), add
`bad_content` to `serve_pure._STATUS_ORDER`, and surface it in the run warnings alongside the
failed list. Pure predicate `fetch_pure.is_docx_payload(data: bytes) -> bool` + tests
(happy, HTML error page, empty body, attempts accrual, no CAS write on reject).

## Acceptance — the P1 ✓ tracker row (all demonstrated, then ticked)

1. `make check` green (lint + mypy + full tests ≥95% cov).
2. On the live lake (network fine, mostly CAS-side): `vdocs fetch --all` (contract bump makes
   it PROCEED without `--force`), then `vdocs run --to manifest`. Expect the cascade to run
   convert→…→manifest via the `#contract_ver` fold, with **no `--force`**  — if stages skip,
   that is itself a finding against the cascade logic; stop and diagnose.
3. Measured equalities, recorded in the tracker Notes:
   `fetched (1,040) == raw-index docs == converted bundles == normalized bundles ==
   doc_meta_staged rows`; the six doc_ids present in `doc_meta_staged`
   (`sqlite3 ~/data/vdocs/index.db "SELECT doc_id FROM doc_meta_staged WHERE doc_id IN (…)"`)
   . Expected downstream shifts — verify, don't be surprised by: documents 1,034 → 1,040;
   consolidate groups 615 → ~617 (the CPRS/PSJ twins share slug stems and fold into existing
   version groups; the two `psn_*_r` twins have distinct stems and mint new groups — that
   duplicate-content pair of anchors is *correct*: dedup now happens at version-grouping, not
   by silent index collapse); `validate` green including the new Step 5; `vdocs doctor`
   GREEN (615-baseline checks re-baseline themselves off live counts — confirm no floor in
   `registries/doctor-policy.yaml` hardcodes 615).
4. Red-path demo on a **scratch lake** (`DATA_DIR` override — never the live one): break one
   seam by hand (delete a raw-index entry), run `validate`, show the blocking finding, restore.
5. Tick tracker rows P1.1–P1.3 + P1 ✓ (commit hashes + measured numbers), then per the
   execution protocol: **write `P2-doctor-into-the-dag-kickoff.md`** (plan §P2, folding in
   P1's final measured counts), update the prompts README row, and retire this prompt to
   `docs/prompts/historical/`.

## Increment protocol

Commit + push per step (trailer per `~/.claude/CLAUDE.md`); update
`docs/vdocs-design.md` in the P1.1 commit (RAW_INDEX shape + fetch contract note) and the
P1.2 commit (validate's new requires/Step 5). If anything here contradicts the code you find,
**the plan is the bug report** — stop and reconcile the plan first, don't improvise around it.
