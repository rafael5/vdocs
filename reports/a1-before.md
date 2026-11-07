# A1 before: the index as built on 2026-11-06, measured 2026-11-07

Provenance: `index_db` /home/rafael/data/vdocs/index.db · documents 1040 · chunks 57804 ·
`corpus_content_hash` `5b118189…` · read contract 1.8 ·
362.3 MB. Kickoff: `docs/prompts/a1-clean-index-text-kickoff.md`;
expected values are the review's (`docs/proposals/end-to-end-search-architecture-review.md` §3.1).

## Plan confirmation (steps 1–7)

| Step | Measured | Expected | Verdict |
|---|---|---|---|
| 1 markup share, 8,000 random `chunks_fts.body` rows (1,929,343 tokens) | **10.08%** removed | about 10% | matches |
| 1 per class: HTML tags / `<img>` / link targets / nav line / images / heading marks / emphasis | 7.01% / 2.15% / 2.04% / 1.33% / 0.07% / 0.0% / 0.0% | 7 / 2.3 / 1.6 / 1.3 | matches (link targets measured one at a time overlap the image class) |
| 2 chunks with `Back to Contents` | **80.62%** (`chunks.text`), 80.62% (`chunks_fts.body`) | 80.6 | matches |
| 2 chunks with `<`+letter | **36.15%** | about 36% | matches |
| 3 vocabulary terms (`fts5vocab`, scratch copy) | **138,350** (15,254,735 occurrences) | 138,350 | matches |
| 3 terms matching `[0-9a-f]{40,64}` | **11,486** | 11,486 | matches |
| 3 `back` / `contents` rank by document frequency | **3 / 4** (top 10: to, the, back, contents, of, and, user, a, manual, for) | in the top 10 | matches |
| 5 link-polluted titles (`is_latest=1`, `title LIKE '%](#%'`) | **320** in **10** documents (258 FTS title rows) | about 320 in about 10 | matches |
| 6 snippet chrome, golden keyword forms at k=15 | **33.41%** (143 of 428: 115 nav line, 29 `<`) | about 15% | **higher** — see below |
| 7 nDCG@10, 30 keyword questions | **0.4437** (MRR 0.5426, recall@10 0.4636) | 0.425 | differs — see below |
| 7 nDCG@10, the 24 originals | **0.5316** | 0.524 | differs — see below |
| 7 patch ids in the top 5 (synonym table on) | **216/256** | 216 of 256 | matches |
| 7 `file #N` in the top 5 | **25/30** (missed: 1, 101, 2, 4, 405) | 25 of 30 | matches |

**Step 6.** The review's 15% came from the MCP review's probe set; over the 31 golden keyword
forms at k=15 a third of snippets carry chrome, because `snippet()` favours the chunk opening, which
is the heading line followed by the nav line. It changes nothing in the plan except the size of
the payoff.

**Step 7.** The harness numbers differ from the kickoff's expected values because those were the
fix 4 report (`reports/fix4-golden-keywords.json`, 22:34 on 2026-11-06); the index was rebuilt at
23:23 the same day with the final synonym table (fix 3, run 2). Same 57,804 chunks; four questions
moved, all by synonyms: `vpr-allergy-data` 0.576→0.736, `cprs-enter-immunization` 0.527→0.554,
`plain-change-password` 0.000→0.553, `plain-enter-patient-allergies` 0.174→0.000 (the D4 cost the
operator accepted). This file is therefore the paired baseline for A1; the engine is unchanged.

## Step 4: keystroke and placeholder notation (the whitelist's negative test)

Distinct `<Word>` tokens that are not HTML element names: **131** across the whole FTS body,
35 in the 6,000-chunk sample. Sample, most frequent first: `<Enter>` ×155, `<CR>` ×71, `<RET>` ×29, `<PF1>` ×23, `<Tab>` ×12, `<STX>` ×11, `<ETX>` ×11, `<sp>` ×11, `<value>` ×6, `<Ctrl>` ×3, `<F1>` ×2, `<ServerName>` ×2.
Whole corpus: `<Enter>` ×1313, `<CR>` ×1053, `<RET>` ×445, `<PF1>` ×193, `<Alt>` ×39, `<Tab>` ×37, `<RETURN>` ×32, `<Ctrl>` ×23, `<stn>` ×16, `<NONE>` ×15, `<value>` ×14, `<X>` ×13, `<F1>` ×13, `<PF2>` ×12, `<REDACTED>` ×12, `<LIN>` ×12, `<sp>` ×12, `<STX>` ×11, `<ETX>` ×11, `<name>` ×8.

