# Title Normalization Proposal — de-noising gold document names

> **Status:** proposal, 2026-06-10. Companion to
> [`doc-classification-filtering-summary.md`](doc-classification-filtering-summary.md)
> (the field/gate reference) and the TUI work in `vista-cloud-dev/vdocs-tui`.
> Motivated by: in the faceted-discovery TUI, version/patch tokens embedded in
> document titles dominate the name and bury the actual application — and every
> app names its docs differently. This proposes a single de-noised display title,
> with version/patch preserved as the metadata they already (mostly) are.

## 1. Problem, quantified

Scan of all **615 `is_latest` gold documents** (`index.db`, the 2026-06-10 build):

- **72.7% (447/615)** of titles carry version and/or patch noise.
- That information is **already parsed** into columns: `patch_id` populated for
  **499/615**, `version` for **512/615** — yet it is *also* left verbatim in
  `title`, so the title is both redundant *and* inconsistent across the
  **109 distinct applications**, each with its own convention.

Representative raw titles (the pain):

```
RMPR*3*59 Delayed Order Report (DOR) (GUI) User Manual
Accounts Receivable Version 4.5 User Manual - Title Page
Controlled Substances Version 3 Supervisor's User Manual (Updated PSD*3*76)
National Drug File - User Manual (Updated PSN*4.0*575)
Consult/Request Tracking Technical Manual (GMRC*3.0*189)
PSGW*2.3*13 Automatic Replenishment/Ward Stock User Manual Change Pages
```

## 2. Noise taxonomy (what to strip), with frequency

| # | Class | Example | Freq |
|---|-------|---------|------|
| A | **`NS*ver*patch` token** (leading or inline) | `RMPR*3*59`, `PSO*7.0*123`, `IB*2` | 36% |
| B | **"Version/Release N[.N]" word** | `Version 4.5`, `Release 1.22.3` | 43% |
| C | **"(Updated NS*v*p)" parenthetical** | `(Updated PSN*4.0*575)` | 8% |
| D | **trailing/inline patch parenthetical** | `(GMRC*3.0*189)` | 4% |
| E | **bare dotted version** (no keyword) | `IEP 3.1`, `VSE GUI 1.7.2.1` | (subset of B) |
| F | **leading `NS*` token** (special case of A) | `XWB*1.1*73 …` | 22% |

Two structural problems beyond simple stripping:

- **App-name loss (36 docs).** When a title is *only* `NS*v*p` + a doc-type label
  (e.g. `XWB*1.1*73 User Guide`, `PSJ*5*279 Nurse's User Manual Change Pages`),
  stripping the patch leaves **just "User Guide"** — no product name. These are
  mostly **patch "Change Pages"** addenda whose identity *was* the patch.
- **Multi-segment versions** (`2.4.1`, `1.7.2.1`) and **punctuation variants**
  (`Version.5.1`) must be handled or they leak a fragment (`VBECS .1`).

## 3. Preserve, don't lose — the metadata model

Nothing is discarded; the version/patch is **moved** from the display string to
fields (most already exist):

| Field | Status | Role |
|-------|--------|------|
| `patch_id` (`PSO*7.0*123`) | **exists** (`documents` col + FM frontmatter) | the canonical patch identity |
| `version` (`7.0`) | **exists** | the version |
| `title` | exists — *raw* today | → becomes the **clean display name** |
| `title_source` *(new)* | proposed | the original raw title, kept for provenance/search |
| `app_name` *(new col)* | proposed | the application's canonical name (for the §5 fallback); sourced from the inventory `app_name_full` |

In gold `body.md` frontmatter the same holds: keep `patch_id`/`version` (already
baked), set `title` to the clean name, add `title_source`.

## 4. The normalized naming convention

> **Canonical display title** =
> `<Application/Product name>[ : <subtitle>][ <role/variant qualifier>] <Doc-type label>`
> — with all version and patch tokens removed.

Principles:

1. **App name leads.** The product/application name is the head of the title.
   When the raw title doesn't carry one (it led with a `NS*` token), fall back to
   the application's canonical `app_name` (§5).
2. **Keep the doc-type label word** ("User Manual", "Technical Manual"). It *is*
   redundant with the `doc_type` column, but humans expect it in a name and the
   user's complaint is specifically version/patch — so it stays. *(Optional future
   toggle: drop it for an even terser name, since the TUI already shows a doc-type
   tag.)*
3. **Keep meaningful qualifiers** that distinguish sibling docs: role
   (`Nurse's`, `Supervisor's`, `Inspector's`), variant (`GUI Version`,
   `List Manager Version`), part (`- ADT Module`, `Unit 4, Part 1`), and
   `Change Pages`. These are *not* version noise.
4. **Strip only version/patch**, never plain English. `Version`/`Release` are
   removed **only when followed by a number** — so `CPRS … GUI Version`,
   `Release Notes`, and `Auto Release` are correctly preserved.

## 5. The cleaning rules (validated against all 615)

Applied in order to the raw title; the parsed `patch_id`/`version` confirm what
was removed.

