"""convert integration — raw CAS → text@converted bundles + image extraction (Phase 3, §8).

A fake converter (no Pandoc) returns markdown + an inline image; the stage must store the
image in the shared asset CAS, rewrite the body's image ref to the asset sha, and write the
bundle at silver/text/01-converted/<app>/<slug>/body.md. Driven through the orchestrator so
the fetch→convert contract (preflight on RAW_TREE + RAW_INDEX) is exercised.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from vdocs.contracts.registry import RAW_INDEX, RAW_TREE
from vdocs.kernel.cas import Cas
from vdocs.models.stage import StageRun
from vdocs.orchestrator.engine import Orchestrator
from vdocs.orchestrator.stage import PostflightError
from vdocs.stages.convert.convert_pure import ConvertedDoc, ConvertedImage
from vdocs.stages.convert.stage import ConvertStage

_IMG = b"\x89PNG fake image bytes"
_IMG_SHA = hashlib.sha256(_IMG).hexdigest()


def fake_convert(data: bytes, ext: str) -> ConvertedDoc:
    # mimic Pandoc: an HTML <img> with an absolute temp path (the real-corpus shape)
    return ConvertedDoc(
        markdown=(
            "# DG Installation\n\nIntro.\n\n"
            '<img src="/tmp/tmpZ/media-root/media/image1.png" alt="logo" />\n'
        ),
        images=(ConvertedImage(ref="/tmp/tmpZ/media-root/media/image1.png", data=_IMG, ext="png"),),
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
    # not routed → Pandoc; no per-doc errors; nothing to prune
    assert result.counts == {
        "documents": 1,
        "assets": 1,
        "docling": 0,
        "errors": 0,
        "pruned": 0,
    }

    # the bundle landed at the converted path with the app/slug layout
    body = ctx.cfg.silver_converted / "ADT" / "dg_5_3_1057_dibr" / "body.md"
    assert body.exists()
    text = body.read_text()
    assert text.startswith("# DG Installation")
    # the HTML <img> ref was rewritten to the content-addressed asset filename
    assert f'<img src="{_IMG_SHA}.png" alt="logo" />' in text
    assert "/tmp/tmpZ" not in text  # the dead temp path is gone

    # the image bytes live in the shared asset CAS, write-once
    assert Cas(ctx.cfg.assets).get(_IMG_SHA, ext="png") == _IMG


def test_load_converter_routing_empty_when_absent(tmp_path):
    from vdocs.stages.convert.stage import _load_converter_routing

    assert _load_converter_routing(tmp_path / "nope.yaml") == frozenset()  # no registry → Pandoc


def test_convert_skips_on_clean_rerun(ctx):
    _seed_fetched(ctx)
    orch = Orchestrator([ConvertStage(convert=fake_convert)])
    orch.run(ctx)
    assert orch.run(ctx) == [None]  # SKIP_IF_UNCHANGED → skipped second time


def _seed_many(ctx, slugs):
    """Place one fetched DOCX per slug in the raw CAS + index, and record fetch ok."""
    raw = Cas(ctx.cfg.bronze_raw)
    index = {}
    for slug in slugs:
        sha = raw.put(f"docx-{slug}".encode(), ext="docx")
        index[sha] = {
            "app_code": "ADT",
            "doc_slug": slug,
            "title": slug,
            "source_url": f"https://va.gov/d/{slug}.docx",
            "ext": "docx",
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
        )  # fmt: skip
    )


def test_convert_isolates_a_single_doc_failure(ctx):
    # R6: one bad doc is isolated (logged + counted), the rest of the batch still converts
    _seed_many(ctx, ["aaa", "bad", "ccc"])

    def conv(data: bytes, ext: str) -> ConvertedDoc:
        if b"bad" in data:
            raise ValueError("boom")
        return ConvertedDoc(markdown="# ok\n")

    (result,) = Orchestrator([ConvertStage(convert=conv)]).run(ctx)
    assert result.status == "ok"
    assert result.counts["errors"] == 1 and result.counts["documents"] == 2
    assert (ctx.cfg.silver_converted / "ADT" / "aaa" / "body.md").exists()
    assert (ctx.cfg.silver_converted / "ADT" / "ccc" / "body.md").exists()
    assert not (ctx.cfg.silver_converted / "ADT" / "bad" / "body.md").exists()


def test_convert_fails_the_stage_when_error_rate_is_systemic(ctx):
    # every doc fails (100% > the 50% limit) → postflight fails the stage, not a silent pass
    _seed_many(ctx, ["aaa", "bbb"])

    def conv(data: bytes, ext: str) -> ConvertedDoc:
        raise ValueError("boom")

    with pytest.raises(PostflightError):
        Orchestrator([ConvertStage(convert=conv)]).run(ctx)


def test_convert_prunes_bundle_whose_input_vanished(ctx):
    # R5: a doc withdrawn upstream (gone from raw/index.json) must leave no ghost bundle
    plain = lambda data, ext: ConvertedDoc(markdown="# x\n")  # noqa: E731
    _seed_many(ctx, ["keep", "gone"])
    Orchestrator([ConvertStage(convert=plain)]).run(ctx)
    assert (ctx.cfg.silver_converted / "ADT" / "gone" / "body.md").exists()

    _seed_many(ctx, ["keep"])  # 'gone' withdrawn from the input set
    (result,) = Orchestrator([ConvertStage(convert=plain)]).run(ctx, force=True)
    assert (ctx.cfg.silver_converted / "ADT" / "keep" / "body.md").exists()
    assert not (ctx.cfg.silver_converted / "ADT" / "gone").exists()  # ghost bundle pruned
    assert result.counts["pruned"] == 1


def test_convert_routes_allowlisted_doc_to_docling(ctx, tmp_path):
    # point registries at a temp dir that routes this doc to Docling (ADR-010, §9.6)
    routing = tmp_path / "registries"
    (routing / "converter-routing").mkdir(parents=True)
    (routing / "converter-routing" / "converter-routing.yaml").write_text(
        "docling:\n  - ADT/dg_5_3_1057_dibr\n"
    )
    ctx.cfg = ctx.cfg.model_copy(update={"registries_dir": routing})
    _seed_fetched(ctx)

    def docling_fake(data: bytes, ext: str) -> ConvertedDoc:
        return ConvertedDoc(markdown="# Recovered By Docling\n\n## Setup\n\nstructured\n")

    (result,) = Orchestrator([ConvertStage(convert=fake_convert, docling=docling_fake)]).run(ctx)
    assert result.counts["docling"] == 1  # routed away from Pandoc
    body = (ctx.cfg.silver_converted / "ADT" / "dg_5_3_1057_dibr" / "body.md").read_text()
    assert body.startswith("# Recovered By Docling")  # Docling output, not the Pandoc fake
