"""``vdocs serve-mcp`` — the MCP stdio front door over the gold corpus (§14, lexical slice).

Aligned with **vista-meta's MCP server** (the peer front door): the same protocol plumbing
(newline-delimited JSON-RPC 2.0 over stdio, tools-only capabilities), the same shared tools —
``orientation`` (pins + surface + citation contract), ``query`` (SELECT/WITH-only SQL over a
read-only connection, row-capped), ``lookup`` (keyed, pre-cited, with an explicit
"not in the corpus" miss) — plus each side's native strength: ``search`` (lexical FTS5, the
``vdocs ask`` engine) here, ``bridge`` (vdocs entity → measured row) on the vista-meta side.

The §14.3 semantic/hybrid surface (resources, prompts, vector modes) remains parked per the
2026-06-08 direction reset — this is the lexical/structural front door only.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from vdocs.kernel import db
from vdocs.server import ids, search

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "vdocs", "version": "1.0.0"}

MAX_ROWS_CEILING = 500
DEFAULT_MAX_ROWS = 50
# RR.1: the assistant-path result count is one shared constant in `server.search` (measured knee,
# 8 → 15), not a number this module owns — so the MCP tool and `ask --json` cannot drift apart.
DEFAULT_K = search.ASSISTANT_DEFAULT_K
MENTION_SAMPLE = 25

_SELECT_ONLY = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)

# --- "an index miss is not corpus absence" -------------------------------------------------------
# MEASURED on index.db (latest-version documents), re-measured 2026-08-02 after P6.1b: of 52,128
# live sections, 5,469 (10.5%) return NO text — down from 13,899 (26.7%), because `searchable` is
# now the retrieval predicate (any substantive token, or content relocated to a referent) instead of
# an alias for `kind`. What stays unindexed is a bare heading with nothing under it: 4,648
# containers whose whole substance is their subsections, plus 821 empty `hollow` sections.
# **The rule still holds** — it is now a smaller, sharper claim, not a weaker one: prose can still
# live in the gold `body.md` and the extracted `table-NN.csv` sidecars, and a wrong "not in the
# corpus" answer costs exactly what it always did (four researchers once retracted a report of
# "missing" FileMan APIs whose text had been present the whole time). Every client-facing surface
# below (instructions · orientation · tool descriptions · search · lookup) states it.
#
# The rule itself now lives in `server.search` (P6.3) — the module the MCP tool, `vdocs ask`, and
# `ask --json` all already import — so one re-measure moves all three surfaces or none. Re-exported
# here because the instruction/orientation strings below embed it.
NOT_INDEXED_RULE = search.NOT_INDEXED_RULE
# One-liner for the tool-description slot (some clients surface only that).
TOOL_RULE = (
    "An empty result means NOT INDEXED, not absent — ~27% of sections (container/hollow) carry no "
    "indexed text; read the gold body.md + tables/*.csv before concluding the corpus lacks it."
)

TOOLS = [
    {
        "name": "search",
        "description": (
            "Lexical FTS5 search over the gold corpus (the `vdocs ask` engine): ranked, "
            "pre-cited hits (section_id, doc/section titles, snippet, vdocs:// URI, gold "
            "body_path). Optional structured pre-filters: app (app codes), doc_type (doc codes). "
            f"ZERO HITS IS NOT ABSENCE — {TOOL_RULE}"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "k": {"type": "integer", "minimum": 1, "maximum": 50},
                "app": {"type": "array", "items": {"type": "string"}},
                "doc_type": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["query"],
        },
    },
    {
        "name": "lookup",
        "description": (
            "Keyed lookup with a ready-made citation. kind: doc (doc_key, e.g. 'CPRS/or_um') | "
            "section (section_id) | entity (entity_id '<type>:<canonical_name>'). A miss means "
            "the KEY is not in the INDEX, never that the corpus lacks the fact; a hit carries "
            f"`has_indexed_text` — when false the section's text is NOT retrievable here. "
            f"{TOOL_RULE}"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["doc", "entity", "section"]},
                "key": {"type": "string"},
            },
            "required": ["kind", "key"],
        },
    },
    {
        "name": "query",
        "description": (
            "Read-only SQL (SELECT/WITH only) over index.db: documents, doc_sections, entities, "
            "entity_mentions, relations, chunks_fts, … Call `orientation` first if unsure."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "A single SELECT/WITH statement"},
                "max_rows": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_ROWS_CEILING,
                    "description": f"Row cap (default {DEFAULT_MAX_ROWS})",
                },
            },
            "required": ["sql"],
        },
    },
    {
        "name": "orientation",
        "description": (
            "The front door: corpus provenance pins, the queryable surface, and the citation "
            "contract. Call once per session before querying."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
]


class ToolError(Exception):
    """Tool-execution failure — returned as isError content, not a JSON-RPC error."""


def _rows_to_dicts(cursor: sqlite3.Cursor, rows: list) -> list[dict[str, Any]]:
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, r)) for r in rows]


def _dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=1, ensure_ascii=False)


class Handler:
    """Route one JSON-RPC message to a response (None for notifications)."""

    def __init__(self, index_db: Path):
        self.index_db = index_db
        self.con = db.connect(index_db, read_only=True)
        self.con.row_factory = None
        self.meta = dict(self.con.execute("SELECT key, value FROM meta").fetchall())

    # -- tools ------------------------------------------------------------
    def tool_search(self, args: dict[str, Any]) -> str:
        k = args.get("k", DEFAULT_K)
        if not isinstance(k, int) or not 1 <= k <= 50:
            raise ToolError("k must be 1..50")
        hits = search.lexical_search(
            self.index_db,
            args.get("query", ""),
            k=k,
            app=args.get("app") or None,
            doc_type=args.get("doc_type") or None,
        )
        # A bare `[]` reads as "nothing exists" — the shared envelope says what zero hits actually
        # mean, in the same words `vdocs ask` uses (P6.3).
        return _dumps(search.search_envelope(hits))

    def _lookup_doc(self, key: str) -> dict[str, Any] | None:
        cur = self.con.execute("SELECT * FROM documents WHERE doc_key = ?", (key,))
        rows = _rows_to_dicts(cur, cur.fetchall())
        if not rows:
            return None
        d = rows[0]
        body = ids.gold_body_relpath(
            d.get("app_code") or "", d.get("pkg_ns") or "", d.get("doc_type") or "", key
        )
        return {"rows": rows, "citation": {"doc_key": key, "body_path": body}}

    def _has_chunks(self, section_id: str) -> bool:
        """Does this section actually have retrievable text? Answered by **probing `chunks`**, not
        by trusting `doc_sections.kind`: `kind` answers a QA question, never this one — since P6.1b
        **6,895 of the 11,543** live `container` sections carry chunks (it was 254 when `searchable`
        was a `kind` alias), and a kind-based guess would send an agent to a body file for text the
        index could have handed it. On a `chunks`-less index.db the probe answers False, so the
        client gets the read-the-body guidance rather than a crash."""
        try:
            row = self.con.execute(
                "SELECT 1 FROM chunks WHERE section_id = ? LIMIT 1", (section_id,)
            ).fetchone()
        except sqlite3.OperationalError:
            return False
        return row is not None

    def _lookup_section(self, key: str) -> dict[str, Any] | None:
        cur = self.con.execute(
            "SELECT s.*, d.title AS doc_title, d.app_code, d.pkg_ns, d.doc_type AS d_doc_type "
            "FROM doc_sections s JOIN documents d USING (doc_key) WHERE s.section_id = ?",
            (key,),
        )
        rows = _rows_to_dicts(cur, cur.fetchall())
        if not rows:
            return None
        s = rows[0]
        anchor = (
            s.get("app_code") or "", s.get("pkg_ns") or "", s.get("d_doc_type") or "",
            s.get("doc_key") or "",
        )  # fmt: skip
        body = ids.gold_body_relpath(*anchor)
        citation: dict[str, Any] = {"uri": ids.section_uri(key), "body_path": body}
        out: dict[str, Any] = {
            "rows": rows,
            "has_indexed_text": self._has_chunks(key),
            "citation": citation,
        }
        if not out["has_indexed_text"]:
            tables = ids.gold_tables_reldir(*anchor)
            citation["tables_dir"] = tables
            out["guidance"] = (
                f"This section EXISTS but has NO indexed text (kind={s.get('kind')!r}) — its "
                f"prose was never chunked, so `search`/`lookup` cannot return it. That is a "
                f"retrieval gap, NOT a documentation gap: do not report it as undocumented. "
                f"Read the gold body at {body} (find the '{s.get('title')}' heading — in a "
                f"reference manual this lead-in is the API contract: Format, Input Parameters, "
                f"flag tables) and the extracted tables in {tables}/table-NN.csv."
            )
        return out

    def _lookup_entity(self, key: str) -> dict[str, Any] | None:
        cur = self.con.execute("SELECT * FROM entities WHERE entity_id = ?", (key,))
        rows = _rows_to_dicts(cur, cur.fetchall())
        if not rows:
            return None
        docs = [
            r[0]
            for r in self.con.execute(
                "SELECT DISTINCT doc_key FROM entity_mentions WHERE entity_id = ? "
                "ORDER BY doc_key LIMIT ?",
                (key, MENTION_SAMPLE),
            )
        ]
        return {"rows": rows, "mentioned_in": docs, "citation": {"entity_id": key}}

    def tool_lookup(self, args: dict[str, Any]) -> str:
        kind, key = args.get("kind", ""), args.get("key", "")
        finder = {
            "doc": self._lookup_doc,
            "section": self._lookup_section,
            "entity": self._lookup_entity,
        }.get(kind)
        if finder is None:
            raise ToolError("kind must be one of ['doc', 'entity', 'section']")
        found = finder(key)
        if found is None:
            return (
                f"NOT FOUND IN THE INDEX: no {kind} row keyed {key!r}. This is a statement about "
                f"the KEY, not about the corpus — do NOT report it as 'not documented'. Misses "
                f"are routine: a mistyped/renamed/versioned key, or a fact whose text sits in an "
                f"unindexed container/hollow section. Before concluding absence: (1) `search` the "
                f"plain term, (2) `query` for candidates (LIKE over documents/doc_sections), "
                f"(3) read the nearest document's gold body.md and its tables/*.csv sidecars. "
                f"Only if all three come up empty may you say the corpus does not cover it."
            )
        return _dumps(found)

    def tool_query(self, args: dict[str, Any]) -> str:
        sql = args.get("sql", "")
        max_rows = args.get("max_rows", DEFAULT_MAX_ROWS)
        if not isinstance(max_rows, int) or not 1 <= max_rows <= MAX_ROWS_CEILING:
            raise ToolError(f"max_rows must be 1..{MAX_ROWS_CEILING}")
        if not _SELECT_ONLY.match(sql):
            raise ToolError(
                "only a single SELECT/WITH statement is allowed (the connection is read-only)"
            )
        try:
            cur = self.con.execute(sql)
            rows = cur.fetchmany(max_rows + 1)
        except sqlite3.Error as e:
            raise ToolError(f"sqlite: {e}") from e
        truncated = len(rows) > max_rows
        rows = rows[:max_rows]
        return _dumps(
            {
                "columns": [d[0] for d in cur.description],
                "rows": _rows_to_dicts(cur, rows),
                "row_count": len(rows),
                "truncated": truncated,
            }
        )

    def tool_orientation(self, args: dict[str, Any]) -> str:
        kinds = dict(
            self.con.execute(
                "SELECT name, type FROM sqlite_master WHERE type IN ('table','view') ORDER BY name"
            ).fetchall()
        )
        tables = sorted(n for n, t in kinds.items() if t == "table")
        return (
            "vdocs — the gold corpus of VA VistA documentation (what the docs SAY)\n\n"
            "Provenance pins (state in answers):\n"
            f"  corpus_content_hash: {self.meta.get('corpus_content_hash')}\n"
            f"  corpus_doc_count: {self.meta.get('corpus_doc_count')}\n"
            f"  read_schema_version: {self.meta.get('read_schema_version')}\n\n"
            f"Tables: {', '.join(tables)}\n\n"
            "Citation contract — cite every claim with its stable section anchor:\n"
            "  vdocs://section/<section_id>  (+ the gold body_path)\n"
            "(`search` and `lookup` return these ready-made).\n\n"
            "THREE SOURCES — the index is only the first. Nothing matching the index is NOT "
            "nothing in the corpus:\n"
            "  1. `search`/`lookup` — indexed text; covers ~89% of the 52,128 live sections.\n"
            "  2. documents/gold/consolidated/<app>/<slug>/body.md — the full document. The other "
            "5,469 sections (10.5%) are bare headings whose substance sits in their subsections, "
            "but the body.md is still the authority on layout, ordering and anything the chunker "
            "split across sections.\n"
            "  3. rich-tables/<app>/<slug>/tables/*.csv — the extracted tables (4,246 corpus-wide)."
            "\n\nAn empty result is a RETRIEVAL artefact, never proof of absence. You MUST read "
            'sources 2 and 3 before answering "not in the vdocs gold corpus" — reporting a '
            "documented API as missing is the worst failure this server has.\n\n"
            "Peer front door: the vista-meta MCP server holds what the system measurably IS "
            "(same tool conventions; its extra tool is `bridge` — vdocs entity_id → measured "
            "row). Label findings documented: (here) vs measured: (there); never reconcile "
            "silently."
        )

    # -- JSON-RPC routing ---------------------------------------------------
    def _call_tool(self, msg_id: Any, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name", "")
        tool = {
            "search": self.tool_search,
            "lookup": self.tool_lookup,
            "query": self.tool_query,
            "orientation": self.tool_orientation,
        }.get(name)
        if tool is None:
            return _error(msg_id, -32602, f"unknown tool {name!r}")
        try:
            text = tool(params.get("arguments") or {})
            is_error = False
        except ToolError as e:
            text, is_error = str(e), True
        return _result(msg_id, {"content": [{"type": "text", "text": text}], "isError": is_error})

    def handle(self, msg: dict[str, Any]) -> dict[str, Any] | None:
        method = msg.get("method", "")
        msg_id = msg.get("id")
        if method == "initialize":
            return _result(
                msg_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": SERVER_INFO,
                    "instructions": (
                        "Documented VistA facts only — call `orientation` first; cite every "
                        "claim by section anchor.\n"
                        "THREE SOURCES, in order: (1) `search`/`lookup` — indexed text, ~89% of "
                        "live sections; (2) the gold body.md at the cited `body_path` — the "
                        "remaining 10.5% are bare headings whose substance sits in their "
                        "subsections, and the body.md is still the authority on layout, ordering "
                        "and anything split across sections; (3) the `tables/*.csv` sidecars "
                        "beside it.\n"
                        "An empty search or a lookup miss is a RETRIEVAL artefact, not a "
                        "documentation gap. Read sources 2 and 3 before ever answering "
                        '"not in the vdocs gold corpus".'
                    ),
                },
            )
        if method == "ping":
            return _result(msg_id, {})
        if method == "tools/list":
            return _result(msg_id, {"tools": TOOLS})
        if method == "tools/call":
            return self._call_tool(msg_id, msg.get("params") or {})
        if "id" not in msg:
            return None  # notifications/* — nothing to say
        return _error(msg_id, -32601, f"method {method!r} not supported")


def _result(msg_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def serve_lines(handler: Handler, lines: Iterable[str]) -> Iterator[str]:
    """Transport-agnostic loop: JSON lines in → JSON lines out."""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as e:
            yield json.dumps(_error(None, -32700, f"parse error: {e}"))
            continue
        resp = handler.handle(msg)
        if resp is not None:
            yield json.dumps(resp)
