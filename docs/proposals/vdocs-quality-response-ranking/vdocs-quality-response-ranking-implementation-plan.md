# vdocs-quality-response-ranking — implementation plan

Proposal: [`vdocs-quality-response-ranking.md`](vdocs-quality-response-ranking.md) ·
Tracker: [`vdocs-quality-response-ranking-tracker.md`](vdocs-quality-response-ranking-tracker.md) ·
Prompts: [`prompts/`](prompts/)

⛔ **Do not start before `vdocs-quality-report-card` lands.** Three steps, commit subjects `RR.1:` /
`RR.2:` / `RR.3:`, cheapest first, each adopted **only** on a measured win. House rules: TDD,
`make check` green before commit, tick the tracker in the same commit.

## The measurement discipline for this effort

Every step is judged the same way, and the discipline is stricter than the mean:

1. Run the answer key **before** the change and **after**, on the production collection.
2. Confirm both reports carry the same `corpus_content_hash` **and** the same passage count. The hash
   alone is not sufficient — it fingerprints the document set, not the index build.
3. Compare **per question**. A rising mean with one question falling to zero is a loss, not a win.
4. Keep both reports; they are the evidence the tracker row cites.

## RR.1 — Show more results

Raise the default result count on the assistant path (`mcp.DEFAULT_K`, currently 8) to 15–20, and
allow the CLI to retrieve more while displaying a short list. No ranking logic changes.

Rationale, measured: the share of correct answers a user sees goes **51.0% → 68.6%** between list
lengths 10 and 25, and two failing questions have their answer at rank 13 and 14 against a default of
8.

*Tests first:* the default is what the tool advertises and what it returns; an explicit `k` still
wins; the shared result envelope (`{hits, hit_count[, warning]}`) is unchanged so all three surfaces
stay identical.

**Watch for:** longer lists shift reading work to a human. Widen retrieval for assistants; keep the
human display tight.

## RR.2 — Re-sweep the relevance weights on the real collection

Grid-search the four field weights (document title 2.5 / section title 2.0 / section path 1.5 / body
1.0) against the answer key on the production collection, and adopt a new set **only** if it wins per
question, not merely on average.

Rationale: the current values were fitted on the 451-document development collection. The production
collection is 2.3× larger, and inter-document competition — precisely what field weighting balances —
is the thing that scaled.

*Tests first:* the weights are a named constant with a test pinning the shipped values, so a sweep
result is a deliberate committed change rather than a drifting tuning knob.

**Watch for overfitting.** 18 questions is a small key. Prefer small, explicable moves; treat a large
single-question gain as a warning. If no configuration wins cleanly, **record that and keep the
current weights** — a negative result here is a real finding, not a failed step.

## RR.3 — Stop parents displacing their children

Measure first: how many parent/child heading twins exist where the parent is searchable and its child
holds the substantive content? Then choose the narrowest fix that removes the displacement without
reversing the coverage win that made parent lead-ins searchable in the first place.

Known case: `VBECS/…/accept-orders-cancel-a-pending-order-uc_61` (parent) outranks
`…/accept-orders-cancel-a-pending-order` (child) for the same query.

*Tests first:* a fixture with a parent whose lead-in restates its child's heading ranks the child
first; a parent with its own substantive content still ranks on its own merits.

**Do not** revert parent lead-ins to unsearchable. That change made 6,779 sections findable and is
measured; this is about ordering between two results, not about excluding one.

## Sequencing

RR.1 → RR.2 → RR.3. RR.1 is free and moves the biggest number, so it establishes the new baseline the
other two are measured against. Stop early if the key stops improving — the remaining headroom is in
the 25.5% that is not retrieved at all, and that is a different effort.

## Out of scope

Semantic/vector retrieval (evaluated and rejected for this collection), chunking changes (finished,
and mixing them in makes both unmeasurable), and the answers that are genuinely not retrieved.
