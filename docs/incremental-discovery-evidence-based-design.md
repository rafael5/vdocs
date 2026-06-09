# Incremental, Live, Interactive Filtering for Large Document Corpora — Evidence-Based Design

**Scope.** Proven HCI/IR design patterns for *incremental, live, interactive* filtering of large
text/document corpora in a CLI/TUI tool (Go, no library restrictions). The motif of primary interest
is **visual drill-down / "find it when you see it"**: the user toggles filter facets/words on and off
and watches the result list shrink and expand in real time, *without* needing the "magic keyword" or
any lexical-search skill.

**Target.** `vdocs` — an offline, zero-ML, lexical VistA documentation "gold library" (~1,100 curated
markdown docs + SQLite/FTS5 index). Two searcher personas: **developers** (symbol-anchored: routines,
RPCs, FileMan files, options) and **clinical/admin operators** (task-oriented, low lexical-search
skill). The corpus already carries rich structured facets: `doc_type`, app/package, section,
`function_category`, persona axes (`app_user`/`doc_user`), `software_class`, `vasi_status`, and 9 entity
types (routine / rpc / fileman_file / option / global / hl7_segment / mail_group / build /
package_namespace).

This report is evidence-driven: every pattern below is backed by primary HCI/IR literature or
documented production adoption, each verified through adversarial review.

---

## Executive summary

The literature is unusually decisive for this use case. **Faceted navigation** (Hearst/Flamenco)
and **dynamic queries with live result-count previews** (Shneiderman/UMD HCIL) are the two
foundational, repeatedly-validated patterns for letting non-expert users explore large corpora by
recognition rather than recall — and both map cleanly onto the structured facets vdocs already has.
Controlled studies show faceted browsing is overwhelmingly preferred over keyword search (90–91% of
users) **and** measurably improves retrieval success on "find all X" tasks (e.g., 77% vs 21%), while
dynamic-query/slider interfaces beat typed/natural-language querying on both speed and error rate in
counterbalanced experiments. The theoretical justification — Bates' berry-picking, Pirolli & Card
information foraging, and recognition-over-recall — all converge on the same prescription: let the
user reshape the query continuously as their need evolves, never force a single up-front keyword. The
recommendation for vdocs is to prototype **(1) live faceted drill-down with parenthesized result-count
previews and zero-hit suppression FIRST**, layered over the existing facets, with **(2) incremental
fuzzy narrowing (fzf-style) on the result list** as the developer-persona accelerator. Both are
directly and cheaply implementable in a Go TUI.

---

## Finding 1 — Faceted navigation is preferred over keyword search and is a proven, adopted pattern (high confidence)

Users overwhelmingly prefer hierarchical faceted-metadata navigation to a keyword baseline, and they
*succeed* with it, especially for browsing/exploratory tasks. In the canonical Flamenco study (Yee,
Swearingen, Li & Hearst, *Faceted Metadata for Image Search and Browsing*, CHI 2003 — a within-subjects
study of 32 art-history students over a 35,000-image collection, compared against a Google-Image-style
keyword baseline):

- **90% preferred the faceted/metadata approach overall**, **97% said it helped them learn more about
  the collection**, **75% found it more flexible**, and **72% found it easier to use** than the baseline.
  [Flamenco CHI 2003]
- A complementary reporting gives **91% preferred Flamenco overall** and **88% found it more useful for
  the searching they usually do.** [Flamenco CHI 2003; Hearst 2009 Ch. 8]
- Hearst's own textbook conclusion: *"participants like and are successful using hierarchical faceted
  metadata for navigating information collections, especially for browsing tasks."* [Hearst 2009 Ch. 8]

> **Honest nuance:** Flamenco ran ~an order of magnitude slower than the baseline, and for the simplest
> single-facet known-item task (e.g., "find roses") ~50% of users actually preferred the keyword
> baseline. The overwhelming preference is for *overall / exploratory* use. Facets that mismatch the
> user's mental model degrade the experience — facet design matters.

