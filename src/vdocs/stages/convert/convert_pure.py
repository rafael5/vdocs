"""Pure logic for `convert` — bundle paths + image-ref rewriting (§5.2, §8).

The binary→markdown conversion itself is I/O (a subprocess / library call) and is injected
into the stage; these functions are the pure parts: where a document's bundle lives, and how
its inline image references are rewritten to point at the shared content-addressed asset
store (``assets/<sha256>.<ext>``) once the images have been extracted and stored.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# markdown image: ![alt](target "optional title")
_IMG_RE = re.compile(r"(!\[[^\]]*\]\()([^)\s]+)([^)]*\))")
# app codes may carry slashes/plus (AR/WS, DRM+) — sanitise before any filesystem path (§8)
_PATH_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class ConvertedImage:
    """An image extracted during conversion: its in-markdown ``ref`` + bytes + extension."""

    ref: str  # the path/name as it appears in the converted markdown (e.g. "media/image1.png")
    data: bytes
    ext: str  # without the dot


@dataclass(frozen=True)
class ConvertedDoc:
    """The result of converting one binary document to markdown (pre-identity-frontmatter)."""

    markdown: str
    images: tuple[ConvertedImage, ...] = ()


def safe_component(name: str) -> str:
    """Filesystem-safe path component: non-[A-Za-z0-9._-] runs → '_', trimmed (e.g. AR/WS→ar_ws)."""
    return _PATH_UNSAFE.sub("_", name).strip("_") or "_"


def bundle_dir(root: Path, app_code: str, doc_slug: str) -> Path:
    """The per-document bundle directory ``<root>/<app>/<slug>/`` (§5.2)."""
    return root / safe_component(app_code) / safe_component(doc_slug)


def asset_filename(sha256: str, ext: str) -> str:
    """The shared-asset-store key for an image: ``<sha256>.<ext>`` (referenced, never copied)."""
    return f"{sha256}.{ext}" if ext else sha256


def rewrite_image_refs(markdown: str, ref_to_asset: dict[str, str]) -> str:
    """Repoint every inline image whose target is in ``ref_to_asset`` to its asset filename.

    Images extracted to the CAS are referenced by ``<sha256>.<ext>`` from ``body.md`` rather
    than copied into the bundle (§5.2). Unknown targets (external URLs, already-asset refs)
    are left untouched."""

    def repl(m: re.Match[str]) -> str:
        target = m.group(2)
        asset = ref_to_asset.get(target)
        return f"{m.group(1)}{asset}{m.group(3)}" if asset is not None else m.group(0)

    return _IMG_RE.sub(repl, markdown)
