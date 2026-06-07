"""Unit tests for contracts.registry — the single artifact registry (§7.1, §11)."""

import pytest

from vdocs.contracts.registry import (
    ArtifactRegistry,
    default_registry,
    foundational_registry,
)
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


def test_default_registry_declares_bronze_artifacts():
    reg = default_registry()
    keys = {c.key for c in reg.all()}
    assert {
        "vdl",
        "inventory/catalog.raw",
        "inventory/catalog.enriched",
        "bronze/raw",
        "bronze/raw/index.json",
        "registries",
    } <= keys
    assert reg.get("bronze/raw").produced_by == "fetch"


def test_default_registry_declares_ai_corpus_card(tmp_path):
    # the AI corpus card (§14.7) — both renderings are manifest-produced gold files
    reg = default_registry()
    keys = {c.key for c in reg.all()}
    assert {"gold/ai-manifest.json", "gold/CORPUS.md"} <= keys
    for key in ("gold/ai-manifest.json", "gold/CORPUS.md"):
        c = reg.get(key)
        assert c.produced_by == "manifest"
        assert c.kind is Kind.FILE


def test_registries_contract_resolves_to_repo_dir_and_fingerprints_edits(tmp_path):
    # REGISTRIES is curated repo config (root=REGISTRIES), not lake data — but a *real* tree
    # fingerprint so a curation edit invalidates its consumers' inputs (§7.3, §8 note).
    from vdocs.config import Settings
    from vdocs.contracts.registry import REGISTRIES
    from vdocs.models.artifact import Kind, Root

    regs = tmp_path / "registries"
    (regs / "phrases").mkdir(parents=True)
    (regs / "phrases" / "phrases.yaml").write_text("phrases: []\n")
    cfg = Settings(data_dir=tmp_path / "lake", registries_dir=regs)

    assert REGISTRIES.root is Root.REGISTRIES
    assert REGISTRIES.kind is Kind.TREE_TEXT
    assert REGISTRIES.produced_by is None  # curated input, like the external VDL source
    assert REGISTRIES.locate(cfg).path == regs
    assert REGISTRIES.validate(cfg).ok

    fp1 = REGISTRIES.fingerprint(cfg)
    # a curation edit to a pattern registry (in its §11 subdir) changes the tree signature
    (regs / "phrases" / "phrases.yaml").write_text("phrases:\n  - End of document\n")
    assert REGISTRIES.fingerprint(cfg) != fp1
