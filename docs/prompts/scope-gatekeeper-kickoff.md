# Kickoff — Corpus Scope Gatekeeper (deterministic, declared admission gate)

**For a fresh session.** Goal: turn the ad-hoc "what's allowed into vdocs" rule into a **single,
deterministic, version-controlled gate** that every app/document passes through before it is
fetched, analysed, or published to the gold library. Right now the rule lives only as helper
logic in `scripts/seed_app_profiles.py::classify_scope` and as the `_excluded` block of the draft
`registries/inventory/app-profiles.yaml`. Promote it to a real pipeline gate.

## Why this exists (the policy — declare it, don't re-derive it)

vdocs is a **VistA (M-based) corpus**. These classes are **out of scope** — never fetched,
converted, enriched, indexed, or published to gold:

1. **Non-VistA / pure COTS** — commercial products and standalone systems that aren't VistA M
   packages (e.g. `system_type` ∈ {COTS product, Web client, VA enterprise service, Integration
   middleware, VBA system, Program documentation, Data patch}).
2. **Decommissioned** — retired packages (`app_status == "decommissioned"`, or VDL/Monograph
   marks them retired).
3. **Inactive** — Monograph `VASI System Status == "Inactive"`.

**In scope = active VistA M package.** Concretely the current predicate (the seed of the gate):

```
in_scope  ⟺  system_type.startswith("VistA")          # VistA, VistA + GUI/COTS/middleware
            AND app_status != "decommissioned"
            AND vasi_status.lower() != "inactive"
```

VistA-hybrids (`VistA + COTS`, `VistA + GUI`, `VistA + middleware`) **stay in** — they are
VistA-based. Only *pure* COTS/web/enterprise-service apps are excluded.

> **This is an app-level scope axis, distinct from the existing doc-level one.** `EnrichedRecord.
> out_of_scope_reason` already gates by *document format* (docx-only, §1/§5.6). The gatekeeper adds
> an orthogonal **app-level** gate (app type / lifecycle). Keep them separate fields; a doc is
> admitted only if **both** gates pass.

## What already exists (reuse, don't reinvent)

- `scripts/seed_app_profiles.py` — `classify_scope()` is the reference predicate (tested in
  `tests/unit/test_seed_app_profiles.py`). The draft `registries/inventory/app-profiles.yaml`
  `_excluded:` block is the current ruling on all 196 apps (61 non-vista + 13 decommissioned + 9
  inactive = 83 excluded) — use it as the expected-output fixture for the gate.
- Signals available on every inventory row: `system_type`, `cots_dependent`, `app_status`,
  `app_name_abbrev`, `pkg_ns`; plus Monograph `VASI System Status` where the app joins.

## Two gates, one job

