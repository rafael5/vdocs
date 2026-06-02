"""Unit tests for ``kernel/registry`` — the shared curated-YAML loader (§9.2/§11).

The ``exists?→read_text→yaml.safe_load or {}`` pattern was duplicated ~10× across
``catalog``/``convert``/``normalize`` registry loaders; it lives once here.
"""

from __future__ import annotations

import pytest

from vdocs.kernel import registry


def test_load_mapping_reads_yaml_mapping(tmp_path):
    p = tmp_path / "phrases.yaml"
    p.write_text("phrases:\n  - foo\n  - bar\n", encoding="utf-8")
    assert registry.load_mapping(p) == {"phrases": ["foo", "bar"]}


def test_load_mapping_empty_file_is_empty_dict(tmp_path):
    p = tmp_path / "empty.yaml"
    p.write_text("", encoding="utf-8")
    assert registry.load_mapping(p) == {}


def test_load_mapping_missing_ok_returns_empty(tmp_path):
    """A curated registry that hasn't been populated yet → a no-op empty mapping."""
    assert registry.load_mapping(tmp_path / "absent.yaml", missing_ok=True) == {}


def test_load_mapping_missing_not_ok_raises(tmp_path):
    """A required inventory vocabulary that is absent is a loud failure, not a silent empty."""
    with pytest.raises(FileNotFoundError):
        registry.load_mapping(tmp_path / "absent.yaml")
