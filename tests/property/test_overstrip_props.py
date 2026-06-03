"""Property tests for the over-strip guardrail (fidelity §10.5).

Invariants that must hold for any heading tree: the rate is a well-formed fraction tied to the
hollow set, the score is its complement, and the verdict is a monotone function of the score."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from vdocs.stages.fidelity import overstrip_pure as op

_titles = (
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=1, max_size=12)
    .map(str.strip)
    .filter(bool)
)
# each section is either substantive prose or a bare back-link (hollow)
_REAL = "real word tokens enough to clear the floor here now"
_HOLLOW = "[↑ Back to Contents](#contents)"
_sections = st.lists(
    st.tuples(_titles, st.sampled_from([_REAL, _HOLLOW])),
    min_size=0,
    max_size=8,
)


@given(sections=_sections)
def test_rate_score_and_verdict_are_consistent(sections: list[tuple[str, str]]):
    body = "# Title\n\n" + "\n\n".join(f"## {t}\n\n{b}" for t, b in sections)
    v = op.score_over_strip(body)
    assert 0.0 <= v.over_strip_rate <= 1.0
    assert abs(v.score - (1.0 - v.over_strip_rate)) < 1e-9
    if v.content_chunks:
        assert abs(v.over_strip_rate - len(v.hollow) / v.content_chunks) < 1e-9
    # verdict is monotone in score
    if v.score >= 1.0:
        assert v.verdict == op.PASS
    elif v.score >= 0.5:
        assert v.verdict == op.REVIEW
    else:
        assert v.verdict == op.QUARANTINE
