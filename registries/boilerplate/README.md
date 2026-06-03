# registries/boilerplate

Meaningful-but-duplicated blocks (legal notices, "how to use this manual", standard
headers/footers). Key = block identity (shingle hash). Disposition = **REFERENCE**:
`normalize` replaces the block with a link to one canonical copy under
`gold/_shared/boilerplate/<id>.md` (§9.6/§9.7).

Populated by curating `discover`'s near-duplicate boilerplate candidates
(`reports/patterns`) into approved YAML here.

## Entry shape

`{id, label, key, text, evidence_docs, status}` plus an optional **`doc_types`** tag. The
corpus-global head (no `doc_types`) is the cross-corpus boilerplate; entries carrying `doc_types`
were mined per-`doc_type` (Task 5: `DIBR`/`IG`/`TM`/`DG`). `key` is the `kernel.block_key` match
identity; `text` is the canonical copy destined for `gold/_shared/boilerplate/<id>.md`.

Boilerplate pays off across far more of the corpus than templates do — it does **not** require a
doc_type to have a coherent skeleton — so the per-type heads are promoted even for the
heterogeneous types whose *templates* are deferred (see `registries/templates/README.md` and
`reports/discover-validation.md`).
