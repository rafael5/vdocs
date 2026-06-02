"""Property test for kernel.discovery MinHash estimation (§9.6, §12).

``estimate_jaccard`` (over MinHash signatures) must track the exact Jaccard similarity within the
MinHash sampling tolerance. This is what makes ``exact_jaccard`` a live **reference oracle** rather
than dead code (closes A1's note): the estimate is validated against the exact value here."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from vdocs.kernel import discovery as kd

_NUM_PERM = 256
_TOL = 0.2  # generous vs the ~1/sqrt(256)≈0.06 MinHash std, so the property never flakes

_text = st.text(alphabet="abcdefghij klmno", min_size=1, max_size=80)


@given(a=_text, b=_text)
def test_estimate_jaccard_tracks_exact_jaccard(a: str, b: str):
    sa, sb = kd.shingles(a), kd.shingles(b)
    # both-empty shingle sets are the one degenerate case (no signal to estimate from); skip it
    if not sa or not sb:
        return
    exact = kd.exact_jaccard(sa, sb)
    est = kd.estimate_jaccard(
        kd.minhash_signature(sa, _NUM_PERM), kd.minhash_signature(sb, _NUM_PERM)
    )
    assert abs(est - exact) <= _TOL
