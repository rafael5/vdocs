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
    """A compiled recognizer for one entity type (pattern-mode or terms-mode)."""

    type: str
    regex: re.Pattern[str]
    canonical_group: int  # 0 = whole match, 1 = capture group 1
    casefold: bool


def compile_rules(entries: list[dict]) -> list[EntityRule]:
    """Compile curated `registries/entities` entries into recognizers (pure).

    A `terms` rule is compiled to a single whole-word alternation regex, so both modes share one
    fast scan path. A rule with neither `pattern` nor `terms` is a curation error — fail loud."""
    rules: list[EntityRule] = []
    for e in entries:
        etype = e["type"]
        if "pattern" in e:
            regex = re.compile(e["pattern"])
            group = 1 if e.get("canonical") == "group1" else 0
            rules.append(EntityRule(etype, regex, group, bool(e.get("casefold"))))
        elif "terms" in e:
            terms = sorted((str(t) for t in e["terms"]), key=len, reverse=True)
            flags = 0 if e.get("case_sensitive") else re.IGNORECASE
            alt = "|".join(re.escape(t) for t in terms)
            regex = re.compile(rf"(?<![A-Za-z0-9])(?:{alt})(?![A-Za-z0-9])", flags)
            rules.append(EntityRule(etype, regex, 0, bool(e.get("casefold"))))
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
            out.append((rule.type, name.upper() if rule.casefold else name))
    return out
