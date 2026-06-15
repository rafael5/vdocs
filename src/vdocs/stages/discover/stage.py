"""The `discover` stage — mine candidate patterns from the converted corpus (§8, §9.6).

Reads every ``text@converted`` body corpus-wide and runs the pure miners (recurring blocks →
boilerplate/dead-phrase candidates; acronyms → glossary candidates; structural conventions →
structures candidates; per-``(doc_type, era)`` scaffolds → template candidates), emitting
candidates with evidence + a proposed disposition + a curation grade to ``reports/patterns``.
It **mutates no corpus content** — it only *proposes* registry updates; a separate curation gate
(a human/auto decision recorded in version-controlled ``registries/``) promotes them, and
`normalize` then subtracts the *curated* patterns. Diagnostic-but-on-path: it feeds the registry
seam before `normalize` so no pattern is ever hard-coded (tenet #13).

The ``catalog.enriched`` input supplies only the authoritative ``doc_code`` (doc_type) for the
``(doc_type, era)`` template induction — classification stays a `catalog` decision (tenet #13),
not re-derived here. ``era`` is read from each body's own title-page date (§9.8).
"""

from __future__ import annotations

from vdocs.contracts.registry import CATALOG_ENRICHED, PATTERNS, TEXT_CONVERTED
from vdocs.kernel import cas, ids
from vdocs.models.catalog import EnrichedInventory, EnrichedRecord
from vdocs.models.stage import Idempotency, RunResult
from vdocs.orchestrator.stage import Stage, StageContext


class DiscoverStage(Stage):
    name = "discover"
    description = (
        "mine candidate boilerplate / dead-phrase / glossary / structure / template patterns "
        "(proposals only)"
    )
    requires = [TEXT_CONVERTED, CATALOG_ENRICHED]
    produces = [PATTERNS]
    idempotency = Idempotency.SKIP_IF_UNCHANGED

    def run(self, ctx: StageContext, force: bool) -> RunResult:
        from vdocs.stages.discover import discover_pure as dp

        root = ctx.cfg.silver_converted
        docs = {
            str(body.parent.relative_to(root)): body.read_text(encoding="utf-8")
            for body in sorted(root.rglob("body.md"))
        }
        records = EnrichedInventory.model_validate_json(
            ctx.cfg.catalog_enriched.read_text(encoding="utf-8")
        ).records
        doc_types = _doc_types_by_bundle_path(records)

        report = dp.PatternReport(
            blocks=dp.mine_recurring_blocks(docs),
            glossary=dp.mine_glossary(docs),
            converter_routing=dp.mine_converter_routing(docs),
            structures=dp.mine_structures(docs),
            templates=dp.mine_templates(docs, doc_types),
        )
        cas.atomic_write(ctx.cfg.patterns_report, report.model_dump_json(indent=2).encode("utf-8"))

        counts = {
            "documents": len(docs),
            "glossary": len(report.glossary),
            "converter_routing": len(report.converter_routing),
            "structures": len(report.structures),
            "templates": len(report.templates),  # induced (doc_type, era) templates (§9.8)
        }
        # recurring-block candidates, per registry; the "templates" registry here is raw recurring
        # scaffold *lines* (distinct from the induced templates above) → keyed as scaffold_blocks
        for c in report.blocks:
            key = "scaffold_blocks" if c.registry == "templates" else c.registry
            counts[key] = counts.get(key, 0) + 1
        return RunResult(counts=counts)


def _doc_types_by_bundle_path(records: list[EnrichedRecord]) -> dict[str, str]:
    """Map each ``<app>/<slug>`` bundle path → its catalog ``doc_code`` (genuine docs only, DOCX
    preferred), matching the convert bundle layout — mirrors `enrich`'s join (§9.2 pattern)."""
    out: dict[str, str] = {}
    for r in records:
        if r.noise_type or not r.doc_code:
            continue
        path = ids.bundle_path(r.app_name_abbrev, r.doc_slug)
        if path not in out or r.doc_format == "docx":
            out[path] = r.doc_code
    return out