1. Remove `\s*\(\s*updated[^)]*\)` — the "(Updated …)" parentheticals.
2. Remove `\s*\([A-Z][A-Z0-9]*\*[\d.*]+\)` — inline patch parentheticals.
3. Remove `\b[A-Z][A-Z0-9]+\*\d+(\.\d+)*(\*\d+)?` — `NS*ver*patch` tokens.
4. Remove `\b[A-Z]{2,}\s+\d+\.\d+\s+\d+\b` — space-separated `SD 5.3 574`.
5. Remove `\b(version|release|rel\.?|ver\.?)[\s.]*\d+(\.\d+)*[A-Za-z]?\b` (case-insensitive) — keyworded versions, **number-required**.
6. Remove `\bv\.?\s*\d+(\.\d+)+\b` — short `v1.5` / `V. 1.6`.
7. Remove `\b\d+\.\d+(\.\d+)*\b` — bare dotted versions (`IEP 3.1`, `VSE 1.7.2.1`).
8. Remove orphans `\b\d+\.\d+\*\d+\b` and `\*\d+\b`; then tidy (empty parens,
   trailing `:`/`-`, doubled spaces, leading punctuation).

**Then** the §5 app-name fallback: if the result, with doc-type-label words
removed, has no name residue (≥3 alnum chars), prepend `app_name`
(e.g. `PRCA*4.5*315 AR User Manual` → fallback → `Accounts Receivable — AR User Manual`).

### Measured outcome

- **509/615 titles change**; **0 collapse to empty**.
- **8 residual "Version/Release" survivors — all correct** (variant names /
  `Release Notes`), not misses. The number-required rule (§4.4) is what saves them.
- **36 titles** trigger the app-name fallback (mostly Change Pages).

Before → after sample:

```
RMPR*3*59 Delayed Order Report (DOR) (GUI) User Manual   → Delayed Order Report (DOR) (GUI) User Manual
Accounts Receivable Version 4.5 User Manual - Title Page → Accounts Receivable User Manual - Title Page
Consult/Request Tracking Technical Manual (GMRC*3.0*189) → Consult/Request Tracking Technical Manual
National Drug File - User Manual (Updated PSN*4.0*575)   → National Drug File - User Manual
VistALink Version 1.5 Developer Guide                    → VistALink Developer Guide
QUASAR Version 3 User Manual (Updated ACKQ*3*21)         → QUASAR User Manual
XWB*1.1*73 User Guide          → [fallback] RPC Broker — User Guide
PSJ*5*279 Nurse's User Manual Change Pages → [fallback] Inpatient Medications — Nurse's User Manual Change Pages
```

## 6. Edge cases & manual overrides

- **`title-overrides.yaml`** (new, version-controlled registry, keyed by
  `doc_key`): a tiny escape hatch for any title the rules mangle. Today the rules
  need **~0** real overrides, but the registry keeps the fix data-not-code
  (tenet #13) and absorbs future oddities (e.g. HL7's irregular `HL7 V. 1.6*14`).
- **Change Pages / role variants** are preserved deliberately — they distinguish
  otherwise-identical sibling docs; removing them would create duplicate display
  names.
- **`app_name` dependency.** The fallback needs a canonical per-app name. It
  exists in the inventory plane (`EnrichedRecord.app_name_full`); expose it as a
  `documents.app_name` column at `index` time (a join, no new derivation).

## 7. Where to implement — two options

**Option A — canonical (recommended).** Compute the clean title in the **Python
pipeline** (a `kernel/titles.py` pure function), bake it into gold frontmatter
(`title` = clean, `title_source` = raw) at `enrich`/`normalize`, and land it +
`app_name` into `index.db` at `index`. Single source of truth → `vdocs ask`, the
TUI, and `publish` all get clean names for free. Cost: a re-index (no re-fetch,
no re-convert — cheap); the rules are deterministic and unit-testable
(property tests over the 615 titles as fixtures).

**Option B — display-only (interim).** A Go `cleanTitle()` in `vdocs-tui`,
applied at render time, using `patch_id`/`version` already in `index.db`. Ships
**immediately**, no pipeline change, no re-index — instant relief for the
reported TUI pain. Downside: each consumer (ask, publish) would re-implement it.

**Recommendation:** do **B now** for instant TUI relief, treating its rule set as
the executable spec; then land **A** as the durable fix and retire B's copy
(the TUI reads the baked `title`, falls back to `cleanTitle()` only if the column
is absent). The app-name fallback (§5) needs `app_name`, which arrives with A.

## 8. Acceptance

- Every gold title renders without a `NS*v*p` token, a `(Updated …)` clause, or a
  "Version/Release N" phrase — verified by re-running the §5 scan to **0** A–E
  matches (the 8 word-sense survivors excepted and asserted).
- No title is empty or shorter than its app name; the 36 label-only titles carry
  their `app_name`.
- `patch_id` + `version` remain populated and unchanged (the data is moved, not
  lost); `title_source` preserves the original for full-text search.
- Regression fixture: the 615 raw→clean pairs (Option A unit test / Option B
  Go test), so a rule change shows its full diff.
```