Two facts the kickoff did not state, both measured here and both binding on the projection:

1. **The dominant form is Pandoc-escaped.** `\<Enter\>` occurs 12,805 times and bare `<Enter>`
   1,313; `\<RET\>` 8,898 vs 445; 545 distinct escaped forms. A tag matcher that accepts `\` before
   `>` would eat them. The projection's tag shape is `<`, optional `/`, an element name, then
   whitespace, `/` or `>` — a backslash is none of those, so every escaped form is left as written.
2. **Placeholders collide with element names only in case.** Pandoc emits lowercase tags; the
   corpus writes `\<A\>` ×221, `<Code\>`/`</Code\>` ×137, `<P>` ×6, `<A>` ×5, `<B\>` ×6, `<U\>` ×5,
   `<I\>` ×3 as keystrokes or placeholders. The whitelist is therefore **case-sensitive lowercase**;
   `<A>` and `<P>` survive, `<a href>` and `<p>` are tags.

Real HTML elements present that the kickoff's whitelist omitted (Pandoc output, each with an `id`
or `class` attribute whose tokens would otherwise remain as residue): `h2`–`h5` (about 1,450),
`mark` (223), `caption` (205), `hr` (103), `aside` (103), `br` (372), plus 7 HTML comments. The
whitelist is extended with the HTML element names Pandoc emits (`h1`–`h6`, `mark`, `caption`,
`hr`, `aside`, `tfoot`, `dl`, `dt`, `dd`, `kbd`, `s`, `del`, `ins`, `small`, `cite`, `q`, `abbr`,
`figure`, `figcaption`, `section`, `header`, `footer`, `nav`, `article`, `details`, `summary`),
and comments are dropped. Lowercase placeholders (`<name of file>`, `<http://…>`,
`<universal id>`) do not have the tag shape and stay.

`<img>` attributes in the corpus: `src` 17,352, `style` 17,128, `alt` 12,027, `title` 593 — so a
third of figures have no alt text and reduce to nothing. `<span>` carries `class="mark"` (16,071)
or a `_Toc` `id` (4,369) and nothing else; `<a>` is the footnote back-link (1,158).

**Titles.** The 320 polluted titles have the legacy TOC shape `[Preface [ii](#preface)](#preface)`:
the inner link is a page number, not label text. The projection reduces that shape to `Preface`
(the page number is dropped with its target); a plain link keeps its label. The section **slug stays
computed from the raw title** (`preface-iiprefacepreface`), because `refs.yaml` and every consumer
cite it; only the stored title and the `section_path` built from titles change. A further 161
latest `section_path` values carry a link (`… \[FHSELX\][1](#_bookmark6)`) and are corrected by
the same rule.

Documents with polluted titles: `ACKQ/ackq3_0_p12tm`, `FH/fh5_5p8ag`, `GMRC/constm`, `GMRV/vitl_5_p22_um`, `PRCN/prcn_1_tm`, `PSA/phar_1_api_r0520`, `PSN/phar_1_api_0520`, `PSN/phar_1_p576_api_r`, `PSX/phar_1_api_r0110`, `YS/ys_mha_um`.

## Decision

The plan stands: markup is 10%, not under 5%; the keystroke notation is distinguishable from tags
by case and by the escaped form. Amendments recorded above: extended whitelist, case-sensitive
match, comments dropped, legacy-TOC page numbers dropped from titles.

Scripts: the session scratchpad's `a1/measure_markup.py` (steps 1–5) and `a1/probes.py` (steps
6–7, through `server.search.lexical_search` with the index's synonym table); the harness section
below is `scripts/baseline_golden.py --out reports/a1-before.md` (JSON beside it).

---

# Phase 0.4 baseline — lexical retrieval quality (golden set)

