"""The read-only serving layer over the gold derived stores (§14).

`ids` (stable-ID / URI / gold-path resolution, shared with the stages), `search_pure` + `search`
(the lexical retrieval engine — FTS5 over the is_latest search chunks, surfaced as `vdocs ask`),
and `facets` (the faceted-discovery surface). Lexical-first and offline; no semantic/vector path.
"""
