"""Tests for the shared figure/asset-resolution primitives (kernel/figures.py, §9.2).

The single home for "given a gold body + the asset CAS, which figures does it reference and where do
they live on disk" — used by `index` (count/bytes per doc) and the rich-publication subset bundle.
"""

from __future__ import annotations

from pathlib import Path

from vdocs.kernel import figures


def _asset(assets: Path, name: str, data: bytes) -> None:
    (assets / name).write_bytes(data)


def test_resolve_assets_returns_existing_referenced_files_deduped(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    _asset(assets, "abc123.png", b"\x89PNG-one")
    _asset(assets, "def456.jpg", b"jpeg-two")
    body = (
        "# Doc\n\ntext\n\n"
        "![a fig](abc123.png)\n"
        '<img src="def456.jpg" alt="x"/>\n'
        "![again](abc123.png)\n"  # dup -> resolved once
        "![nested](media/def456.jpg)\n"  # basename matches the same on-disk asset -> still once
    )
    got = figures.resolve_assets(body, assets)
    assert got == [assets / "abc123.png", assets / "def456.jpg"]  # first-seen order, deduped


def test_resolve_assets_skips_refs_with_no_file_in_cas(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    _asset(assets, "present.png", b"here")
    body = "![ok](present.png)\n![missing](gone.png)\n![external](https://x/y.png)\n"
    assert figures.resolve_assets(body, assets) == [assets / "present.png"]


def test_resolve_assets_empty_when_no_images_or_missing_dir(tmp_path):
    assert figures.resolve_assets("# Title\n\njust prose, [a link](x).\n", tmp_path) == []
    # an absent assets dir resolves nothing rather than raising
    assert figures.resolve_assets("![x](a.png)\n", tmp_path / "nope") == []


def test_asset_stats_counts_and_sums_resolved_bytes(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    _asset(assets, "a.png", b"12345")  # 5 bytes
    _asset(assets, "b.png", b"678")  # 3 bytes
    body = "![one](a.png)\n![two](b.png)\n![missing](c.png)\n![dup](a.png)\n"
    assert figures.asset_stats(body, assets) == (2, 8)  # 2 distinct resolved figures, 5+3 bytes


def test_asset_stats_zero_when_no_resolved_figures(tmp_path):
    assert figures.asset_stats("# Title\n\nprose only\n", tmp_path) == (0, 0)
