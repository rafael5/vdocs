# Kickoff — End-to-End Pipeline Run + Gold-Library Quality Gate (emit GREEN)

**For a fresh session.** Goal: run the **entire vdocs pipeline de-novo with gated admission** to
build the gold document library, smoke-test it end-to-end, then run a **comprehensive quality &
fidelity validation** of the gold library — most especially the **`index.db` search indexes and the
YAML registries** that the search/queries depend on. End by emitting a single **GREEN** (or **RED**)
verdict. **GREEN is the gate that authorizes building the TUI** (see `tui-build-kickoff.md`).

> Read first: `docs/de-novo-run.md` (the run procedure), `docs/doc-classification-filtering-summary.md`
> (the authoritative spec for what *should* be in gold — every field, gate, and taxonomy), and the
> project memory `app-profiles-monograph.md`. The corpus is the **gated full set (~1,036 admitted
> docs)** built via a **real VDL fetch — no mocks, no omissions**.

---

## Part A — Build the gold library (de-novo, gated, real fetch)

Follow `docs/de-novo-run.md` exactly. Summary:

1. **Shared-lake check** (`pgrep -af "vdocs run"` + `reports/*.log`) — this is the big destructive op.
2. Wipe the derived lake; rebuild inventory (`vdocs crawl/catalog/serve-inventory --force`).
3. `vdocs fetch --all` — real VDL download of all **1,036** gate-admitted docs (verify
   `vdocs fetch --all --dry-run` says `1036 of 1036`). **Idempotent: re-run until `acquisitions`
   `failed = 0`** (network flakiness is expected; the gate guarantees only the 1,036 are attempted).
4. `vdocs run --from convert --to manifest --force` — convert → discover → enrich (bakes the 4
   persona tags) → normalize → consolidate (B1 grouping) → index → relate → manifest.

**Smoke test (every stage):** assert each stage recorded `status='ok'` in `state.db`, produced its
artifacts, and the counts are sane (no stage silently produced 0). Capture the per-stage counts.

---

## Part B — Comprehensive quality & fidelity validation

This is the core deliverable. Validate against the spec in `doc-classification-filtering-summary.md`.
Build a **validation report** (`reports/gold-validation.md` in the lake, or a committed doc) with a
PASS/FAIL per check and the final GREEN/RED. Be adversarial — *try to find corruption*.

### B1. `index.db` — the search surface (most critical)
- **Schema v3**: `documents` has `app_user, doc_user, software_class, function_category` columns +
  `idx_documents_persona`; `chunks_fts` (FTS5) exists; `entities`/`entity_mentions` present.
- **Persona columns populated**: `app_user`/`doc_user`/`function_category`/`software_class` non-empty
  for **~100% of `is_latest=1` docs** (every gold app has a profile → 100% coverage was proven).
  Any gap is a bug — list the offending `app_code`s.
- **FTS integrity**: `chunks_fts` row count > 0; a sample `MATCH` returns hits; FTS only indexes
  `is_latest` searchable chunks (no competing patch versions in results).
- **`is_latest` integrity (B1)**: exactly one `is_latest=1` per logical document; `anchor_key` is the
  **4-part** `app:pkg:doc_code:stem` form; **no over-grouped anchors** — e.g. `XU:XU:UG%` resolves to
  *many* distinct anchors, not 1 (the B1 fix). Cross-check: distinct `anchor_key` count ≈ gold doc count.
- **Gate fidelity**: `doc_type` distribution contains **only Tier-A codes** (UM/UG/TM/DG/API/INT/REF/
  AG/SM/SG/TG/QRG/TRG/FAQ) — **zero** DIBR/IG/RN/CRU/VDD/SUP/etc. (omitted B/C/D). Every `app_code`
  maps to an in-scope VistA app (no COTS/web/decommissioned).
- **Entities**: all 9 types present (routine/rpc/fileman_file/option/global/hl7_segment/mail_group/
  build/package_namespace); `entity_mentions` join is intact (no dangling `entity_id`/`doc_key`).
- **Facet counts work**: for each facet axis, `COUNT(*) … GROUP BY` runs and the totals reconcile to
  the gold doc count (these are the exact queries the TUI will run).

