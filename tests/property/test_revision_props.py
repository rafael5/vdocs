"""Property tests for revision_pure (§6.4, §12).

Two invariants: ``_norm_date`` is idempotent (normalising an already-normalised date is a no-op),
and the HTML ``<table>`` and GFM pipe-table dialects parse to the **same** records for the same
logical revision rows (the converter-routing choice must never change the captured history)."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from vdocs.stages.normalize import revision_pure as rev

_date_like = st.one_of(
    st.from_regex(r"\A[0-9]{1,2}/[0-9]{4}\Z", fullmatch=True),
    st.from_regex(r"\A[0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4}\Z", fullmatch=True),
    st.text(alphabet="0123456789-/ ", max_size=10),
)


@given(text=_date_like)
def test_norm_date_is_idempotent(text: str):
    once = rev._norm_date(text)
    assert rev._norm_date(once) == once


# simple cell text: no pipes / angle brackets / digits — so the two dialects tokenise identically
# and the page column is the only source of page numbers
_word = st.text(alphabet="abcdefghij ", min_size=1, max_size=12).map(lambda s: " ".join(s.split()))
_row = st.tuples(
    st.from_regex(r"\A[0-9]{1,2}/[0-9]{4}\Z", fullmatch=True),  # date
    st.from_regex(r"\A[0-9]\.[0-9]\Z", fullmatch=True),  # version
    st.integers(min_value=0, max_value=999),  # page
    _word.filter(bool),  # change
)


@given(rows=st.lists(_row, min_size=1, max_size=5))
def test_html_and_pipe_dialects_parse_equally(rows: list[tuple[str, str, int, str]]):
    header_cells = ["Date", "Version", "Page", "Change"]
    html = (
        "<table><tr>"
        + "".join(f"<th>{h}</th>" for h in header_cells)
        + "</tr>"
        + "".join(
            "<tr>" + "".join(f"<td>{c}</td>" for c in (d, v, str(p), ch)) + "</tr>"
            for d, v, p, ch in rows
        )
        + "</table>"
    )
    pipe_lines = [
        "| " + " | ".join(header_cells) + " |",
        "| " + " | ".join("---" for _ in header_cells) + " |",
        *("| " + " | ".join((d, v, str(p), ch)) + " |" for d, v, p, ch in rows),
    ]
    pipe = "\n".join(pipe_lines)

    assert rev.parse_revision_table(html) == rev.parse_revision_table(pipe)
