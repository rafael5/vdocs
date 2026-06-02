# Handoff + kickoff prompt — land the open PR stack, then start Phase 4 (`consolidate`)

> Paste this whole file as the opening message of a fresh session. It is self-contained except for
> the repo itself. **Part A** clears the outstanding git/PR state and the two logged follow-ups;
> **Part B** is the next build increment. Keep `make check` green between increments
> (ruff line 100 · mypy · pytest random-order · coverage ≥95%). Read the files it points at before
> writing code. The design doc is the source of truth — **propose design changes by editing it first**.

## Where things stand (2026-06-02)

Phase 3 silver is **complete** — `convert`/`discover`/`enrich`/`normalize` all green on a real
469-doc VA corpus; `make check` green (385 tests, 100% cov). The `normalize` F-steps all shipped,
including the legacy-TOC strip (`registries/structures` CANONICALIZE `toc`) added this session.
**All Phase-3 work is merged to `master`** (PRs #3/#4/#5) — the working tree is clean and the next
build starts from a green master.

### A1 — The feature PR stack (DONE — merged; just verify) + dependabot (open)

The three stacked feature PRs are **merged to `master`** (origin/master tip = `224ab51`,
"Merge pull request #5"):

```
PR #3  feat/normalize-refs-yaml-anchors  — P0–P2 + normalize ✅ (Phase 3)        MERGED
PR #4  fix/design-compliance             — close 5 design-vs-code deviations     MERGED
PR #5  feat/strip-legacy-toc             — strip legacy in-body TOC              MERGED
```

So there is **no merge work outstanding** on the feature side. Just verify the landed state before
building on it:

```bash
git checkout master && git pull && make check     # must be green (385 tests, 100% cov)
git log --oneline -6                              # normalize + compliance + legacy-TOC commits present
```

Still open and independent of the stack:
- **Dependabot PR #1 (actions/checkout 4→6)** and **PR #2 (setup-uv 5→7)** — merge or close at will;
  they touch only CI workflow pins. (There is no CI configured to gate on, so the merge gate is a
  local `make check`.)
- The merged feature branches (`feat/normalize-refs-yaml-anchors`, `fix/design-compliance`,
  `feat/strip-legacy-toc`) can be deleted locally/remotely once you've confirmed master is green.

### A2 — Two logged follow-ups inside `normalize` (small; do opportunistically, not blocking Phase 4)

`registries/structures` has three curated CANONICALIZE conventions; only `toc` is consumed. The other
two are curated-but-unbuilt and explicitly logged in the tracker (row 60) and `registries/structures/README.md`:

- **`callout` → GFM alerts.** Admonition styling (`**Note:**`, `NOTE:`, `**Warning** :`, …) →
  `> [!NOTE]` / `> [!WARNING]` / a bold blockquote for non-alert labels (Example/Reminder). This is a
  **multi-line body transform** (label line + continuation) — riskier than the TOC strip, so it earns
  its own TDD increment. Add `_load_structure_callouts()` in `normalize/stage.py` (mirror
  `_load_structure_toc_titles`) and a `canonicalize_callouts()` pure step in `normalize_pure.py`,
  wired into `normalize_body` after `subtract_boilerplate`. Write the failing unit test first.
- **`revision-table` heading shape.** The revision *table* already leaves the body to `history.yaml`
  (`revision_pure`, §6.6); only a residual heading variant (`## Revisions` → `## Revision History`)
  would remain. Low value — fold it into the callout increment or skip with a one-line note.

These are **not** required to start Phase 4. Mention them, don't gate on them.

## Part B — Next build increment: `consolidate` (Phase 4 head, §6.6 / §8 / §17 step 4)

With Phase 3 silver done, the design's next stage is **`consolidate`** — the head of **Phase 4 (Gold
derive)**: `consolidate → index → relate → manifest`. Start here because it directly consumes the
`history.yaml` lineage that `normalize` now produces, and everything else in Phase 4 depends on the
version-group grouping it establishes.

### Read first (source of truth)

- `docs/vdocs-design.md` **§6.6** (version lineage: one anchor document, patch history captured for
  later git replay) — the *what and why*. **§8** consolidate row — the contract. **§5.5** (stable IDs)
  and **§5.6 / §566–570** (`anchor_key` version-group grouping; `consolidate` finalizes grouping for
  rows whose `doc_code` was unresolved). **§4 / §327 / §397** (gold lake layout:
  `gold/consolidated/<app>/<type>/...`).
