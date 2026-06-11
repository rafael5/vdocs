"""The published **read contract** (ADR-0001): the versioned, consumer-facing interface over
``index.db``. ``contracts/read/v<MAJOR>.json`` is the single source of truth; the ``v_*`` views are
GENERATED from it (:func:`view_ddl`) so they cannot drift from the spec, and ``vdocs doctor``
asserts the emitted DB matches it (:func:`view_columns`). Consumers (vdocs-tui, vdocs-web, MCP) bind
only to the views + the named ``chunks_fts`` surface — never to physical tables — so the pipeline
can refactor the physical schema freely behind them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

Spec = dict[str, Any]


def contract_dir() -> Path:
    """The in-repo read-contract directory (sibling to ``registries/``, not in the lake)."""
    # src/vdocs/kernel/read_contract.py → repo root = parents[3]
    return Path(__file__).resolve().parents[3] / "contracts" / "read"


def contract_path(version_major: int = 1, *, base: Path | None = None) -> Path:
    """Path to the ``v<MAJOR>.json`` spec (``base`` overrides the default dir, e.g. from config)."""
    return (base or contract_dir()) / f"v{version_major}.json"


def load(path: Path) -> Spec:
    """Parse a read-contract spec file."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def version(spec: Spec) -> str:
    """The ``read_schema_version`` the spec declares."""
    return str(spec["read_schema_version"])


def capabilities(spec: Spec) -> list[str]:
    """The named capabilities consumers can require (e.g. ``fts5``, ``pub_year``)."""
    return list(spec.get("capabilities", []))


def view_columns(spec: Spec) -> dict[str, list[str]]:
    """Map each view name → its ordered column names (the contract surface to validate against)."""
    return {name: list(v["columns"].keys()) for name, v in spec.get("views", {}).items()}


def view_ddl(spec: Spec) -> str:
    """Generate the ``CREATE VIEW`` DDL for every view in the spec — the views ARE the spec."""
    stmts = [
        f"CREATE VIEW {name} AS SELECT {', '.join(v['columns'].keys())} FROM {v['source']};"
        for name, v in spec.get("views", {}).items()
    ]
    return "\n".join(stmts) + ("\n" if stmts else "")


def _column_types(spec: Spec) -> dict[str, dict[str, str]]:
    """``{view: {column: declared type}}`` — for detecting breaking type changes."""
    return {
        name: {col: str(meta.get("type", "")) for col, meta in v["columns"].items()}
        for name, v in spec.get("views", {}).items()
    }


def _parse_version(v: str) -> tuple[int, int]:
    major, _, minor = v.partition(".")
    return int(major), int(minor or 0)


def lint_bump(prev: Spec, nxt: Spec) -> list[str]:
    """Enforce semver bump-type between two contract versions (ADR-0001 P1.6): a **breaking** change
    (removed view/column, column type change, removed capability) requires a MAJOR bump; a purely
    **additive** change (new view/column/capability) requires at least a MINOR bump. Returns the
    list of violations (empty = the bump is correctly sized)."""
    prev_t, next_t = _column_types(prev), _column_types(nxt)
    breaking: list[str] = []
    additive: list[str] = []

    for view, cols in prev_t.items():
        if view not in next_t:
            breaking.append(f"view {view} removed")
            continue
        for col, typ in cols.items():
            if col not in next_t[view]:
                breaking.append(f"{view}.{col} removed")
            elif next_t[view][col] != typ:
                breaking.append(f"{view}.{col} type {typ}→{next_t[view][col]}")
    for view, cols in next_t.items():
        if view not in prev_t:
            additive.append(f"view {view} added")
        else:
            additive += [f"{view}.{c} added" for c in cols if c not in prev_t[view]]

    prev_caps, next_caps = set(capabilities(prev)), set(capabilities(nxt))
    breaking += [f"capability {c} removed" for c in prev_caps - next_caps]
    additive += [f"capability {c} added" for c in next_caps - prev_caps]

    (pmaj, pmin), (nmaj, nmin) = _parse_version(version(prev)), _parse_version(version(nxt))
    problems: list[str] = []
    if breaking and nmaj <= pmaj:
        problems.append(
            f"breaking changes require a MAJOR bump ({pmaj}.x→{pmaj + 1}.0): {breaking}"
        )
    elif additive and not breaking and (nmaj, nmin) <= (pmaj, pmin):
        problems.append(f"additive changes require at least a MINOR bump: {additive}")
    return problems


def lint_latest(base: Path | None = None) -> list[str]:
    """Lint the two highest-numbered ``v<N>.json`` specs in ``base`` (the ``make contract-lint``
    gate). A no-op while only one version exists; activates the moment a v2 is authored."""
    d = base or contract_dir()
    versions = sorted(int(p.stem[1:]) for p in d.glob("v*.json") if p.stem[1:].isdigit())
    if len(versions) < 2:
        return []
    return lint_bump(load(d / f"v{versions[-2]}.json"), load(d / f"v{versions[-1]}.json"))
