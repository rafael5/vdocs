# registries/templates

The document skeleton each manual was poured into, discovered per `(doc_type, era)`,
**plus its computable structural schema** (expected sections / markers / roles — §9.8).
Key = `(doc_type, era)`. Disposition = **STRIP** scaffold from body + stamp `template_id`
+ **RETAIN** schema (§9.6/§9.7/§9.8, ADR-018/019).

Populated by curating `discover`'s `(doc_type, era)` template candidates (`mine_templates`
over the converted corpus).

## Section schema (`sections[]`)

Each retained section is a **computable** `TemplateSection` (§9.8), not just a strippable title:

| field | meaning |
|---|---|
| `section_id` | GitHub-anchor slug of the consensus title — the stable identity (joins to `index`) |
| `title` | the consensus (most common) heading spelling |
| `title_pattern` | a regex matching the section's title across docs, **numbering-tolerant** (`Introduction` / `1. Introduction` / `2.1 Introduction` align); the validation-oracle matcher |
| `level` | the modal heading level |
| `required` | section covers ≥ 50 % of the cluster (see policy below) |
| `repeatable` | section legitimately recurs within a document (e.g. per-patch subsections) |
| `semantic_role` | orientation / installation / back-out / glossary / … (null when not inferable) |
| `toc_level` | whether the section belongs in the regenerated TOC (§6.7) |

## The `required` policy (a coverage ratio, not "every member")

A section is **retained** when it covers ≥ **25 %** of the cluster's members (absolute floor 2 docs)
and marked **`required`** when it covers ≥ **50 %**; `[25 %, 50 %)` is the **optional** tier. "Present
in every member" was rejected: the spike found genuine DIBR sections at **60–94 %** coverage (real
manuals omit inapplicable sections), which "every member" would mislabel as optional. The ratios are
the `_ADMIT_RATIO` / `_REQUIRED_RATIO` constants in `discover_pure`. See `docs/vdocs-design.md` §9.8.
