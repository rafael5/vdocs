"""Pure helpers for `embed` (§14.6) — batching + a dimension-uniformity check. The embedding itself
is an injected backend (see ``stage.py``); these are the deterministic, I/O-free parts (§9.2)."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence


def batched(items: Iterable[str], size: int) -> Iterator[list[str]]:
    """Yield successive ``size``-length batches of ``items`` (the last may be short). ``size <= 0``
    yields a single batch — so an injected backend that prefers one call still works."""
    buf: list[str] = []
    if size <= 0:
        yield list(items)
        return
    for it in items:
        buf.append(it)
        if len(buf) == size:
            yield buf
            buf = []
    if buf:
        yield buf


def uniform_dim(vectors: Sequence[Sequence[float]]) -> int:
    """The single embedding dimension shared by every vector — the backend contract check.

    Raises if the backend returned ragged dims (a misconfigured model), so a corrupt ``vectors.db``
    is never built silently. Callers guard the empty case (no chunks ⇒ no vectors ⇒ dim 0)."""
    dims = {len(v) for v in vectors}
    if len(dims) != 1:
        raise ValueError(f"embedder returned non-uniform vector dims: {sorted(dims)}")
    return dims.pop()
