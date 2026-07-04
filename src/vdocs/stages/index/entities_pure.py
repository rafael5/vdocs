"""Generic, registry-driven entity recognition (§8 note, §5.5, D2).

A pure function of `(text, compiled rules)` — the *vocabulary and patterns* live in
`registries/entities` (data), never in this code (tenet #13). Each rule recognizes one entity
`type` either by a regex `pattern` or by a literal `terms` vocabulary; `extract` returns one
`(type, canonical_name)` tuple per occurrence (the caller dedups and counts), so `index` can both
list the global entities and record per-section mentions for `relate`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class EntityRule:
    """A compiled recognizer for one entity type (pattern-mode or terms-mode).

    A rule with a ``vocab`` is membership-validated: the pattern proposes a
    candidate, the named authoritative vocabulary decides — the candidate is
    trimmed word-by-word to its longest vocabulary member, or dropped."""

    type: str
    regex: re.Pattern[str]
    canonical_group: int  # 0 = whole match, 1 = capture group 1
    casefold: bool
    vocab: frozenset[str] | None = None


def compile_rules(
    entries: list[dict],
    *,
    excluded_types: frozenset[str] = frozenset(),
    vocabularies: dict[str, frozenset[str]] | None = None,
) -> list[EntityRule]:
    """Compile curated `registries/entities` entries into recognizers (pure).

    A `terms` rule is compiled to a single whole-word alternation regex, so both modes share one
    fast scan path. A rule with neither `pattern` nor `terms` is a curation error — fail loud.
    Types quarantined by `registries/entity-quality.yaml` (D2.5 `excluded`) never compile: the
    type cannot be extracted, so mentions and rebuilt relations cascade to zero."""
    rules: list[EntityRule] = []
    for e in entries:
        etype = e["type"]
        if etype in excluded_types:
            continue
        vocab: frozenset[str] | None = None
        if "vocab" in e:
            vocab = (vocabularies or {}).get(e["vocab"])
            if vocab is None:
                raise ValueError(
                    f"entity rule {etype!r} names vocabulary {e['vocab']!r} but none was provided"
                )
        if "pattern" in e:
            regex = re.compile(e["pattern"])
            group = 1 if e.get("canonical") == "group1" else 0
            rules.append(EntityRule(etype, regex, group, bool(e.get("casefold")), vocab))
        elif "terms" in e:
            terms = sorted((str(t) for t in e["terms"]), key=len, reverse=True)
            flags = 0 if e.get("case_sensitive") else re.IGNORECASE
            alt = "|".join(re.escape(t) for t in terms)
            regex = re.compile(rf"(?<![A-Za-z0-9])(?:{alt})(?![A-Za-z0-9])", flags)
            rules.append(EntityRule(etype, regex, 0, bool(e.get("casefold")), vocab))
        else:
            raise ValueError(f"entity rule {etype!r} has neither 'pattern' nor 'terms'")
    return rules


def extract(text: str, rules: list[EntityRule]) -> list[tuple[str, str]]:
    """Every `(type, canonical_name)` occurrence in `text`, in rule then match order.

    One tuple per occurrence (not deduped): the caller dedups for the global `entities` table and
    counts for `mention_count`. `canonical_name` is the whole match or capture group 1, uppercased
    when the rule sets `casefold`."""
    out: list[tuple[str, str]] = []
    for rule in rules:
        for m in rule.regex.finditer(text):
            name = m.group(rule.canonical_group)
            if name is None:
                continue
            name = name.upper() if rule.casefold else name
            if rule.vocab is not None:
                name = _longest_vocab_prefix(name, rule.vocab)
                if name is None:
                    continue
            out.append((rule.type, name))
    return out


def _longest_vocab_prefix(candidate: str, vocab: frozenset[str]) -> str | None:
    """The longest leading word-run of ``candidate`` that is a vocabulary member,
    or None — the membership filter behind vocab-validated rules."""
    words = candidate.split()
    for n in range(len(words), 0, -1):
        prefix = " ".join(words[:n])
        if prefix in vocab:
            return prefix
    return None
