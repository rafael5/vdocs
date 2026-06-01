"""The artifact registry — one place where every ArtifactContract is declared (§7.1, §11).

Stages reference artifacts by ``key``; the registry is the single lookup so a key is
defined exactly once. As stages land per phase, their produced/consumed contracts are
added here — never redeclared inline. Phase 1 seeds only the external ``vdl`` source;
bronze→gold artifacts arrive with their stages.
"""

from __future__ import annotations

from vdocs.models.artifact import ArtifactContract, Kind, StorageClass


class ArtifactRegistry:
    """A name→contract map enforcing one definition per artifact key."""

    def __init__(self) -> None:
        self._by_key: dict[str, ArtifactContract] = {}

    def register(self, contract: ArtifactContract) -> ArtifactContract:
        if contract.key in self._by_key:
            raise ValueError(f"artifact {contract.key!r} already registered")
        self._by_key[contract.key] = contract
        return contract

    def get(self, key: str) -> ArtifactContract:
        return self._by_key[key]

    def all(self) -> list[ArtifactContract]:
        return list(self._by_key.values())

    def __contains__(self, key: object) -> bool:
        return key in self._by_key


# The canonical external source: the VDL website (§8, the `crawl` input). It is the one
# artifact with no producer and no lake location.
VDL = ArtifactContract(
    key="vdl",
    kind=Kind.EXTERNAL,
    storage_class=StorageClass.EXTERNAL,
    produced_by=None,
)


def foundational_registry() -> ArtifactRegistry:
    """Build a registry seeded with the artifacts that exist before any stage runs."""
    reg = ArtifactRegistry()
    reg.register(VDL)
    return reg
