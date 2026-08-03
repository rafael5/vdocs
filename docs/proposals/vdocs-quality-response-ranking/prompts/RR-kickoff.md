# Kickoff — vdocs-quality-response-ranking (RR.1–RR.3)

> **To start the session**, `cd ~/projects/vdocs` and say:
>
> > Read `docs/proposals/vdocs-quality-response-ranking/prompts/RR-kickoff.md` and execute it.

> ## ⛔ Check this first
>
> **`vdocs-quality-report-card` must be ticked `RC ✓` before this effort starts** — the family-wide rule (operator direction, 2026-08-03). If it is not, stop and run that effort instead.
>
> **Measure before you act.** The first step below is a measurement. No code, configuration, curation or gate lands until it is complete and written down.

**Repo: `vdocs`** (`~/projects/vdocs`) — offline analytical workload. Read `CLAUDE.md`, the proposal
and plan in [`..`](..), then tick the tracker per landed step. **Shared-lake rule:**
`pgrep -af "vdocs run"` before any command touching `~/data/vdocs`.

## The one measurement that sizes this work

51 correct answers across the 18 answerable questions, by the position search returns them at:

| position | count | share |
|---|---:|---:|
| **1–10** (visible) | 26 | **51.0%** |
| 11–25 | 9 | 17.6% |
| 26–100 | 3 | 5.9% |
| 101–500 | 6 | 11.8% |
| >500 / not returned | 7 | 13.7% |

Share visible at list length 10 / 25 / 100: **51.0% / 68.6% / 74.5%** — the curve flattens after 25.
**23.5% of correct answers are already retrieved and shown to nobody.** That band is this effort;
the 25.5% that is never retrieved is not.

Defaults today: `mcp.DEFAULT_K = 8`, `ask --k 8`. Two failing questions have their answer at rank
**13** and **14**.

## The measurement discipline — this project has been burned three times

1. Run the key **before** and **after**, on the production collection
   (`.venv/bin/python scripts/baseline_golden.py --k 10 --out reports/<name>.md`).
2. Check both rollups share `corpus_content_hash` **and** `chunks`. The hash alone is not enough — it
   fingerprints the document set, not the index build; two indexes with different chunking carry the
   same hash (measured: 48,769 vs 57,895 passages, one hash).
3. Compare **per question**. A rising mean has hidden two questions falling to 0.000 in this repo.
4. If nothing wins cleanly in RR.2, **record that and keep the current weights.** A negative result
   is a finding.

## Order and the traps in each step

- **RR.1 (free, biggest move):** raise the assistant-path default. Widen retrieval for assistants;
  keep the human display short — more results is not free for a person.
- **RR.2:** the current weights (doc title 2.5 / title 2.0 / path 1.5 / body 1.0) were fitted on the
  **451-document dev collection**. Sweep on production. Watch overfitting: 18 questions is small, so
  prefer small explicable moves and treat a big single-question gain as a warning.
- **RR.3:** measured case — `VBECS/…/accept-orders-cancel-a-pending-order-uc_61` (parent) outranks
  its own child `…/accept-orders-cancel-a-pending-order`. **Do not** make parent lead-ins
  unsearchable again; that made 6,779 sections findable. This is about ordering between two results.

## Close-out

Tick RR.1–RR.3 and RR ✓ with both reports cited, then write the kickoff for whichever effort the
operator sequences next (`vdocs-quality-crawl-integrity` is the standing recommendation), carrying
the new baseline.
