"""discover integration — mine the converted corpus → reports/patterns (Phase 3, §9.6).

Seeds a few text@converted bundles with a shared boilerplate block + shared acronyms, runs
DiscoverStage through the orchestrator (exercising the convert→discover contract), and asserts
the candidate report is written with the right dispositions — and that no body is mutated.
"""

from __future__ import annotations

from vdocs.contracts.registry import TEXT_CONVERTED
from vdocs.kernel import cas
from vdocs.models.stage import StageRun
from vdocs.orchestrator.engine import Orchestrator
from vdocs.stages.discover.discover_pure import PatternReport
from vdocs.stages.discover.stage import DiscoverStage

_BOILER = (
    "How to Use This Manual: read each section in order and consult the index for the "
    "specific topics covered throughout this CPRS document."
)


def _seed_converted(ctx, n=4):
    root = ctx.cfg.silver_converted
    for i in range(n):
        body = root / "CPRS" / f"doc_{i}" / "body.md"
        text = f"# Doc {i}\n\n{_BOILER}\n\n**Note:** read it.\n\nUnique content for doc {i}.\n"
        cas.atomic_write(body, text.encode())
    ctx.state.record(
        StageRun(
            stage="convert",
            scope="",
            status="ok",
            started_at="t",
            finished_at="t",
            inputs_fp={},
            outputs_fp={TEXT_CONVERTED.key: TEXT_CONVERTED.fingerprint(ctx.cfg)},
            counts={},
            contract_ver=1,
            tool_ver=ctx.cfg.tool_ver,
        )
    )


def test_discover_emits_candidate_patterns(ctx):
    _seed_converted(ctx, n=4)
    bodies_before = {p: p.read_bytes() for p in ctx.cfg.silver_converted.rglob("body.md")}

    (result,) = Orchestrator([DiscoverStage()]).run(ctx)
    assert result.status == "ok"
    assert result.counts["documents"] == 4
    assert result.counts["boilerplate"] >= 1  # per-registry count

    report = PatternReport.model_validate_json(ctx.cfg.patterns_report.read_text())
    boiler = [c for c in report.blocks if "how to use this manual" in c.key]
    assert boiler and boiler[0].disposition == "REFERENCE" and boiler[0].doc_count == 4
    # CPRS appears in all 4 docs → a glossary candidate
    assert "CPRS" in {c.key for c in report.glossary}
    # the recurring **Note:** callout → a structures (CANONICALIZE) candidate
    note = [c for c in report.structures if c.key == "callout:note"]
    assert note and note[0].canonical_form == "> [!NOTE]" and note[0].doc_count == 4

    # discover mutates NO corpus content (proposals only, §9.6)
    assert {p: p.read_bytes() for p in ctx.cfg.silver_converted.rglob("body.md")} == bodies_before


def test_discover_skips_on_clean_rerun(ctx):
    _seed_converted(ctx, n=4)
    orch = Orchestrator([DiscoverStage()])
    orch.run(ctx)
    assert orch.run(ctx) == [None]
