"""Load the corpus admission gate from the version-controlled policy registries (I/O).

Thin loader (not pure — it reads YAML), mirroring ``catalog/registries.py``. Reads
``registries/inventory/scope-policy.yaml`` (app scope) and ``doctype-policy.yaml`` (doc-type
keep/omit) into the pure :class:`vdocs.stages.fetch.fetch_pure.GatePolicy` enforced by
``select_fetch_targets``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from vdocs.stages.fetch.fetch_pure import GatePolicy


def _read(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_gate_policy(registries_dir: Path) -> GatePolicy:
    """Build the :class:`GatePolicy` from ``registries/inventory/{scope,doctype}-policy.yaml``."""
    inv = registries_dir / "inventory"
    scope = _read(inv / "scope-policy.yaml").get("app_scope", {})
    doctypes = _read(inv / "doctype-policy.yaml").get("doctypes", {})
    omitted = frozenset(
        code for code, spec in doctypes.items() if (spec or {}).get("decision") == "omit"
    )
    return GatePolicy(
        allowed_system_prefixes=tuple(scope.get("allowed_system_type_prefixes", [])),
        denied_app_status=frozenset(scope.get("denied_app_status", [])),
        omitted_doc_codes=omitted,
    )


@dataclass(frozen=True)
class DocTypeRule:
    """One doc-type's policy row for the operator-facing ``vdocs gate`` explain (label + reason)."""

    code: str
    tier: str
    decision: str
    label: str
    reason: str


@dataclass(frozen=True)
class GateConfig:
    """The human-readable assembled gate config behind ``vdocs gate`` — the same files
    :func:`load_gate_policy` enforces, kept with their labels/reasons for display."""

    allowed_system_prefixes: tuple[str, ...]
    denied_app_status: tuple[str, ...]
    default_doctype: str
    doctypes: tuple[DocTypeRule, ...]

    @property
    def kept(self) -> tuple[DocTypeRule, ...]:
        return tuple(d for d in self.doctypes if d.decision == "keep")

    @property
    def omitted(self) -> tuple[DocTypeRule, ...]:
        return tuple(d for d in self.doctypes if d.decision == "omit")


def load_gate_config(registries_dir: Path) -> GateConfig:
    """Load the gate registries as a display structure (labels + reasons + the ``default``)."""
    inv = registries_dir / "inventory"
    scope = _read(inv / "scope-policy.yaml").get("app_scope", {})
    raw = _read(inv / "doctype-policy.yaml")
    rules = tuple(
        DocTypeRule(
            code=code,
            tier=str((spec or {}).get("tier", "")),
            decision=str((spec or {}).get("decision", "")),
            label=str((spec or {}).get("label", "")),
            reason=str((spec or {}).get("reason", "")),
        )
        for code, spec in (raw.get("doctypes") or {}).items()
    )
    return GateConfig(
        allowed_system_prefixes=tuple(scope.get("allowed_system_type_prefixes", [])),
        denied_app_status=tuple(scope.get("denied_app_status", [])),
        default_doctype=str(raw.get("default", "keep")),
        doctypes=rules,
    )
