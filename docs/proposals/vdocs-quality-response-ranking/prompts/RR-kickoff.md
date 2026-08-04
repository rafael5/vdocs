# Kickoff — vdocs-quality-response-ranking (RR.1–RR.3)

> **To start the session**, `cd ~/projects/vdocs` and say:
>
> > Read `docs/proposals/vdocs-quality-response-ranking/prompts/RR-kickoff.md` and execute it.

> ## ⛔ Check this first
>
> **`vdocs-quality-crawl-integrity` `CI ✓` and `vdocs-quality-report-card` `RC ✓` are BOTH ticked (2026-08-03)** — this effort is unblocked. Later efforts wait on this tracker's `RR ✓`.
>
> **The baseline you compare against is `reports/rc-final-baseline.*`** (2026-08-03, post-RC key: 24 labelled queries, 109 labels, 0 unscoreable): **nDCG@10 0.6386 · MRR 0.7535 · recall@10 0.7134**, `corpus_content_hash 726d22a4…`, 57,895 chunks. Numbers quoting 0.5305/18-answerable predate the RC key repair and are not comparable. The harness now **exits non-zero** if any labelled query goes unscoreable — a red gate here means the key rotted again, not that you broke search.
>
> **Search-owned failures RC.2 hands you (the work list, read `reports/rc2-key-rejudged.*`):**
> - `fileman-add-field` — the one remaining 0.000: ScreenMan-tutorial lexical trap outranks the real DG answers, which sit below rank 10.
> - `vbecs-accept-order` — 0.05: the measured container/leaf twin defect (RR.3's case).
> - `vista-signon-credentials` — 0.17: vocabulary gap ("credentials" vs Access/Verify-code prose).
> - Zero key-owned failures remain; every other query scores ≥ 0.43.
>
> **Measure before you act.** The first step below is a measurement. No code, configuration, curation or gate lands until it is complete and written down.

**Repo: `vdocs`** (`~/projects/vdocs`) — offline analytical workload. Read `CLAUDE.md`, the proposal
and plan in [`..`](..), then tick the tracker per landed step. **Shared-lake rule:**
`pgrep -af "vdocs run"` before any command touching `~/data/vdocs`.

## The one measurement that sizes this work

Recomputed 2026-08-03 on the post-RC key (109 judged answers across 24 questions; the pre-RC
version of this table — 51 answers / 18 questions / 51.0% visible — is superseded):

| position | count | share |
|---|---:|---:|
| **1–10** (visible) | 76 | **69.7%** |
| 11–25 | 11 | 10.1% |
| 26–100 | 7 | 6.4% |
| 101–500 | 7 | 6.4% |
| >500 / not returned | 8 | 7.3% |

Share visible at list length 10 / 25 / 100: **69.7% / 79.8% / 86.2%** — the curve still flattens
after 25. **16.5% of correct answers are already retrieved and shown to nobody** (ranks 11–100).
That band is this effort; the 13.7% at >100/absent is not. The near band is smaller than the
pre-RC table claimed because RC.2 credited answers search was already surfacing — what remains
is the honest residue.

Defaults today: `mcp.DEFAULT_K = 8`, `ask --k 8`.

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
