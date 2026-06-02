#!/usr/bin/env python3
"""Make silver document bundles previewable offline — without copying asset bytes.

The pipeline stores images write-once in the shared content-addressed store
(``~/data/vdocs/assets/<sha256>.<ext>``, ADR-003) and rewrites each body's inline image refs
to the *bare* asset filename ``<sha>.<ext>`` (``convert``, §5.2). A bare ref resolves relative
to ``body.md``, so a markdown viewer looks for the image *next to* the body — where it isn't —
and nothing renders.

This dev helper builds a throwaway **preview tree** that bridges the gap with a *single*
symlink and zero copied image bytes — effectively a dry-run of the future ``publish`` stage
(images materialised from the asset store, ADR-011):

    ~/data/vdocs/_preview/
      assets -> ../assets               # ONE symlink into the CAS, total
      01-converted/<app>/<slug>/body.md # text copy; refs → ../../../assets/<sha>.<ext>
      02-enriched/...                   # (markdown copies are tiny; images never duplicated)
      03-normalized/...

The canonical silver bundles are left pristine (just ``body.md``). Point any markdown tool
(VS Code preview, grip, Obsidian) at a ``_preview/.../body.md`` and the images render through
the single ``assets`` symlink. Teardown is ``--clean`` (removes the whole ``_preview`` tree).

Usage:
    python scripts/preview.py [PATH] [--clean]

    PATH   subtree of silver/text to mirror; default: the whole silver/text tree.
           e.g. `python scripts/preview.py "$DATA_DIR/silver/text/01-converted/PXRM"`
"""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path

from vdocs.config import Settings
from vdocs.stages.convert.convert_pure import image_basename, image_targets, rewrite_image_refs


def _ensure_assets_symlink(preview_root: Path, assets: Path) -> None:
    """The single ``_preview/assets`` symlink into the shared CAS (idempotent)."""
    link = preview_root / "assets"
    rel = os.path.relpath(assets, preview_root)
    if link.is_symlink():
        if os.readlink(link) == rel:
            return
        link.unlink()
    elif link.exists():
        raise SystemExit(f"refusing to overwrite non-symlink {link}")
    preview_root.mkdir(parents=True, exist_ok=True)
    link.symlink_to(rel)


def build(root: Path, silver_text: Path, assets: Path, preview_root: Path) -> tuple[int, int, int]:
    """Mirror every ``body.md`` under ``root`` into the preview tree with its image refs
    rewritten to point through the single ``assets`` symlink. Returns
    ``(documents, linked_refs, missing_assets)``."""
    _ensure_assets_symlink(preview_root, assets)
    assets_link = preview_root / "assets"
    docs = linked = missing = 0
    for body in sorted(root.rglob("body.md")):
        text = body.read_text(encoding="utf-8")
        mapping: dict[str, str] = {}
        for target in image_targets(text):
            if "://" in target:  # external URL, not a CAS asset
                continue
            name = image_basename(target)
            if (assets / name).is_file():
                out_parent = (preview_root / body.relative_to(silver_text)).parent
                mapping[name] = os.path.relpath(assets_link / name, out_parent)
                linked += 1
            else:
                missing += 1
        out = preview_root / body.relative_to(silver_text)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rewrite_image_refs(text, mapping), encoding="utf-8")
        docs += 1
    return docs, linked, missing


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("path", nargs="?", type=Path, help="silver/text subtree (default: all)")
    ap.add_argument("--clean", action="store_true", help="remove the whole _preview tree")
    args = ap.parse_args()

    cfg = Settings()
    preview_root = cfg.lake / "_preview"

    if args.clean:
        if preview_root.exists():
            shutil.rmtree(preview_root)
            print(f"removed preview tree {preview_root}")
        else:
            print(f"nothing to remove ({preview_root} does not exist)")
        return

    root = args.path or cfg.silver_text
    if not root.exists():
        raise SystemExit(f"no such path: {root}")

    docs, linked, missing = build(root, cfg.silver_text, cfg.assets, preview_root)
    print(f"mirrored {docs} doc(s), {linked} image ref(s) → {preview_root}")
    print(f"open e.g. {preview_root}/01-converted/<app>/<slug>/body.md in your markdown viewer")
    if missing:
        print(f"note: {missing} referenced asset(s) are not in the CAS (e.g. unconverted .wmf)")


if __name__ == "__main__":
    main()
