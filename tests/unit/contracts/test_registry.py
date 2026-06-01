"""Unit tests for contracts.registry — the single artifact registry (§7.1, §11)."""

import pytest

from vdocs.contracts.registry import ArtifactRegistry, foundational_registry
from vdocs.models.artifact import ArtifactContract, Kind, StorageClass


def _c(key: str) -> ArtifactContract:
    return ArtifactContract(
        key=key,
        kind=Kind.FILE,
        storage_class=StorageClass.TEXT_VERSIONED,
        relpath=f"{key}.txt",
    )


def test_register_and_get_round_trip():
    reg = ArtifactRegistry()
    c = _c("a")
    reg.register(c)
    assert reg.get("a") is c
    assert "a" in reg


def test_register_duplicate_key_raises():
    reg = ArtifactRegistry()
    reg.register(_c("a"))
    with pytest.raises(ValueError):
        reg.register(_c("a"))


def test_get_missing_key_raises():
    reg = ArtifactRegistry()
    with pytest.raises(KeyError):
        reg.get("nope")


def test_all_returns_every_registered_contract():
    reg = ArtifactRegistry()
    reg.register(_c("a"))
    reg.register(_c("b"))
    assert {c.key for c in reg.all()} == {"a", "b"}


def test_foundational_registry_declares_external_vdl():
    reg = foundational_registry()
    vdl = reg.get("vdl")
    assert vdl.kind is Kind.EXTERNAL
    assert vdl.produced_by is None
