"""Property tests for kernel.frontmatter (Hypothesis): codec round-trip (§9.3)."""

from hypothesis import given
from hypothesis import strategies as st

from vdocs.kernel import frontmatter as fm

# Scalar frontmatter values: strings, ints, bools, floats (the realistic identity-FM types).
_keys = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd")),
    min_size=1,
    max_size=12,
)
# Identity frontmatter values are human-curated printable strings — not arbitrary
# control bytes (YAML legitimately normalizes Unicode line-break controls).
_printable = st.characters(blacklist_categories=("Cc", "Cf", "Cs", "Zl", "Zp"))
_values = st.one_of(
    st.text(alphabet=_printable, max_size=40),
    st.integers(min_value=-(10**6), max_value=10**6),
    st.booleans(),
)
_meta = st.dictionaries(_keys, _values, max_size=8)
# Body text without a carriage return (yaml/markdown normalize CR); never starts with "---".
_body = st.text(alphabet=st.characters(blacklist_characters="\r"), max_size=200).filter(
    lambda b: not b.startswith("---")
)


@given(meta=_meta, body=_body)
def test_emit_parse_round_trip(meta: dict, body: str):
    parsed_meta, parsed_body = fm.parse(fm.emit(meta, body))
    assert parsed_meta == meta
    assert parsed_body == body
