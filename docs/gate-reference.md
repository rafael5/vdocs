# The vdocs admission gate — operator reference

**What this is.** The *admission gate* decides which VA VistA Document Library documents enter the
`vdocs` corpus — what gets **fetched** (downloaded) and, identically, what reaches **gold**. It is
**declarative and reversible**: every decision lives in version-controlled YAML under
`registries/inventory/`, nothing is hard-coded, and flipping a decision + re-running re-partitions the
corpus. Nothing is ever deleted from the lake — an omitted document is simply not promoted.

> **See the effective gate before you run anything:** `vdocs gate`
> It prints the assembled policy in plain terms plus, when a gold inventory exists, how the gate
> partitions it (admitted vs excluded, with a per-doc-type breakdown).

---

## The gate is four narrowings, applied in order

A document is admitted only if it survives **all four**. The first two are computed upstream (at
`catalog`); the last two are the `GatePolicy` (`fetch/policy.py::load_gate_policy`) enforced by
`select_fetch_targets`.

| # | Narrowing | Driven by | What it drops |
|---|---|---|---|
| 1 | **Noise gate** (§9.5) | `registries/inventory/noise-domains.yaml` | site chrome, VBA forms, and other non-document rows (tagged `noise_type`) |
| 2 | **DOCX-only scope** (§1) | the pipeline (representation check) | non-DOCX representations (a PDF-only document yields no target) |
| 3 | **App scope** (G3) | `registries/inventory/scope-policy.yaml` | apps whose `system_type` lacks an allowed prefix, or whose `app_status` is denied (e.g. decommissioned) |
| 4 | **Doc-type policy** (G4) | `registries/inventory/doctype-policy.yaml` | doc-types explicitly marked `decision: omit` (Tiers B/C/D) |

Rows surviving 1–2 are the **genuine in-scope** universe; rows surviving all four are **admitted**
(the fetch targets, deduped to one per logical document).

---

## The two operator-facing files

### `scope-policy.yaml` — which **applications** are in scope (G3)
```yaml
app_scope:
  allowed_system_type_prefixes: [VistA]      # system_type must start with one of these
  denied_app_status: [decommissioned]        # …and the app status must not be denied
```
`"VistA + GUI"` matches the `VistA` prefix; `"Web client"` / pure-COTS apps do not.

### `doctype-policy.yaml` — which **document types** are kept (G4)
```yaml
default: keep                                # fail-safe: an untyped/unmapped doc is ADMITTED
doctypes:
  UM:   {tier: A, decision: keep, label: User Manual,        reason: reference core}
  RN:   {tier: B, decision: omit, label: Release Notes,      reason: ephemeral changelog}
  ...
```
- `decision: keep` → admitted; `decision: omit` → excluded. Each row records a `reason` so the
  trade-off is explicit at the toggle.
- **`default: keep` is the fail-safe (F5):** a document whose `doc_type` is empty or unmapped is
  **admitted** (and surfaces for triage in `vdocs doctor`) rather than silently dropped.

---

## Fetch gate vs gold gate

They are the **same gate at two checkpoints**, not two configs:
- **fetch** applies the gate so an out-of-scope or omitted document is never even downloaded;
- **gold** is reached by everything that was fetched — `consolidate` (G5) only *dedups* version
  groups, it does **not** re-admit or re-exclude.

So "what is fetched" == "what reaches gold". (If you ever need to fetch broadly but promote narrowly,
that would be a second, independent gold-gate config — it does not exist today.)

---

## Changing the gate (reversible)

1. Edit the relevant YAML (e.g. flip an `omit` → `keep`, or add a `system_type` prefix).
2. Preview the effect: **`vdocs gate`** (no run needed) — confirm the admitted count and breakdown.
3. Re-run from the inventory: `vdocs serve-inventory --force` → `vdocs fetch --all`
   (then the document plane: `vdocs run --from convert --to manifest`).

Because the policy fingerprint participates in `SKIP_IF_UNCHANGED`, a policy edit re-runs the affected
stages automatically; an unchanged policy is a no-op. To widen for a stress test (admit *all*
doc-types), flip every `omit` → `keep` and re-run from `serve-inventory`.
