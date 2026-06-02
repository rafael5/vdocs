"""Unit tests for kernel.frontmatter — the *only* YAML frontmatter codec (§9.2)."""

from vdocs.kernel import frontmatter as fm


def test_parse_extracts_mapping_and_body():
    doc = "---\ntitle: Hello\napp_code: LR\n---\n\n# Body\n\ntext here\n"
    meta, body = fm.parse(doc)
    assert meta == {"title": "Hello", "app_code": "LR"}
    assert body == "# Body\n\ntext here\n"


def test_parse_no_frontmatter_returns_empty_and_original():
    doc = "# Just a body\n\nno frontmatter\n"
    meta, body = fm.parse(doc)
    assert meta == {}
    assert body == doc


def test_parse_unterminated_frontmatter_is_treated_as_body():
    doc = "---\ntitle: oops\nno closing delimiter\n"
    meta, body = fm.parse(doc)
    assert meta == {}
    assert body == doc


def test_emit_orders_identity_keys_first():
    meta = {"app_code": "LR", "title": "T", "word_count": 5, "version": "1.0"}
    out = fm.emit(meta, "body\n")
    # title precedes app_code precedes version; computed/unknown keys go last
    keys_in_order = [
        line.split(":")[0]
        for line in out.splitlines()
        if line and not line.startswith("-") and ":" in line
    ]
    assert keys_in_order.index("title") < keys_in_order.index("app_code")
    assert keys_in_order.index("app_code") < keys_in_order.index("version")
    assert keys_in_order.index("version") < keys_in_order.index("word_count")


def test_round_trip_preserves_meta_and_body():
    meta = {"title": "Résumé “quoted”", "app_code": "PSO", "version": "2.1"}
    body = "# Heading\n\nSome prose with a — dash.\n"
    again_meta, again_body = fm.parse(fm.emit(meta, body))
    assert again_meta == meta
    assert again_body == body


def test_parse_non_mapping_frontmatter_is_treated_as_body():
    doc = "---\n- a\n- b\n---\n\nbody\n"  # a YAML list, not a mapping
    meta, body = fm.parse(doc)
    assert meta == {}
    assert body == doc


def test_parse_malformed_frontmatter_isolates_as_no_frontmatter():
    # R8: a bad-YAML frontmatter block must not crash the run (isolate the one bad doc) — it is
    # treated as having no frontmatter, the whole document left intact as the body
    doc = '---\ntitle: "unterminated\n  bad: [unclosed\n---\n\nBody text.\n'
    meta, body = fm.parse(doc)
    assert meta == {}
    assert body == doc  # nothing lost


def test_emit_starts_and_ends_frontmatter_block():
    out = fm.emit({"title": "X"}, "b")
    assert out.startswith("---\n")
    assert "\n---\n" in out
