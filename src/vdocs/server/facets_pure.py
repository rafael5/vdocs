"""Pure helpers for faceted (focused) search (LF) — no I/O, just narrowing logic.

Faceted search narrows the corpus by structured facets *before* content search, so the heavy
lifting is exact SQL filtering, not ranking. Every facet — including the two persona axes
(`app_user`, `doc_user`) and the profile attributes (`software_class`, `function_category`) — is a
**baked column** on `documents` (resolved once at `enrich` from app-profiles.yaml + doc-user.yaml;
see `kernel.personas`). So narrowing is a uniform column `IN (...)` filter; the registries don't
need to be present at serve time.

**Two persona axes, one vocabulary** (`clinical · clinical-admin · business-admin · developer ·
sysadmin`): `app_user` = who *operates the app*; `doc_user` = who *reads the doc* (operator-facing
doc-types already delegated to the app's `app_user` at bake time).
"""

from __future__ import annotations


def _in(col: str, values: list[str]) -> tuple[str, list[str]]:
    """`col IN (?, …)` + its params."""
    return f"{col} IN ({', '.join('?' for _ in values)})", list(values)


def narrow_clause(
    doc_type: list[str] | None = None,
    app: list[str] | None = None,
    pkg_ns: list[str] | None = None,
    app_user: list[str] | None = None,
    doc_user: list[str] | None = None,
    software_class: list[str] | None = None,
    function_category: list[str] | None = None,
) -> tuple[str, list[str]]:
    """A `WHERE` fragment (always `is_latest = 1`) + params for the explicit facet filters, each a
    baked `documents` column. Columns are ANDed in a fixed order; absent facets are skipped."""
    clauses = ["is_latest = 1"]
    params: list[str] = []
    for col, values in (
        ("doc_type", doc_type),
        ("app_code", app),
        ("pkg_ns", pkg_ns),
        ("app_user", app_user),
        ("doc_user", doc_user),
        ("software_class", software_class),
        ("function_category", function_category),
    ):
        if values:
            clause, p = _in(col, values)
            clauses.append(clause)
            params += p
    return " AND ".join(clauses), params
