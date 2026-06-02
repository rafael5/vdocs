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

import yaml

from vdocs.contracts.registry import ASSETS, RAW_INDEX, RAW_TREE, TEXT_CONVERTED
from vdocs.kernel import cas
from vdocs.kernel.cas import Cas
from vdocs.models.stage import Idempotency, RunResult
from vdocs.orchestrator.stage import Stage, StageContext
from vdocs.stages.convert.convert_pure import ConvertedDoc, safe_component

Converter = Callable[[bytes, str], ConvertedDoc]


class ConvertStage(Stage):
    name = "convert"
    description = "convert fetched documents to markdown bundles + extract images to the asset CAS"
    requires = [RAW_TREE, RAW_INDEX]
    produces = [TEXT_CONVERTED, ASSETS]
    idempotency = Idempotency.SKIP_IF_UNCHANGED

    def __init__(self, convert: Converter | None = None, docling: Converter | None = None) -> None:
        self._pandoc = convert  # default Pandoc when None
        self._docling = docling  # default Docling when None

    def run(self, ctx: StageContext, force: bool) -> RunResult:
        from vdocs.stages.convert import convert_pure as cp

        pandoc = self._pandoc or _pandoc_convert
        docling = self._docling or _docling_convert
        routing = _load_converter_routing(ctx.cfg.registries / "converter-routing.yaml")
        index: dict[str, dict[str, str]] = json.loads(ctx.cfg.raw_index.read_text(encoding="utf-8"))
        raw = Cas(ctx.cfg.bronze_raw)
        assets = Cas(ctx.cfg.assets)

        n_docs = n_assets = n_docling = 0
        for sha, entry in index.items():
            ext = entry["ext"]
            # route by bundle identity (safe app / safe slug) — Docling for the curated
            # bare-marker-explosion allowlist (ADR-010, §9.6), Pandoc otherwise
            key = f"{safe_component(entry['app_code'])}/{safe_component(entry['doc_slug'])}"
            use_docling = key in routing
            doc = (docling if use_docling else pandoc)(raw.get(sha, ext=ext), ext)
            n_docling += use_docling

            # key by basename — converters reference media by full/absolute path and as HTML <img>,
            # so the basename is the robust join (unique per document)
            basename_to_asset: dict[str, str] = {}
            for img in doc.images:
                img_sha = assets.put(img.data, ext=img.ext)
                basename_to_asset[cp.image_basename(img.ref)] = cp.asset_filename(img_sha, img.ext)
                n_assets += 1

            body = cp.rewrite_image_refs(doc.markdown, basename_to_asset)
            bundle = cp.bundle_dir(ctx.cfg.silver_converted, entry["app_code"], entry["doc_slug"])
            cas.atomic_write(bundle / "body.md", body.encode("utf-8"))
            n_docs += 1

        return RunResult(counts={"documents": n_docs, "assets": n_assets, "docling": n_docling})


def _load_converter_routing(path) -> frozenset[str]:  # type: ignore[no-untyped-def]
    """Bundle identities (``<app>/<slug>``) curated to convert with Docling (empty if absent)."""
    if not path.exists():
        return frozenset()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return frozenset(data.get("docling") or [])


def _docling_convert(data: bytes, ext: str) -> ConvertedDoc:  # pragma: no cover - subprocess I/O
    """Docling DOCX→markdown for the routed allowlist (ADR-010): its layout/structure analysis
    recovers headings Pandoc flattens. Run **out-of-process** via the ``docling`` CLI (installed
    isolated, e.g. ``uv tool install 'docling-slim[standard]'``) — it pins ``typer<0.22`` which
    conflicts with the CLI's ``typer``, so it must not share this environment."""
    import shutil
    import subprocess
    import tempfile
    from pathlib import Path

    from vdocs.stages.convert.convert_pure import ConvertedDoc, ConvertedImage

    exe = shutil.which("docling") or str(Path.home() / ".local" / "bin" / "docling")
    if not Path(exe).exists():
        raise RuntimeError(
            "convert routed a document to Docling but the `docling` CLI is not installed "
            "(install isolated: `uv tool install 'docling-slim[standard]'`)"
        )
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / f"in.{ext}"
        src.write_bytes(data)
        out = Path(td) / "out"
        out.mkdir()
        cmd = [exe, "--to", "md", "--image-export-mode", "referenced", "--output", str(out)]
        subprocess.run([*cmd, str(src)], capture_output=True, text=True, check=True)
        md_files = list(out.glob("*.md"))
        markdown = md_files[0].read_text(encoding="utf-8") if md_files else ""
        images = tuple(
            ConvertedImage(ref=p.name, data=p.read_bytes(), ext=p.suffix.lstrip(".").lower())
            for p in sorted(out.rglob("*"))
            if p.is_file() and p.suffix.lower() != ".md"
        )
        return ConvertedDoc(markdown=markdown, images=images)


def _pandoc_convert(data: bytes, ext: str) -> ConvertedDoc:  # pragma: no cover - subprocess I/O
    """Default converter: Pandoc for DOCX (GFM + media extraction).

    The pipeline is DOCX-only (§1); Docling (:func:`_docling_convert`) is the alternative DOCX
    converter for the bare-marker-explosion allowlist (ADR-010), routed in by the stage above.
    """
    import subprocess
    import tempfile
    from pathlib import Path

    from vdocs.stages.convert.convert_pure import ConvertedDoc, ConvertedImage

    if ext != "docx":
        raise ValueError(f"convert: unexpected non-docx ext {ext!r} (pipeline is DOCX-only, §1)")
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
