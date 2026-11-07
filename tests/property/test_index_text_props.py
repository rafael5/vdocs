"""Property tests for `index_pure.index_text` — the clean FTS projection (end-to-end review A1).

The strategy builds a markdown section from fragments that each know which word tokens the
projection must keep: prose, keystroke notation, whitelisted HTML with attributes, `<img>` with an
asset hash and alt text, markdown links/images, legacy-TOC entries, the nav line, table markers,
headings, emphasis, inline code, fenced code and an HTML table. The invariants are the kickoff's:
every token not inside a dropped construct survives; no whitelisted tag, `](`, `↑`, fence or
40–64-character hex token survives; keystroke notation survives as written; table cell text
survives. On arbitrary text the projection never invents a token. The projection is one pass and
deliberately NOT idempotent: its last step restores Pandoc's backslash-escaped punctuation as
content (`\<Enter\>` → `<Enter>`, `\[ENTER\](value)` → `[ENTER](value)`), which a second pass
would read as markup.
"""

from __future__ import annotations

import re
from collections import Counter

from hypothesis import given
from hypothesis import strategies as st

from vdocs.stages.index import index_pure as ip

_TOKEN = re.compile(r"[^\W_]+")
_HEX = re.compile(r"\b[0-9a-f]{40,64}\b")
_WHITELISTED_TAG = re.compile(
    "</?(?:" + "|".join(sorted(ip.HTML_ELEMENTS, key=len, reverse=True)) + r")(?=[\s/>])"
)

# keystroke/placeholder notation measured in the corpus (kickoff step 4, reports/a1-before.md):
# bare, Pandoc-escaped, and the forms that collide with an element name only in case. The escaped
# forms survive as the bare notation (the escape is restored last).
KEYSTROKES = [
    "<Enter>", "<RET>", "<Tab>", "<CR>", "<PF1>", "<Ctrl>", "<ServerName>", "<Z224001>",
    "\\<Enter\\>", "\\<RET\\>", "\\<Spacebar\\>", "<A>", "<P>", "\\<A\\>", "<Code\\>", "</Code\\>",
    "<B\\>", "<U\\>", "<I\\>", "<name of file>", "<http://vista.example>",
]  # fmt: skip


def unescaped(keystroke: str) -> str:
    return keystroke.replace("\\<", "<").replace("\\>", ">")


word = st.from_regex(r"[A-Za-z][A-Za-z0-9]{0,7}", fullmatch=True)
words = st.lists(word, min_size=1, max_size=5).map(" ".join)
hex64 = st.from_regex(r"[0-9a-f]{64}", fullmatch=True)
attrs = st.sampled_from(
    ["", ' style="width: 20%"', ' class="odd"', ' id="_Toc12345"', ' style="text-align: left;"']
)


def _frag(text: str, kept: str) -> tuple[str, list[str]]:
    return text, _TOKEN.findall(kept)


