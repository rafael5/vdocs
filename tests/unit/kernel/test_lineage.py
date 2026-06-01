"""Unit tests for kernel.lineage — provenance stamping (§9.2, §9.4)."""

import pytest

from vdocs.kernel import lineage


def test_stamp_has_required_provenance_keys():
    s = lineage.stamp(source_sha256="a" * 64, tool_ver="0.1.0", at="2026-06-01T00:00:00Z")
    assert s["source_sha256"] == "a" * 64
    assert s["tool_ver"] == "0.1.0"
    assert s["at"] == "2026-06-01T00:00:00Z"


def test_stamp_is_deterministic():
    kw = dict(source_sha256="b" * 64, tool_ver="0.1.0", at="2026-06-01T00:00:00Z")
    assert lineage.stamp(**kw) == lineage.stamp(**kw)


def test_stamp_omits_converter_when_absent():
    s = lineage.stamp(source_sha256="c" * 64, tool_ver="0.1.0", at="t")
    assert "converter" not in s


def test_stamp_includes_converter_when_given():
    s = lineage.stamp(source_sha256="c" * 64, tool_ver="0.1.0", at="t", converter="pandoc")
    assert s["converter"] == "pandoc"


def test_stamp_merges_extra_fields():
    s = lineage.stamp(source_sha256="d" * 64, tool_ver="0.1.0", at="t", extra={"stage": "convert"})
    assert s["stage"] == "convert"


def test_stamp_rejects_empty_source():
    with pytest.raises(ValueError):
        lineage.stamp(source_sha256="", tool_ver="0.1.0", at="t")
