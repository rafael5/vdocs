"""Pure logic for `convert` — bundle paths + image-ref rewriting (§5.2, §8).

The binary→markdown conversion itself is I/O (a subprocess / library call) and is injected
into the stage; these functions are the pure parts: where a document's bundle lives, and how
its inline image references are rewritten to point at the shared content-addressed asset
store (``assets/<sha256>.<ext>``) once the images have been extracted and stored.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from vdocs.kernel.text import safe_component

# Install hints surfaced as the preflight remediation when an external converter binary is absent
# (the convert stage shells these out; they are system tools, not pip dependencies).
PANDOC_HINT = "install pandoc — `sudo apt install pandoc` (or `brew install pandoc`)"
DOCLING_HINT = "install the Docling CLI isolated: `uv tool install 'docling-slim[standard]'`"


def missing_converters(
    need_pandoc: bool, need_docling: bool, available: Callable[[str], bool]
) -> list[tuple[str, str]]:
    """Which required external converter binaries are absent, as ``(tool, install_hint)`` pairs.

    Pure: the caller supplies the ``available(tool) -> bool`` probe (real impl wraps
    ``shutil.which``) so this is unit-testable with no filesystem. ``need_pandoc``/``need_docling``
    reflect whether
    each converter will actually be invoked this run — a converter injected by a test (or a routing
    file that sends nothing to Docling) is *not* needed, so its binary is never demanded.
    """
    missing: list[tuple[str, str]] = []
    if need_pandoc and not available("pandoc"):
        missing.append(("pandoc", PANDOC_HINT))
    if need_docling and not available("docling"):
        missing.append(("docling", DOCLING_HINT))
    return missing


# markdown image: ![alt](target "optional title")
_MD_IMG_RE = re.compile(r"(!\[[^\]]*\]\()([^)\s]+)([^)]*\))")
# HTML image (Pandoc emits these for sized/captioned images): <img ... src="target" ... />
_HTML_IMG_RE = re.compile(r'(<img\b[^>]*?\bsrc=")([^"]+)(")', re.IGNORECASE)


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


def bundle_dir(root: Path, app_code: str, doc_slug: str) -> Path:
    """The per-document bundle directory ``<root>/<app>/<slug>/`` (§5.2)."""
    return root / safe_component(app_code) / safe_component(doc_slug)


def asset_filename(sha256: str, ext: str) -> str:
    """The shared-asset-store key for an image: ``<sha256>.<ext>`` (referenced, never copied)."""
    return f"{sha256}.{ext}" if ext else sha256


def image_basename(ref: str) -> str:
    """The bare filename of an image ref (handles ``/`` and ``\\`` paths, markdown or HTML).

    Pandoc references extracted images by their *full* (often absolute, temp-dir) path — and as
    HTML ``<img>`` for sized/captioned ones — so matching on the basename is the robust join:
    within one document Pandoc names media uniquely (``image1.png``, ``image2.png``)."""
    return ref.replace("\\", "/").rsplit("/", 1)[-1]


def rewrite_image_refs(markdown: str, basename_to_asset: dict[str, str]) -> str:
    """Repoint every inline image (markdown ``![]()`` **and** HTML ``<img src>``) whose basename
    is in ``basename_to_asset`` to its ``<sha256>.<ext>`` asset filename (§5.2). Images live in
    the shared CAS, referenced — never copied into the bundle. Unknown targets (external URLs,
    already-asset refs) are left untouched."""

    def repl(m: re.Match[str]) -> str:
        asset = basename_to_asset.get(image_basename(m.group(2)))
        return f"{m.group(1)}{asset}{m.group(3)}" if asset is not None else m.group(0)

    return _HTML_IMG_RE.sub(repl, _MD_IMG_RE.sub(repl, markdown))
