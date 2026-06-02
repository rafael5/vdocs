"""discover integration — mine the converted corpus → reports/patterns (Phase 3, §9.6).

Seeds a few text@converted bundles with a shared boilerplate block + shared acronyms, runs
DiscoverStage through the orchestrator (exercising the convert→discover contract), and asserts
the candidate report is written with the right dispositions — and that no body is mutated.
"""

from __future__ import annotations

from vdocs.contracts.registry import CATALOG_ENRICHED, TEXT_CONVERTED
from vdocs.kernel import cas
from vdocs.models.catalog import EnrichedInventory, EnrichedRecord
from vdocs.models.stage import StageRun
from vdocs.orchestrator.engine import Orchestrator
from vdocs.stages.discover.discover_pure import PatternReport
from vdocs.stages.discover.stage import DiscoverStage

_BOILER = (
    "How to Use This Manual: read each section in order and consult the index for the "
    "specific topics covered throughout this CPRS document."
)
# a shared title-page date (2013 → 2010s era) + a shared section scaffold → one (UM, 2010s) template
_SECTIONS = "## Orientation\n\n## Getting Started\n\n## Troubleshooting\n\n## Glossary"


def _seed_converted(ctx, n=4):
    root = ctx.cfg.silver_converted
    for i in range(n):
        body = root / "CPRS" / f"doc_{i}" / "body.md"
        text = (
            f"# Doc {i}\n\nUser Manual\n\nJanuary 2013\n\n{_BOILER}\n\n"
            f"**Note:** read it.\n\n{_SECTIONS}\n\nUnique content for doc {i}.\n"
        )
        cas.atomic_write(body, text.encode())
    records = [
        EnrichedRecord(
            app_name_abbrev="CPRS", doc_slug=f"doc_{i}", doc_code="UM", doc_format="docx"
        )
        for i in range(n)
    ]
    # a noise row (no doc_code, classified noise) — excluded from the doc_type join
    records.append(
        EnrichedRecord(
            app_name_abbrev="CPRS", doc_slug="vba_form_x", doc_code="", noise_type="vba_form"
        )
    )
    cas.atomic_write(
        ctx.cfg.catalog_enriched,
        EnrichedInventory(records=records).model_dump_json().encode("utf-8"),
    )
    for stage, art in (("catalog", CATALOG_ENRICHED), ("convert", TEXT_CONVERTED)):
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
    # the shared (UM, 2010s) scaffold → one template candidate with a retained schema (§9.8)
    assert result.counts["templates"] == 1
    (tmpl,) = report.templates
    assert tmpl.doc_type == "UM" and tmpl.era == "2010s" and tmpl.disposition == "STRIP"
    assert [s.title for s in tmpl.sections] == [
        "Orientation",
        "Getting Started",
        "Troubleshooting",
        "Glossary",
    ]

    # discover mutates NO corpus content (proposals only, §9.6)
    assert {p: p.read_bytes() for p in ctx.cfg.silver_converted.rglob("body.md")} == bodies_before


def test_discover_skips_on_clean_rerun(ctx):
    _seed_converted(ctx, n=4)
    orch = Orchestrator([DiscoverStage()])
    orch.run(ctx)
    assert orch.run(ctx) == [None]
