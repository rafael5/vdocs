# Kickoff — inventory browser, step 2: use the view, then decide the web mode

> **To start the session**, on or after **2026-12-05** (a month after step 1 landed),
> `cd ~/projects/vdocs` and say:
>
> > Read `docs/prompts/inventory-browser-step2-kickoff.md` and execute it.
>
> Run it earlier only if the operator says the question is already answered.

**Repo: `vdocs`** (`~/projects/vdocs`). Read `CLAUDE.md`, then the proposal of record,
[`docs/proposals/inventory-browser-proposal.md`](../proposals/inventory-browser-proposal.md): §1
(the case the view had to answer), §2 (what the web mode would add), §8 steps 1–4, and §10 D1 and
D5. The `vdocs-corpus` skill's `v_inventory` section has the queries. Every decision in §10 was
taken on 2026-11-05; do not reopen them. This step answers the question D5 left for it: *in a
month of use, how often was the table opened, and for what?*

This step writes nothing to the shared lake.

## Why this exists

D5 put the producer first. Step 1 made the whole §1 case answerable from `sqlite3` on
`v_inventory`; the web mode (step 4: Go routes, a Svelte mode and their tests in vdocs-web) is the
larger half, and its value was unmeasured. It is built only if a month of use shows it is wanted.
A decision taken without that evidence would undo the reason for the order.

## What to do

1. **Measure the use, by hand, once.** No tool for this exists, and none is to be built. A *use*
   is one query against `~/data/vdocs/index.db` that names `v_inventory`, made after step 1
   landed (vdocs `23c9d28`, 2026-11-05T20:06:50Z). Three sources:
   - **Claude Code transcripts**, `~/.claude/projects/*/*.jsonl`: count the tool calls whose
     *input* names `v_inventory`, per session, with the question the operator was asking. Match
     tool inputs only: since 2026-11-05 the `vdocs-corpus` skill's description contains
     `v_inventory`, so every session's skill listing does too, and a plain grep of the files
     counts every session. Leave out session `9cffe8fa-e19f-4406-adca-81dde9571f8f` (step 1 and
     its knowledge capture).
   - **`~/.bash_history`**, which is timestamped (`#<epoch>` lines). It held no line naming
     `v_inventory` on 2026-11-05, so every such line now is a use.
   - **The operator's account.** Ask what they opened the view for, what they could not get from
     `sqlite3`, and whether the mockup's features (§2: facets, the summary strip, the record
     panel, the month range) would have changed what they did.

   Record what you counted and how, so the count can be re-run.
2. **Take D5**: go, no-go, or extend the trial to a named date. Write the decision into §10 D5
   with its evidence (the counts, the questions, the operator's account) in plain sentences.
3. **Follow the branch.**
   - **Go.** Identity continuity across re-filing (step 3) must land before step 4 (D1). The next
     session writes step 3's short proposal, so write its kickoff, not step 4's.
   - **No-go.** Steps 4 and 5 do not proceed; say so in §8 and in the status line. Step 1 left two
     things for the web mode that then need an owner: vdocs-web's `TYPE_FAMILIES` copy (the
     families are published as `v_vocab` kind `doc_type_family`, so the Library could read them in
     its own small change), and D1's stopgap (`registries/inventory/refiled.yaml`, which still
     expires only with identity continuity). Say what happens to each; build neither here.
   - **Extend.** Name the new date and what the extra time must show.
4. Rewrite §8 step 2 in the past tense with the evidence. Update `docs/README.md`'s current-state
   entry, and move this kickoff to `docs/prompts/historical/` in the same commit, re-pointing its
   relative links. Republish the private proposal page,
   <https://claude.ai/artifact/MivhwihatSqjoeVbgvXJyB>, from the corrected file through its URL,
   naming the new commit.

## Out of scope

Building anything: a usage tracker, any vdocs-web change, any identity-continuity code (step 3
starts with its own proposal). Library namespace renames (D4). Dating the never-fetched documents
(D6).

## Done when

- §10 D5 records the decision with the measured use and the operator's account, and §8 step 2
  says, in the past tense, what was measured.
- The next step is named: for go, its kickoff is written; for no-go, the two owners are named; for
  extend, the new date is set.
- The commit is pushed, `docs/README.md` is current, this kickoff is in `prompts/historical/`, and
  the proposal page is republished.
