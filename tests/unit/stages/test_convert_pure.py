"""Unit tests for convert pure logic — bundle paths + image-ref rewriting (§5.2, §8)."""

from __future__ import annotations

from pathlib import Path

from vdocs.stages.convert import convert_pure as cp


def test_bundle_dir():
    root = Path("/lake/silver/text/01-converted")
    assert cp.bundle_dir(root, "ADT", "dg_5_3_1057_dibr") == root / "ADT" / "dg_5_3_1057_dibr"
    # slash in app code is sanitised for the filesystem
    assert cp.bundle_dir(root, "AR/WS", "x") == root / "AR_WS" / "x"


def test_asset_filename():
    assert cp.asset_filename("abc123", "png") == "abc123.png"
    assert cp.asset_filename("abc123", "") == "abc123"


def test_image_basename_handles_paths_and_slashes():
    assert cp.image_basename("/tmp/tmpXXX/media-root/media/image1.png") == "image1.png"
    assert cp.image_basename("media/image2.jpg") == "image2.jpg"
    assert cp.image_basename("logo.png") == "logo.png"


def test_rewrite_image_refs_markdown_and_html_by_basename():
    # Pandoc emits HTML <img> (absolute temp path) for sized images, markdown for plain ones —
    # both are matched by basename and repointed to the asset filename.
    md = (
        "# Title\n\n"
        "![logo](media/image1.png)\n"
        '<img src="/tmp/tmpQ/media-root/media/image2.gif" style="width:2in" alt="VA logo" />\n'
        "![external](https://example/other.png)\n"
    )
    out = cp.rewrite_image_refs(md, {"image1.png": "aaa.png", "image2.gif": "bbb.gif"})
    assert "![logo](aaa.png)" in out
    assert '<img src="bbb.gif" style="width:2in" alt="VA logo" />' in out  # the real-data bug
    assert "![external](https://example/other.png)" in out  # unknown basename untouched


def test_rewrite_image_refs_noop_when_no_map():
    md = "![x](media/y.png)"
    assert cp.rewrite_image_refs(md, {}) == md
