"""validate integration — the sidecar-verification HARD GATE (Steps 2-3; §8, FF C2/C5).

Seeds a normalized tree of bundles (each with capture.yaml + refs.yaml), blesses the normalize
upstream with its emitted counts, runs ValidateStage through the orchestrator, and asserts the gate:
PASSES on a clean corpus (writing the findings report), and FAILS loudly on a per-document
absent-unexpected (typed absence), a corpus-zero whole-detector failure (count reconciliation), a
severed cross-ref (ref resolution), and a cross-run count drop.
"""

from __future__ import annotations

import json

import pytest
import yaml

from vdocs.contracts.registry import TEXT_NORMALIZED
from vdocs.kernel import cas, frontmatter
from vdocs.models.stage import StageRun
from vdocs.orchestrator.engine import Orchestrator
from vdocs.orchestrator.stage import PostflightError
from vdocs.stages.validate.stage import ValidateStage


def _bless_normalize(ctx, counts):
    ctx.state.record(
        StageRun(
            stage="normalize",
            scope="",
            status="ok",
            started_at="t",
            finished_at="t",
            inputs_fp={},
            outputs_fp={TEXT_NORMALIZED.key: TEXT_NORMALIZED.fingerprint(ctx.cfg)},
            counts=counts,
            contract_ver=1,
            tool_ver=ctx.cfg.tool_ver,
        )  # fmt: skip
    )


def _seed_bundle(ctx, slug, *, captures, anchors=("intro",), outbound=None):
    """Write one normalized bundle: body.md + capture.yaml + refs.yaml."""
    bundle = ctx.cfg.silver_normalized / "ADT" / slug
    cas.atomic_write(
        bundle / "body.md",
        frontmatter.emit(
            {"title": slug, "app_code": "ADT", "tool_ver": "0.1.0"}, "# Doc\n"
        ).encode(),
    )
    cas.atomic_write(
        bundle / "capture.yaml",
        yaml.safe_dump(
            {"doc_id": f"ADT/{slug}", "captures": {k: {"outcome": v} for k, v in captures.items()}}
        ).encode(),
    )
    cas.atomic_write(
        bundle / "refs.yaml",
        yaml.safe_dump(
            {
                "doc_id": f"ADT/{slug}",
                "anchors": [{"slug": s, "title": s} for s in anchors],
                "outbound": outbound or {},
            }
        ).encode(),
    )


def test_validate_passes_clean_corpus_and_writes_report(ctx):
    _seed_bundle(ctx, "a", captures={"refs": "captured", "tables": "captured"})
    _bless_normalize(ctx, {"documents": 1, "refs_sidecars": 1, "tables_sidecars": 1})

    (result,) = Orchestrator([ValidateStage()]).run(ctx)
    assert result.status == "ok"
    assert result.counts["blocking"] == 0

    report = json.loads(ctx.cfg.validation_report.read_text())
    assert report["blocking"] is False
    assert report["counts"]["documents"] == 1  # recorded as the cross-run baseline


def test_validate_fails_on_absent_unexpected(ctx):
    # Step 1's per-document silent miss must trip the gate (typed-absence gate)
    _seed_bundle(ctx, "a", captures={"refs": "captured", "revisions": "absent-unexpected"})
    _bless_normalize(ctx, {"documents": 1, "refs_sidecars": 1, "absent_unexpected": 1})

    with pytest.raises(PostflightError):
        Orchestrator([ValidateStage()]).run(ctx)
    report = json.loads(ctx.cfg.validation_report.read_text())
    assert report["blocking"] is True
    assert any(f["kind"] == "absent-unexpected" for f in report["reconcile_findings"])