- `docs/vdocs-implementation-tracker.md` Phase-4 rows — current status (all ☐).
- The shipped producers it builds on: `normalize/stage.py` + `normalize/revision_pure.py`
  (`history.yaml` shape) and `catalog` (`group_key` / version-free `anchor_key`).

### The contract (from §8 — authoritative)

```
consolidate · 🥇 DOC · SKIP_IF_UNCHANGED
  requires:  text@normalized, assets
  produces:  consolidated/ — one anchor document per version group; ordered history.yaml lineage +
             retained prior bodies captured as travel-with sidecars; is_latest flagged
```

What it must do (§6.6):
1. **Group** every normalized bundle by its **version-free `anchor_key`** (= identity with the
   patch/version component removed). Order members **oldest → newest** (patch number, then official
   revision date). Finalize grouping for bundles whose `anchor_key` was empty (singletons) per §566–570.
2. **Collapse each group to one anchor document** at a stable, version-free path
   (`gold/consolidated/<app>/<type>/<anchor-slug>/`), whose `body.md` is the **latest** normalized body.
   Prior versions are **not** separate published files.
3. **Capture lineage, don't replay** (§6.6): write/extend the anchor's `history.yaml` — ordered, for
   each version: patch id, official date, revision note, `source_sha256`, stable doc ID, and a
   **content-addressed reference to that version's retained normalized body**. Retain prior bodies
   content-addressed (CAS); never re-acquire. Capture is **append-only** — a later run that promotes a
   new latest body appends one entry and retains the previous body; nothing already captured is rewritten.
4. **Flag `is_latest`** on the newest member (this is a computed field → it belongs in `index.db`
   per §6.3, but `consolidate` is the stage that *determines* it; record it where the design says — the
   §8 `index` row owns the table, so consolidate's job is the grouping + ordering that `index` reads).

### Build it the project way (TDD, §9.2)

- **Pure core first:** `src/vdocs/stages/consolidate/consolidate_pure.py` — zero I/O. The grouping +
  ordering + lineage-merge logic over plain values: `group_by_anchor_key(bundles) -> groups`,
  `order_members(group) -> ordered`, `merge_history(existing, ordered) -> history` (append-only).
  Write each failing unit test first (realistic multi-patch fixtures: e.g. `ADT/DG` 5.1 → 5.2 → 5.3),
  confirm red, implement, confirm green.
- **Thin I/O driver:** `src/vdocs/stages/consolidate/stage.py` — a `Stage` subclass
  (`requires=[TEXT_NORMALIZED, ASSETS]`, `produces=[CONSOLIDATED]`, `SKIP_IF_UNCHANGED`). Reuse the
  kernel: `cas` for content-addressed prior-body retention + atomic writes, `frontmatter`, `lineage`.
  **No copy-paste across stages** (§9.2) — if you need a primitive that isn't in `kernel/`, add it there.
- **Add the `CONSOLIDATED` contract** to `contracts/registry.py` (a `TREE_*` over the gold bundle, like
  `TEXT_NORMALIZED`) and the gold path to `config.py` if not already derived. The orchestrator derives
  DAG order from the §8 table — don't hand-wire edges.
- **Integration test** through the orchestrator: seed two normalized bundles that are patches of one
  logical doc → assert one anchor bundle at the version-free path, latest body promoted, `history.yaml`
  with both versions ordered + a CAS ref to the older retained body, prior body present in CAS.
- **Update the tracker** (flip consolidate ◐/✅, fill Evidence) and **`docs/vdocs-design.md` in the same
  commit** if any input/output/CLI detail shifts (§ "Claude guidelines"). Commit as its own increment.

### Guardrails

- **Do not start `index`/`relate`/`manifest` or any Phase 5+ stage** in this increment — `consolidate`
  only. Land it green, then the next session picks up `index`.
- Acquisition/processing is **per-version-group** (§691): prior bodies are exactly what capture (and
  any future `push --replay-history`, §6.6) preserve — don't discard non-latest members.
- Data lives in `~/data/vdocs` (`DATA_DIR`), **never in this repo**. `registries/` stays in the repo.
- Keep `make check` green; pure functions stay pure (`structlog`, never `print`); no mocks unless
  unavoidable.
```
