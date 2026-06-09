"""Load the corpus admission gate from the version-controlled policy registries (I/O).

Thin loader (not pure — it reads YAML), mirroring ``catalog/registries.py``. Reads
``registries/inventory/scope-policy.yaml`` (app scope) and ``doctype-policy.yaml`` (doc-type
keep/omit) into the pure :class:`vdocs.stages.fetch.fetch_pure.GatePolicy` enforced by
``select_fetch_targets``.
"""

from __future__ import annotations

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