prose = words.map(lambda w: _frag(w, w))
keystroke = st.sampled_from(KEYSTROKES).map(lambda k: (k, []))
inline_tag = st.tuples(
    st.sampled_from(["p", "span", "u", "strong", "em", "blockquote", "li", "sup", "code", "mark"]),
    attrs,
    words,
).map(lambda t: _frag(f"<{t[0]}{t[1]}>{t[2]}</{t[0]}>", t[2]))
img = st.tuples(hex64, words).map(
    lambda t: _frag(f'<img src="{t[0]}.png" style="width:6in;height:8in" alt="{t[1]}" />', t[1])
)
# alt text quoting a prompt dialogue, keystroke notation included (DI/fm22_2um1)
img_alt_keystroke = st.tuples(hex64, words, st.sampled_from(["<Enter>", "<RET>"]), words).map(
    lambda t: _frag(f'<img src="{t[0]}.png" alt="{t[1]} {t[2]} {t[3]}" />', f"{t[1]} {t[3]}")
)
# a TOC link whose label ends in a lone backslash (89 live links)
backslash_label_link = st.tuples(words, st.sampled_from(["\\", "\\/\\/\\"])).map(
    lambda t: _frag(f"[{t[0]} {t[1]}](#slug)", t[0])
)
bare_img = hex64.map(lambda h: _frag(f'<img src="{h}.png" style="width:6in" />', ""))
md_image = st.tuples(words, hex64).map(lambda t: _frag(f"![{t[0]}](assets/{t[1]}.png)", t[0]))
link = st.tuples(words, st.sampled_from(["#intro", "tables/table-01.csv", "../x.md"])).map(
    lambda t: _frag(f"[{t[0]}]({t[1]})", t[0])
)
toc_entry = st.tuples(words, st.sampled_from(["ii", "12", "7-9", "xxxiv"])).map(
    lambda t: _frag(f"[{t[0]} [{t[1]}](#slug)](#slug)", t[0])
)
nav = st.just(_frag("[↑ Back to Contents](#contents)", ""))
table_marker = st.integers(1, 40).map(
    lambda n: _frag(f"_[Table {n} (extracted to CSV)](tables/table-{n:02d}.csv)_", "")
)
heading = st.tuples(st.integers(1, 8), words).map(lambda t: _frag("#" * t[0] + " " + t[1], t[1]))
emphasis = st.tuples(st.sampled_from(["**", "*", "_", "`", "***"]), words).map(
    lambda t: _frag(f"{t[0]}{t[1]}{t[0]}", t[1])
)
# a fence opens at a line start and a closing fence ends its line (CommonMark allows nothing after
# it), so the fragment carries its own newlines whatever separators surround it
fence = st.tuples(st.sampled_from(["```", "```text", "~~~"]), words, words).map(
    lambda t: _frag(
        f"\n{t[0]}\nS X={t[1].replace(' ', '_')}\nD ^{t[2].split()[0]}\n{t[0][:3]}\n",
        f"{t[1]} {t[2].split()[0]}",
    )  # fmt: skip
)
html_table = st.tuples(attrs, words, words, words).map(
    lambda t: _frag(
        '<table>\n<colgroup>\n<col style="width: 50%" />\n</colgroup>\n<thead>\n<tr class="header">'
        f"\n<th>{t[1]}</th>\n</tr>\n</thead>\n<tbody>\n<tr{t[0]}>\n<td{t[0]}>{t[2]}</td>\n"
        f"<td>{t[3]}</td>\n</tr>\n</tbody>\n</table>",
        f"{t[1]} {t[2]} {t[3]}",
    )
)
# labels with Pandoc-escaped brackets (1,496 live links) or a footnote reference (85)
escaped_label_link = st.tuples(words, word, words).map(
    lambda t: _frag(f"[{t[0]} \\[{t[1]}\\] {t[2]}](#slug)", f"{t[0]} {t[1]} {t[2]}")
)
footnote_link = st.tuples(words, st.integers(1, 99)).map(
    lambda t: _frag(f"[{t[0]}[^{t[1]}]](#slug{t[1]})", f"{t[0]} {t[1]}")
)
# a screen capture: an escaped keystroke followed by a parenthesised value is NOT a link
escaped_bracket_text = st.tuples(st.sampled_from(["ENTER", "RET"]), st.integers(1, 28)).map(
    lambda t: _frag(f"\\[{t[0]}\\](JUN {t[1]}, 1996@09:00)", f"{t[0]} JUN {t[1]} 1996 09 00")
)
# an escaped XML example with a real highlight span inside it (VistALink guides); the element
# name is not an HTML one — an escaped `\<p …\>` ABOUT HTML is content and keeps its `<p`
xml_name = word.filter(lambda w: w not in ip.HTML_ELEMENTS)
nested_placeholder = st.tuples(xml_name, words).map(
    lambda t: _frag(f'\\<{t[0]} name="<span class="mark">{t[1]}</span>"/\\>', f"{t[0]} name {t[1]}")
)
fragment = st.one_of(
    prose, keystroke, inline_tag, img, bare_img, md_image, link, toc_entry, nav, table_marker,
    heading, emphasis, fence, html_table, escaped_label_link, footnote_link,
    escaped_bracket_text, nested_placeholder, img_alt_keystroke, backslash_label_link,
)  # fmt: skip
separator = st.sampled_from([" ", "\n", "\n\n", "\n\n\n", "\t"])


@st.composite
def sections(draw):
    frags = draw(st.lists(fragment, min_size=1, max_size=12))
    seps = draw(st.lists(separator, min_size=len(frags), max_size=len(frags)))
    text = "".join(f + s for (f, _), s in zip(frags, seps))
    kept = Counter(tok for _, ks in frags for tok in ks)
    keystrokes = [f for f, ks in frags if f in KEYSTROKES]
    cells = [ks for f, ks in frags if f.startswith("<table>")]
    return text, kept, keystrokes, cells


@given(sections())
def test_every_token_outside_a_dropped_construct_survives(sec):
    text, kept, _, _ = sec
    out = Counter(_TOKEN.findall(ip.index_text(text)))
    missing = kept - out
    assert not missing, (missing, text)


@given(sections())
def test_no_markup_residue_survives(sec):
    text, _, _, _ = sec
    out = ip.index_text(text)
    assert _WHITELISTED_TAG.search(out) is None, out
    # no link target survives (a restored `\[ENTER\](value)` is content and may carry `](`)
    assert not re.search(r"\]\((?:#|tables/|assets/|\.\./)", out), out
    assert "↑" not in out and "<img" not in out and "<!--" not in out
    assert "```" not in out and "~~~" not in out
    assert _HEX.search(out) is None, out
    assert re.search(r"\s\s|^\s|\s$|\n", out) is None  # whitespace collapsed


@given(sections())
def test_keystroke_notation_survives_as_written(sec):
    text, _, keystrokes, _ = sec
    out = ip.index_text(text)
    for k in keystrokes:
        assert unescaped(k) in out, (k, out)


@given(sections())
def test_html_table_cell_text_survives(sec):
    text, _, _, cells = sec
    out = Counter(_TOKEN.findall(ip.index_text(text)))
    for ks in cells:
        assert not (Counter(ks) - out), (ks, out)


@given(st.text())
def test_projection_never_invents_a_token_or_raises(s: str):
    out = ip.index_text(s)
    assert not (Counter(_TOKEN.findall(out)) - Counter(_TOKEN.findall(s)))
    assert "\n" not in out and out == out.strip()
