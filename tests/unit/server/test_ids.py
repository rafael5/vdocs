"""Unit tests for server.ids — the shared stable-ID / URI / gold-path resolution (§11, §14.5).

These are the resolvers both `manifest` (the AI card) and `search` (the `ask` query path) use, so a
citation's `body_path` and `section_id` are derived in exactly one place (§9.2 — no copy-paste).
"""

from __future__ import annotations

from vdocs.server import ids


def test_gold_body_relpath_grouped_doc_uses_version_free_anchor():
    # a versioned doc anchors on <app>/<pkg_ns>_<doc_type> (lowercased), invariant across patches
    rel = ids.gold_body_relpath("CPRS", "OR", "UM", "CPRS/or_um")
    assert rel == "documents/gold/consolidated/CPRS/or_um/body.md"


def test_gold_body_relpath_standalone_doc_uses_doc_slug_tail():
    # a standalone doc (no doc_type ⇒ no version group) anchors on its own doc_key slug tail
    rel = ids.gold_body_relpath("KAAJEE", "", "", "KAAJEE/dibr")
    assert rel == "documents/gold/consolidated/KAAJEE/dibr/body.md"


def test_section_uri_is_the_mcp_resource_form():
    assert (
        ids.section_uri("CPRS/or_um/authentication") == "vdocs://section/CPRS/or_um/authentication"
    )
