"""RR.1 — the two default result counts: wide for assistants, tight for a human reader.

Measured on the production collection with the post-RC key (109 judged answers): the share an
assistant sees rises **61.5% @8 → 77.1% @15**, and flattens after that (78.0% @20, 79.8% @25).
So 15 is the knee, and 8 was costing an assistant roughly one correct answer in six.

A person reading a terminal is the opposite case — a longer list is reading work, not free recall —
so the human `vdocs ask` display stays at 8. These tests pin both numbers and the rule that an
explicit `k` always wins, because a silently drifting default is exactly what made the old value
un-auditable.
"""

from __future__ import annotations

from vdocs.server import mcp, search


def test_assistant_default_is_the_measured_knee_not_the_old_eight() -> None:
    # 15 is not a taste: at k=8 an assistant saw 61.5% of judged answers, at 15 it sees 77.1%,
    # and 20 buys only +0.9pt more. Change this only with a fresh measurement in the tracker.
    assert search.ASSISTANT_DEFAULT_K == 15
    assert search.ASSISTANT_DEFAULT_K > search.HUMAN_DISPLAY_K


def test_human_display_default_stays_tight() -> None:
    # More results are not free for a person: the terminal list is reading work.
    assert search.HUMAN_DISPLAY_K == 8


def test_mcp_default_k_is_the_shared_assistant_constant() -> None:
    # One constant, both assistant surfaces (MCP `search` and `ask --json`) — the same discipline
    # NOT_INDEXED_RULE follows, so a re-measure cannot move one surface and leave the other stale.
    assert mcp.DEFAULT_K is search.ASSISTANT_DEFAULT_K


def test_mcp_search_schema_admits_the_new_default() -> None:
    schema = next(t for t in mcp.TOOLS if t["name"] == "search")["inputSchema"]["properties"]["k"]
    assert schema["minimum"] <= search.ASSISTANT_DEFAULT_K <= schema["maximum"]
