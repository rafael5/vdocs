"""Decode HTML entities in the body, so escaped code is searchable (§6.5).

Docling escapes `<` and `>` in text, and VistA manuals are full of M code that uses them:
`K:$L(X)>40!($L(X)<3) X` arrives as `K:$L(X)&gt;40!($L(X)&lt;3) X`. On the FileMan Developer's Guide
that is **1,659 escapes — 892 `&gt;` and 751 `&lt;`** — and every one of them costs a search: FTS5
tokenises `&gt;` into the noise token `gt`, so a query for `$L(X)>40` cannot match the text that
contains it.

This is also a convergence fix. The Pandoc path already yields raw `<`/`>` in code — gold contains
`K:$L(X)>40!($L(X)<3) X` today — so leaving Docling's escaped, and only Docling's, would keep the
two converters producing different text for identical source.

Runs late, after every step that reads HTML structure (table extraction, HTML→GFM, text-box
fencing), so a decoded `<` can never be mistaken for markup by this pipeline.
"""

from vdocs.stages.normalize.normalize_pure import decode_entities


class TestDecoding:
    def test_escaped_m_code_operators_are_decoded(self) -> None:
        assert decode_entities("K:$L(X)&gt;40!($L(X)&lt;3) X") == "K:$L(X)>40!($L(X)<3) X"

    def test_ampersand_is_decoded(self) -> None:
        assert decode_entities("OI&amp;T") == "OI&T"

    def test_numeric_references_are_decoded(self) -> None:
        assert decode_entities("a&#124;b") == "a|b"

    def test_a_prompt_placeholder_is_decoded(self) -> None:
        assert decode_entities("Press &lt;RET&gt; to continue") == "Press <RET> to continue"

    def test_text_with_no_entities_is_unchanged(self) -> None:
        body = "Just prose with < and > used literally.\n"
        assert decode_entities(body) == body

    def test_it_is_idempotent(self) -> None:
        once = decode_entities("OI&amp;T and $L(X)&gt;40")
        assert decode_entities(once) == once


class TestSafety:
    def test_a_double_escaped_ampersand_decodes_only_one_level(self) -> None:
        """`&amp;lt;` is the literal text `&lt;`, not an escaped `<` — decoding twice would
        silently turn documentation *about* escaping into the thing it describes."""
        assert decode_entities("&amp;lt;") == "&lt;"

    def test_existing_real_markup_is_untouched(self) -> None:
        body = '<img src="a.png" />\n\n| a | b |\n|---|---|\n'
        assert decode_entities(body) == body
