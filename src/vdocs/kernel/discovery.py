"""Near-duplicate detection primitives — shared by every `discover` instance (§9.2, §9.6).

Shingling + MinHash + Jaccard estimation live here *once* (tenet #4) so the Phase-3
boilerplate / template / glossary miners all build on the same maths rather than
re-implementing it. Pure functions; deterministic (no RNG — permutation coefficients
are derived from the permutation index, so signatures are reproducible across runs).

Used by `discover`'s near-duplicate boilerplate miner (``mine_recurring_blocks`` →
``cluster_near_duplicates``): exact-string equality only catches byte-identical blocks, so the
shingle/MinHash/Jaccard substrate here clusters near-identical boilerplate that drifts by a word
or two across the corpus (§9.6 step 1).
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from collections.abc import Sequence

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


# --- near-duplicate clustering (LSH banding + union-find) -------------------
#
# Used by `discover`'s near-dup boilerplate miner (§9.6 step 1): exact-string equality only
# catches byte-identical blocks, but corpus boilerplate drifts by a word or two across docs.
# LSH banding turns the O(n²) all-pairs comparison into "compare only signatures that already
# collide in some band", then union-find groups the verified near-duplicates.


def lsh_candidate_pairs(signatures: list[tuple[int, ...]], *, bands: int) -> set[tuple[int, int]]:
    """Index pairs that collide in ≥1 LSH band — the candidate near-duplicates.

    Each signature is split into ``bands`` contiguous rows; two signatures sharing an
    identical band land in the same bucket and become a candidate pair (verified later by
    :func:`estimate_jaccard`). ``num_perm`` must be divisible by ``bands``. With more bands
    (fewer rows each) the band-collision threshold drops, so banding stays a permissive
    pre-filter beneath the verification threshold (no false negatives for true near-dups)."""
    if not signatures:
        return set()
    n = len(signatures[0])
    if n % bands != 0:
        raise ValueError(f"signature length {n} not divisible by bands {bands}")
    rows = n // bands
    pairs: set[tuple[int, int]] = set()
    for b in range(bands):
        lo = b * rows
        buckets: dict[tuple[int, ...], list[int]] = defaultdict(list)
        for idx, sig in enumerate(signatures):
            buckets[sig[lo : lo + rows]].append(idx)
        for members in buckets.values():
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    pairs.add((members[i], members[j]))
    return pairs


def _auto_bands(num_perm: int, threshold: float) -> int:
    """Fewest LSH bands whose collision threshold ``(1/b)^(1/rows)`` ≤ ``threshold``.

    Banding must be at least as permissive as the verification threshold or true near-duplicates
    can slip through the candidate-pair stage (a silent false negative). Picking the smallest such
    ``b`` (a divisor of ``num_perm``) keeps the candidate set tight while guaranteeing recall."""
    for b in range(1, num_perm + 1):
        if num_perm % b:
            continue
        rows = num_perm // b
        if (1.0 / b) ** (1.0 / rows) <= threshold:
            return b
    return num_perm


def cluster_near_duplicates(
    signatures: list[tuple[int, ...]], *, threshold: float, bands: int | None = None
) -> list[list[int]]:
    """Partition signature indices into near-duplicate clusters (union-find).

    Two signatures join the same cluster when their estimated Jaccard ≥ ``threshold``; LSH
    banding restricts verification to candidate pairs. ``bands`` defaults to a value derived from
    ``threshold`` (:func:`_auto_bands`) so banding never drops a true near-duplicate; pass it
    explicitly only to tune the recall/cost trade-off. Every index appears in exactly one cluster
    (singletons included). Returns clusters as sorted index lists, ordered by their smallest
    member — deterministic, so callers get stable candidate identities."""
    n = len(signatures)
    if bands is None:
        bands = _auto_bands(len(signatures[0]), threshold) if signatures else 1
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, j in lsh_candidate_pairs(signatures, bands=bands):
        if estimate_jaccard(signatures[i], signatures[j]) >= threshold:
            parent[find(i)] = find(j)

    groups: dict[int, list[int]] = defaultdict(list)
    for idx in range(n):
        groups[find(idx)].append(idx)
    return sorted((sorted(g) for g in groups.values()), key=lambda g: g[0])


# --- structural (heading-scaffold) fingerprints (§9.8 template induction) ----
#
# A document's *structural* identity is the ordered sequence of its heading titles — the scaffold
# each manual of a given (doc_type, era) was poured into. `discover` clusters bodies by this
# scaffold to induce per-(doc_type, era) templates. ``structural_fingerprint`` is the exact
# identity (the ``template_id`` basis); ``scaffold_shingles`` feeds the near-dup clustering above
# so scaffolds that differ by a section or two still group.


def structural_fingerprint(titles: Sequence[str]) -> str:
    """sha256 over the normalized, ordered heading-title sequence — the exact scaffold identity.

    Order is load-bearing (a template *is* its section order), so this is a sequence hash, not a
    set hash; case/whitespace noise in titles is normalized away first."""
    h = hashlib.sha256()
    for title in titles:
        h.update(" ".join(title.lower().split()).encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def scaffold_shingles(titles: Sequence[str], k: int = 2) -> set[str]:
    """Overlapping k-gram shingles over the *heading sequence* (each token is a whole title).

    Unlike :func:`shingles` (word n-grams within one string), the unit here is a heading — so two
    documents with the same section scaffold share shingles even when individual section prose
    differs. Short scaffolds (≤ k headings) yield one shingle; empty → empty."""
    norm = [" ".join(t.lower().split()) for t in titles if t.strip()]
    if not norm:
        return set()
    if len(norm) <= k:
        return {" › ".join(norm)}
    return {" › ".join(norm[i : i + k]) for i in range(len(norm) - k + 1)}
