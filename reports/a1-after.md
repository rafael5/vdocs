# A1 after: the index rebuilt with the clean projection, measured 2026-11-07

Provenance: `index_db` /home/rafael/data/vdocs/index.db · documents 1040 · chunks 57804 ·
`corpus_content_hash` `5b118189…` (unchanged: the document set did not change, only
the FTS text) · read contract 1.8 · 343.8 MB. Before: `reports/a1-before.md`
(same hash, same 57,804 chunks, 362.3 MB). Paired ranking: `reports/a1-paired.md`.
Rebuild: `vdocs run --from index --to manifest --force` (log `~/data/vdocs/reports/run-a1-clean-index-5-2026-11-07.log`,
`index` 1m07s), then `vdocs doctor`: **GOLD LIBRARY: GREEN** (22 pass, 0 warn, 0 fail).

## Success criteria (kickoff "after building")

| Criterion | Before | After | Target | Verdict |
|---|---|---|---|---|
| 1 markup share by the kickoff's six patterns, 8,000 random `chunks_fts.body` rows | 10.08% | **1.02%** | under 0.5%, residue all keystroke notation | met in substance — the 1.02% is entirely the `<[^>]+>` pattern matching **keystroke and placeholder notation**, which is content by decision (below); HTML markup is 0 |
| 1 nav-line prevalence in `chunks_fts.body` | 80.62% | **0.0%** (`chunks.text` still 80.62%, unchanged by design) | 0 | met |
| 1 chunks with `<`+letter in the FTS body | 36.15% | **14.82%** (all notation) | — | — |
| 1 hex-hash vocabulary terms `[0-9a-f]{40,64}` | 11,486 | **10** — 4 digit rulers in the GEN code-sheet example, 6 SHA values the XU data-security guide and an SR manual quote as example output | 0 | met for asset hashes; the 10 are document content |
| 1 `back` / `contents` rank by document frequency | 3 / 4 | **out of the top 100** (top 10: the, to, of, and, user, a, manual, for, in, is) | out of the top 100 | met |
| 1 total vocabulary | 138,350 | **115,421** (**−16.6%**) | about −8% | exceeded |
| 2 link-polluted titles (`is_latest=1`) | 320 in 10 docs | **0** (FTS title rows 0; polluted `section_path` values 161 → 0) | 0 | met |
| 3 snippet chrome, golden keyword forms at k=15 | 33.4% (143 of 428) | **0 nav lines**; 6 of 428 (1.4%) contain `<`, all keystroke notation (`<PF1>E`, `<Enter>`, `<RET>` in screen dialogue) | 0% | met |
| 4 ranking, paired per question | — | no judged section lost from any top 10; one grade-3 section gained | no top-10 loss | **adoption rule passed** |
| 4 patch ids in the top 5 / `file #N` in the top 5 | 216 of 256 / 25 of 30 | **223/256** / **25/30** (missed: 1, 101, 2, 4, 405, the same five) | not below 216 / 25 | met |
| 5 `vdocs doctor` | GREEN | **GREEN** | GREEN | met |
| 5 `make check` in `~/vista-forge/vdocs-web` and `~/projects/vdocs-cli` | — | **both green** (fixtures build their own tables; nothing in the read contract moved, version stays 1.8) | green | met |
| 6 index.db size | 362.3 MB | **343.8 MB** (−5.1%); FTS content + index 172 → **154 MB** (−10.5%) | FTS about −10% | met |

## The residue, listed

Over the whole FTS body (12,802,769 word tokens, 57,804 chunks):

