"""Unit: the entity-quality registry (D2.5) — the type-level quality contract.

Every entity type shipping in index.db must be declared with a status —
floor-verified (measured rate >= floor vs a named vocabulary), no-authoritative-
vocabulary, or excluded (quarantined at emit, cascading). The registry is the
single authority: index (rule filtering), manifest (declaration block), doctor
(residue check) and the release gate all read it.
"""

from __future__ import annotations

import pytest

from vdocs.kernel.entity_quality import EntityTypePolicy, load_entity_quality

_YAML = """\
peer_vocabulary:
  artifact: vista-meta-data
  tag: data-v1
  content_hash: "23d0" # abridged
types:
  fileman_file: {status: floor-verified, floor: 0.80, vocabulary: "files.tsv:file_number"}
  option:       {status: excluded, reason: "1.7% join — prose noise"}
  build:        {status: no-authoritative-vocabulary}
"""


def test_loads_types_with_status_and_floor(tmp_path):
    (tmp_path / "entity-quality.yaml").write_text(_YAML, encoding="utf-8")
    q = load_entity_quality(tmp_path)
    assert q.types["fileman_file"] == EntityTypePolicy(
        status="floor-verified", floor=0.80, vocabulary="files.tsv:file_number", reason=""
    )
    assert q.types["option"].status == "excluded"
    assert q.peer_vocabulary["content_hash"] == "23d0"


def test_excluded_types_helper(tmp_path):
    (tmp_path / "entity-quality.yaml").write_text(_YAML, encoding="utf-8")
    assert load_entity_quality(tmp_path).excluded_types() == frozenset({"option"})


def test_floor_verified_requires_floor_and_vocabulary(tmp_path):
    (tmp_path / "entity-quality.yaml").write_text(
        "types:\n  rpc: {status: floor-verified}\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="rpc"):
        load_entity_quality(tmp_path)


def test_unknown_status_is_loud(tmp_path):
    (tmp_path / "entity-quality.yaml").write_text(
        "types:\n  rpc: {status: probably-fine}\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="probably-fine"):
        load_entity_quality(tmp_path)


def test_missing_registry_means_no_policy(tmp_path):
    q = load_entity_quality(tmp_path)
    assert q.types == {} and q.excluded_types() == frozenset()
