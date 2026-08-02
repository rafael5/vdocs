# P5: every lineage record in the corpus was wrong, and nothing had been lost

*2026-08-01 · phase P5 of the pipeline audit remediation · commits `75d12e6`, `30351e9`, `91bc921`*

## What this session was for

One phase, driven by its kickoff prompt: make `history.yaml` — the artifact the design designates
as the replay source — stop describing bodies that are no longer in the bundle, and add the gate
that keeps it that way. The prompt arrived with a measured claim I was told to verify rather than
trust: **615 of 615** gold anchors carried a latest-member `body_sha256` that disagreed with their
own `body.md`.

## What happened

I re-measured before touching anything, and it reproduced exactly: 615 stale of 615, **zero**
retained bodies missing from the `_shared/history` CAS, 92 version groups with more than one
member. That pairing is the whole character of the defect and worth stating plainly — *nothing had
been lost*. Every prior body was still in the store, exactly as §6.6 promises. What was wrong was
the record *about* them. A hundred-percent-prevalent defect that destroyed no data is a strange
thing to find, and it made the fix easy to scope: no migration script, no data repair, just a code
change and the next `consolidate` run.

The mechanism is a single word. `merge_history` was append-only, and it treated `doc_id` as
*identity*: a member already captured kept its facts forever. That is exactly right for a new VDL
patch, and exactly wrong for a member re-processed into a different body — a registry fix or a
converter upgrade changes the normalized body under the same `doc_id`, the anchor's `body.md` is
refreshed, and the entry goes on quoting the sha of a body that has moved to the CAS. The fix
(P5.1) is that on a changed `body_sha256` the entry adopts the fresh facts and pushes the prior
fact-dict onto a `superseded` list: append-only *preserved* rather than append-only *frozen*.

Two small decisions inside that, both recorded because they will look arbitrary later. The demoted
dict drops `is_latest` (a derived pointer, not a captured fact) and its own `superseded` — keeping
the latter would nest exponentially, so the chain is flat and oldest-first, which also means the
file only ever grows at the tail. And the trigger stays `body_sha256` alone. I considered widening
it to "any captured fact differs", which would additionally catch a member whose `revisions.yaml`
was re-parsed under an unchanged body, and rejected it: the audit's own [S9]a describes `revisions`
going stale *because* the body changed, and a wider trigger would demote on any input jitter —
trading this bug for the one the idempotence assertion exists to prevent. A lineage record that
grows on every run is its own kind of lie.

P5.2 is the gate, and the interesting part is *why* the defect was invisible for so long.
`bundle.yaml` is a signed manifest recomputed from the parts on disk — and `history.yaml` is one of
those parts. So the manifest hashed the lying file perfectly and verified green, every run, over
all 615. The verification was closed under itself. The new check is the companion that compares
**two parts to each other** rather than each part to its own hash: the `is_latest` member's
`body_sha256` must equal `sha256(body.md)`. I folded it into Step 4's existing `bundle_findings`
rather than adding a seventh step, because what it catches is a bundle defect — it just isn't one a
manifest can reach.

Sequencing mattered and the prompt was right to insist on it: P5.2 would have red-flagged 615
bundles the moment it landed. So P5.1 first, then the live `consolidate` re-run, then re-measure —
**0 of 615** — and only then wire the gate. I re-confirmed that zero twice, by two different
routes, because a zero-finding gate is a coverage claim until you count positively (P3's lesson):
once with my own comparison script, and once by running the *shipped* `check_lineage` over all 615
bundles directly (615 clean, 0 findings).

The live result has a detail I did not predict. **1,034 of 1,040** member entries gained exactly
one `superseded` record — depth one across the board. The six that gained none turned out to be the
six documents P1 restored: first captured *after* the enrich change that caused the drift, so they
had nothing stale to demote. That fell out for free and is a nice independent confirmation that the
supersede path fired for exactly the population that needed it.

## What I got wrong, and what bit

My frontmatter-only / body-differs split came out 566 / 49 against the prompt's 531 / 84. My
splitter was cruder (a naive `---` split); the aggregate — the number that actually matters — was
identical. Not worth chasing, but worth not quietly restating the prompt's numbers as if I had
confirmed them.

The real bite was the acceptance run. `consolidate` re-ran, `index` re-ran behind it, `merge`
skipped, and `doctor` went **RED** on the SKL-projections check — the exact sequence P4's tracker
row says "cannot recur by construction". It recurred. P4 closed the *input* half: a content change
in `index.db` now reaches `merge`. This is the *output* half — when `index` rebuilds
content-identically, `merge`'s inputs genuinely are unchanged so skipping is *correct*, and its
`entity_skl` projection has been wiped anyway by `index` recreating the table. Nothing checks that
a stage's own outputs survived another stage's rebuild. `vdocs run --from merge --force` repaired
it in thirty seconds, but I put it in the P5 ✓ row and the P6 prompt rather than fixing it here:
it is not P5's to fix, and it is certainly not P5's to hide. R‑1 is half closed.

## What I left for P6, and one thing P6 should argue about first

The prompt's closing step asks for P6's live inputs, and one of them changes the phase. Running the
shipped shredder over all 615 gold bodies, **6,779 of 11,543** container sections (58.7%) clear the
substantive-token floor on their own lead-in — so P6.1 would take the chunk-less share from 27% to
about **14%**, not the plan's `< 8%`. The remaining 4,764 bare containers and 2,627 hollow sections
have no lead-in prose to chunk; for them "unsearchable" is correct, not a defect. I wrote that into
the P6 prompt with a recommendation (strike the target, state the measured residual) rather than
silently letting the next session build against a row it cannot satisfy. The golden baseline also
moved on its own — nDCG@10 is **0.5134** today, not the audit's 0.469 — so P6 measures against its
own pre-run, not against a number in a document.