- **Angle-bracket notation: 47,821 tokens holding 0.857% of word tokens** — `<Enter>` ×15,443, `<RET>` ×9,387, `<ENTER>` ×2,059, `<PF1>` ×1,291, `<CR>` ×1,094, `<Tab>` ×643, `<RETURN>` ×347, `<ret>` ×336, `<Spacebar>` ×301, `<Ctrl>` ×163, `<TAB>` ×150, `<DIN>` ×118, … (615 distinct
  bare `<Word>` forms). All content: keystrokes, HL7 control characters, placeholders. Pandoc's
  escaped forms (`\<Enter\>`, 12,805 in the source) are restored to the bare notation, so `<Enter>`
  is now one surface in snippets and in the index.
- **Whitelisted tag shapes: 68, none a tag.** Every one is a Pandoc-escaped literal in the source
  (`\<code\>` ×45 in LR/LA/LEDI ICR text — "where `<code>` is a LOINC or NLT code" — `\<i\>` as an
  M array subscript in HL7/PX, `\<p\>`, `\<b\>`, `\<dt\>`, `\<caption\>`, `\<section\>` in prose
  about markup). Unescaped tag shapes: **0**.
- **Link targets `](#…)`: 18, all in `GMRC/constm`.** The oversized-split's character windows cut a
  single enormous line mid-link, so a `#pN` window begins with the tail of a link the projection
  cannot see whole. A chunking matter, not the projection's; left for the chunking work.
- **`↑`: 32** — arrow-key prose ("pressing the ↑ and ↓ keys"), not the nav line (0).
- **`<img`: 0. Table markers: 0. HTML comments: 0** unescaped (7 escaped XML comments in
  VistALink guides are content and stay).
- **Backslash escapes left: `\^` 213, `\|` 154, `\*` 78** — each is a literal backslash the
  source wrote as `\\` followed by punctuation; the escape rule restores one level only.

## What the projection does (as built, `index_pure.index_text`)

In order: drop the nav line, extracted-table markers, HTML comments and fence lines; strip
tag-shaped tokens whose name is a lowercase HTML element (Pandoc emits lowercase; `<A>`, `<P>`,
`<Code>` are placeholders and stay) — a block element becomes a space, an inline element a gap that
is a space only between two word characters, `<img>` its alt text — where a tag is `<`, `/`?, name,
then whitespace, `/` or `>`, attributes that may hold one nested `<…>` (a figure's alt text quoting
`<Enter>`), and a `>` not written `\>` (Pandoc's escaped literals `\<Enter\>`, `\</Console\>`
always end in `\>`; content ending in a bare backslash before a real tag, `\F\</p>`, does not);
reduce links and images to their labels (escaped brackets, footnote refs and a lone trailing
backslash allowed inside a label; a legacy TOC entry `[Title [ii](#a)](#a)` drops its page number;
an escaped `\[` never opens a link); drop heading marks and unescaped emphasis / inline-code
delimiters at word edges (`A_B`, `A*B` stay); restore Pandoc's backslash-escaped punctuation;
collapse whitespace. Property-tested (`tests/property/test_index_text_props.py`): every word token
outside a dropped construct survives; no whitelisted tag, link target, nav arrow, fence or
40–64-character hex token survives; keystroke notation survives; table cell text survives; on
arbitrary text the projection never invents a token.

Five rebuilds were needed to reach this: each residue pass found a corpus shape the kickoff did not
list (escaped keystrokes, placeholders differing from elements only in case, escaped brackets and
footnote refs inside labels, `<Enter>` inside an `<img>` alt, labels ending in a lone backslash,
content ending in a backslash before a tag), each got a failing test first, and the last rebuild is
the one measured here.

Scripts: the session scratchpad's `a1/measure_markup.py`, `a1/probes.py`, `a1/paired.py`; the
harness section below is `scripts/baseline_golden.py --out reports/a1-after.md`.

---

# Phase 0.4 baseline — lexical retrieval quality (golden set)

- **Lake:** `/home/rafael/data/vdocs`  ·  **mode:** lexical (FTS5+BM25), keyword forms  ·  **k:** 10
- **Labeled queries:** 30 of 31
- **mean nDCG@10:** 0.453
- **mean MRR:** 0.5449
- **mean recall@10:** 0.4747
- **mean redundancy@10:** 0.0903 (all queries)

