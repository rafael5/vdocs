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


# --- inventory medallion (§4, §5.3, §8) ---
# The inventory catalog manifests are control-plane bookkeeping describing what exists
# upstream — regenerated each crawl, so STATE-class (not content-addressed evidence, not
# versioned text). They live on the inventory track's own bronze/silver, separate from the
# document medallion's content-addressed `raw` tree.
CATALOG_RAW = ArtifactContract(
    key="inventory/catalog.raw",
    kind=Kind.FILE,
    storage_class=StorageClass.STATE,
    produced_by="crawl",
    relpath="inventory/bronze/catalog.raw.json",
)
CATALOG_ENRICHED = ArtifactContract(
    key="inventory/catalog.enriched",
    kind=Kind.FILE,
    storage_class=StorageClass.STATE,
    produced_by="catalog",
    relpath="inventory/silver/catalog.enriched.json",
)
RAW_TREE = ArtifactContract(
    key="bronze/raw",
    kind=Kind.TREE_ASSET_CAS,
    storage_class=StorageClass.ASSET_WRITE_ONCE,
    produced_by="fetch",
    relpath="bronze/raw",
)
RAW_INDEX = ArtifactContract(
    key="bronze/raw/index.json",
    kind=Kind.FILE,
    storage_class=StorageClass.STATE,
    produced_by="fetch",
    relpath="bronze/raw/index.json",
)


def foundational_registry() -> ArtifactRegistry:
    """Build a registry seeded with the artifacts that exist before any stage runs."""
    reg = ArtifactRegistry()
    reg.register(VDL)
    return reg


def default_registry() -> ArtifactRegistry:
    """The registry of every artifact declared so far (foundational + bronze)."""
    reg = foundational_registry()
    for contract in (CATALOG_RAW, CATALOG_ENRICHED, RAW_TREE, RAW_INDEX):
        reg.register(contract)
    return reg
