"""Selective-casing core — the pure heart of the SKL S1 "fix the casing bug at the source"
quick win (``docs/skl-proposal.md`` §7, ``docs/skl-implementation-plan.md`` S1.2/S1.3).

The controlled vocabulary is a flat list of ~1,117 approved spellings. Enforcing each term's
*exact capitalization* everywhere (Vale's blanket ``Vale.Terms``) is wrong for the acronyms that
collide with ordinary English — ``CAN``/``SITE``/``AN``/``OR``/``IS`` — because then every
sentence "can" gets flagged "use ``CAN``". ``fileman-docs`` worked around this with a
hand-maintained ``Brand.yml`` + ``Vale.Terms = NO`` — exactly the hand-curated parallel list
(tenet #13 violation) this program exists to kill.

The fix, here, with no human guessing which acronyms collide:

* ``collides_with_english`` — a term collides iff it is **uniform-case** (all-upper or all-lower)
  **and** its lowercase form is a real word in the same Hunspell dictionary Vale's speller
  consults (vendored to ``registries/glossary/english-words.txt`` from Vale's ``en_US-web.dic``).
  The uniform-case guard is load-bearing: "vista" *is* an English word, but the brand surface
  ``VistA`` is mixed-case typography no English word takes, so it is always safe to force-case —
  a naive lowercase-membership check would wrongly veto ``VistA`` and break the Vista→VistA gate.
* ``selective_casing_swap`` — project the safe set (``enforce_case && !collides``, single token)
  into a Vale ``substitution`` swap of canonical→canonical identity entries, which (with
  ``ignorecase: true``) flags any *mis*-casing while leaving the canonical form and every
  colliding word untouched.

Both functions are pure (no I/O): the English word set is passed in; the loader and Vale-style
rendering live in ``kernel.termbase`` (the I/O boundary).
"""

from __future__ import annotations

from collections.abc import Iterable, Set


def collides_with_english(surface: str, english_words: Set[str]) -> bool:
    """True when force-casing ``surface`` would flag ordinary English prose.

    A surface collides iff its lowercase form is in ``english_words`` **and** it is not
    *brand-cased*. Brand-cased means distinctive internal typography no English word takes —
    mixed upper/lower that is **not** plain Title-case: ``VistA``, ``FileMan`` (``surface !=
    surface.capitalize()``). Those are always safe to enforce even though "vista" is a word.

    The guard is load-bearing in two directions: a naive lowercase-membership check would wrongly
    veto ``VistA``; but treating *any* mixed case as a brand would wrongly enforce Title-case
    common words (``Site``, ``Host``, ``Map``) and flag ordinary "site"/"host"/"map" in prose.
    All-caps acronyms (``CAN``, ``SITE``) and Title-case words (``Site``) both collide; only
    internal-capital brands escape.
    """
    if not surface or surface.lower() not in english_words:
        return False
    has_upper = any(c.isupper() for c in surface)
    has_lower = any(c.islower() for c in surface)
    brand_cased = has_upper and has_lower and surface != surface.capitalize()
    return not brand_cased


def selective_casing_swap(
    *,
    terms: Iterable[str],
    english_words: Set[str],
    no_enforce: Set[str],
) -> dict[str, str]:
    """The safe casing map: ``{term: term}`` (canonical→canonical) for each single-token term
    whose casing is safe to enforce — i.e. not opted out (``no_enforce``) and not colliding with
    English. Multiword terms are skipped (Vale substitutions match per token). Sorted + deduped
    for deterministic diffs."""
    swap: dict[str, str] = {}
    for term in terms:
        if not term or " " in term:
            continue
        if term in no_enforce or collides_with_english(term, english_words):
            continue
        swap[term] = term
    return dict(sorted(swap.items()))
