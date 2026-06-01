"""Near-duplicate detection primitives — shared by every `discover` instance (§9.2, §9.6).

Shingling + MinHash + Jaccard estimation live here *once* (tenet #4) so the Phase-3
boilerplate / template / glossary miners all build on the same maths rather than
re-implementing it. Pure functions; deterministic (no RNG — permutation coefficients
are derived from the permutation index, so signatures are reproducible across runs).
"""

from __future__ import annotations

import hashlib
import re

# A large Mersenne prime > 2**32, for the (a*x + b) mod P universal-hash family.
_PRIME = (1 << 61) - 1
_MASK32 = (1 << 32) - 1
_WORD_RE = re.compile(r"\w+")


def shingles(text: str, k: int = 3) -> set[str]:
    """Set of overlapping k-word shingles (lowercased). Short text → one shingle."""
    words = _WORD_RE.findall(text.lower())
    if len(words) <= k:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i : i + k]) for i in range(len(words) - k + 1)}


def exact_jaccard(a: set[str], b: set[str]) -> float:
    """Exact Jaccard similarity of two shingle sets; 0.0 when both are empty."""
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def _hash(shingle: str) -> int:
    return int.from_bytes(hashlib.sha1(shingle.encode("utf-8")).digest()[:8], "big")


def _coeffs(i: int) -> tuple[int, int]:
    seed = hashlib.sha256(str(i).encode("ascii")).digest()
    a = (int.from_bytes(seed[:8], "big") % (_PRIME - 1)) + 1
    b = int.from_bytes(seed[8:16], "big") % _PRIME
    return a, b


def minhash_signature(shingle_set: set[str], num_perm: int = 128) -> tuple[int, ...]:
    """MinHash signature: ``num_perm`` minima under deterministic hash permutations."""
    hashes = [_hash(s) for s in shingle_set]
    signature: list[int] = []
    for i in range(num_perm):
        a, b = _coeffs(i)
        if hashes:
            signature.append(min(((a * h + b) % _PRIME) & _MASK32 for h in hashes))
        else:
            signature.append(_MASK32)
    return tuple(signature)


def estimate_jaccard(sig_a: tuple[int, ...], sig_b: tuple[int, ...]) -> float:
    """Estimate Jaccard from two equal-length MinHash signatures."""
    if len(sig_a) != len(sig_b):
        raise ValueError("signatures must be the same length")
    if not sig_a:
        return 0.0
    return sum(1 for x, y in zip(sig_a, sig_b) if x == y) / len(sig_a)
