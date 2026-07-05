"""Integration: the ``serve-mcp`` front door — MCP stdio tools over a tiny real index.db.

The tool surface is ALIGNED with vista-meta's MCP server (the peer front door):
same protocol plumbing (newline-delimited JSON-RPC 2.0, tools-only capabilities),
same shared tools (``orientation`` / ``query`` / ``lookup``) with the same
conventions (read-only SQL, row caps, pre-cited answers, an explicit
"not in the corpus" miss), plus each side's native strength — ``search``
(lexical FTS5) here, ``bridge`` on the vista-meta side.
"""

from __future__ import annotations

import json

from vdocs.kernel import db
from vdocs.server import mcp


def _build(index_db):
    conn = db.connect(index_db)
    conn.executescript(
        """
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE documents (
          doc_key TEXT PRIMARY KEY, doc_id TEXT, title TEXT, app_code TEXT, doc_type TEXT,
          pkg_ns TEXT, is_latest INTEGER
        );
        CREATE TABLE doc_sections (
          section_id TEXT PRIMARY KEY, doc_key TEXT, slug TEXT, title TEXT, level INTEGER,
          toc_level INTEGER, is_latest INTEGER, kind TEXT, searchable INTEGER,
          section_path TEXT, seq INTEGER
        );
        CREATE TABLE entities (
          entity_id TEXT PRIMARY KEY, type TEXT, canonical_name TEXT, mention_count INTEGER
        );
        CREATE TABLE entity_mentions (entity_id TEXT, doc_key TEXT, section_id TEXT);
        CREATE VIRTUAL TABLE chunks_fts USING fts5(
          chunk_id UNINDEXED, section_id UNINDEXED, doc_key UNINDEXED, title, doc_title,
          section_path, body
        );
        """
    )
    conn.executemany(
        "INSERT INTO meta VALUES (?, ?)",
        [
            ("corpus_content_hash", "c" * 64),
            ("corpus_doc_count", "2"),
            ("read_schema_version", "1.5"),
        ],
    )
    conn.executemany(
        "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("CPRS/or_um", "CPRS:or_um", "OR User Manual", "CPRS", "UM", "OR", 1),
            ("KAAJEE/dibr", "KAAJEE:dibr", "KAAJEE DIBR", "KAAJEE", "", "", 1),
        ],
    )
    conn.execute(
        "INSERT INTO doc_sections VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("CPRS/or_um/auth", "CPRS/or_um", "auth", "Authentication", 2, 2, 1, "section", 1, "OR", 1),
    )
    conn.execute(
        "INSERT INTO entities VALUES (?, ?, ?, ?)",
        ("rpc:ORWPT SELECT", "rpc", "ORWPT SELECT", 2),
    )
    conn.execute(
        "INSERT INTO entity_mentions VALUES (?, ?, ?)",
        ("rpc:ORWPT SELECT", "CPRS/or_um", "CPRS/or_um/auth"),
    )
    conn.execute(
        "INSERT INTO chunks_fts "
        "(chunk_id, section_id, doc_key, title, doc_title, section_path, body) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("CPRS/or_um/auth", "CPRS/or_um/auth", "CPRS/or_um", "Authentication", "OR User Manual",
         "OR", "KAAJEE handles user authentication and single sign-on tokens."),
    )  # fmt: skip
    conn.commit()
    conn.close()


def _handler(tmp_path):
    index_db = tmp_path / "index.db"
    _build(index_db)
    return mcp.Handler(index_db)


def _call(handler, name, args, id=1):
    return handler.handle(
        {"jsonrpc": "2.0", "id": id, "method": "tools/call",
         "params": {"name": name, "arguments": args}}
    )  # fmt: skip


def _text(resp):
    return resp["result"]["content"][0]["text"]


def test_initialize_and_tools_list_align_with_the_peer_front_door(tmp_path):
    h = _handler(tmp_path)
    init = h.handle(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05"}}
    )  # fmt: skip
    r = init["result"]
    assert r["protocolVersion"] == mcp.PROTOCOL_VERSION
    assert r["serverInfo"]["name"] == "vdocs"
    assert "tools" in r["capabilities"]
    tools = {
        t["name"]
        for t in h.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
    }
    # the aligned surface: shared trio + this side's native strength
    assert tools == {"orientation", "query", "lookup", "search"}
    assert h.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert h.handle({"jsonrpc": "2.0", "id": 3, "method": "ping"})["result"] == {}
    err = h.handle({"jsonrpc": "2.0", "id": 4, "method": "resources/list"})
    assert err["error"]["code"] == -32601


