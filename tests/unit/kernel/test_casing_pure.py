"""Unit tests for kernel.casing_pure — the selective-casing core for the SKL S1 quick win
(``docs/skl-implementation-plan.md`` S1.2/S1.3).

The casing bug: ``build-termbase`` whitelists ~1,117 terms; turning on Vale's blanket
case-enforcement then demands "use ``CAN``" on every ordinary "can" because acronyms collide
with English words. The fix is to *auto-derive* which surfaces collide (lowercase ∈ the same
Hunspell dict Vale's speller consults) and force-case only the safe set — no hand-curated
``Brand.yml`` parallel list (tenet #13).

``collides_with_english`` is the grounded, self-maintaining classifier; ``selective_casing_swap``
is the projector that turns the safe set into a Vale ``substitution`` swap. Both are pure.
"""

from __future__ import annotations

from vdocs.kernel import casing_pure as c

# A synthetic stand-in for "the lowercase base words Vale's speller accepts". The real loader
# reads registries/glossary/english-words.txt (vendored from Vale's en_US-web.dic).
_WORDS = frozenset(
    {"can", "site", "an", "or", "is", "option", "item", "vista", "mumps", "help", "map", "host"}
)


# --- collides_with_english ----------------------------------------------------------------------
def test_uniform_case_acronym_whose_lowercase_is_english_collides():
    # The CAN problem: all-caps acronyms that are ordinary words lowercased must NOT be force-cased.
    for surface in ("CAN", "SITE", "AN", "OR", "IS"):
        assert c.collides_with_english(surface, _WORDS) is True, surface


def test_internal_capital_brand_never_collides_even_if_lowercase_is_a_word():
    # "vista" IS an English word, but the brand surface "VistA" has an internal capital — typography
    # no English word takes — so it is always safe to enforce. Load-bearing: a naive
    # lowercase-membership check would wrongly veto VistA and break the Vista→VistA gate.
    assert c.collides_with_english("VistA", _WORDS) is False
    assert c.collides_with_english("FileMan", _WORDS) is False


def test_title_case_common_word_collides():
    # The other load-bearing edge: a Title-case word ("Site"/"Host"/"Map") is NOT a brand — its
    # lowercase is ordinary prose, so enforcing it would flag "site"/"host"/"map" everywhere.
    for surface in ("Site", "Host", "Map"):
        assert c.collides_with_english(surface, _WORDS) is True, surface


def test_uniform_case_term_absent_from_dict_does_not_collide():
    # "KIDS"/"fileman" are not English words → enforce their casing.
    assert c.collides_with_english("KIDS", _WORDS) is False
    assert c.collides_with_english("PIMS", _WORDS) is False


def test_lowercase_word_surface_collides():
    # An all-lowercase surface that is itself an English word is uniform-case + in-dict → collides.
    assert c.collides_with_english("map", _WORDS) is True


def test_collision_is_case_insensitive_on_membership():
    # MUMPS → "mumps" is a (medical) English word → collides → spelling-accept only.
    assert c.collides_with_english("MUMPS", _WORDS) is True


def test_empty_or_nonword_surface_does_not_collide():
    assert c.collides_with_english("", _WORDS) is False
    assert c.collides_with_english("XU", _WORDS) is False  # not in dict


# --- selective_casing_swap ----------------------------------------------------------------------
def test_swap_enforces_safe_single_token_terms_only():
    swap = c.selective_casing_swap(
        terms=["FileMan", "VistA", "PIMS", "CAN", "MUMPS", "VA FileMan"],
        english_words=_WORDS,
        no_enforce=frozenset(),
    )
    # safe brands/abbrs → enforced (canonical→canonical identity entries)
    assert swap == {"FileMan": "FileMan", "VistA": "VistA", "PIMS": "PIMS"}
    # colliding acronyms dropped; multiword "VA FileMan" dropped (single-token only)
    assert "CAN" not in swap and "MUMPS" not in swap and "VA FileMan" not in swap


def test_swap_respects_no_enforce_opt_out():
    swap = c.selective_casing_swap(
        terms=["FileMan", "PIMS"],
        english_words=_WORDS,
        no_enforce=frozenset({"PIMS"}),
    )
    assert swap == {"FileMan": "FileMan"}


def test_swap_is_deterministic_and_dedupes():
    swap = c.selective_casing_swap(
        terms=["VistA", "VistA", "FileMan"],
        english_words=_WORDS,
        no_enforce=frozenset(),
    )
    assert swap == {"FileMan": "FileMan", "VistA": "VistA"}
    assert list(swap) == sorted(swap)  # deterministic order
