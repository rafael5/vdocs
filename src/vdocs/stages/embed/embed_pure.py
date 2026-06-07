"""Pure helpers for `embed` (§14.6) — batching, a dimension-uniformity check, and the A1
no-truncation budget gate. The embedding itself is an injected backend (see ``stage.py``); these are
the deterministic, I/O-free parts (§9.2)."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Iterator, Sequence

# Conservative char→token ratio for the budget estimate. English+code tokenizers average ~4 chars
# per token; dense/symbol-heavy text runs lower. 3.2 over-counts a little on purpose — the budget
# gate must never *under*-count and let a silently-truncated chunk through.
_CHARS_PER_TOKEN = 3.2
_TOKENS_PER_WORD = 1.3


def estimate_tokens(text: str) -> int:
    """A deliberately conservative (upper-bound) token count, with no model/tokenizer load.

    Takes the **max** of a word-based and a char-based estimate so neither a prose chunk (many
    short words) nor a giant unspaced block (one huge "word", e.g. a wide table/fence) can slip
    under the budget gate. Empty/blank text is 0 tokens."""
    stripped = text.strip()
    if not stripped:
        return 0
    by_words = math.ceil(len(stripped.split()) * _TOKENS_PER_WORD)
    by_chars = math.ceil(len(stripped) / _CHARS_PER_TOKEN)
    return max(by_words, by_chars)


def assert_within_budget(
    ids: Sequence[str],
    texts: Sequence[str],
    *,
    max_tokens: int,
    estimate: Callable[[str], int] = estimate_tokens,
) -> None:
    """A1 gate (§9a): raise if any chunk would exceed the embedding model's token limit.

    A chunk longer than ``max_tokens`` is silently truncated by the model at embed time — its tail
    never embedded, a quiet hole in the vector index. We fail the build instead, naming the worst
    offenders, so chunk sizing stays aligned to the chosen embedder. ``estimate`` is injectable so a
    real backend can substitute the model's true tokenizer for the conservative default."""
    offenders = [(cid, n) for cid, t in zip(ids, texts) if (n := estimate(t)) > max_tokens]
    if offenders:
        offenders.sort(key=lambda x: -x[1])
        shown = ", ".join(f"{cid} (~{n} tok)" for cid, n in offenders[:5])
        more = f" (+{len(offenders) - 5} more)" if len(offenders) > 5 else ""
        raise ValueError(
            f"{len(offenders)} chunk(s) exceed the embedder's {max_tokens}-token budget and would "
            f"be truncated: {shown}{more}. Right-size chunking (index_pure CHUNK_TARGET/OVERSIZED) "
            f"or choose a longer-context model."
        )


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
