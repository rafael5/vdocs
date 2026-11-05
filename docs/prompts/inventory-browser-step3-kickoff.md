# Kickoff — inventory browser, step 3: identity continuity across re-filing (the proposal)

> **To start the session**, `cd ~/projects/vdocs` and say:
>
> > Read `docs/prompts/inventory-browser-step3-kickoff.md` and execute it.

**Repo: `vdocs`** (`~/projects/vdocs`). Read `CLAUDE.md`, then the inventory browser proposal,
[`docs/proposals/inventory-browser-proposal.md`](../proposals/inventory-browser-proposal.md): §8
step 3 and §10 D1 and D5. D1 chose option A, and D5 said go to the web mode on 2026-11-05. Do
not reopen either decision. Identity continuity must land before the web mode (step 4); otherwise
the browser shows every re-filed document twice, once as *gold only* and once as *held but not in
gold*.

This session writes a short proposal and nothing else: no code, no registry change, no run on the
shared lake. The code comes in a later session, once the operator has taken the proposal's
decisions.

## Read first: an identity rework was proposed once and withdrawn

- [`docs/proposals/vdocs-quality-vdl-observatory/vo-identity-and-classification-audit.md`](../proposals/vdocs-quality-vdl-observatory/vo-identity-and-classification-audit.md),
  Part A. It found that all four identity keys start with the application code: `doc_id`,
  `doc_key` (the key the search layer joins on), `anchor_key` (the version family) and
  `group_key`. `<app>/<slug>/` is also a directory in silver and gold. On 2026-08-05 the
  re-filing of 14 unchanged documents would have re-keyed about 1,550 rows.
- [`docs/memory/search-quality-programme.md`](../memory/search-quality-programme.md), the section
  *"THE `doc_slug`-AS-IDENTITY PLAN WAS MEASURED AND WITHDRAWN"*. Cross-listing is VA's deliberate
  per-package variant (99.96% identical text, each copy titled with its own patch), not a
  duplicate. Do not propose the slug as the identity, and do not change the shape of `doc_id`.
  What survived that ruling is this step: when VA moves an already-acquired document to another
  application page, it keeps the id it had. The note calls it the identity analogue of master-set
  retention ([crawl-integrity CI.2](../proposals/vdocs-quality-crawl-integrity/vdocs-quality-crawl-integrity-implementation-plan.md)),
  which keeps the document in the set but not its key.
- [`registries/anchor-aliases.yaml`](../../registries/anchor-aliases.yaml): the precedent, a
  hand-kept alias list applied at both places the version-group key is derived.
- The stopgap this step retires: [`registries/inventory/refiled.yaml`](../../registries/inventory/refiled.yaml)
  (14 entries) and `refiled_exceptions_check` in `src/vdocs/server/doctor.py`. That check FAILs
  once a listed id joins without the file.

## The case, measured 2026-11-05

VA re-filed 14 ISS release user guides from ADT to Scheduling (SD).
- `state.db` `acquisitions` holds them only as `ADT:iss_release_…`, and so do gold and silver.
- The inventory lists them as `SD:iss_release_…`, disposition *held*. They are among the 216 held
  ids that are not in gold, and `v_inventory.refiled_from` labels their 28 rows.
- Unverified since 2026-08-05: whether the next `vdocs fetch` would acquire the same 14 files a
  second time under the SD ids.

## What the proposal must settle

Give each decision its options, their cost and a recommendation, in the format of the inventory
browser's §10. Measure before designing, and name the measurement that would kill the
recommendation. Twice already a cheap measurement collapsed a large plan here.

1. **Evidence of a re-filing.** D1 rejected a slug match alone, because a slug can shadow across
   applications. What else must hold? For example: the old listing departed in the same crawl,
   and the file's bytes or text match the acquired copy. Check the rule against the 14 cases and
   the cross-listed slugs before recommending it. Comparing files needs the SD copies; say how you
   got them, and keep them out of the lake.
2. **Which keys keep their old value.** If only `doc_id` is kept, `anchor_key` and `group_key`
   still move the document into another version family. Say what happens to each of the four
   keys and to the silver and gold paths.
3. **Where the kept id is decided and stored.** A hand-kept list rots with every crawl; D1 held
   that against option C. Derived from what has already been acquired? In which stage, and how is
   it red-proved?
4. **What a row shows afterwards.** A row would carry `doc_id` `ADT:…` with `app_code` `SD`.
   Check that no consumer reads the application out of `doc_id`. A first grep of vdocs-web found
   none; confirm it, and check the read contract (`contracts/read/v1.json`).
5. **Retiring the stopgap.** Deleting `refiled.yaml` is planned. `v_inventory.refiled_from` is a
   1.7 contract column, and removing a column is a MAJOR bump (`contracts/read/CHANGELOG.md`
   header), while a column that is always empty describes nothing. Decide which happens, and
   whether doctor's check goes with the file.
6. **What the next fetch does with the 14**, and whether this change must land before the next
   `fetch --all`.

## Out of scope

Building any of it. Cross-listing (a deliberate variant). The slug as identity. Library namespace
renames (D4). Dating never-fetched documents (D6). Any vdocs-web change.

## Done when

- The proposal exists in `docs/proposals/`, short and in the intent form the global no-stubs rule
  allows: no usage lines, no flag tables, no names reserved for things not built. Every number in
  it was measured, and says how.
- Its decisions are put to the operator. The ones taken are recorded with the date; the ones left
  open are listed.
- §8 step 3 of the inventory browser proposal links the new proposal, and `docs/README.md`'s
  current-state entry is updated. This kickoff moves to `docs/prompts/historical/` in the same
  commit, with its relative links re-pointed.
- The commit is pushed, and the private inventory browser page,
  <https://claude.ai/artifact/MivhwihatSqjoeVbgvXJyB>, is republished through its URL from the
  corrected file, naming the commit.
- The next session is named: the build of identity continuity. The web mode's kickoff (step 4)
  is written only after that build lands.
