"""Unit tests for the anchor substrate — bookmark capture, link rewrite, anchor map,
round-trip back-links (§6.7, §5.5). The deferred F-step that closes the Phase-4 prerequisite."""

from __future__ import annotations

from vdocs.stages.normalize import anchors_pure as ac
from vdocs.stages.normalize import normalize_pure as nz


def test_parse_headings_captures_toc_bookmark():
    # late-gen: the _Toc bookmark span sits inline on the real `##` line
    body = '## <span id="_Toc1234" class="anchor"></span>Introduction\n\nbody\n\n## Plain Section\n'
    heads = ac.parse_headings(body)
    by_text = {h.text: h for h in heads}
    assert by_text["Introduction"].bookmark == "_Toc1234"
    assert by_text["Introduction"].slug == "introduction"
    assert by_text["Plain Section"].bookmark is None  # no bookmark → None


def test_parse_headings_captures_bookmark_on_line_above():
    # the span can sit on the line immediately above the heading (recovery seed shape)
    body = '<span id="_Ref99" class="anchor"></span>\n## Recovered\n\nbody\n'
    (head,) = ac.parse_headings(body)
    assert head.text == "Recovered" and head.bookmark == "_Ref99"


def test_bookmark_only_heading_is_skipped_everywhere():
    # a heading line that is *only* a bookmark span has no display text → not a heading anchor;
    # both parse_headings and insert_back_links drop it (no slug, no back-link)
    body = '## Real Section\n\nbody\n\n## <span id="_Toc9"></span>\n\nmore\n'
    heads = ac.parse_headings(body)
    assert [h.text for h in heads] == ["Real Section"]
    out = ac.insert_back_links(body, heads, (2, 3))
    assert out.count("[↑ Back to Contents](#contents)") == 1  # only under the real section


def test_rewrite_link_targets_maps_bookmark_to_slug():
    body = "See [Intro](#_Toc1234) for details.\n"
    out, outbound = ac.rewrite_link_targets(body, {"_Toc1234": "introduction"})
    assert "[Intro](#introduction)" in out
    assert "#_Toc1234" not in out
    assert outbound["_Toc1234"] == "introduction"


def test_rewrite_link_targets_records_unresolved():
    body = "Broken [ref](#_Toc9999) here.\n"
    out, outbound = ac.rewrite_link_targets(body, {})
    assert outbound["_Toc9999"] == "UNRESOLVED"
    assert "#_Toc9999" in out  # left untouched in the body — a fidelity signal, no crash


def test_rewrite_drops_redundant_bookmark_spans():
    body = '<span id="_Toc1" class="anchor"></span>\n## Heading\n\ntext\n'
    out, _ = ac.rewrite_link_targets(body, {"_Toc1": "heading"})
    assert "_Toc1" not in out  # the heading-anchor span is dropped (GitHub mints slug anchors)
    assert "## Heading" in out


def test_build_anchor_map_rows():
    # duplicate title "Intro" → the second gets the `-1` slug (GitHub doc-order disambiguation)
    body = "# Title\n\n## Intro\n\nx\n\n### Detail\n\ny\n\n## Intro\n\nz\n"
    heads = ac.parse_headings(body, "app/doc")
    amap = ac.build_anchor_map(heads, "app/doc", (2, 3))
    rows = {r.github_slug: r for r in amap.rows}
    assert rows["intro"].stable_section_id == "app/doc/intro"
    assert rows["intro"].toc_level is True and rows["intro"].level == 2
    assert rows["intro-1"].title == "Intro"  # GitHub duplicate disambiguation in doc order
    assert rows["detail"].toc_level is True  # H3 within [2, 3]
    assert rows["title"].toc_level is False  # H1 is the doc title, never a TOC entry


def test_insert_back_links_under_toc_headings():
    body = "# Title\n\n## Contents\n\n- [A](#a)\n\n## A\n\nx\n\n#### Deep\n\ny\n"
    heads = ac.parse_headings(body)
    out = ac.insert_back_links(body, heads, (2, 3))
    a_idx = out.index("## A")
    deep_idx = out.index("#### Deep")
    assert "[↑ Back to Contents](#contents)" in out[a_idx:deep_idx]  # H2 gets a back-link
    assert "[↑ Back to Contents](#contents)" not in out[deep_idx:]  # H4 (out of depth) does not


def test_back_links_idempotent():
    body = "# T\n\n## A\n\nx\n"
    heads = ac.parse_headings(body)
    once = ac.insert_back_links(body, heads, (2, 3))
    twice = ac.insert_back_links(once, ac.parse_headings(once), (2, 3))
    assert twice == once
    assert once.count("[↑ Back to Contents](#contents)") == 1


def test_insert_back_links_ignores_headings_inside_code_fences():
    # a `#` line inside a fenced block is not a heading → no spurious back-link there
    body = "# T\n\n## A\n\n```\n# not a heading\n```\n\ndone\n"
    heads = ac.parse_headings(body)
    out = ac.insert_back_links(body, heads, (2, 3))
    assert out.count("[↑ Back to Contents](#contents)") == 1  # only under the real H2
    assert "# not a heading" in out  # fenced content untouched


def test_normalize_body_roundtrip_idempotent():
    body = "# Guide\n\n## Setup\n\nsteps\n\n### Details\n\nmore\n\n## Usage\n\nrun it\n"
    once_body, once_map = nz.normalize_body(body, frozenset(), doc_id="app/guide")
    twice_body, twice_map = nz.normalize_body(once_body, frozenset(), doc_id="app/guide")
    assert twice_body == once_body  # body is a fixpoint
    assert twice_map == once_map  # the anchor map is stable too


def test_anchor_map_every_toc_entry_resolves():
    # §6.7 hard-gate invariant at unit level: no TOC entry points at an absent anchor
    body = "# Guide\n\n## Alpha\n\nx\n\n### Beta\n\ny\n\n## Gamma\n\nz\n"
    out_body, amap = nz.normalize_body(body, frozenset(), doc_id="app/g")
    slugs = {r.github_slug for r in amap.rows}
    toc_targets = [
        ln.split("](#", 1)[1].rstrip(")")
        for ln in out_body.splitlines()
        if ln.lstrip().startswith("- [") and "](#" in ln
    ]
    assert toc_targets  # the TOC was actually generated
    assert all(t in slugs for t in toc_targets)  # zero dead anchors