### B2. Registries (the YAML basis of classification & gates)
- All load without error and round-trip: `app-profiles.yaml` (104 profiles + 21 fallback + 71
  `_excluded`; **0 needs-review** except the known pending-fetch `MJCF`), `doc-user.yaml` (every
  in-corpus `doc_type` mapped; `operator` delegates resolve), `doctype-policy.yaml` (keep/omit;
  default keep), `scope-policy.yaml`, `system-types.yaml`, `doc-types.yaml`, `noise-domains.yaml`.
- **Gate consistency**: the doc_types present in gold == `doctype-policy` `keep` set; the apps present
  == `scope-policy`-admitted set. The registries and the actual corpus must agree.
- **Persona vocabulary closed**: every `app_user`/`doc_user` value ∈ {clinical, clinical-admin,
  business-admin, developer, sysadmin} (no stray/typo'd personas; no `needs-review` in gold).

### B3. Document metadata / frontmatter fidelity
- Every gold `body.md` carries the identity frontmatter (`app_code, doc_type, pkg_ns, patch_id,
  title, section, published, version, source_url, source_sha256, tool_ver`) **plus** the 4 persona
  tags. `source_sha256` matches the CAS; `doc_id` (`app_code:doc_slug`) is unique and joins
  inventory ⋈ index ⋈ frontmatter consistently.
- No mojibake / encoding artifacts in titles or bodies (spot-check); markdown is well-formed.

### B4. End-to-end search smoke (prove the queries the TUI needs)
- A few `vdocs ask "<q>"` return ranked, **pre-cited** real hits.
- Faceted queries via `server.facets`: `app_user=clinical`, `doc_user=developer`,
  `doc_type=UM`, an entity facet (e.g. a known routine/file) — each returns a sane candidate set.
- `facet_catalog` returns non-empty `app_user`/`doc_user`/`doc_type`/`entity_type` value→count maps.

### B5. Registry coverage vs the FULL corpus (the curated-input completeness check)
> **Why this matters:** the curated registries (`phrases`, `boilerplate`, `structures`, `templates`,
> `glossary`, `entities`) were built against the *dev sample*. The de-novo full corpus (~1,036 real
> docs) will contain patterns they don't cover yet — and the pipeline does **not** auto-learn them. It
> only *proposes* them: `discover` emits candidates to `reports/patterns`; a human promotes them into
> `registries/`; `normalize` then subtracts the *curated* ones. **Uncurated patterns pass straight
> through** — boilerplate not stripped, acronyms missing from the glossary, entities unrecognised —
> which directly degrades the gold corpus the TUI sits on. This is a *fidelity* check, distinct from
> B2 (which only checks the registries load/are-consistent).

- **Review `~/data/vdocs/reports/patterns`** (the `discover` output) for high-grade candidates the
  registries don't yet contain: recurring boilerplate blocks, dead phrases, acronyms/glossary terms,
  structural conventions, `(doc_type, era)` templates. Quantify: how many high-confidence candidates
  are **un-promoted**?
- **Coverage signals (sample the corpus):** residual boilerplate left in normalized bodies (the same
  block repeated across many gold docs → a missed `boilerplate.yaml` entry); acronyms in bodies not in
  the glossary; entity-types whose mention counts look implausibly low for the corpus (e.g. far fewer
  `routine`/`option` mentions than the ~1,036 technical docs should yield → `entities.yaml` patterns
  too narrow for the full corpus's naming).
- **Disposition:** if material gaps exist, **promote the high-grade candidates into `registries/`**
  (the human curation gate) and **re-run `normalize → index`** before declaring GREEN — the registries
  are the bedrock, so the corpus must be normalized against *curated* (not sample-era) patterns.
- If coverage is already adequate (few/low-grade un-promoted candidates, no gross residual
  boilerplate), record that and pass.

---

## Acceptance — the GREEN gate

- Every Part-B check PASSES; the validation report records each result.
- Emit a clear, final **`GOLD LIBRARY: GREEN`** (all checks pass) or **`GOLD LIBRARY: RED`** (with the
  exact failing checks). RED ⇒ do **not** proceed to the TUI; fix or report.
- Commit the validation report. **GREEN authorizes `tui-build-kickoff.md`.**

Be honest: if a check is weak or unmeasurable, say so rather than green-washing. The whole point is
that the TUI is built on a corpus *known* to be sound — the indexes and YAML are the search's bedrock.
