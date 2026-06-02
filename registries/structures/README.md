# registries/structures

Recurring structural conventions — callout/admonition styling, revision-table shape,
TOC shape. Key = convention id. Disposition = **CANONICALIZE** to standard GFM
(§9.6/§9.7).

Populated by curating `discover`'s structural-convention candidates. Each entry's `match`
list is the case-insensitive token (callouts) or heading text (`toc`/`revision-table`) the
`normalize` CANONICALIZE step keys on; `canonical_form` is the GFM target.

Consumed by `normalize`: the `toc` convention drives `strip_legacy_toc` (remove the source's
in-body table of contents before the derived `## Contents` is generated, §6.7). The `callout`
and `revision-table` conventions are curated but not yet applied (follow-up).