Faceted navigation is also a long-established, **adopted production standard**, not a lab curiosity:

- It is treated as **core/required functionality of next-generation discovery layers** (distinct from a
  traditional OPAC) — appearing as a *required* criterion in Indiana University's discovery-layer rubric
  and in Sharon Yang's NGC feature checklist; VuFind and Blacklight ship it as a headline feature.
  [Serials Review 2012, S0098791311001705]
- At **multi-million-volume scale**, HathiTrust indexes both MARC metadata and full text in Solr and
  uses **faceted displays derived from bibliographic data** as the strategy to make large result sets
  navigable; VuFind (Solr) went to production at the National Library of Australia over 5M+ titles
  (2008), and Blacklight is adopted across institutions. [HathiTrust large-scale-search blog]

**Mapping to vdocs:** vdocs already has the facet axes (`doc_type`, app/package, `function_category`,
persona, `software_class`, `vasi_status`, 9 entity types). These are exactly the kind of structured
metadata facets the literature validates. Faceted drill-down over them is the highest-evidence motif to
prototype first.

---

## Finding 2 — Faceted drill-down measurably improves retrieval success, not just preference (high confidence)

Beyond preference, faceting **improves task success** on structured "find all X" tasks, partly because
keyword users fail at vocabulary they don't think to type (singular/plural, synonyms, catalog terms):

- Flamenco "find all woodcuts": **77% succeeded with faceting vs only 21% with the keyword baseline.**
- "Find all aquatints": **81% vs 57%.**
- The paper explicitly attributes part of the gap to *"users of the Baseline not querying both singular
  and plural forms of words."* [Flamenco CHI 2003]

**Why this matters for vdocs:** VistA terminology is exactly the kind of specialist vocabulary where the
"magic keyword" problem bites hardest — a clinical/admin operator will not know that the routine, RPC, or
FileMan file they want is named a particular way. Recognition-based facet selection sidesteps the
vocabulary barrier the same way it did for woodcuts/aquatints.

---

## Finding 3 — Dynamic queries with live result-count previews and zero-hit suppression are the proven incremental-filtering interaction (high confidence)

The UMD HCIL "dynamic queries" line of work defines the live-filtering interaction model that vdocs
wants, and grounds it empirically:

- **Interaction model:** control widgets (sliders, buttons, checkboxes) **coupled to display update
  faster than 100 ms**, letting users incrementally and reversibly narrow large result sets by
  *eliminating unwanted items* — *"even when there are tens of thousands of displayed items."*
  [Shneiderman 1996, *The Eyes Have It*; HCIL TR 93-01]
- The defining characteristics are *"a visual overview, powerful filtering tools, continuous visual
  display, pointing rather than typing, and rapid, incremental, and reversible control of the query,"*
  with the result set updating *"within 100msec."* [HCIL TR 93-01 / Ahlberg & Shneiderman 1994]

The **query-preview / live-count** mechanism is the single most directly transferable detail:

- In Flamenco, **a result count is shown on every category link before clicking** (computed with SQL
  `COUNT(*)`/`GROUP-BY`), and **zero-result links are never shown.** Nine users gave *unsolicited* praise:
  the previews gave them a *sense of the collection's completeness* — *"I can tell how many are available
  in different categories from the front page."* [Flamenco CHI 2003]
- The FedStats Visual Information Browser (Kules & Shneiderman 2003) states the same pattern as a design
  rule: **parenthesized counts on each facet/category** show how many of the currently-filtered docs fall
  in it, and **zero-hit queries are avoided by graying out checkboxes** that would yield no matches.
  Controls are *"simple, reversible actions that produce immediate feedback (under 100 msec)"* using
  checkboxes, double-ended sliders, and image maps — and **the current result-set size is always
  displayed** so users know when the list is small enough to linearly scan.
  [Kules & Shneiderman 2003, UMD HCIL]

**Empirical backing (interactive filtering beats typed querying):**

