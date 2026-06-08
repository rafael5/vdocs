# Human validation — how to use this folder

This folder holds the **human-in-the-loop validation tables** for the offline lexical search work
(phase **L1.5**, see `docs/offline-lexical-search-implementation-plan.md`). Each `.csv` is a table of
candidate curation decisions. The search *metric* can tell us whether a change helps; only a human
supplies the **common sense** about which terms are noise. That judgement happens here.

## The workflow

1. **Open a CSV** in a spreadsheet (LibreOffice/Excel/Sheets) or a text editor.
2. **Edit the `decision` column** — that is the only column you change. Each row's `recommendation`
   column is my suggested call (pre-copied into `decision` so "accept all" means leave it as-is).
3. **Save** the CSV (keep it as CSV, comma-separated, UTF-8).
4. Tell me **"apply the human validation"** (or name a specific file). I then:
   - encode your `decision`s into `registries/` data + a title-normalization rule,
   - re-index the **dev** lake (seconds, no model),
   - **measure each change against the 19-query golden set**, and
   - **keep only the changes that help** (a change that regresses is reported and dropped).
5. Once dev looks good, the change graduates to the prod corpus on a deliberate re-index.

Nothing here is applied automatically — these tables are *input you control*.

## Decision vocabulary

| value | meaning |
|---|---|
| `KEEP` | discriminative — leave it as a normal search term |
| `STOP` | drop from the **weighted** fields (title / doc_title) — it is noise there (the body is unaffected; BM25's IDF already handles the body) |
| `STRIP` | remove this boilerplate fragment from the **indexed doc_title** so the distinctive part of the title (the package/topic) carries the weight |
| `DEMOTE` | lower this entity type's ranking influence (don't remove it) |
| `TEST` | try this synonym **individually** and keep it only if it moves the metric (blanket expansion already failed — L1.3) |
| `?` | undecided — I'll leave it untouched until you decide |

You can also write free text (e.g. `KEEP caps-only`, `STOP`, your own note) — I'll read it.

## The files

| file | what you're deciding | columns to edit |
|---|---|---|
| `1-title-tokens.csv` | which common title words are noise in the ×2.5-weighted `doc_title` field (e.g. "guide" is in 48% of titles) | `decision` → `STOP` / `KEEP` |
| `2-title-boilerplate-fragments.csv` | which scaffolding phrases to strip from the indexed title (e.g. "…back out and rollback guide") | `decision` → `STRIP` / `KEEP` |
| `3-entity-types.csv` | which entity types to demote vs keep (globals like `^TMP` are everywhere) | `decision` → `DEMOTE` / `KEEP` |
| `4-ambiguous-terms.csv` | overloaded acronyms / homographs (order, note, SD/RA/AR) | `decision` → your call |
| `5-selective-synonyms.csv` | acronym→expansion pairs worth testing one at a time | `decision` → `TEST` / leave `?` |

## Notes

- **Source.** These tables were generated from the **prod** corpus (`~/data/vdocs`, the full
  ~462-latest-doc set) — corpus-frequency noise only shows at full scale.
- **Re-generating overwrites your edits.** If the candidate lists are ever regenerated from the
  corpus, that would overwrite the `decision` column. Tell me before regenerating so I preserve your
  decisions (or I'll regenerate into a side file).
- **Scope.** Stoplist/normalization apply to the **weighted title fields only**, never the body — so
  a word like "installation" can be noise in a title yet still a valid body search term.
- **Related human-validation artifact.** The graded relevance judgements that score every change live
  separately as `registries/golden-queries.yaml` (the eval set). That one stays canonical as YAML;
  it is not duplicated here.
