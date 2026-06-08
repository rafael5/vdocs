"""Pure helpers for faceted (focused) search (LF) — no I/O, just narrowing logic.

Faceted search narrows the corpus by structured facets (doc_type / audience / package) *before*
content search, so the heavy lifting is exact SQL filtering, not ranking. These helpers build the
`WHERE` fragment + params and resolve the audience facet to its doc_type codes; the thin I/O driver
(`facets.py`) runs them against `index.db`.
"""

from __future__ import annotations


def audience_codes(audience: str, mapping: dict[str, str]) -> list[str]:
    """The doc_type codes whose audience equals `audience` (sorted, deterministic)."""
    return sorted(code for code, aud in mapping.items() if aud == audience)


def resolve_doc_types(
    doc_type: list[str] | None, audience: str | None, mapping: dict[str, str]
) -> list[str]:
    """The effective doc_type filter: explicit codes ∪ the audience's codes (de-duped, sorted)."""
    codes = set(doc_type or [])
    if audience:
        codes |= set(audience_codes(audience, mapping))
    return sorted(codes)


def narrow_clause(
    doc_type: list[str] | None = None,
    app: list[str] | None = None,
    pkg_ns: list[str] | None = None,
) -> tuple[str, list[str]]:
    """A `WHERE` fragment (always `is_latest = 1`) + params for the given facet filters, in column
    order `doc_type, app_code, pkg_ns`. Each filter becomes an `IN (?, …)` with one placeholder per
    value. Audience is resolved to `doc_type` codes upstream (`resolve_doc_types`)."""
    clauses = ["is_latest = 1"]
    params: list[str] = []
    for col, values in (("doc_type", doc_type), ("app_code", app), ("pkg_ns", pkg_ns)):
        if values:
            clauses.append(f"{col} IN ({', '.join('?' for _ in values)})")
            params.extend(values)
    return " AND ".join(clauses), params