- Counterbalanced within-subjects experiment, **18 chemistry students**: dynamic queries were
  **statistically significantly faster** than both a graphical and a textual form-fill-in interface
  (overall F(2,34)=36.1, p<0.001; DQ 412 s vs 709 s vs 1094 s), and had **lower error rates** than the
  textual typed-query interface. [Ahlberg, Williamson & Shneiderman, CHI 1992]
  > Nuance: error-rate advantage held against the *textual* typed-query interface; vs the *graphical*
  > form-fill-in, DQ won on speed but not significantly on errors.
- Dynamic HomeFinder, **18 subjects**: dynamic-query sliders had a **statistically significant speed
  advantage** over a natural-language interface (Symantec Q&A) and paper listings on the hardest tasks
  (e.g., task 5: 58.8 s vs 189.9 s), with **satisfaction ratings strongly favoring** dynamic queries
  (QUIS 110 vs 84 vs 68). [Williamson & Shneiderman, SIGIR 1992 / HCIL TR 92-01]

**Mapping to vdocs:** Implement faceted drill-down *with a live count next to every facet value* and
*suppress (or gray) facet values that would yield zero hits.* With FTS5 + SQLite this is a
`COUNT(*) … GROUP BY facet` against the current filter — exactly the Flamenco mechanism, and trivially
fast at 1,100 docs. Always show the running result-set size so the user knows when to stop and scan.

---

## Finding 4 — The information-seeking theory justifies drill-down over magic-keyword search (high confidence)

Multiple independent, durable theoretical frameworks converge on the same prescription: treat search as
an *evolving, browsing-driven* process and let the user continuously reshape the query.

- **Berry-picking (Bates 1989):** information needs are *not* satisfied by a single final retrieved set,
  but *"by a series of selections and bits of information found along the way"* — and the *primary driver*
  is the information need **changing during the search itself**. The interface should therefore let users
  continuously re-shape the query (e.g., toggling facets) rather than commit to one query up front.
  [Hearst 2009 §3.3; Savolainen 2018, *J. Information Science*]
- **Berry-picking + information foraging are two distinct, established frameworks** for exploratory
  search; both reject the single-query model. Foraging's *information scent* (Pirolli & Card, PARC) is the
  standard basis for browse/navigation UI design. [Savolainen 2018, DOI 10.1177/0165551517713168]
