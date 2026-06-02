"""The `convert` stage — raw binaries → ``text@converted`` markdown bundles + assets (§8).

Reads the fetched CAS (`raw/<sha>.<ext>` + `raw/index.json`), converts each document to
markdown via an **injected converter** (so tests need no Pandoc/Docling and the binary
backend is pluggable), extracts inline images into the shared content-addressed asset store,
rewrites the body's image refs to those asset shas, and writes one bundle per document at
``silver/text/01-converted/<app>/<slug>/body.md``. Identity frontmatter is *not* added here —
that is ``enrich``'s job (§6.3). Idempotent: re-converting identical bytes is a CAS/atomic no-op.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from vdocs.contracts.registry import ASSETS, RAW_INDEX, RAW_TREE, TEXT_CONVERTED
from vdocs.kernel import cas
from vdocs.kernel.cas import Cas
from vdocs.models.stage import Idempotency, RunResult
from vdocs.orchestrator.stage import Stage, StageContext
from vdocs.stages.convert.convert_pure import ConvertedDoc

Converter = Callable[[bytes, str], ConvertedDoc]


class ConvertStage(Stage):
    name = "convert"
    description = "convert fetched documents to markdown bundles + extract images to the asset CAS"
    requires = [RAW_TREE, RAW_INDEX]
    produces = [TEXT_CONVERTED, ASSETS]
    idempotency = Idempotency.SKIP_IF_UNCHANGED

    def __init__(self, convert: Converter | None = None) -> None:
        self._convert = convert

    def run(self, ctx: StageContext, force: bool) -> RunResult:
        from vdocs.stages.convert import convert_pure as cp

        convert = self._convert or _pandoc_convert
        index: dict[str, dict[str, str]] = json.loads(ctx.cfg.raw_index.read_text(encoding="utf-8"))
        raw = Cas(ctx.cfg.bronze_raw)
        assets = Cas(ctx.cfg.assets)

        n_docs = n_assets = 0
        for sha, entry in index.items():
            ext = entry["ext"]
            doc = convert(raw.get(sha, ext=ext), ext)

            ref_to_asset: dict[str, str] = {}
            for img in doc.images:
                img_sha = assets.put(img.data, ext=img.ext)
                ref_to_asset[img.ref] = cp.asset_filename(img_sha, img.ext)
                n_assets += 1

            body = cp.rewrite_image_refs(doc.markdown, ref_to_asset)
            bundle = cp.bundle_dir(ctx.cfg.silver_converted, entry["app_code"], entry["doc_slug"])
            cas.atomic_write(bundle / "body.md", body.encode("utf-8"))
            n_docs += 1

        return RunResult(counts={"documents": n_docs, "assets": n_assets})


def _pandoc_convert(data: bytes, ext: str) -> ConvertedDoc:  # pragma: no cover - subprocess I/O
    """Default converter: Pandoc for DOCX (GFM + media extraction). PDF is deferred (Docling)."""
    import subprocess
    import tempfile
    from pathlib import Path

    from vdocs.stages.convert.convert_pure import ConvertedDoc, ConvertedImage

    if ext != "docx":
        raise NotImplementedError(f"convert backend for .{ext} not wired yet (PDF → Docling, TODO)")
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / f"in.{ext}"
        src.write_bytes(data)
        media = Path(td) / "media-root"
        markdown = subprocess.run(
            ["pandoc", str(src), "-t", "gfm", "--wrap=none", f"--extract-media={media}"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        images: list[ConvertedImage] = []
        for img in sorted(media.rglob("*")):
            if img.is_file():
                ref = str(img.relative_to(Path(td)))  # how pandoc references it in the markdown
                images.append(
                    ConvertedImage(
                        ref=ref, data=img.read_bytes(), ext=img.suffix.lstrip(".").lower()
                    )
                )
        return ConvertedDoc(markdown=markdown, images=tuple(images))
