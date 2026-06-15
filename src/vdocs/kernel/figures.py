"""Figure/asset resolution — the single home (§9.2/§11) for "which figures does a body reference,
and where do they live in the asset CAS".

``convert`` rewrites every inline image ref to a content-addressed ``<sha>.<ext>`` asset basename
(stored flat at ``DATA_DIR/documents/assets/``). Two consumers need to map a gold/normalized body
back to those on-disk asset files: ``index`` (count a doc's figures + sum their bytes for the
read-contract figure stats) and the **rich-publication subset bundle** (collect the curated docs'
assets to ship alongside ``index.db``). The ref-parsing lives in ``kernel.markdown.image_targets``;
the *resolution* (basename → on-disk file, skip what doesn't resolve) lives here once, so a ref to a
missing/external asset is handled identically everywhere.

Pure-ish I/O boundary: it reads filesystem metadata (existence, size) and returns plain values.
"""

from __future__ import annotations

from pathlib import Path

from vdocs.kernel import markdown


def resolve_assets(body: str, assets_dir: Path) -> list[Path]:
    """The asset files ``body`` references that actually exist in ``assets_dir`` — deduped in
    first-seen order. A ref whose ``<sha>.<ext>`` basename has no file in the CAS (a missing or
    external image) is skipped; an absent ``assets_dir`` resolves nothing rather than raising."""
    out: list[Path] = []
    for name in markdown.image_targets(body):
        p = assets_dir / name
        if p.is_file():
            out.append(p)
    return out


def asset_stats(body: str, assets_dir: Path) -> tuple[int, int]:
    """``(image_count, image_bytes)`` for a doc — the distinct figures it references that resolve in
    the asset CAS, and their total bytes. The per-doc figure stat ``index`` records; the subset
    bundle's size is the *union* of resolved assets across docs (a shared image counts once), of
    which this per-doc sum is the safe upper bound."""
    paths = resolve_assets(body, assets_dir)
    return len(paths), sum(p.stat().st_size for p in paths)
