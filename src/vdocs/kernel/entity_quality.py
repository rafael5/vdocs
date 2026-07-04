"""The entity-quality registry (D2.5) — the type-level quality contract, as data.

Every entity type shipping in ``index.db`` is declared in
``registries/entity-quality.yaml`` with one of three statuses:

- ``floor-verified`` — joins a named authoritative vocabulary (the vista-meta
  ``data-v1`` export) at a measured rate; the declared ``floor`` is the release
  gate's regression tripwire (a number, not an adjective).
- ``no-authoritative-vocabulary`` — no membership oracle exists; shipped as
  declared-unverified.
- ``excluded`` — quarantined at emit: `index` skips the type's recognizers, so
  mentions and (rebuilt) relations cascade to zero; `doctor` fails on residue.

The registry is the single authority — index, manifest, doctor and the release
gate all read it through this loader. A malformed declaration raises: no
partial quality contract is ever consumed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from vdocs.kernel import registry as kregistry

STATUSES = ("floor-verified", "no-authoritative-vocabulary", "excluded")


@dataclass(frozen=True)
class EntityTypePolicy:
    status: str
    floor: float = 0.0
    vocabulary: str = ""
    reason: str = ""


@dataclass(frozen=True)
class EntityQuality:
    types: dict[str, EntityTypePolicy] = field(default_factory=dict)
    peer_vocabulary: dict[str, str] = field(default_factory=dict)

    def excluded_types(self) -> frozenset[str]:
        return frozenset(t for t, p in self.types.items() if p.status == "excluded")


def load_entity_quality(registries_dir: Path) -> EntityQuality:
    """Load ``registries/entity-quality.yaml``; absent file → empty policy (no-op)."""
    raw = kregistry.load_mapping(registries_dir / "entity-quality.yaml", missing_ok=True)
    types: dict[str, EntityTypePolicy] = {}
    for name, spec in (raw.get("types") or {}).items():
        spec = spec or {}
        status = str(spec.get("status", ""))
        if status not in STATUSES:
            raise ValueError(f"entity-quality: type {name!r} has unknown status {status!r}")
        policy = EntityTypePolicy(
            status=status,
            floor=float(spec.get("floor", 0.0)),
            vocabulary=str(spec.get("vocabulary", "")),
            reason=str(spec.get("reason", "")),
        )
        if status == "floor-verified" and not (policy.floor > 0 and policy.vocabulary):
            raise ValueError(
                f"entity-quality: floor-verified type {name!r} needs both a floor and a vocabulary"
            )
        types[name] = policy
    peer = {k: str(v) for k, v in (raw.get("peer_vocabulary") or {}).items()}
    return EntityQuality(types=types, peer_vocabulary=peer)
