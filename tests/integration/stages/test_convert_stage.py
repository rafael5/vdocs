"""convert integration — raw CAS → text@converted bundles + image extraction (Phase 3, §8).

A fake converter (no Pandoc) returns markdown + an inline image; the stage must store the
image in the shared asset CAS, rewrite the body's image ref to the asset sha, and write the
bundle at silver/text/01-converted/<app>/<slug>/body.md. Driven through the orchestrator so
the fetch→convert contract (preflight on RAW_TREE + RAW_INDEX) is exercised.
"""

from __future__ import annotations

import hashlib
import json

from vdocs.contracts.registry import RAW_INDEX, RAW_TREE
from vdocs.kernel.cas import Cas
from vdocs.models.stage import StageRun
from vdocs.orchestrator.engine import Orchestrator
from vdocs.stages.convert.convert_pure import ConvertedDoc, ConvertedImage
from vdocs.stages.convert.stage import ConvertStage

_IMG = b"\x89PNG fake image bytes"
_IMG_SHA = hashlib.sha256(_IMG).hexdigest()


def fake_convert(data: bytes, ext: str) -> ConvertedDoc:
    return ConvertedDoc(
        markdown="# DG Installation\n\nIntro.\n\n![logo](media/image1.png)\n",
        images=(ConvertedImage(ref="media/image1.png", data=_IMG, ext="png"),),
    )


def _seed_fetched(ctx):
    """Place one fetched DOCX in the raw CAS + its index entry, and record fetch ok."""
    raw = Cas(ctx.cfg.bronze_raw)
    sha = raw.put(b"PK\x03\x04 fake docx", ext="docx")
    index = {
        sha: {
            "app_code": "ADT",
            "doc_slug": "dg_5_3_1057_dibr",
            "title": "DG*5.3*1057 Installation Guide",
            "source_url": "https://va.gov/d/dg_5_3_1057_dibr.docx",
            "ext": "docx",
        }
    }
    ctx.cfg.raw_index.parent.mkdir(parents=True, exist_ok=True)
    ctx.cfg.raw_index.write_text(json.dumps(index))
    ctx.state.record(
        StageRun(
            stage="fetch",
            scope="",
            status="ok",
            started_at="t",
            finished_at="t",
            inputs_fp={},
            outputs_fp={
                RAW_TREE.key: RAW_TREE.fingerprint(ctx.cfg),
                RAW_INDEX.key: RAW_INDEX.fingerprint(ctx.cfg),
            },
            counts={},
            contract_ver=1,
            tool_ver=ctx.cfg.tool_ver,
        )
    )


def test_convert_writes_bundle_and_extracts_assets(ctx):
    _seed_fetched(ctx)
    (result,) = Orchestrator([ConvertStage(convert=fake_convert)]).run(ctx)

    assert result.status == "ok"
    assert result.counts == {"documents": 1, "assets": 1}

    # the bundle landed at the converted path with the app/slug layout
    body = ctx.cfg.silver_converted / "ADT" / "dg_5_3_1057_dibr" / "body.md"
    assert body.exists()
    text = body.read_text()
    assert text.startswith("# DG Installation")
    # the image ref was rewritten to the content-addressed asset filename
    assert f"![logo]({_IMG_SHA}.png)" in text
    assert "media/image1.png" not in text

    # the image bytes live in the shared asset CAS, write-once
    assert Cas(ctx.cfg.assets).get(_IMG_SHA, ext="png") == _IMG


def test_convert_skips_on_clean_rerun(ctx):
    _seed_fetched(ctx)
    orch = Orchestrator([ConvertStage(convert=fake_convert)])
    orch.run(ctx)
    assert orch.run(ctx) == [None]  # SKIP_IF_UNCHANGED → skipped second time
