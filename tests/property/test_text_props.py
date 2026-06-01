"""Property tests for kernel.text (Hypothesis, ADR-008): idempotency."""

from hypothesis import given
from hypothesis import strategies as st

from vdocs.kernel import text


@given(st.text())
def test_clean_is_idempotent(s: str):
    once = text.clean(s)
    assert text.clean(once) == once


@given(st.text())
def test_scrub_control_chars_idempotent(s: str):
    once = text.scrub_control_chars(s)
    assert text.scrub_control_chars(once) == once


@given(st.text(alphabet=st.characters(blacklist_categories=("Cs",))))
def test_clean_never_contains_control_chars(s: str):
    out = text.clean(s)
    assert not any(0x00 <= ord(c) <= 0x08 or ord(c) == 0x7F for c in out)
