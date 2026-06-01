"""Unit tests for kernel.text — the single mojibake/scrub/strip primitive (§9.2)."""

from vdocs.kernel import text


def test_repair_mojibake_smart_quotes():
    # cp1252 smart quotes mis-decoded as latin-1/utf-8 (the classic mojibake)
    broken = "the â€œquotedâ€ word"
    assert text.repair_mojibake(broken) == "the “quoted” word"


def test_repair_mojibake_em_dash_and_apostrophe():
    broken = "itâ€™s a testâ€”really"
    assert text.repair_mojibake(broken) == "it’s a test—really"


def test_repair_mojibake_leaves_clean_text_untouched():
    clean = "A normal sentence with “curly” quotes and an em—dash."
    assert text.repair_mojibake(clean) == clean


def test_scrub_control_chars_removes_c0_but_keeps_whitespace():
    raw = "line1\nline2\tcol\x00\x07\x1b end\r\n"
    out = text.scrub_control_chars(raw)
    assert "\x00" not in out and "\x07" not in out and "\x1b" not in out
    # newlines and tabs are legitimate whitespace and survive
    assert "\n" in out and "\t" in out


def test_strip_html_removes_tags_keeps_text():
    html = "<p>Hello <b>world</b> &amp; <a href='x'>link</a></p>"
    assert text.strip_html(html) == "Hello world & link"


def test_clean_composes_all_three():
    broken = "<p>itâ€™s\x00 fine</p>"
    assert text.clean(broken) == "it’s fine"


def test_clean_is_idempotent():
    broken = "<p>the â€œwordâ€\x07</p>"
    once = text.clean(broken)
    assert text.clean(once) == once
