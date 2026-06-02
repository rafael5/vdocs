"""Unit tests for convert pure logic — bundle paths + image-ref rewriting (§5.2, §8)."""

from __future__ import annotations

from pathlib import Path

from vdocs.stages.convert import convert_pure as cp


def test_safe_component_sanitises_slashes_and_plus():
    # case-preserving sanitiser: only path-unsafe runs collapse to '_' (slashes, '+', spaces)
    assert cp.safe_component("AR/WS") == "AR_WS"
    assert cp.safe_component("DRM+") == "DRM"  # trailing '_' trimmed
    assert cp.safe_component("ADT") == "ADT"
    assert cp.safe_component("///") == "_"


def test_bundle_dir():
    root = Path("/lake/silver/text/01-converted")
    assert cp.bundle_dir(root, "ADT", "dg_5_3_1057_dibr") == root / "ADT" / "dg_5_3_1057_dibr"
    # slash in app code is sanitised for the filesystem
    assert cp.bundle_dir(root, "AR/WS", "x") == root / "AR_WS" / "x"


def test_asset_filename():
    assert cp.asset_filename("abc123", "png") == "abc123.png"
    assert cp.asset_filename("abc123", "") == "abc123"


def test_rewrite_image_refs_repoints_known_targets_only():
    md = (
        "# Title\n\n"
        "![logo](media/image1.png)\n"
        "![diagram](media/image2.jpg 'a title')\n"
        "![external](https://example/x.png)\n"
    )
    out = cp.rewrite_image_refs(md, {"media/image1.png": "aaa.png", "media/image2.jpg": "bbb.jpg"})
    assert "![logo](aaa.png)" in out
    assert "![diagram](bbb.jpg 'a title')" in out
    assert "![external](https://example/x.png)" in out  # unknown target untouched


def test_rewrite_image_refs_noop_when_no_map():
    md = "![x](media/y.png)"
    assert cp.rewrite_image_refs(md, {}) == md