def test_search_returns_pre_cited_hits(tmp_path):
    h = _handler(tmp_path)
    out = json.loads(_text(_call(h, "search", {"query": "KAAJEE authentication", "k": 5})))
    assert out["hits"], "expected hits"
    top = out["hits"][0]
    assert top["uri"] == f"vdocs://section/{top['section_id']}"
    assert top["body_path"].startswith("documents/gold/consolidated/")


def test_search_empty_query_reports_no_hits(tmp_path):
    out = json.loads(_text(_call(_handler(tmp_path), "search", {"query": "!!"})))
    assert out["hits"] == []


def test_lookup_doc_section_entity(tmp_path):
    h = _handler(tmp_path)
    doc = json.loads(_text(_call(h, "lookup", {"kind": "doc", "key": "CPRS/or_um"})))
    assert doc["rows"][0]["title"] == "OR User Manual"
    assert doc["citation"]["body_path"].startswith("documents/gold/consolidated/")
    sec = json.loads(_text(_call(h, "lookup", {"kind": "section", "key": "CPRS/or_um/auth"})))
    assert sec["citation"]["uri"] == "vdocs://section/CPRS/or_um/auth"
    ent = json.loads(_text(_call(h, "lookup", {"kind": "entity", "key": "rpc:ORWPT SELECT"})))
    assert ent["rows"][0]["canonical_name"] == "ORWPT SELECT"
    assert ent["mentioned_in"] == ["CPRS/or_um"]


def test_lookup_miss_and_bad_kind(tmp_path):
    h = _handler(tmp_path)
    miss = _call(h, "lookup", {"kind": "doc", "key": "NOPE/nope"})
    assert not miss["result"]["isError"]
    assert "not in the vdocs gold corpus" in _text(miss)
    bad = _call(h, "lookup", {"kind": "widget", "key": "x"})
    assert bad["result"]["isError"]


def test_query_readonly_and_capped(tmp_path):
    h = _handler(tmp_path)
    ok = json.loads(
        _text(_call(h, "query", {"sql": "SELECT doc_key FROM documents", "max_rows": 1}))
    )
    assert ok["row_count"] == 1 and ok["truncated"] is True
    bad = _call(h, "query", {"sql": "DELETE FROM documents"})
    assert bad["result"]["isError"]
    assert _call(h, "query", {"sql": "SELECT 1", "max_rows": 0})["result"]["isError"]
    sneaky = _call(h, "query", {"sql": "WITH x AS (SELECT 1) INSERT INTO documents SELECT 1"})
    assert sneaky["result"]["isError"]


def test_orientation_carries_pin_contract_and_peer_pointer(tmp_path):
    text = _text(_call(_handler(tmp_path), "orientation", {}))
    assert "c" * 64 in text  # corpus_content_hash pin
    assert "vdocs://section/" in text  # citation contract
    assert "not in the vdocs gold corpus" in text  # the miss answer
    assert "vista-meta" in text  # cross-pointer to the peer front door


def test_serve_lines_survives_malformed_input(tmp_path):
    h = _handler(tmp_path)
    lines = [
        "garbage",
        json.dumps({"jsonrpc": "2.0", "id": 7, "method": "tools/list"}),
    ]
    replies = [json.loads(o) for o in mcp.serve_lines(h, iter(lines))]
    assert replies[0]["error"]["code"] == -32700
    assert replies[1]["id"] == 7


def test_unknown_tool_is_invalid_params(tmp_path):
    resp = _call(_handler(tmp_path), "nope", {})
    assert resp["error"]["code"] == -32602


def test_cli_serve_mcp_speaks_the_protocol(tmp_path):
    from typer.testing import CliRunner

    from vdocs.cli.app import app

    _build(tmp_path / "index.db")
    lines = (
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05"}})
        + "\n"
        + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                      "params": {"name": "lookup",
                                 "arguments": {"kind": "doc", "key": "CPRS/or_um"}}})
        + "\n"
    )  # fmt: skip
    result = CliRunner().invoke(app, ["serve-mcp"], input=lines, env={"DATA_DIR": str(tmp_path)})
    assert result.exit_code == 0, result.output
    replies = [json.loads(ln) for ln in result.output.strip().splitlines()]
    assert replies[0]["result"]["serverInfo"]["name"] == "vdocs"
    assert "OR User Manual" in replies[1]["result"]["content"][0]["text"]


def test_cli_serve_mcp_without_index_db_exits_cleanly(tmp_path):
    from typer.testing import CliRunner

    from vdocs.cli.app import app

    result = CliRunner().invoke(app, ["serve-mcp"], input="", env={"DATA_DIR": str(tmp_path)})
    assert result.exit_code == 1
    assert "no index.db" in result.output
