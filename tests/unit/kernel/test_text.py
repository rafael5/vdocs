"""Unit tests for kernel.text — the single mojibake/scrub/strip primitive (§9.2)."""

from vdocs.kernel import text


def test_slugify_keeps_github_rule_and_honors_sep_and_fallback():
    # the single slug primitive: drop punctuation, keep word chars/hyphens, spaces→sep
    assert text.slugify("Getting Started") == "getting-started"
    assert text.slugify("Sign On", sep="_") == "sign_on"
    assert text.slugify("", fallback="section") == "section"
    assert text.slugify("&&&", fallback="x") == "x"  # all-punctuation → empty → fallback


def test_github_slug_base_is_slugify_with_hyphen():
    # github_slug_base is just slugify(sep='-'); behavior pinned (GitHub-accurate) is unchanged
    assert text.github_slug_base("FileMan & the Data_Dictionary (v22.2)") == text.slugify(
        "FileMan & the Data_Dictionary (v22.2)"
    )


def test_github_slug_base_lowercases_and_hyphenates():
    assert text.github_slug_base("Getting Started") == "getting-started"


def test_github_slug_base_drops_punctuation_keeps_hyphens_and_word_chars():
    # GitHub anchor rule: drop punctuation, keep word chars/hyphens, spaces→hyphens.
    got = text.github_slug_base("FileMan & the Data_Dictionary (v22.2)")
    assert got == "fileman--the-data_dictionary-v222"


def test_github_slug_base_is_dedup_free():
    # The base is identity-only; the -1/-2 disambiguation lives in anchors_pure (layered on top).
    assert text.github_slug_base("Options") == text.github_slug_base("Options")


def test_github_slug_base_anchors_pure_layers_dedup_on_it():
    # anchors_pure.github_slug must produce the base for the first occurrence, then -1, -2 …
    from vdocs.stages.normalize import anchors_pure

    seen: dict[str, int] = {}
    assert anchors_pure.github_slug("Options", seen) == text.github_slug_base("Options")
    assert anchors_pure.github_slug("Options", seen) == "options-1"


def test_repair_mojibake_smart_quotes():
    # utf-8 smart quotes mis-decoded through cp1252 (the classic mojibake); ftfy recovers them,
    # then normalises the curly quotes to straight ASCII (uncurl_quotes, its default) — the
    # canonical corpus behavior the catalog already relies on (§9.2).
    assert text.repair_mojibake("the â€œquotedâ€\x9d word") == 'the "quoted" word'


def test_repair_mojibake_apostrophe_and_em_dash():
    assert text.repair_mojibake("donâ€™t") == "don't"
    assert text.repair_mojibake("itâ€™s a testâ€”really") == "it's a test—really"


def test_repair_mojibake_latin1_accents():
    assert text.repair_mojibake("cafÃ©") == "café"
    assert text.repair_mojibake("naÃ¯ve") == "naïve"


def test_repair_mojibake_leaves_clean_text_untouched():
    clean = "A normal sentence with an em—dash and no mojibake."
    assert text.repair_mojibake(clean) == clean


def test_repair_mojibake_is_the_shared_catalog_fixer():
    # §9.2: exactly ONE mojibake fixer. catalog.fix_mojibake delegates to the kernel, so the
    # two must agree byte-for-byte across mojibake, clean text, and the empty string.
    from vdocs.stages.catalog import enrich_pure as ep

    for s in ["cafÃ©", "donâ€™t", "the â€œquotedâ€\x9d word", "plain text", ""]:
        assert text.repair_mojibake(s) == ep.fix_mojibake(s)


def test_scrub_control_chars_removes_c0_but_keeps_whitespace():
    raw = "line1\nline2\tcol\x00\x07\x1b end\r\n"
    out = text.scrub_control_chars(raw)
    assert "\x00" not in out and "\x07" not in out and "\x1b" not in out
    # newlines and tabs are legitimate whitespace and survive
    assert "\n" in out and "\t" in out


def test_strip_html_removes_tags_keeps_text():
    html = "<p>Hello <b>world</b> &amp; <a href='x'>link</a></p>"
    assert text.strip_html(html) == "Hello world & link"


def test_safe_component_sanitises_slashes_and_plus():
    # case-preserving bundle-path slug: only path-unsafe runs collapse to '_' (slashes, '+', spaces)
    assert text.safe_component("AR/WS") == "AR_WS"
    assert text.safe_component("DRM+") == "DRM"  # trailing '_' trimmed
    assert text.safe_component("ADT") == "ADT"
    assert text.safe_component("///") == "_"


def test_clean_composes_all_three():
    broken = "<p>itâ€™s\x00 fine</p>"
    assert text.clean(broken) == "it's fine"


def test_clean_is_idempotent():
    broken = "<p>the â€œwordâ€\x9d\x07</p>"
    once = text.clean(broken)
    assert text.clean(once) == once


def test_block_key_collapses_whitespace_and_lowercases():
    assert text.block_key("  Hello   World  ") == "hello world"
    # newlines collapse too (a block may span lines)
    assert text.block_key("Line one\n  Line two") == "line one line two"
    # spacing/case-only differences map to the same key
    assert text.block_key("The  NOTICE.") == text.block_key("the notice.")


def test_decade_bucket_finds_first_month_year():
    assert text.decade_bucket("Cover\n\nJanuary 1998\n") == "1990s"
    assert text.decade_bucket("September 2020") == "2020s"
    assert text.decade_bucket("no date here") == "unknown"


def test_decade_bucket_respects_line_window():
    body = "title\n" + "x\n" * 50 + "June 1995\n"  # date past the window
    assert text.decade_bucket(body, max_lines=40) == "unknown"
    assert text.decade_bucket(body) == "1990s"  # no window → found
