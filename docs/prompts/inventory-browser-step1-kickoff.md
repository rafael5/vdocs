# Kickoff — inventory browser, step 1: the producer

> **To start the session**, `cd ~/projects/vdocs` and say:
>
> > Read `docs/prompts/inventory-browser-step1-kickoff.md` and execute it.

**Repo: `vdocs`** (`~/projects/vdocs`). Read `CLAUDE.md`, then the proposal of record,
[`docs/proposals/inventory-browser-proposal.md`](../proposals/inventory-browser-proposal.md): §3, §4,
§5, §7 and §8 step 1 closely; §10 D1, D3 and D4 for the decisions this step carries out. Then read
[`reports/inventory-browser-measurements.md`](../../reports/inventory-browser-measurements.md): it is
step 0's measurement of the 2026-11-05 lake, and the numbers this step must reproduce come from it.
Every decision in §10 was taken on 2026-11-05, and so were the four namespace names in §3; do not
reopen them.

**This step writes the shared lake once, at the end** (the index rebuild). Before it, check
`pgrep -af "vdocs run"` and the newest `~/data/vdocs/reports/*.log`; if an operator run is live,
wait for it and run only what it has not covered. Kill only your own process.

## Why this exists

Step 2 is the operator using the inventory from `sqlite3` for a while, and the decision on the web
mode (D5) is taken only after that. So this step has to make the whole §1 case answerable from
`index.db` alone: every inventory record with its disposition and reason, gold status by a join on
`doc_id`, and each gold document's own last-updated date.

## What you are building

None of this exists yet. Names marked *suggested* are free to change.

1. **A structured reason from `classify()`** (`stages/serve_inventory/completeness_pure.py`): a
   reason kind plus value alongside the existing string, which stays exactly as it is (the
   `completeness` CLI and the step 0 report print it). The kinds are the closed set `classify()`
   emits; each kind's explanation is one sentence, worded from the registry that produces it (§5).
   No second grammar generated from the policy registries.
2. **The row key, moved into `src/`.** `row_keys()` lives in `scripts/inventory_measurements.py`
   today. Move it to a pure module under `src/` and have the script import it, so there is one
   definition; its test moves with it.
3. **A pure function from (records, policy, profile maps, namespace names) to rows**, one per
   inventory record, with the columns §5 lists: row key, `doc_id` (through `kernel.ids.doc_id`),
   application code and name, VDL section, doc type, title, file name, format, patch id, lifecycle
   label, system type, VDL URL, application page URL (the "listed on N pages" count of D2 is a
   query over it), the four profile tags, namespace, disposition, reason, and reason kind and value.
   Check what "lifecycle label" means against the `lifecycle_labels` capability in
   `contracts/read/v1.json` before choosing the field.
4. **The namespace names registry** (*suggested* `registries/inventory/namespace-names.yaml`): the
   namespace → PACKAGE-file (#9.4) name pairs copied from vista-meta's
   `vista/export/code-model/package-namespace.tsv`, with a header naming the vista-meta commit it
   was copied from; an overrides section, applied after the copy, holding the four names decided
   on 2026-11-05 (OR *Order Entry (CPRS)*, GMRV *Vitals*, LR *Lab*, MAG *VistA Imaging*); and the
   fallback to the same-code application's name, flagged as such. Copy the PACKAGE names verbatim,
   capitals included: their casing is decided with the Library renames (D4), not here. Make the copy
   re-derivable from the header; how is this session's call.
5. **The index stage** (`stages/index/stage.py`): `GOLD_INVENTORY` (`contracts/registry.py`) joins
   `requires`; the new table is written in the same atomic build as everything else, with one
   projection view over it (*suggested* `v_inventory`). The vocab rows (`kernel/vocab.py`,
   `vocab_rows()`) gain the six disposition definitions, the reason-kind explanations, the
   namespace names (read by the Inventory mode only, D4) and the doc-type families. The families
   are hardcoded today in vdocs-web's `web/src/routes/+page.svelte` (`TYPE_FAMILIES`: *Manuals &
   Guides* UM UG QRG TRG FAQ TG; *Technical* TM DG API INT REF; *Admin & Security* SG SM AG; the
   rest *Other*); move them into a registry `vocab_rows()` reads. vdocs-web keeps its copy until
   step 4. `meta` gains the inventory's record count and an order-independent content hash over
   the enriched records, computed the way `stages/crawl/snapshot_pure.py:canonical_hash()` is.
