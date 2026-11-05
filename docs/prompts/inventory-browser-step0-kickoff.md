# Kickoff — inventory browser, step 0: commit the measurements

> **To start the session**, `cd ~/projects/vdocs` and say:
>
> > Read `docs/prompts/inventory-browser-step0-kickoff.md` and execute it.

**Repo: `vdocs`** (`~/projects/vdocs`). Read `CLAUDE.md`, then the proposal of record,
[`docs/proposals/inventory-browser-proposal.md`](../proposals/inventory-browser-proposal.md): §1, §3,
§4 and §8 step 0 closely, §10 for context. Every decision in §10 was taken on 2026-11-05; do not
reopen them.

**This step is read-only on the lake.** It reads `~/data/vdocs` and writes nothing there; open every
SQLite file with `mode=ro`. Check `pgrep -af "vdocs run"` first all the same: a live run rewrites
`index.db` and `inventory.json`, and a measurement taken across two builds is not evidence.

## Why this exists

Every number in the proposal came from ad-hoc scripts that were never committed, and two have
already proved wrong: the row-key claim (corrected in `7c6bfe3`) and the label on
`vdocs inventory --status`, which counts every non-noise document of any system type, not VistA
documents (corrected while this kickoff was written). Step 1's tests will assert against these
numbers, so they must be right first. The project's own lesson from the August audit applies: a
measurement that cannot name what it read is not evidence.

## What you are building

One script, which does not exist yet (suggested name `scripts/inventory_measurements.py`), that
re-derives every figure in proposal §1, §3 and §4 from the lake and the registries. It writes
`reports/inventory-browser-measurements.md` and a sibling `.json` in this repo, committed the way
`reports/baseline-phase0.*` is. The report opens by naming what it read: the sha256 and record count
of `inventory.json`, `index.db`'s `read_schema_version` and `corpus_content_hash`, the vdocs and
vista-meta commits, and the run date. The same lake must give the same JSON, apart from the one
run-date field.

Do not copy the proposal's figures into a second list. The report's sections mirror §1, §3 and §4,
and each figure appears with the proposal's value beside the measured one. Then correct the proposal
in place wherever they differ.

## Use the pipeline's own definitions

The numbers must mean what step 1 will compute, so the script imports the definitions rather than
restating them:

- **The join key:** `kernel.ids.doc_id`.
- **Disposition, and what a VistA record is:** `stages.fetch.policy.load_gate_policy`,
  `fetch_pure.sole_survivors`, `completeness_pure.classify`. A VistA record is a genuine record the
  gate's `app_in_scope` admits. The ad-hoc numbers used a `system_type` prefix check plus "not
  decommissioned"; where the gate's definition moves a count, the gate wins and the proposal changes.
- **Profile tags:** `kernel.personas.load_profile_maps` and `profile_tags`.
- **Fetch status:** `serve_pure.inventory_status` over `StateStore.all_acquisitions()`, the join
  behind `vdocs inventory --status`.
- **The last-updated date:** `official_date` from each `history.yaml` under
  `documents/gold/consolidated/`, matching members and their `superseded` entries by `doc_id`. Not
  `v_documents.published`, which is the title-page date only: measured while this kickoff was
  written, `published` dates 1,864 records where the proposal says `official_date` dates 2,018.

Follow the layout of `scripts/baseline_golden.py` and its test: pure functions that `tests/unit/`
imports through the `sys.path` insert, and a thin `main()`. `make lint` and `make mypy` cover only
`src/` and `tests/`, so run `ruff check` and `mypy` on the new script by hand.

## TDD

Tests first, real objects, no mocks: a few hand-written records, a minimal `index.db` with
`v_documents` and `meta`, and one `history.yaml`. Each test plants the case its figure exists to
catch:

- a slug listed under two app codes with gold under the old one counts once as gold-only and once
  as held-but-not-in-gold;
- two identical listings on one page get distinct row keys by ordinal, and the keys survive
  reordering the input;
- a gold document whose newest revision is later than its title page is dated by the revision;
- a record with no gold document whose fetch failed counts as failed, not as never fetched.

## Known problems to settle

1. **Two figures of 3,834.** The status total is distinct non-noise `doc_id`s of any system type,
   2,941 of them VistA (read from `serve_pure.inventory_status`). The undated-VistA figure was
   derived by subtraction, 5,852 VistA records less 2,018 dated. Measure it directly. If it really
   is 3,834, the report says the match is a coincidence.
2. **"Never fetched" was used to mean "no gold document".** §4's 3,732 records have no gold match,
   and some of them were fetched and failed or were rejected (§1 counts 5 and 1). Split them by
   acquisition status and reword §4.
3. **1,861 against 1,911.** §4 says 1,861 distinct `doc_id`s; decision D6 says 1,911 documents, 1,903
   with a Word version. 1,809 distinct slugs is a third candidate. Find the unit behind 1,911 or
   correct D6.
4. **Namespace names, §3.** The source the first measurement used was not recorded. The likely one
   is vista-meta's `vista/export/code-model/package-namespace.tsv`, whose `package_name` column is the
   PACKAGE-file (#9.4) NAME according to `host/scripts/build_package_namespace.py`. Confirm it by
   reproducing "102 of 162", and pin the vista-meta commit in the report. The criterion behind
   "agree on 73 of 94" was never written down: choose one, such as case- and punctuation-folded
   equality, state it, and measure against it. "15 substantive, 32 reworded" is a human reading,
   not a measurement: the report lists every differing pair, and the proposal says the split is a
   reading of that list.
5. **"Namespace differs on 2 documents."** Name the two.

## Out of scope — leave these cited as they are

- Decision D6's network and ZIP measurements: D6 put that work out of scope.
- The before-and-after counts of `9f9df51`: history, cited by commit.
- The 11 mis-ordered version groups: cited from `docs/memory/pxrm-refresh-2026-11-05.md`.
- D7's stage timings: cited from the lake's run log.
- §6's 3.1 MB: step 1 measures it on the real table.

Do not touch `src/`, run any pipeline stage, write to the lake, or start step 1.

## Done when

- The script and its tests are committed, `make check` is green, and ruff and mypy pass on the
  script.
- The report is committed in `reports/`.
- The proposal is corrected in place for every figure that moved, and the commit message lists each
  one as old value and new value.
- §8 step 0 is rewritten in the past tense, naming the script and the report, and the header note
  saying the scripts were not committed is removed.
- This kickoff moves to `docs/prompts/historical/` in the same commit, per `docs/README.md`.
- The private proposal page, <https://claude.ai/artifact/MivhwihatSqjoeVbgvXJyB>, is republished
  from the corrected file through its URL, so it matches the commit it names.
