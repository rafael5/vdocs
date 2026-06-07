"""The read-only serving layer over the gold derived stores (§14).

`ids` (stable-ID / URI / gold-path resolution, shared with the stages), `search_pure` + `search`
(the hybrid-retrieval engine — its lexical slice is live now and surfaced as `vdocs ask`; semantic
fusion arrives with `embed`/`vectors.db` in Phase 6). The MCP server (`mcp.py`) wraps these.
"""