- **Lake:** `/home/rafael/data/vdocs`  ·  **mode:** lexical (FTS5+BM25), keyword forms  ·  **k:** 10
- **Labeled queries:** 30 of 31
- **mean nDCG@10:** 0.4437
- **mean MRR:** 0.5426
- **mean recall@10:** 0.4636
- **mean redundancy@10:** 0.0935 (all queries)

## Per-query

| query | axis | nDCG@10 | MRR | recall@10 | redundancy@10 | hits |
|---|---|---|---|---|---|---|
| kids-install-build | kids-install | 0.0 | 0.0 | 0.0 | 0.0 | 10 |
| pharmacy-api-dispense | redundancy-probe | — | — | — | 0.7 | 10 |
| fileman-add-field | fileman-dd | 0.0 | 0.0 | 0.0 | 0.0 | 10 |
| rpc-broker-client-call | rpc-broker | 0.0673 | 0.1429 | 0.1111 | 0.0 | 10 |
| mailman-decnet-transmission | mailman-network | 0.783 | 1.0 | 0.5714 | 0.3 | 7 |
| radiology-cancel-exam | radiology | 0.3308 | 0.1429 | 0.6667 | 0.0 | 10 |
| pharmacy-release-signed-order | pharmacy-release | 0.8415 | 1.0 | 0.5 | 0.3 | 8 |
| tiu-unsigned-notes | tiu-notes | 0.7661 | 1.0 | 0.5 | 0.2 | 8 |
| vpr-allergy-data | vpr-domains | 0.7364 | 1.0 | 1.0 | 0.1 | 9 |
| lab-file60-audit | lab-audit | 0.9329 | 1.0 | 1.0 | 0.0 | 10 |
| cprs-enter-immunization | cprs-gui | 0.554 | 1.0 | 1.0 | 0.0 | 10 |
| vbecs-accept-order | vbecs-orders | 0.7126 | 1.0 | 0.25 | 0.0 | 10 |
| hl7-security-keys | hl7-security | 0.9173 | 1.0 | 0.5 | 0.2 | 9 |
| fileman-file-200-new-person | fileman-dd | 0.0 | 0.0 | 0.0 | 0.0 | 10 |
| fileman-import-host-file | api-leadin | 0.2404 | 0.1429 | 0.5 | 0.0 | 10 |
| fileman-input-transform-definition | api-leadin | 0.5714 | 1.0 | 1.0 | 0.3 | 10 |
| fileman-blddialog-icr-number | api-leadin | 0.9173 | 1.0 | 0.5 | 0.0 | 1 |
| quasar-package-wide-variables | short-reference | 1.0 | 1.0 | 1.0 | 0.0 | 1 |
| hl7-table-0136-values | short-reference | 1.0 | 1.0 | 1.0 | 0.0 | 10 |
| kids-backup-transport-global | kids-install | 0.2891 | 0.1 | 1.0 | 0.0 | 10 |
| hl7-start-tcpip-link | hl7-links | 0.7829 | 1.0 | 0.6667 | 0.0 | 10 |
| fileman-file-access-security | kernel-security | 0.5483 | 1.0 | 0.5714 | 0.0 | 10 |
| vista-signon-credentials | kernel-auth | 0.0 | 0.0 | 0.0 | 0.0 | 10 |
| fileman-finder-api | fileman-api | 0.2953 | 0.25 | 0.2 | 0.0 | 10 |
| taskman-monitor | kernel-ops | 0.4715 | 1.0 | 0.5714 | 0.0 | 10 |
| plain-change-password | plain-english | 0.5525 | 0.5 | 0.8 | 0.1 | 10 |
| plain-create-user-account | plain-english | 0.0 | 0.0 | 0.0 | 0.3 | 10 |
| plain-background-jobs | plain-english | 0.0 | 0.0 | 0.0 | 0.1 | 10 |
| plain-set-up-printer | plain-english | 0.0 | 0.0 | 0.0 | 0.0 | 10 |
| plain-enter-patient-allergies | plain-english | 0.0 | 0.0 | 0.0 | 0.2 | 9 |
| plain-send-email | plain-english | 0.0 | 0.0 | 0.0 | 0.1 | 9 |
