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
        CREATE TABLE chunks (
          chunk_id TEXT PRIMARY KEY, section_id TEXT, doc_key TEXT, part INTEGER, text TEXT
        );
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
    conn.executemany(
        "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?)",
        [("DI/fm22_2dg", "DI:fm22_2dg", "FileMan Developer's Guide", "DI", "DG", "DI", 1)],
    )
    conn.executemany(
        "INSERT INTO doc_sections VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("CPRS/or_um/auth", "CPRS/or_um", "auth", "Authentication",
             2, 2, 1, "section", 1, "OR", 1),
            # a real container section: its lead-in prose (the API contract) is NOT chunked,
            # so lookup/search return nothing for it — the false-"not documented" trap.
            ("DI/fm22_2dg/updatedie-updater", "DI/fm22_2dg", "updatedie-updater",
             "UPDATE^DIE(): Updater", 2, 2, 1, "container", 0, "DI", 2),
        ],
    )  # fmt: skip
    conn.execute(
        "INSERT INTO chunks VALUES (?, ?, ?, ?, ?)",
        ("CPRS/or_um/auth", "CPRS/or_um/auth", "CPRS/or_um", 0, "KAAJEE handles authentication."),
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
    assert "NOPE/nope" in _text(miss)
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


# -- the "index miss ≠ corpus absence" contract ------------------------------
# Four researchers once concluded documented FileMan APIs were "missing from the corpus"
# when the text was present the whole time: 26.7% of live sections (container/hollow) carry
# NO indexed text, so search/lookup return empty for prose that exists in the gold body.
# These tests are the regression gate — every client-facing surface must name the fallbacks.

_FALLBACK_TOKENS = ("body.md", "tables")


def test_initialize_instructions_teach_the_three_source_protocol(tmp_path):
    init = _handler(tmp_path).handle(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05"}}
    )  # fmt: skip
    text = init["result"]["instructions"]
    assert all(tok in text for tok in _FALLBACK_TOKENS), text
    # It must EXPLAIN the unindexed residual, not merely assert one. This used to check for the
    # words "container"/"hollow"; since P6.1b `kind` is explicitly *not* the retrieval predicate
    # (`is_searchable` is), so naming kinds here would teach a client something false — the residual
    # is bare headings whose substance sits in their subsections, whatever their kind.
    assert "subsections" in text
    # the empty result must be framed as a retrieval artefact, never as corpus absence
    assert "retrieval" in text.lower()
    # the exact clause that caused the incident must not be reinstated
    assert 'answer "not in the vdocs gold corpus" when nothing matches' not in text


def test_orientation_replaces_say_so_and_stop_with_the_fallback_rule(tmp_path):
    text = _text(_call(_handler(tmp_path), "orientation", {}))
    assert all(tok in text for tok in _FALLBACK_TOKENS), text
    assert "subsections" in text  # explains the residual (see the initialize test — not by `kind`)
    # regression gate: the "stop" directive is what told agents not to check the fallbacks
    assert "say so and stop" not in text
    assert "and stop" not in text


def test_no_client_surface_quotes_a_retired_coverage_constant(tmp_path):
    """The chunk-less rule is quoted on five surfaces that must move together (P6.2). A stale one
    is worse than none: it tells an agent to go read a body file for text `search` would now hand
    it. This pins the retired numbers so a re-measure cannot land on four of the five."""
    from vdocs.stages.manifest import manifest_pure

    handler = _handler(tmp_path)
    surfaces = [
        mcp.NOT_INDEXED_RULE,
        manifest_pure.USAGE,
        _text(_call(handler, "orientation", {})),
        handler.handle(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2024-11-05"}}
        )["result"]["instructions"],
    ]  # fmt: skip
    retired = ("26.7%", "~73%", "13,899", "52,048", "11,526")
    for text in surfaces:
        for stale in retired:
            assert stale not in text, f"retired constant {stale!r} still quoted: {text[:120]}"


def test_lookup_container_section_reports_no_indexed_text_with_guidance(tmp_path):
    out = json.loads(
        _text(_call(_handler(tmp_path), "lookup",
                    {"kind": "section", "key": "DI/fm22_2dg/updatedie-updater"}))
    )  # fmt: skip
    assert out["has_indexed_text"] is False
    body = out["citation"]["body_path"]
    tables = out["citation"]["tables_dir"]
    # the two sidecars must point at the SAME gold bundle
    assert tables == body.replace("documents/gold/consolidated/", "rich-tables/").replace(
        "/body.md", "/tables"
    )
    guidance = out["guidance"]
    assert body in guidance and tables in guidance
    assert "not" in guidance.lower() and "gap" in guidance.lower()


def test_lookup_normal_section_is_unchanged_and_flagged_indexed(tmp_path):
    out = json.loads(
        _text(_call(_handler(tmp_path), "lookup", {"kind": "section", "key": "CPRS/or_um/auth"}))
    )
    assert out["has_indexed_text"] is True
    assert "guidance" not in out
    assert out["citation"] == {
        "uri": "vdocs://section/CPRS/or_um/auth",
        "body_path": out["citation"]["body_path"],
    }
    assert out["rows"][0]["title"] == "Authentication"


def test_lookup_miss_does_not_claim_corpus_absence(tmp_path):
    text = _text(_call(_handler(tmp_path), "lookup", {"kind": "section", "key": "DI/nope/nope"}))
    # the miss is about the INDEX, not the corpus
    assert "index" in text.lower()
    assert "not in the vdocs gold corpus" not in text
    assert "report this as the answer" not in text
    assert all(tok in text for tok in _FALLBACK_TOKENS), text


def test_zero_hit_search_carries_the_warning_not_a_bare_empty_list(tmp_path):
    h = _handler(tmp_path)
    out = json.loads(_text(_call(h, "search", {"query": "zzzznomatchzzzz"})))
    assert out["hits"] == [] and out["hit_count"] == 0
    warning = out["warning"]
    assert all(tok in warning for tok in _FALLBACK_TOKENS), warning
    assert "subsections" in warning  # explains the residual without naming `kind` (see P6.1b)
    # a hit-bearing search must NOT carry the warning (it would train clients to ignore it)
    hit = json.loads(_text(_call(h, "search", {"query": "KAAJEE"})))
    assert hit["hits"] and "warning" not in hit


def test_chunkless_index_degrades_to_guidance_not_a_crash(tmp_path):
    """The emptiness probe reads `chunks`. On an index.db without it, answer "not indexed" —
    the client then gets the read-the-body guidance instead of a server-killing exception."""
    h = _handler(tmp_path)
    h.con.close()
    index_db = tmp_path / "index.db"
    conn = db.connect(index_db)
    conn.execute("DROP TABLE chunks")
    conn.commit()
    conn.close()
    out = json.loads(
        _text(_call(mcp.Handler(index_db), "lookup",
                    {"kind": "section", "key": "CPRS/or_um/auth"}))
    )  # fmt: skip
    assert out["has_indexed_text"] is False
    assert out["citation"]["body_path"] in out["guidance"]
    assert out["citation"]["tables_dir"].startswith("rich-tables/")


def test_tool_descriptions_carry_the_one_line_rule(tmp_path):
    tools = {t["name"]: t["description"] for t in mcp.TOOLS}
    for name in ("search", "lookup"):
        desc = tools[name]
        assert "body.md" in desc, f"{name}: {desc}"
        assert "absen" in desc.lower() or "gap" in desc.lower(), f"{name}: {desc}"


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
