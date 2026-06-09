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
self-contradicting). To pull the true Class II apps out of the `I` default, the only authoritative
source is the VA **SAC/SACC class designations** or **FORUM National Patch Module / PACKAGE file
(#9.4)** — neither is in the corpus. When that list is available, seed a curated
`registries/inventory/software-class.yaml` (by namespace, same pattern as `package-master.yaml`) and
join it in the profile build to overwrite the default. Until then `software_class` stays I/III only.
This pairs with the gate: `software_class` + `vasi_status` are the per-app *importance* gradient the
gate's in/out decision doesn't capture on its own.

## References

- `registries/inventory/app-profiles.yaml` (draft) — `_excluded` / `_needs_fallback` blocks;
  `software_class` / `software_class_basis` / `vasi_status` fields.
- `scripts/seed_app_profiles.py` — `classify_scope`, `_distinct_apps` (the seed logic + signals).
- `src/vdocs/models/catalog.py` — `EnrichedRecord` (where `out_of_scope_reason` lives; add the
  app-level fields beside it).
- `docs/offline-lexical-search-plan.md` / `…-implementation-plan.md` — the active plan; wire the
  gate into the stage sequence there.
