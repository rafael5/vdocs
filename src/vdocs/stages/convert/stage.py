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

import structlog

from vdocs.contracts.registry import ASSETS, RAW_INDEX, RAW_TREE, TEXT_CONVERTED
from vdocs.kernel import cas
from vdocs.kernel import registry as kregistry
from vdocs.kernel.cas import Cas
from vdocs.kernel.docloop import DocLoop
from vdocs.kernel.text import safe_component
from vdocs.models.stage import Decision, Idempotency, PostflightResult, PreflightResult, RunResult
from vdocs.orchestrator.stage import Stage, StageContext
from vdocs.stages.convert.convert_pure import ConvertedDoc, missing_converters

log = structlog.get_logger(__name__)

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
        self._errors = 0  # per-document failures isolated this run (R6 — see doc_error_gate)
        self._total = 0

    def preflight(self, ctx: StageContext, force: bool) -> PreflightResult:
        """On top of the generic preflight, fail fast with a remediation hint if a required external
        converter binary is missing — *before* the per-document loop, so a missing `pandoc` reads as
        "install pandoc" instead of "N documents failed to convert" (a mis-reported corpus defect).
        Only checks when this run will actually convert (PROCEED); a skipped/resumed convert needs
        no binary. Injected converters (tests / backends) are never gated on the system tool.
        """
        base = super().preflight(ctx, force)
        if base.decision is not Decision.PROCEED:
            return base  # FAIL (bad input) or SKIP (unchanged) — no conversion this run
        routing = _load_converter_routing(
            ctx.cfg.registries / "converter-routing" / "converter-routing.yaml"
        )
        missing = missing_converters(
            need_pandoc=self._pandoc is None,
            need_docling=self._docling is None and bool(routing),
            available=_converter_available,
        )
        if missing:
            tools = ", ".join(tool for tool, _hint in missing)
            hints = "; ".join(hint for _tool, hint in missing)
            return PreflightResult.fail(
                f"required converter binary not found: {tools}", remediation=hints
            )
        return base

    def run(self, ctx: StageContext, force: bool) -> RunResult:
        from vdocs.stages.convert import convert_pure as cp

        pandoc = self._pandoc or _pandoc_convert
        docling = self._docling or _docling_convert
        routing = _load_converter_routing(
            ctx.cfg.registries / "converter-routing" / "converter-routing.yaml"
        )
        index: dict[str, dict[str, str]] = json.loads(ctx.cfg.raw_index.read_text(encoding="utf-8"))
        raw = Cas(ctx.cfg.bronze_raw)
        assets = Cas(ctx.cfg.assets)

        n_docs = n_assets = n_docling = 0
        kept: set[str] = set()  # <app>/<slug> bundles in this run's input set (R5 pruning)
        total = len(index)
        # Per-document error isolation (R6): a single bad doc is logged + counted + skipped so one
        # failure never abandons the batch; the postflight gate fails the stage only if the error
        # *rate* is systemic (doc_error_gate). The shared guard lives in kernel.docloop (§9.2).
        loop = DocLoop("convert", log)
        for n, (sha, entry) in enumerate(index.items(), 1):
            if n % 25 == 0 or n == total:
                ctx.progress(f"{n}/{total} converted")
            # route by bundle identity (safe app / safe slug) — Docling for the curated
            # bare-marker-explosion allowlist (ADR-010, §9.6), Pandoc otherwise
            key = f"{safe_component(entry['app_code'])}/{safe_component(entry['doc_slug'])}"
            kept.add(key)
            with loop.guard(key):
                ext = entry["ext"]
                use_docling = key in routing
                doc = (docling if use_docling else pandoc)(raw.get(sha, ext=ext), ext)
                n_docling += use_docling

                # key by basename — converters reference media by full/absolute path and as HTML
                # <img>, so the basename is the robust join (unique per document)
                basename_to_asset: dict[str, str] = {}
                for img in doc.images:
                    img_sha = assets.put(img.data, ext=img.ext)
                    basename_to_asset[cp.image_basename(img.ref)] = cp.asset_filename(
                        img_sha, img.ext
                    )
                    n_assets += 1

                body = cp.rewrite_image_refs(doc.markdown, basename_to_asset)
                bundle = cp.bundle_dir(
                    ctx.cfg.silver_converted, entry["app_code"], entry["doc_slug"]
                )
                cas.atomic_write(bundle / "body.md", body.encode("utf-8"))
                n_docs += 1

        n_pruned = cas.prune_bundles(ctx.cfg.silver_converted, kept)
        self._errors, self._total = loop.errors, loop.total
        return RunResult(
            counts={
                "documents": n_docs,
                "assets": n_assets,
                "docling": n_docling,
                "errors": loop.errors,
                "pruned": n_pruned,
            },
            warnings=loop.warnings(action="convert"),
        )

    def deep_gate(self, ctx: StageContext) -> PostflightResult:
        """Fail only if the per-document error rate is systemic (R6); one bad doc is isolated."""
        return self.doc_error_gate(self._errors, self._total)


def _load_converter_routing(path) -> frozenset[str]:  # type: ignore[no-untyped-def]
    """Bundle identities (``<app>/<slug>``) curated to convert with Docling (empty if absent)."""
    data = kregistry.load_mapping(path, missing_ok=True)
    return frozenset(data.get("docling") or [])


def _converter_available(tool: str) -> bool:
    """Whether an external converter binary is on PATH. Docling is commonly installed as a uv tool
    under ``~/.local/bin`` (mirrors :func:`_docling_convert`'s fallback), so check there too."""
    import shutil
    from pathlib import Path

    if shutil.which(tool):
        return True
    return tool == "docling" and (Path.home() / ".local" / "bin" / "docling").exists()


def _docling_convert(data: bytes, ext: str) -> ConvertedDoc:  # pragma: no cover - subprocess I/O
    """Docling DOCX→markdown for the routed allowlist (ADR-010): it reconstructs the lists Pandoc
    shreds into bare markers. Run **out-of-process** via the ``docling`` CLI (installed isolated,
    e.g. ``uv tool install 'docling-slim[standard]'``) — it pins ``typer<0.22`` which conflicts
    with the CLI's ``typer``, so it must not share this environment. Docling parses no alt-text and
    emits ``<!-- image -->`` placeholders; we recover alt-text + media from the DOCX XML (1:1) and
    inject ``![alt](media)`` refs (:mod:`docx_images`, the v1 approach)."""
    import shutil
    import subprocess
    import tempfile
    from pathlib import Path

    from vdocs.stages.convert.convert_pure import ConvertedDoc
    from vdocs.stages.convert.docx_images import extract_pictures, inject_placeholders

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
        cmd = [exe, "--to", "md", "--image-export-mode", "placeholder", "--output", str(out)]
        subprocess.run([*cmd, str(src)], capture_output=True, text=True, check=True)
        md_files = list(out.glob("*.md"))
        raw_markdown = md_files[0].read_text(encoding="utf-8") if md_files else ""
    markdown, images = inject_placeholders(raw_markdown, extract_pictures(data))
    return ConvertedDoc(markdown=markdown, images=tuple(images))


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
