# registries/entities

The curated **VistA-domain entity vocabulary** — the data that drives `index`'s generic entity
extraction (§8 note, §9.6/§9.7, D2). Disposition = **EXTRACT**: `index`'s `entities_pure` pass
recognizes these over the normalized bodies and writes `index.db:entities` keyed by the
`(type, canonical-name)` stable id (§5.5). **No entity patterns are hard-coded in stage code** —
recognition is a pure function of `(body, this registry)` (tenet #13).

Seeded from domain knowledge as a high-confidence starter set; augmentable by `discover`'s
corpus-frequency candidates (the same induction→curation→consumption loop as the other registries,
§9.6). `relate` (the knowledge graph) only adds *edges* over the entities `index` extracts — it does
no extraction.

## Schema (`entities.yaml`)

A list of `entities:` entries, each a recognizer for one entity `type`. An entry recognizes by
**one** of two modes (generic, so the registry — not the code — owns what an entity is):

- `pattern: <regex>` — a regular expression; each match is an occurrence. `canonical: whole`
  (default) uses the full match as the canonical name; `canonical: group1` uses capture group 1.
  `casefold: true` uppercases the canonical name (so `^dpt`/`^DPT` are one entity).
- `terms: [<str>, …]` — a literal vocabulary; each term is matched as a whole word. `canonical`
  is the listed term. `case_sensitive: true` matches the term exactly (used for uppercase
  namespaces, where a lowercase English homograph like "or" must not match).

Common fields: `type` (the entity type — e.g. `build`, `global`, `fileman_file`,
`package_namespace`, `routine`, `rpc`, `option`, `protocol`, `hl7_segment`, `mail_group`),
`status` (`approved` = past the §9.6 curation gate), `note`.

## Entity types

| type | what | example canonical |
|---|---|---|
| `build` | KIDS build / patch id | `OR*3.0*539` |
| `global` | M global reference | `^DPT` |
| `fileman_file` | FileMan file (by number, in "file #N" context) | `#2` |
| `package_namespace` | VistA package namespace | `DG` |

Start narrow and high-precision; widen as `discover` proposes well-supported candidates.
