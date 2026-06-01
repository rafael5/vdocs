"""Unit tests for kernel.discovery — shared near-duplicate primitive (§9.2, §9.6).

Phase-1 scope: the shingling + MinHash + Jaccard primitive every `discover` instance
will share. The full pattern miners are built in Phase 3.
"""

from vdocs.kernel import discovery as d


def test_shingles_are_word_ngrams():
    assert d.shingles("the quick brown fox", k=2) == {
        "the quick",
        "quick brown",
        "brown fox",
    }


def test_shingles_short_text_is_single_shingle():
    assert d.shingles("one two", k=3) == {"one two"}


def test_exact_jaccard_bounds():
    a = d.shingles("the quick brown fox", k=2)
    b = d.shingles("the quick brown dog", k=2)
    assert d.exact_jaccard(a, a) == 1.0
    assert 0.0 < d.exact_jaccard(a, b) < 1.0
    assert d.exact_jaccard(a, set()) == 0.0
    assert d.exact_jaccard(set(), set()) == 0.0


def test_minhash_signature_is_deterministic_and_fixed_length():
    s1 = d.minhash_signature(d.shingles("alpha beta gamma delta", k=2), num_perm=64)
    s2 = d.minhash_signature(d.shingles("alpha beta gamma delta", k=2), num_perm=64)
    assert s1 == s2
    assert len(s1) == 64


def test_estimate_jaccard_identical_is_one():
    sig = d.minhash_signature(d.shingles("a b c d e f", k=2), num_perm=128)
    assert d.estimate_jaccard(sig, sig) == 1.0


def test_shingles_empty_text_is_empty_set():
    assert d.shingles("", k=3) == set()


def test_minhash_of_empty_set_is_max_sentinel():
    sig = d.minhash_signature(set(), num_perm=8)
    assert len(sig) == 8
    assert all(v == (1 << 32) - 1 for v in sig)


def test_estimate_jaccard_empty_signatures_is_zero():
    assert d.estimate_jaccard((), ()) == 0.0


def test_estimate_jaccard_length_mismatch_raises():
    import pytest

    with pytest.raises(ValueError):
        d.estimate_jaccard((1, 2), (1,))


def test_estimate_tracks_overlap():
    base = d.shingles("the standard legal notice applies to all documents here", k=2)
    near = d.shingles("the standard legal notice applies to most documents here", k=2)
    far = d.shingles("completely different words with nothing at all in common", k=2)
    sig_base = d.minhash_signature(base, num_perm=128)
    sig_near = d.minhash_signature(near, num_perm=128)
    sig_far = d.minhash_signature(far, num_perm=128)
    assert d.estimate_jaccard(sig_base, sig_near) > d.estimate_jaccard(sig_base, sig_far)
