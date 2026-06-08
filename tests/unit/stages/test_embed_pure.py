"""Pure embed helpers — the A1 no-truncation budget gate.

`assert_within_budget` is the A1 gate (§9a): a chunk longer than the embedding model's token limit
would be **silently truncated** at embed time (its tail never embedded). The check raises loudly
instead, naming the offending chunk, so a too-large chunk is a build failure rather than a quiet
hole in the vector index. `estimate_tokens` is a deliberately *conservative* (upper-bound) token
count so the gate never *under*-counts a borderline chunk through.
"""

from __future__ import annotations

import pytest

from vdocs.stages.embed import embed_pure as ep


def test_estimate_tokens_zero_for_empty():
    assert ep.estimate_tokens("") == 0
    assert ep.estimate_tokens("   ") == 0


def test_estimate_tokens_is_a_conservative_upper_bound():
    # at least one token per whitespace-word (a safe lower floor for the estimate)
    text = "the quick brown fox jumps"  # 5 words
    assert ep.estimate_tokens(text) >= 5


def test_estimate_tokens_catches_a_giant_unspaced_block():
    # a 30k-char single "word" (e.g. a big table/fence) has no whitespace, so a word-only estimate
    # would say ~1 token — the char-based term must dominate and exceed an 8k budget.
    assert ep.estimate_tokens("x" * 30_000) > 8192


def test_assert_within_budget_passes_when_all_under():
    ep.assert_within_budget(["d/a", "d/b"], ["alpha text", "beta text"], max_tokens=8192)


def test_assert_within_budget_raises_naming_the_offender():
    with pytest.raises(ValueError, match="d/big"):
        ep.assert_within_budget(
            ["d/ok", "d/big"],
            ["small", "x" * 100_000],
            max_tokens=8192,
        )


def test_assert_within_budget_accepts_injected_estimator():
    # the estimator is injectable so the real backend can later supply the model's true tokenizer
    ep.assert_within_budget(["d/a"], ["whatever"], max_tokens=10, estimate=lambda _t: 5)
    with pytest.raises(ValueError):
        ep.assert_within_budget(["d/a"], ["whatever"], max_tokens=10, estimate=lambda _t: 11)


# --- token-budget batching (OOM fix) -------------------------------------------------------------
#
# A fixed *item-count* batch OOMs the embedder: ONNX pads each batch to its longest member, so the
# transient activation footprint scales with `len(batch) × longest_sequence`. A batch of 256 where
# one chunk is ~2.5k tokens forces all 256 to that length → tens of GB. `token_batched` bounds the
# *padded* footprint (`items × longest`) instead, so a long chunk shrinks its own batch.


def test_token_batched_empty_yields_nothing():
    assert list(ep.token_batched([], max_padded_tokens=100, max_items=10)) == []


def test_token_batched_covers_all_items_in_order():
    items = [f"t{i}" for i in range(10)]
    out = list(ep.token_batched(items, max_padded_tokens=10, max_items=3, estimate=lambda _t: 1))
    assert [x for b in out for x in b] == items  # order preserved, every item exactly once


def test_token_batched_caps_by_item_count():
    out = list(
        ep.token_batched(["a"] * 7, max_padded_tokens=10_000, max_items=3, estimate=lambda _t: 1)
    )
    assert [len(b) for b in out] == [3, 3, 1]


def test_token_batched_caps_by_padded_tokens():
    # padded cost = items × longest. budget 200: ["100","100"]→2*100=200 ok; a third →3*100>200
    items = ["100", "100", "100"]
    out = list(ep.token_batched(items, max_padded_tokens=200, max_items=99, estimate=int))
    assert [len(b) for b in out] == [2, 1]


def test_token_batched_a_long_item_shrinks_its_batch():
    # the 500-token item can't share a 500-budget batch with anything else (2*500 > 500)
    items = ["10", "10", "500", "10"]
    out = list(ep.token_batched(items, max_padded_tokens=500, max_items=99, estimate=int))
    assert out == [["10", "10"], ["500"], ["10"]]


def test_token_batched_lone_oversize_item_gets_its_own_batch():
    # an item whose own estimate exceeds the budget still yields alone (never dropped/merged): the
    # A1 gate already caps any chunk at the model's token limit, so it is bounded.
    items = ["50", "9000", "50"]
    out = list(ep.token_batched(items, max_padded_tokens=500, max_items=99, estimate=int))
    assert out == [["50"], ["9000"], ["50"]]


# --- A2a: contextual chunk headers (§9b) ---------------------------------------------------------


def test_contextual_embed_text_prepends_doc_and_section_path():
    out = ep.contextual_embed_text(
        "KAAJEE Installation Guide", "Platform Setup > WebLogic", "## WebLogic\n\nstart the server"
    )
    assert out == (
        "«KAAJEE Installation Guide › Platform Setup › WebLogic»\n\n## WebLogic\n\nstart the server"
    )


def test_contextual_embed_text_doc_title_only_when_no_section_path():
    # a top-level section (no ancestors) still gets the document title — the key context for a
    # terse leaf whose body never repeats the product name.
    assert ep.contextual_embed_text("MailMan UG", "", "body") == "«MailMan UG»\n\nbody"


def test_contextual_embed_text_no_header_when_no_crumbs():
    # nothing to add → return the body unchanged (never an empty «» header)
    assert ep.contextual_embed_text("", "", "body") == "body"


def test_contextual_embed_text_drops_blank_crumbs():
    assert ep.contextual_embed_text("Doc", " > A >  > B", "x") == "«Doc › A › B»\n\nx"