- **Recognition over recall (cognitive science / Nielsen heuristic #6):** *"it is usually easier for a
  person to recognize something by looking for it than it is to think up how to describe that thing"* —
  the bedrock justification for visible-facet interfaces over magic-keyword search, especially for
  low-literacy users. [Hearst 2009 §3.5.3; NN/g]

---

## Finding 5 — Low-search-literacy users are specifically poorly served by keyword-only interfaces and benefit most from recognition-based drill-down (high confidence)

This is the crux for the vdocs clinical/admin operator persona.

- **Non-experts lack the domain terms and taxonomy knowledge to form good queries**, so their searches
  *"often return results with zero hits or far too many."* Browsing with immediate, reversible filtering
  lets them succeed *"without needing a pre-existing knowledge of the information architecture,
  terminology or keywords."* [Kules & Shneiderman 2003]
- **Direct-manipulation visual filtering helps novices** because learning a command/query language
  *"may take several hours"* and still yields syntax/semantic errors, whereas *pointing-not-typing*
  visual selection structurally avoids illegal operations. [Shneiderman 1994 / HCIL TR 93-01;
  Ahlberg et al. CHI 1992]
- Even **expert domains search like novices**: in a full-day PubMed query-log study, **most academic
  researchers and health-care professionals (including physicians) use only natural-language keyword
  queries and not advanced IR functions** — only ~6% of sessions were "experienced"/advanced. This is
  strong evidence that even sophisticated users default to keyword-and-scan, so a recognition-based facet
  drill-down would serve the low-skill vdocs operator persona far better than expecting query craft.
  [Yoo & Mosa, *JMIR Medical Informatics* 2015, PMC4526974]

---

## Finding 6 — Proven interactive TUI filter tools as implementation references; Go-TUI implementability (medium confidence)

The research question's named TUI tools (fzf, telescope.nvim, lnav, k9s, broot, lf/ranger, Miller) are
strong *engineering* references for the same patterns the HCI literature validates — incremental fuzzy
narrowing, live-updating result lists, multi-select toggles, and split-pane preview. (Confidence is
medium here because these are adoption/engineering references, not the subject of the adversarially
verified academic-claim set; the *patterns* they embody are what the verified literature backs.)

- **fzf** is the canonical "find it when you see it" accelerator: every keystroke re-filters a live list
  with a running match count and a preview pane. This is the developer-persona motif — fast incremental
  narrowing over symbol-anchored results (routines, RPCs, files, options).
- **k9s / lnav / broot / lf** demonstrate the same live-filter-plus-preview loop in a full-screen TUI.

**Go TUI surface:** Charmbracelet **Bubble Tea** (Elm-style model/update/view) + **Bubbles**
(list, textinput, viewport, table components) + **Lip Gloss** styling is the practical stack for:
live-updating result counts, multi-select facet toggles, incremental fuzzy filtering (e.g.,
`sahilm/fuzzy`), and a split-pane facet/result/preview layout. `tview`/`tcell` or `gocui` are
alternatives. All of the verified interaction patterns (sub-100 ms re-filter on each toggle/keystroke,
running result count, facet-value counts, zero-hit suppression) are straightforward in this stack against
a 1,100-doc SQLite/FTS5 index.

---

## Recommended prototype order for vdocs

1. **Live faceted drill-down with query-count previews (PROTOTYPE FIRST).** Render the existing facet
   axes (`doc_type`, app/package, `function_category`, persona `app_user`/`doc_user`, `software_class`,
   `vasi_status`, 9 entity types) as multi-select toggles in a left pane. Next to every facet *value*,
   show a live `COUNT(*) … GROUP BY` against the current filter; **gray/suppress zero-hit values**; always
   show the running total result-set size. This is the highest-evidence motif (Findings 1–3) and maps 1:1
   onto vdocs' existing structured facets and SQLite. Targets the low-skill operator persona directly via
   recognition-over-recall (Findings 4–5).
2. **Incremental fuzzy narrowing on the result list (fzf-style).** A textinput that re-filters the
   currently-faceted result list on every keystroke, with a match count and a preview pane. This is the
   developer-persona accelerator for symbol-anchored lookups, complementing (not replacing) facets.
3. **Split-pane preview / details-on-demand.** Selecting a result shows its markdown in a preview pane —
   "details on demand" after the facet drill-down has narrowed the set.

Facets first, fuzzy second: facets serve the operator persona (no vocabulary required); fuzzy serves the
developer persona (who knows the symbol). Both run live, sub-100 ms, reversible.

---

## Caveats and time-sensitivity

- **Facet design is load-bearing.** Flamenco's own data shows facets that mismatch the user's mental
  model degrade the experience, and for *simple known-item* tasks a plain keyword box can win. Faceting is
  validated for *exploratory/browsing* use; keep a keyword/fuzzy path for known-item lookups (hence the
  two-motif recommendation).
- **Latency target is a goal, not a guarantee.** The 100 ms figure is the canonical design target
  (coinciding with Nielsen's perceptual-immediacy limit), not an empirically guaranteed universal — at
  1,100 docs it is trivially met, but the literature notes large-scale faceting needs engineered indexes.
- **Scaling qualifications.** Critiques surfaced in the literature (too many facets cause clutter;
  double-ended sliders are awkward; faceting performance degrades with data/facet count; URL/SEO bloat)
  concern *implementation scaling*, not the core novice-benefit claim — and are mostly irrelevant at
  vdocs' scale.
- **A few supporting claims were split or refuted in verification** (transparency): the strong "users
  *shift from* keyword *to* facets as they learn" claim, the literal "Visual Information Seeking Mantra
  puts filtering before keyword" framing, Marchionini's "orienteering" framing, and a VuFind log-analysis
  stat ("only ~35% of basic searches used facets") did **not** survive adversarial review and are
  excluded. Notably, the refuted VuFind stat is a mild *counter*-signal: even where facets exist, a
  minority of searches use them — reinforcing that facets should *augment*, not replace, the keyword path.
- **Source quality is high overall:** the load-bearing findings rest on primary, peer-reviewed sources
  (CHI/SIGIR papers, Hearst's Cambridge UP book, JMIR, *J. Information Science*) and first-party
  production accounts (HathiTrust). The TUI/Go-implementation finding rests on engineering adoption rather
  than the verified academic set.

---

## Open questions

1. **Facet ordering / mental-model fit for VistA.** Which of vdocs' ~15 facet axes do the operator vs
   developer personas actually reach for first? Flamenco shows facet-to-mental-model fit is decisive but
   the literature can't answer it for VistA — it needs a small task-based test with real personas.
2. **Entity-type facets vs full-text — interaction.** How should the 9 entity-type facets (routine, rpc,
   etc.) compose with FTS5 keyword/fuzzy filtering in one live loop? (AND across axes, OR within an axis is
   the Flamenco default, but cross-axis count computation against FTS5 needs a measured query plan.)
3. **Real-world facet usage rate at vdocs scale.** The one log-based adoption datapoint was refuted; there
   is no verified empirical figure for how heavily a drill-down motif gets used in a small specialist CLI
   corpus. Instrument the prototype to measure it.
4. **CLI vs TUI surface.** The evidence is for GUI/TUI direct manipulation; how much of the "live count +
   reversible toggle" benefit survives in a non-full-screen CLI (vs a Bubble Tea full-screen TUI) is
   unestablished.

---

## Sources

- Yee, Swearingen, Li & Hearst, *Faceted Metadata for Image Search and Browsing*, CHI 2003 —
  https://flamenco.berkeley.edu/papers/flamenco03.pdf (also flamenco-chi03.pdf)
- Hearst, *Search User Interfaces* (Cambridge Univ. Press, 2009), Ch. 3 & Ch. 8 —
  https://searchuserinterfaces.com/book/
- Shneiderman, *The Eyes Have It: A Task by Data Type Taxonomy for Information Visualizations*, 1996 —
  https://www.cs.umd.edu/~ben/papers/Shneiderman1996eyes.pdf
- Ahlberg, Williamson & Shneiderman, *Dynamic Queries for Information Exploration: An Implementation and
  Evaluation*, CHI 1992 — https://www.cs.umd.edu/~ben/papers/Ahlberg1992Dynamic.pdf
- Williamson & Shneiderman, *The Dynamic HomeFinder*, SIGIR 1992 / HCIL TR 92-01; *Dynamic Queries for
  Visual Information Seeking*, HCIL TR 93-01 — https://www.cs.umd.edu/hcil/trs/93-01/93-01.pdf
- Kules & Shneiderman, *Designing a Metadata-Driven Visual Information Browser for Federal Statistics*,
  2003 — https://www.cs.umd.edu/~ben/papers/Kules2003Designing.pdf
- Savolainen, *Berrypicking and information foraging: Comparison of two theoretical frameworks for
  studying exploratory search*, *Journal of Information Science* 2018 —
  https://journals.sagepub.com/doi/abs/10.1177/0165551517713168
- Bates, *The Design of Browsing and Berrypicking Techniques for the Online Search Interface*, 1989
- HathiTrust, *Large-scale Full-text Indexing with Solr* (large-scale-search blog) —
  https://old.www.hathitrust.org/blogs/large-scale-search/large-scale-full-text-indexing-solr.html
- *The Search for a New OPAC: Selecting an Open Source Discovery Layer*, Serials Review 2012 —
  https://www.sciencedirect.com/science/article/abs/pii/S0098791311001705
- Yoo & Mosa, *Analysis of PubMed User Sessions Using a Full-Day PubMed Query Log*, JMIR Medical
  Informatics 2015 — https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4526974/