def test_validate_fails_on_severed_cross_ref(ctx):
    # Step 3: an outbound ref pointing at a slug no heading carries — a dead anchor (hard floor 0)
    _seed_bundle(
        ctx, "a", captures={"refs": "captured"}, anchors=("intro",),
        outbound={"_Toc1": "intro", "_Toc9": "gone"},
    )  # fmt: skip
    _bless_normalize(ctx, {"documents": 1, "refs_sidecars": 1})

    with pytest.raises(PostflightError):
        Orchestrator([ValidateStage()]).run(ctx)
    report = json.loads(ctx.cfg.validation_report.read_text())
    assert report["ref_findings"]["severed"]
    assert report["blocking"] is True


def test_validate_fails_on_corpus_zero_tables(ctx):
    # Step 2: zero tables across a large corpus ⇒ whole-detector failure (count reconciliation)
    for i in range(60):
        _seed_bundle(ctx, f"d{i}", captures={"refs": "captured", "tables": "absent-expected"})
    _bless_normalize(ctx, {"documents": 60, "refs_sidecars": 60, "tables_sidecars": 0})

    with pytest.raises(PostflightError):
        Orchestrator([ValidateStage()]).run(ctx)
    report = json.loads(ctx.cfg.validation_report.read_text())
    assert any(f["kind"] == "corpus-zero" for f in report["reconcile_findings"])


def test_validate_fails_on_count_drop_vs_prior_report(ctx):
    # Step 2: a sidecar count that dropped vs. the prior run over a same-or-larger corpus
    ctx.cfg.validation_report.parent.mkdir(parents=True, exist_ok=True)
    ctx.cfg.validation_report.write_text(
        json.dumps({"counts": {"documents": 60, "refs_sidecars": 60, "tables_sidecars": 55}})
    )
    for i in range(60):
        _seed_bundle(ctx, f"d{i}", captures={"refs": "captured", "tables": "captured"})
    _bless_normalize(ctx, {"documents": 60, "refs_sidecars": 60, "tables_sidecars": 40})

    with pytest.raises(PostflightError):
        Orchestrator([ValidateStage()]).run(ctx)
    report = json.loads(ctx.cfg.validation_report.read_text())
    assert any(f["kind"] == "count-drop" for f in report["reconcile_findings"])


def test_validate_tolerates_unmapped_bookmark_below_floor(ctx):
    # an UNRESOLVED bookmark is the already-flagged class, not a severed regression — one in many
    # outbound refs is below the C5 cross-ref rate floor, so it does not block.
    outbound = {f"_Toc{i}": "intro" for i in range(99)}
    outbound["_TocX"] = "UNRESOLVED"
    _seed_bundle(ctx, "a", captures={"refs": "captured"}, outbound=outbound)
    _bless_normalize(ctx, {"documents": 1, "refs_sidecars": 1})

    (result,) = Orchestrator([ValidateStage()]).run(ctx)
    assert result.status == "ok" and result.counts["blocking"] == 0


def test_validate_handles_bundle_without_sidecars(ctx):
    # a bundle with only body.md (no capture.yaml / refs.yaml) is skipped, not crashed
    bundle = ctx.cfg.silver_normalized / "ADT" / "bare"
    cas.atomic_write(
        bundle / "body.md",
        frontmatter.emit(
            {"title": "bare", "app_code": "ADT", "tool_ver": "0.1.0"}, "# Doc\n"
        ).encode(),
    )
    _bless_normalize(ctx, {"documents": 1})
    (result,) = Orchestrator([ValidateStage()]).run(ctx)
    assert result.status == "ok" and result.counts["blocking"] == 0


def test_validate_tolerates_corrupt_prior_report(ctx):
    # a malformed prior report must not crash the gate (no cross-run baseline → no drop check)
    ctx.cfg.validation_report.parent.mkdir(parents=True, exist_ok=True)
    ctx.cfg.validation_report.write_text("not json{")
    _seed_bundle(ctx, "a", captures={"refs": "captured"})
    _bless_normalize(ctx, {"documents": 1, "refs_sidecars": 1})
    (result,) = Orchestrator([ValidateStage()]).run(ctx)
    assert result.status == "ok"
