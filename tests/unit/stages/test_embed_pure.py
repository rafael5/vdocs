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
