"""Pure helpers for faceted (focused) search (LF) — no I/O, just narrowing logic.

Faceted search narrows the corpus by structured facets (doc_type / package / persona) *before*
content search, so the heavy lifting is exact SQL filtering, not ranking. These helpers build the
`WHERE` fragments + params; the thin I/O driver (`facets.py`) loads the registries and runs them
against `index.db`.

**Two persona axes, one vocabulary** (`clinical · clinical-admin · business-admin · developer ·
sysadmin`):
- **app_user** — who *operates the app* (per `app-profiles.yaml`). `app_user_clause` narrows to the
  apps with that operator.
- **doc_user** — who *reads the doc* (per `doc-user.yaml`). A doc_type is either role-fixed to a
  persona (a Technical Manual is read by developers, any app) or `operator` — read by the app's
  operators, so it resolves to that app's `app_user`. `doc_user_clause` unions the two.
"""

from __future__ import annotations


def _in(col: str, values: list[str]) -> tuple[str, list[str]]:
    """`col IN (?, …)` + its params."""
    return f"{col} IN ({', '.join('?' for _ in values)})", list(values)


def app_codes_for_user(persona: str, app_user_by_app: dict[str, str]) -> list[str]:
    """App codes whose `app_user` (operator) is `persona` (sorted, deterministic)."""
    return sorted(a for a, u in app_user_by_app.items() if u == persona)


def app_user_clause(persona: str, app_user_by_app: dict[str, str]) -> tuple[str, list[str]]:
    """`WHERE` fragment selecting docs whose *app* is operated by `persona`. `("0", [])` if none."""
    apps = app_codes_for_user(persona, app_user_by_app)
    return _in("app_code", apps) if apps else ("0", [])


def doc_user_clause(
    persona: str, doc_user_map: dict[str, str], app_user_by_app: dict[str, str]
) -> tuple[str, list[str]]:
    """`WHERE` fragment selecting docs *read by* `persona` — the union of:

    1. **role-fixed** doc_types mapped straight to `persona` (e.g. developer ⇐ TM/DG/API), and
    2. **operator-facing** doc_types (`operator` in the map) belonging to an app whose `app_user`
       is `persona` (e.g. a clinical-admin clerk reads the User Manuals of clinical-admin apps).

    Returns `("0", [])` when neither branch can match. Branches are OR'd and parenthesised."""
    fixed = sorted(c for c, who in doc_user_map.items() if who == persona)
    operator_codes = sorted(c for c, who in doc_user_map.items() if who == "operator")
    apps = app_codes_for_user(persona, app_user_by_app)

    parts: list[str] = []
    params: list[str] = []
    if fixed:
        clause, p = _in("doc_type", fixed)
        parts.append(clause)
        params += p
    if operator_codes and apps:
        dc, dp = _in("doc_type", operator_codes)
        ac, ap = _in("app_code", apps)
        parts.append(f"({dc} AND {ac})")
        params += dp + ap

    if not parts:
        return "0", []
    if len(parts) == 1:
        return parts[0], params
    return "(" + " OR ".join(parts) + ")", params


def narrow_clause(
    doc_type: list[str] | None = None,
    app: list[str] | None = None,
    pkg_ns: list[str] | None = None,
) -> tuple[str, list[str]]:
    """A `WHERE` fragment (always `is_latest = 1`) + params for the explicit facet filters, in
    column order `doc_type, app_code, pkg_ns`. The persona axes (`app_user`/`doc_user`) are added
    as extra `AND` clauses by the driver via :func:`app_user_clause` / :func:`doc_user_clause`."""
    clauses = ["is_latest = 1"]
    params: list[str] = []
    for col, values in (("doc_type", doc_type), ("app_code", app), ("pkg_ns", pkg_ns)):
        if values:
            clause, p = _in(col, values)
            clauses.append(clause)
            params += p
    return " AND ".join(clauses), params
