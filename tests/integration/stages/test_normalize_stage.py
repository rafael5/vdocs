"""normalize integration — enriched bundle → normalized body (Phase 3, §6.7, §9.6).

Seeds an enriched bundle (with identity FM, headings, a Pandoc artifact, and a dead phrase) +
raw/index.json (for source_sha256), runs NormalizeStage through the orchestrator, and asserts
the normalized body has a regenerated TOC, the artifact + curated phrase gone, and
source_sha256 stamped into the frontmatter.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from vdocs.contracts.registry import RAW_INDEX, TEXT_ENRICHED
from vdocs.kernel import cas, frontmatter
from vdocs.models.stage import StageRun
from vdocs.orchestrator.engine import Orchestrator
from vdocs.orchestrator.stage import PostflightError
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


def test_load_boilerplate_empty_when_registry_absent(tmp_path):
    from vdocs.stages.normalize.normalize_pure import Boilerplate
    from vdocs.stages.normalize.stage import _load_boilerplate

    assert _load_boilerplate(tmp_path / "nope.yaml", Boilerplate) == ()  # absent → no-op


def test_registry_edit_changes_normalize_inputs_fp(tmp_path):
    # §8: a registry change is a contract-version bump for normalize — it must invalidate the
    # input fingerprint so SKIP_IF_UNCHANGED re-runs the affected scopes (§7.3), not skip them.
    from vdocs.config import Settings
    from vdocs.contracts.registry import REGISTRIES
    from vdocs.orchestrator.stage import StageContext
    from vdocs.orchestrator.state import StateStore

    regs = tmp_path / "registries"
    (regs / "phrases").mkdir(parents=True)
    (regs / "phrases" / "phrases.yaml").write_text("phrases:\n  - End of document\n")
    cfg = Settings(data_dir=tmp_path / "lake", registries_dir=regs)
    cfg.lake.mkdir(parents=True)
    store = StateStore.open(cfg.state_db)
    try:
        ctx = StageContext(cfg=cfg, state=store)
        stage = NormalizeStage()
        assert REGISTRIES in stage.requires
        before = stage._input_fps(ctx)
        assert REGISTRIES.key in before
        (regs / "phrases" / "phrases.yaml").write_text(
            "phrases:\n  - End of document\n  - Continued\n"
        )
        after = stage._input_fps(ctx)
        assert after[REGISTRIES.key] != before[REGISTRIES.key]
    finally:
        store.close()


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


def test_normalize_writes_revisions_sidecar_and_strips_table(ctx):
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
    assert result.counts["revision_sidecars"] == 1

    bundle = ctx.cfg.silver_normalized / "ADT" / "tm_doc"
    _, body = frontmatter.parse((bundle / "body.md").read_text())
    assert "<table" not in body and "Updated install" not in body  # apparatus stripped
    assert not (bundle / "history.yaml").exists()  # the cross-version lineage name is consolidate's
    history = yaml.safe_load((bundle / "revisions.yaml").read_text())
    assert history["revision_count"] == 1
    assert history["revisions"][0] == {
        "date": "2024-03",
        "version": "5.3",
        "pages": [],
        "change": "Updated install",
        "refs": [],
    }


def test_normalize_lifts_large_table_to_csv_sidecar(ctx):
    # a long data table is lifted to tables/table-01.csv and replaced by a reference (§6.4/§6.5)
    rows = "".join(f"<tr><td>F{i}</td><td>T{i}</td><td>D{i}</td></tr>" for i in range(12))
    table = "<table><tr><th>Field</th><th>Type</th><th>Desc</th></tr>" + rows + "</table>"
    enriched = frontmatter.emit(
        {"title": "Data Dict", "app_code": "ADT", "tool_ver": "0.1.0"},
        f"# Data Dict\n\n## Fields\n\n{table}\n\nAfter table.\n",
    )
    cas.atomic_write(ctx.cfg.silver_enriched / "ADT" / "dd_doc" / "body.md", enriched.encode())
    ctx.cfg.raw_index.parent.mkdir(parents=True, exist_ok=True)
    ctx.cfg.raw_index.write_text(
        json.dumps({_SHA: {"app_code": "ADT", "doc_slug": "dd_doc", "ext": "docx"}})
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
    assert result.counts["tables_sidecars"] == 1

    bundle = ctx.cfg.silver_normalized / "ADT" / "dd_doc"
    _, body = frontmatter.parse((bundle / "body.md").read_text())
    assert "<table" not in body  # the table left the body
    assert "(tables/table-01.csv)" in body  # replaced by a reference link
    csv_text = (bundle / "tables" / "table-01.csv").read_text()
    assert csv_text.splitlines()[0] == "Field,Type,Desc"
    assert "F0,T0,D0" in csv_text


def test_normalize_references_curated_boilerplate(ctx, tmp_path):
    # point registries at a temp dir with one curated boilerplate block (§9.6 REFERENCE)
    regs = tmp_path / "registries"
    (regs / "boilerplate").mkdir(parents=True)
    block = "This document describes the DIBR plan for all VA Enterprise products."
    from vdocs.kernel.text import block_key

    (regs / "boilerplate" / "boilerplate.yaml").write_text(
        "boilerplate:\n"
        "  - id: bp-test01\n"
        "    label: DIBR plan intro\n"
        f"    key: {block_key(block)!r}\n"
        f"    text: {block!r}\n"
    )
    ctx.cfg = ctx.cfg.model_copy(update={"registries_dir": regs})

    enriched = frontmatter.emit(
        {"title": "DIBR Guide", "app_code": "ADT", "tool_ver": "0.1.0"},
        f"# DIBR Guide\n\n## Intro\n\n{block}\n\nUnique body content.\n",
    )
    cas.atomic_write(ctx.cfg.silver_enriched / "ADT" / "bp_doc" / "body.md", enriched.encode())
    ctx.cfg.raw_index.parent.mkdir(parents=True, exist_ok=True)
    ctx.cfg.raw_index.write_text(
        json.dumps({_SHA: {"app_code": "ADT", "doc_slug": "bp_doc", "ext": "docx"}})
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
    assert result.counts["boilerplate_refs"] == 1

    _, body = frontmatter.parse(
        (ctx.cfg.silver_normalized / "ADT" / "bp_doc" / "body.md").read_text()
    )
    assert block not in body  # the boilerplate text is gone from the body
    assert "(_shared/boilerplate/bp-test01.md)" in body  # replaced by a reference, not deleted
    assert "Unique body content." in body  # the rest is untouched


def test_normalize_stamps_template_id_and_strips_scaffold(ctx, tmp_path):
    # point registries at a temp dir with a (DIBR, 2020s) template (§9.8 STRIP + STAMP)
    regs = tmp_path / "registries"
    (regs / "templates").mkdir(parents=True)
    (regs / "templates" / "templates.yaml").write_text(
        "templates:\n"
        "  - template_id: DIBR:2020s:deadbeef\n"
        "    doc_type: DIBR\n"
        "    era: 2020s\n"
        "    sections:\n"
        "      - {title: Purpose}\n"
        "      - {title: Rollback}\n"
    )
    ctx.cfg = ctx.cfg.model_copy(update={"registries_dir": regs})

    enriched = frontmatter.emit(
        {"title": "DG Deploy", "doc_type": "DIBR", "app_code": "ADT", "tool_ver": "0.1.0"},
        # title-page date → 2020s era; one filled scaffold section + one empty scaffold section
        "# DG Deploy\n\nSeptember 2021\n\n## Purpose\n\nReal purpose text.\n\n## Rollback\n\n",
    )
    cas.atomic_write(ctx.cfg.silver_enriched / "ADT" / "dg_doc" / "body.md", enriched.encode())
    ctx.cfg.raw_index.parent.mkdir(parents=True, exist_ok=True)
    ctx.cfg.raw_index.write_text(
        json.dumps({_SHA: {"app_code": "ADT", "doc_slug": "dg_doc", "ext": "docx"}})
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
    assert result.counts["templates_stamped"] == 1

    meta, body = frontmatter.parse(
        (ctx.cfg.silver_normalized / "ADT" / "dg_doc" / "body.md").read_text()
    )
    assert meta["template_id"] == "DIBR:2020s:deadbeef"  # stamped into identity FM (§6.3)
    assert "Real purpose text." in body  # filled scaffold section retained
    assert "## Rollback" not in body  # the empty scaffold section was stripped
    # the title sits at the top, above the derived TOC (title → Contents → body)
    assert body.index("# DG Deploy") < body.index("## Contents") < body.index("Real purpose")


def test_normalize_strips_legacy_toc_no_duplicate(ctx):
    # an enriched body carrying the source's own text TOC → exactly one derived `## Contents`,
    # driven by the curated registries/structures `toc` convention (§6.7/§9.6 CANONICALIZE)
    enriched = frontmatter.emit(
        {"title": "Legacy Manual", "app_code": "ADT", "tool_ver": "0.1.0"},
        "# Legacy Manual\n\n## Table of Contents\n\n"
        "Overview .......... 1\nSetup .......... 4\n\n"
        "## Overview\n\nintro\n\n## Setup\n\nsteps\n",
    )
    cas.atomic_write(ctx.cfg.silver_enriched / "ADT" / "lm_doc" / "body.md", enriched.encode())
    ctx.cfg.raw_index.parent.mkdir(parents=True, exist_ok=True)
    ctx.cfg.raw_index.write_text(
        json.dumps({_SHA: {"app_code": "ADT", "doc_slug": "lm_doc", "ext": "docx"}})
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
    assert result.status == "ok"

    _, body = frontmatter.parse(
        (ctx.cfg.silver_normalized / "ADT" / "lm_doc" / "body.md").read_text()
    )
    assert "Table of Contents" not in body  # the legacy heading left the body
    assert ".........." not in body  # …and so did its page-numbered entries
    assert body.count("## Contents") == 1  # one derived TOC, not two
    assert "- [Overview](#overview)" in body and "- [Setup](#setup)" in body


def test_normalize_writes_refs_yaml_sidecar(ctx):
    import yaml

    # a bundle with an in-body _Toc cross-ref + a real heading carrying that bookmark (§6.7)
    enriched = frontmatter.emit(
        {"title": "Ref Manual", "app_code": "ADT", "tool_ver": "0.1.0"},
        "# Ref Manual\n\nSee [the setup](#_Toc555) below.\n\n"
        '## <span id="_Toc555" class="anchor"></span>Setup\n\nsteps\n',
    )
    cas.atomic_write(ctx.cfg.silver_enriched / "ADT" / "rm_doc" / "body.md", enriched.encode())
    ctx.cfg.raw_index.parent.mkdir(parents=True, exist_ok=True)
    ctx.cfg.raw_index.write_text(
        json.dumps({_SHA: {"app_code": "ADT", "doc_slug": "rm_doc", "ext": "docx"}})
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
    assert result.counts["refs_sidecars"] == 1

    bundle = ctx.cfg.silver_normalized / "ADT" / "rm_doc"
    _, body = frontmatter.parse((bundle / "body.md").read_text())
    # the dead _Toc cross-ref became a live GitHub slug link + back-link inserted
    assert "[the setup](#setup)" in body and "#_Toc555" not in body
    assert "[↑ Back to Contents](#contents)" in body

    refs = yaml.safe_load((bundle / "refs.yaml").read_text())
    assert refs["doc_id"] == "ADT/rm_doc" and refs["toc_depth"] == [2, 3]
    by_slug = {a["slug"]: a for a in refs["anchors"]}
    assert by_slug["setup"]["stable_id"] == "ADT/rm_doc/setup"
    assert by_slug["setup"]["bookmark"] == "_Toc555" and by_slug["setup"]["toc_level"] is True
    assert refs["outbound"]["_Toc555"] == "setup"


def test_no_refs_yaml_when_no_headings(ctx):
    # a heading-less bundle has no anchors → no refs.yaml, and the count reflects it
    enriched = frontmatter.emit(
        {"title": "Flat", "app_code": "ADT", "tool_ver": "0.1.0"},
        "Just a paragraph with no headings at all.\n",
    )
    cas.atomic_write(ctx.cfg.silver_enriched / "ADT" / "flat_doc" / "body.md", enriched.encode())
    ctx.cfg.raw_index.parent.mkdir(parents=True, exist_ok=True)
    ctx.cfg.raw_index.write_text("{}")
    for stage, art in (("enrich", TEXT_ENRICHED), ("fetch", RAW_INDEX)):
        ctx.state.record(
            StageRun(
                stage=stage, scope="", status="ok", started_at="t", finished_at="t",
                inputs_fp={}, outputs_fp={art.key: art.fingerprint(ctx.cfg)}, counts={},
                contract_ver=1, tool_ver=ctx.cfg.tool_ver,
            )
        )  # fmt: skip

    (result,) = Orchestrator([NormalizeStage()]).run(ctx)
    assert result.counts["refs_sidecars"] == 0
    assert not (ctx.cfg.silver_normalized / "ADT" / "flat_doc" / "refs.yaml").exists()


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


def _seed_many(ctx, slugs):
    """Seed N enriched bundles + a raw/index.json covering them, and bless enrich + fetch."""
    index = {}
    for slug in slugs:
        body = frontmatter.emit({"title": slug, "app_code": "ADT"}, f"# {slug}\n\nbody text\n")
        cas.atomic_write(ctx.cfg.silver_enriched / "ADT" / slug / "body.md", body.encode())
        index[hashlib.sha256(slug.encode()).hexdigest()] = {
            "app_code": "ADT", "doc_slug": slug, "ext": "docx",
        }  # fmt: skip
    ctx.cfg.raw_index.parent.mkdir(parents=True, exist_ok=True)
    ctx.cfg.raw_index.write_text(json.dumps(index))
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
            )  # fmt: skip
        )


def test_normalize_isolates_a_single_doc_failure(ctx, monkeypatch):
    # R6: a single doc that raises is isolated (logged + counted); the rest still normalize
    _seed_many(ctx, ["aaa", "bad", "ccc"])
    from vdocs.stages.normalize import normalize_pure as nz

    real = nz.normalize_body

    def flaky(body, phrases, doc_id="", *args, **kwargs):
        if doc_id == "ADT/bad":
            raise ValueError("boom")
        return real(body, phrases, doc_id, *args, **kwargs)

    monkeypatch.setattr(nz, "normalize_body", flaky)
    (result,) = Orchestrator([NormalizeStage()]).run(ctx)
    assert result.status == "ok"
    assert result.counts["errors"] == 1 and result.counts["documents"] == 2
    assert (ctx.cfg.silver_normalized / "ADT" / "aaa" / "body.md").exists()
    assert not (ctx.cfg.silver_normalized / "ADT" / "bad" / "body.md").exists()


def test_normalize_fails_the_stage_when_error_rate_is_systemic(ctx, monkeypatch):
    _seed_many(ctx, ["aaa", "bbb"])
    from vdocs.stages.normalize import normalize_pure as nz

    def boom(*args, **kwargs):
        raise ValueError("boom")

    monkeypatch.setattr(nz, "normalize_body", boom)  # every doc fails → systemic → stage fails
    with pytest.raises(PostflightError):
        Orchestrator([NormalizeStage()]).run(ctx)


def test_normalize_writes_capture_manifest_for_every_bundle(ctx):
    # §6.4: capture.yaml is ALWAYS written (unlike the conditional sidecars), recording each
    # capture attempt's typed outcome so absence is never ambiguous.
    import yaml

    _seed(ctx)
    (result,) = Orchestrator([NormalizeStage()]).run(ctx)
    assert result.counts["capture_sidecars"] == 1  # one per bundle, always

    manifest = yaml.safe_load(
        (ctx.cfg.silver_normalized / "ADT" / "ig_doc" / "capture.yaml").read_text()
    )
    assert manifest["doc_id"] == "ADT/ig_doc"
    assert set(manifest["captures"]) == {"revisions", "tables", "refs", "toc", "title_date"}
    # the seeded doc has headings → refs captured; no revision table → revisions benignly absent
    assert manifest["captures"]["refs"]["outcome"] == "captured"
    assert manifest["captures"]["revisions"]["outcome"] == "absent-expected"
    assert result.counts["absent_unexpected"] == 0


def test_normalize_capture_flags_silent_detector_miss(ctx):
    # the gap flags.yaml cannot catch: a revision heading variant the strict detector misses
    # ("Change History" is not in the curated vocabulary) but the residue re-scan still sees —
    # so the bundle's capture.yaml records `absent-unexpected`, not a silent benign absence.
    import yaml

    enriched = frontmatter.emit(
        {"title": "Tech Manual", "app_code": "ADT", "tool_ver": "0.1.0"},
        "# Tech Manual\n\n## Change History\n\nNotes about versions, no parseable table.\n\n"
        "## Body\n\ncontent\n",
    )
    cas.atomic_write(ctx.cfg.silver_enriched / "ADT" / "ch_doc" / "body.md", enriched.encode())
    ctx.cfg.raw_index.parent.mkdir(parents=True, exist_ok=True)
    ctx.cfg.raw_index.write_text(
        json.dumps({_SHA: {"app_code": "ADT", "doc_slug": "ch_doc", "ext": "docx"}})
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
    assert result.counts["absent_unexpected"] == 1

    manifest = yaml.safe_load(
        (ctx.cfg.silver_normalized / "ADT" / "ch_doc" / "capture.yaml").read_text()
    )
    assert manifest["captures"]["revisions"]["outcome"] == "absent-unexpected"
    assert manifest["residue"]["revision_heading_present"] is True