The gatekeeper has **two orthogonal axes**, both "what's allowed into gold," both declared-as-data:
- **App-level scope** (this doc's main subject): active VistA only — `registries/inventory/scope-policy.yaml`.
- **Document-level type policy**: which *doc types* are reference-worthy —
  **`registries/inventory/doctype-policy.yaml`** (already drafted). A doc is admitted only if **both**
  its app is in-scope **and** its doc-type `decision: keep`.

### Document-level type policy (already drafted — wire it in)

`doctype-policy.yaml` declares, per doc_type code, `decision: keep|omit` with a `tier` and a `reason`.
**Decision (2026-06-09): keep Tier-A reference core; explicitly OMIT Tiers B, C, D** — this drops the
in-scope corpus from 3728 → **1390 kept (37%)**, omitting 2338:
- **B** install/deploy/operational runbooks (DIBR 668, IG 405, IG-IMP, POM, CFG, SG-SET, RS) — version-specific procedure;
- **C** ephemeral version-delta changelog (RN 796, CRU 168, VDD, PDD, WF) — describes a release, not the system;
- **D** fragments (SUP, APX, DESC, CVG) — not standalone.

**It is a reversible toggle, by design** — omitted docs are NOT deleted from the lake, just not
promoted to gold. To re-admit a category, flip its `decision: omit` → `keep` and re-run from
`serve-inventory`; the per-code `reason` makes the trade-off explicit at the toggle. `default: keep`
is fail-safe (a new/unmapped doc_type is admitted + surfaces for triage, never silently dropped).
Enforce it at the same gate as app-scope (skip + log omitted docs in `state.db`); expose `doc_kept`
+ the policy `tier` as an `index.db` facet; regression-fixture the 1390/2338 split so it can't drift.

## The task (TDD — test first, per CLAUDE.md)

1. **Declare the policy as data**, not code: add `registries/inventory/scope-policy.yaml` —
   the allowed/denied `system_type` values, the denied `app_status`/`vasi_status` values, and any
   per-app manual overrides (with rationale). Discovery is data (tenet #13), so the gate reads the
   registry; it never hard-codes the lists.
2. **Add an app-level scope field to the inventory** (`EnrichedRecord`): e.g. `app_in_scope: bool`
   + `app_scope_reason: str`, derived in the `catalog`/`enrich` stage from the scope-policy
   registry. Pure function first (`*_pure.py`), unit test first.
3. **Enforce at the front of the document pipeline**: `fetch` (and any promote-to-gold step) must
   **skip** out-of-scope apps and record the skip in `state.db` — nothing out-of-scope reaches
   bronze/silver/gold. Make the gate the *only* place this decision is made.
4. **Surface it**: expose `app_in_scope` as a column/facet in `index.db` and stamp it into gold
   document frontmatter (so the boundary is visible offline).
5. **Regression fixture**: assert the gate's ruling on the current 196 apps matches the
   `_excluded` set in the draft profiles (lock the boundary so it can't silently drift).

## Acceptance criteria

- One registry declares the policy; one pure predicate enforces it; zero hard-coded lists in stages.
- `make check` green (lint, mypy, ≥95% coverage on the new pure code).
- Re-running `fetch` admits exactly the in-scope VistA apps; out-of-scope apps are skipped with a
  logged, queryable reason — verified against the 83-app `_excluded` baseline.
- `app_in_scope` is visible in the inventory, the index, and gold frontmatter.

## Related follow-up — Class II via the VA SAC list (importance filtering)

`app-profiles.yaml` already carries a deterministic `software_class`: **`I` (national)** by default
(every in-scope app is in the VDL, which only catalogs nationally-released software), with a single
**`III`** override (NUPA — explicit own-doc reclassification). **`II`** is deliberately *not*
assigned: the field-developed / nationally-distributed-but-optional middle tier is not separable
from the Monograph or doc text (doc-level class mentions are component-level and noisy — 24/142 apps,
self-contradicting).

**Verified (2026-06-09) via the `vista` CLI** (code/doc model of a live VistA): FileMan file **#9.4
PACKAGE** (`^DIC(9.4,`, 31 fields, 479 records) **has no software-class field** — checked every
CLASS-named FileMan field in the model; none belongs to #9.4. Class I/II/III is a **SAC/SACC**
attribute managed on **FORUM** (the national dev / National Patch Module system), not a field in the
distributed PACKAGE file. So #9.4 is a **dead end for class**; the published VA **SAC class list** is
the *only* source. When it's available, seed a curated `registries/inventory/software-class.yaml` (by
namespace, same pattern as `package-master.yaml`) and join it in the profile build to overwrite the
`I` default. Until then `software_class` stays I/III only. `software_class` + `vasi_status` are the
per-app *importance* gradient the gate's in/out decision doesn't capture on its own.

**Namespace cross-check (same `vista` model).** #9.4 *is* the authoritative installed-package roster
(174 namespaces). 87/113 profile namespaces validate against it directly; the 26 non-matches are
**not errors** — they're (a) sub-prefixes of a parent package recorded under #9.66 (FFP=DGFFP,
PRF=DGPF, RMDS=DGRU under DG; SSO/UC=XUSC, XQOR under XU), (b) sub-products of one package (KMPD/KMPR/
KMPS/KMPV/RUM/SAGG → the single `KMP` "Capacity Management" package), (c) registry sub-systems (EFR,
NCR, ROEB/ROEG/ROEV, TBI), and (d) apps newer than / absent from the modeled instance (MJCF, ASCD,
CHDS, IVMB, PAIT, SRA, XOB). Small enrichment opportunities surfaced: fill the empty `namespace` on
ONCO (→ `Oncology` package) and optionally record each sub-prefix app's **parent package**. The
`vista` CLI is a live VistA model worth using to validate the whole profile/namespace set.

## References

- `registries/inventory/app-profiles.yaml` (draft) — `_excluded` / `_needs_fallback` blocks;
  `software_class` / `software_class_basis` / `vasi_status` fields.
- `registries/inventory/doctype-policy.yaml` (draft) — the document-level keep/omit policy
  (Tier A kept; B/C/D omitted, reversible per-code toggle).
- `scripts/seed_app_profiles.py` — `classify_scope`, `_distinct_apps` (the seed logic + signals).
- `src/vdocs/models/catalog.py` — `EnrichedRecord` (where `out_of_scope_reason` lives; add the
  app-level fields beside it).
- `docs/offline-lexical-search-plan.md` / `…-implementation-plan.md` — the active plan; wire the
  gate into the stage sequence there.
