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


def contextual_embed_text(doc_title: str, section_path: str, body: str) -> str:
    """A2a contextual chunk header (§9b): prepend a compact breadcrumb to the **embedded** text.

    Returns ``«{doc_title} › {ancestors…}»\\n\\n{body}``. A terse VistA leaf (e.g. "Select
    Installation Option: 1") is ambiguous in isolation; the breadcrumb injects the document title
    and the ancestor heading path — which the body often never repeats — so semantic recall on such
    sections improves sharply. This decorates *only* the text handed to the embedder; the
    stored/cited chunk body and the FTS row stay clean. Blank crumbs are dropped; with no crumbs at
    all the body is returned unchanged (never an empty ``«»`` header)."""
    crumbs = [c.strip() for c in [doc_title, *section_path.split(" > ")] if c.strip()]
    if not crumbs:
        return body
    return f"«{' › '.join(crumbs)}»\n\n{body}"


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


def token_batched(
    texts: Iterable[str],
    *,
    max_padded_tokens: int,
    max_items: int,
    estimate: Callable[[str], int] = estimate_tokens,
) -> Iterator[list[str]]:
    """Yield batches bounded by their **padded** token footprint — ``len(batch) × longest member`` —
    rather than a fixed item count.

    The embedder pads every batch to its longest sequence before the forward pass, so transient
    activation/attention memory scales with ``items × longest_len`` (and worse with length). A fixed
    256-item batch therefore OOMs the moment one long chunk drags the whole batch up to its length
    (the v1 bug: 256 × ~2.5k-token chunks ≈ tens of GB). Capping the padded footprint makes a long
    chunk shrink its own batch instead. ``max_items`` is a secondary safety cap for the all-tiny
    case. A single text whose own estimate exceeds ``max_padded_tokens`` still yields as its own
    one-item batch (never dropped, never merged) — the A1 budget gate already caps any chunk at the
    model's token limit, so it is bounded. Order is preserved and every text appears exactly once.
    ``estimate`` is injectable (same conservative default as the budget gate)."""
    buf: list[str] = []
    buf_max = 0
    for t in texts:
        n = estimate(t)
        new_max = max(buf_max, n)
        if buf and (len(buf) >= max_items or (len(buf) + 1) * new_max > max_padded_tokens):
            yield buf
            buf, buf_max, new_max = [], 0, n
        buf.append(t)
        buf_max = new_max
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
