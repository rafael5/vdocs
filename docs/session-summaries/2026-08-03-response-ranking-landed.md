# 2026-08-03 (late) — response-ranking lands; three steps, three different kinds of answer

`RR ✓` in one session, straight after `RC ✓`. Three commits: `01f4572` (RR.0+RR.1), `88de33f`
(RR.2), `4721e5e` (RR.3). Gates green throughout, doctor 20/20, lake GREEN.

## The result

nDCG@10 **0.6386 → 0.6447**, recall@10 **0.7134 → 0.7238**, MRR unchanged, **zero questions
regressed**, identical `corpus_content_hash` / chunk count on both sides.

That headline understates one step and overstates the effort. Stated honestly:

- **RR.1 moved the most and the harness cannot see it.** Raising the assistant default from 8 to 15
  took judged answers visible at the default from **61.5% to 76.1%** — but the harness measures at a
  fixed k=10, so it correctly reports the change as flat. A metric that cannot see a change can
  neither credit nor regress it; that was P6.4's lesson and it applies to our own step here.
- **RR.2 changed nothing, and that is the finding.** 120 grid points, zero candidates beat the
  shipped weights without regressing a question.
- **RR.3 is the only engine improvement**, on exactly one question (+0.146).

## Step by step

**RR.0** re-baselined production on the post-RC key and reproduced the RC close-out run byte for
byte — rollup and every per-question score. Determinism confirmed rather than assumed.

**RR.1** picked 15 from the curve, not from the plan's "15–20" range: 61.5% @8 · 69.7% @10 ·
**77.1% @15** · 78.0% @20 · 79.8% @25. Fifteen is the knee. Two constants now live beside
`NOT_INDEXED_RULE` in `server/search.py` for the same reason it does — `ASSISTANT_DEFAULT_K` (MCP
`search`, `ask --json`) and `HUMAN_DISPLAY_K` (the terminal, where a longer list is reading work,
not free recall). It also turned up a **third** assistant surface still advertising `--k 8`: the
published corpus card's query recipe. The doctor's card-staleness check covered the usage rule
beside it but not the recipe — the same hole one field over — so the check was widened, and it
caught this instance live on the lake before the card was refreshed.

**RR.2** swept doc_title × title × section_path against the key on production, measuring the real
engine via a new `weights` override on `lexical_search`. The best mean (+0.031) regresses five
questions; the nearest-to-clean point improves nine and regresses two by at most −0.0045. Rejected
anyway: the no-regression rule was written before the data, and best-of-120 on 24 questions is
textbook overfitting. One directional signal is worth keeping for a larger key: `title` wants 3.0 in
nine of the top ten rows, `section_path` ≤ 1.0 in nine of ten.

**RR.3** measured before building: 784 title-twin parent/child pairs, 120 with a tiny searchable
parent over a much larger child, and **68 of those 120 returned the parent ahead of the child**.
Cause: bm25 length normalisation makes a 118-character container that restates its child's heading
look like a dense perfect match. The fix reorders and excludes nothing — a parent that matches with
no child present is still the answer — and fires only on direct-parent + prefix-twin titles + parent
text under 300 characters, with a 3× over-fetch so the child can actually be promoted into view.
Displacement fell **68 → 2 of 120**.

## Durable lessons

- **Know which of your changes your metric can see.** RR.1's real gain and RR.3's small one are not
  comparable through the same number, and reporting only the mean would have credited the wrong step.
- **A pre-registered rule earns its keep at the moment it is inconvenient.** RR.2's near-miss was
  tempting precisely because it was so nearly clean.
- **Drift hides one field over.** A staleness check written for one code-resident field will not see
  its neighbour; widen it when you find the neighbour rather than fixing the instance.