6. **The last-updated date in `v_documents`**: the date and its source (Revision History or title
   page) from each `history.yaml` member's `official_date`, read during the history walk the stage
   already does (`_latest_bundle_paths()`). Use the step 0 script's source rule: Revision History
   when the date is one of the member's revision dates, otherwise the title page.
7. **Read contract 1.6 → 1.7** in `contracts/read/v1.json` (views are generated from it by
   `kernel.read_contract.view_ddl`), with a capability naming the new view. Test the bump by calling
   `lint_bump()` with the 1.6 spec as the previous version: `lint_latest()`, the `make
   contract-lint` gate, compares the two highest major files and does nothing while only `v1.json`
   exists. Where the test gets the 1.6 spec from is this session's call.
8. **The doctor staleness check** (D3) in `server/doctor.py`: `diagnose_lake()` compares the hash
   stamped in `meta` with the current `inventory.json` and reports **WARN**, naming the fix (re-run
   `vdocs index`). Prove it with a planted mismatch.
9. **D1's stopgap.** The producer lands before identity continuity (§8 step 3), so the view carries
   option C: the 14 re-filed ISS guides (`ADT:iss_release_…` in gold, the same slugs under SD in the
   inventory) are listed in a fixed exception file, and the view says so for those rows. The file
   needs a consumer and a **testable expiry**: a gate that reds once a listed id joins without the
   file, for example a doctor check over the built index. Do not ship the file without that gate.

## TDD and order

Tests first, real objects, no mocks, one increment at a time: test, implement, `make check`,
commit and push. A sensible order: 1 → 2 → 3 → 4 → 5 and 6 with 7 → 8 → 9 → the lake rebuild.
Step 1's tests from §8 apply:

- the rows' disposition counts equal `completeness_report()` on the same input;
- the rows' profile tags equal the gold documents' for records in gold;
- row keys are unique. The 2026-11-05 `inventory.json` is 13 MB, too big to commit, so plant its
  shapes in a small fixture (identical listings on one page; `DVBA_UM`'s three titles and two doc
  codes), and check uniqueness on the real build after the rebuild;
- the contract bump passes `lint_bump()`, and the doctor check warns on a planted mismatch.

Update `docs/vdocs-design.md` in the same commit as the index stage's new input and output
(CLAUDE.md rule).

## The lake rebuild, and what it must show

After the last increment, and after the live-run check above: `vdocs run --from index`. That re-runs
index and every stage after it that the change makes stale (D7 measured index, merge, relate,
manifest and doctor at about a minute and a half). Then check with `sqlite3` on the new view,
against the step 0 report at `722d2c2`:

| Check | Expected |
|---|---|
| Rows | 9,080 |
| Distinct row keys | 9,080 |
| Dispositions | held 1,280 · covered-by-other-format 2,916 · excluded 1,656 · not-vista 3,228 (equal to `vdocs completeness`) |
| Records with a gold match on `doc_id` | 2,120 |
| Records with a last-updated date | 2,018 |
| Gold documents dated (Revision History / title page) | 990 (856 / 134) |
| `vdocs doctor` | GREEN with no WARN (its last run, 2026-11-05: 20 pass, 0 warn, 0 fail), the new checks passing |

A difference is a finding: explain it before calling the step done.

## Out of scope

vdocs-web (step 4); the identity-continuity proposal (step 3); Library namespace renames and the
casing of copied PACKAGE names (D4); `inventory --status` mislabelling PDF fetches and the
completeness-verdict gap (both in `TODO.md`); dating the never-fetched documents (D6).

## Done when

- Every increment is committed and pushed with `make check` green.
- The lake is rebuilt and every check in the table holds, or each difference is explained.
- §8 step 1 is rewritten in the past tense, naming the commits and the measured counts.
- `docs/README.md`'s current-state entry says step 1 landed, and this kickoff moves to
  `docs/prompts/historical/` in the same commit, per `docs/README.md`.
- The private proposal page, <https://claude.ai/artifact/MivhwihatSqjoeVbgvXJyB>, is republished
  from the corrected file through its URL, so it matches the commit it names.