## Per-query

| query | axis | nDCG@10 | MRR | recall@10 | redundancy@10 | hits |
|---|---|---|---|---|---|---|
| kids-install-build | kids-install | 0.0 | 0.0 | 0.0 | 0.0 | 10 |
| pharmacy-api-dispense | redundancy-probe | — | — | — | 0.7 | 10 |
| fileman-add-field | fileman-dd | 0.0 | 0.0 | 0.0 | 0.0 | 10 |
| rpc-broker-client-call | rpc-broker | 0.0637 | 0.125 | 0.1111 | 0.0 | 10 |
| mailman-decnet-transmission | mailman-network | 0.783 | 1.0 | 0.5714 | 0.3 | 7 |
| radiology-cancel-exam | radiology | 0.3308 | 0.1429 | 0.6667 | 0.0 | 10 |
| pharmacy-release-signed-order | pharmacy-release | 0.8415 | 1.0 | 0.5 | 0.3 | 8 |
| tiu-unsigned-notes | tiu-notes | 0.754 | 1.0 | 0.5 | 0.2 | 8 |
| vpr-allergy-data | vpr-domains | 0.7364 | 1.0 | 1.0 | 0.1 | 9 |
| lab-file60-audit | lab-audit | 0.9329 | 1.0 | 1.0 | 0.0 | 10 |
| cprs-enter-immunization | cprs-gui | 0.554 | 1.0 | 1.0 | 0.0 | 10 |
| vbecs-accept-order | vbecs-orders | 0.7126 | 1.0 | 0.25 | 0.0 | 10 |
| hl7-security-keys | hl7-security | 0.9173 | 1.0 | 0.5 | 0.2 | 9 |
| fileman-file-200-new-person | fileman-dd | 0.2351 | 0.125 | 0.3333 | 0.0 | 10 |
| fileman-import-host-file | api-leadin | 0.2404 | 0.1429 | 0.5 | 0.0 | 10 |
| fileman-input-transform-definition | api-leadin | 0.631 | 1.0 | 1.0 | 0.3 | 10 |
| fileman-blddialog-icr-number | api-leadin | 0.9173 | 1.0 | 0.5 | 0.0 | 1 |
| quasar-package-wide-variables | short-reference | 1.0 | 1.0 | 1.0 | 0.0 | 1 |
| hl7-table-0136-values | short-reference | 1.0 | 1.0 | 1.0 | 0.0 | 10 |
| kids-backup-transport-global | kids-install | 0.301 | 0.1111 | 1.0 | 0.0 | 10 |
| hl7-start-tcpip-link | hl7-links | 0.7829 | 1.0 | 0.6667 | 0.0 | 10 |
| fileman-file-access-security | kernel-security | 0.57 | 1.0 | 0.5714 | 0.0 | 10 |
| vista-signon-credentials | kernel-auth | 0.0 | 0.0 | 0.0 | 0.0 | 10 |
| fileman-finder-api | fileman-api | 0.2652 | 0.2 | 0.2 | 0.0 | 10 |
| taskman-monitor | kernel-ops | 0.4697 | 1.0 | 0.5714 | 0.0 | 10 |
| plain-change-password | plain-english | 0.5525 | 0.5 | 0.8 | 0.1 | 10 |
| plain-create-user-account | plain-english | 0.0 | 0.0 | 0.0 | 0.3 | 10 |
| plain-background-jobs | plain-english | 0.0 | 0.0 | 0.0 | 0.1 | 10 |
| plain-set-up-printer | plain-english | 0.0 | 0.0 | 0.0 | 0.0 | 10 |
| plain-enter-patient-allergies | plain-english | 0.0 | 0.0 | 0.0 | 0.2 | 9 |
| plain-send-email | plain-english | 0.0 | 0.0 | 0.0 | 0.0 | 10 |
