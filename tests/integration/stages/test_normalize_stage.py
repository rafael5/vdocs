"""normalize integration — enriched bundle → normalized body (Phase 3, §6.7, §9.6).

Seeds an enriched bundle (with identity FM, headings, a Pandoc artifact, and a dead phrase) +
raw/index.json (for source_sha256), runs NormalizeStage through the orchestrator, and asserts
the normalized body has a regenerated TOC, the artifact + curated phrase gone, and
source_sha256 stamped into the frontmatter.
"""

from __future__ import annotations

import hashlib
import json

from vdocs.contracts.registry import RAW_INDEX, TEXT_ENRICHED
from vdocs.kernel import cas, frontmatter
from vdocs.models.stage import StageRun
from vdocs.orchestrator.engine import Orchestrator
from vdocs.stages.normalize.stage import NormalizeStage

_SHA = hashlib.sha256(b"the source docx bytes").hexdigest()
_ENRICHED = frontmatter.emit(
    {"title": "Install Guide", "doc_type": "IG", "app_code": "ADT", "tool_ver": "0.1.0"},
    "# Install Guide\n\n<!-- -->\n\n## Setup\n\nThis page intentionally left blank.\n\n"
    "Real install steps.\n\n### Prerequisites\n\nmore\n",
)


def _seed(ctx):
    cas.atomic_write(ctx.cfg.silver_enriched / "ADT" / "ig_doc" / "body.md", _ENRICHED.encode())
    ctx.cfg.raw_index.parent.mkdir(parents=True, exist_ok=True)
    ctx.cfg.raw_index.write_text(
        json.dumps({_SHA: {"app_code": "ADT", "doc_slug": "ig_doc", "ext": "docx"}})
    )
    for stage, art in (("enrich", TEXT_ENRICHED), ("fetch", RAW_INDEX)):
        ctx.state.record(
            StageRun(
                stage=stage,
                scope="",
                status="ok",
                started_at="t",
                finished_at="t",
                inputs_fp={},
                outputs_fp={art.key: art.fingerprint(ctx.cfg)},
                counts={},
                contract_ver=1,
                tool_ver=ctx.cfg.tool_ver,
            )
        )


def test_load_phrases_empty_when_registry_absent(tmp_path):
    from vdocs.stages.normalize.stage import _load_phrases

    assert _load_phrases(tmp_path / "nope.yaml") == frozenset()  # no curated registry → no-op


def test_normalize_applies_f_steps_and_stamps_source_sha(ctx):
    _seed(ctx)
    (result,) = Orchestrator([NormalizeStage()]).run(ctx)
    assert result.status == "ok"
    assert result.counts["documents"] == 1 and result.counts["phrases"] >= 1

    meta, body = frontmatter.parse(
        (ctx.cfg.silver_normalized / "ADT" / "ig_doc" / "body.md").read_text()
    )
    # identity FM preserved + source provenance stamped (normalize holds the bronze sha)
    assert meta["title"] == "Install Guide" and meta["source_sha256"] == _SHA
    # F-steps applied: artifact + curated phrase gone, TOC regenerated from the heading tree
    assert "<!-- -->" not in body
    assert "intentionally left blank" not in body
    assert "## Contents" in body
    assert "- [Setup](#setup)" in body and "  - [Prerequisites](#prerequisites)" in body
    assert "Real install steps." in body


def test_normalize_writes_history_sidecar_and_strips_table(ctx):
    import yaml

    enriched = frontmatter.emit(
        {"title": "Tech Manual", "app_code": "ADT", "tool_ver": "0.1.0"},
        "# Tech Manual\n\n## Revision History\n\n"
        "<table><tr><th>Date</th><th>Version</th><th>Change</th></tr>"
        "<tr><td>03/2024</td><td>5.3</td><td>Updated install</td></tr></table>\n\n"
        "## Body\n\ncontent\n",
    )
    cas.atomic_write(ctx.cfg.silver_enriched / "ADT" / "tm_doc" / "body.md", enriched.encode())
    ctx.cfg.raw_index.parent.mkdir(parents=True, exist_ok=True)
    ctx.cfg.raw_index.write_text(
        json.dumps({_SHA: {"app_code": "ADT", "doc_slug": "tm_doc", "ext": "docx"}})
    )
    for stage, art in (("enrich", TEXT_ENRICHED), ("fetch", RAW_INDEX)):
        ctx.state.record(
            StageRun(
                stage=stage, scope="", status="ok", started_at="t", finished_at="t",
                inputs_fp={}, outputs_fp={art.key: art.fingerprint(ctx.cfg)}, counts={},
                contract_ver=1, tool_ver=ctx.cfg.tool_ver,
            )
        )  # fmt: skip

    (result,) = Orchestrator([NormalizeStage()]).run(ctx)
    assert result.counts["history_sidecars"] == 1

    bundle = ctx.cfg.silver_normalized / "ADT" / "tm_doc"
    _, body = frontmatter.parse((bundle / "body.md").read_text())
    assert "<table" not in body and "Updated install" not in body  # apparatus stripped
    history = yaml.safe_load((bundle / "history.yaml").read_text())
    assert history["revision_count"] == 1
    assert history["revisions"][0] == {
        "date": "2024-03",
        "version": "5.3",
        "pages": [],
        "change": "Updated install",
        "refs": [],
    }


def test_normalize_is_idempotent(ctx):
    _seed(ctx)
    orch = Orchestrator([NormalizeStage()])
    orch.run(ctx)
    first = (ctx.cfg.silver_normalized / "ADT" / "ig_doc" / "body.md").read_bytes()
    # re-run forced → byte-identical output (deterministic, §7.4)
    orch.run(ctx, force=True)
    assert (ctx.cfg.silver_normalized / "ADT" / "ig_doc" / "body.md").read_bytes() == first


def test_normalize_without_matching_sha_omits_source_sha256(ctx):
    # raw/index has no entry for this bundle → source_sha256 simply isn't stamped (no crash)
    _seed(ctx)
    ctx.cfg.raw_index.write_text("{}")
    ctx.state.record(  # re-bless fetch for the (now empty) index so preflight sees it current
        StageRun(
            stage="fetch",
            scope="",
            status="ok",
            started_at="t",
            finished_at="t",
            inputs_fp={},
            outputs_fp={RAW_INDEX.key: RAW_INDEX.fingerprint(ctx.cfg)},
            counts={},
            contract_ver=1,
            tool_ver=ctx.cfg.tool_ver,
        )
    )
    Orchestrator([NormalizeStage()]).run(ctx, force=True)
    meta, _ = frontmatter.parse(
        (ctx.cfg.silver_normalized / "ADT" / "ig_doc" / "body.md").read_text()
    )
    assert "source_sha256" not in meta and meta["title"] == "Install Guide"
