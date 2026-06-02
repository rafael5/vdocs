"""The `discover` stage — mine candidate patterns from the converted corpus (§8, §9.6).

Reads every ``text@converted`` body corpus-wide and runs the pure miners (recurring blocks →
boilerplate/dead-phrase candidates; acronyms → glossary candidates), emitting candidates with
evidence + a proposed disposition + a curation grade to ``reports/patterns``. It **mutates no
corpus content** — it only *proposes* registry updates; a separate curation gate (a human/auto
decision recorded in version-controlled ``registries/``) promotes them, and `normalize` then
subtracts the *curated* patterns. Diagnostic-but-on-path: it feeds the registry seam before
`normalize` so no pattern is ever hard-coded (tenet #13).
"""

from __future__ import annotations

from vdocs.contracts.registry import PATTERNS, TEXT_CONVERTED
from vdocs.kernel import cas
from vdocs.models.stage import Idempotency, RunResult
from vdocs.orchestrator.stage import Stage, StageContext


class DiscoverStage(Stage):
    name = "discover"
    description = "mine candidate boilerplate / dead-phrase / glossary patterns (proposals only)"
    requires = [TEXT_CONVERTED]
    produces = [PATTERNS]
    idempotency = Idempotency.SKIP_IF_UNCHANGED

    def run(self, ctx: StageContext, force: bool) -> RunResult:
        from vdocs.stages.discover import discover_pure as dp

        root = ctx.cfg.silver_converted
        docs = {
            str(body.parent.relative_to(root)): body.read_text(encoding="utf-8")
            for body in sorted(root.rglob("body.md"))
        }

        report = dp.PatternReport(
            boilerplate=dp.mine_recurring_blocks(docs),
            glossary=dp.mine_glossary(docs),
        )
        cas.atomic_write(ctx.cfg.patterns_report, report.model_dump_json(indent=2).encode("utf-8"))

        return RunResult(
            counts={
                "documents": len(docs),
                "boilerplate": len(report.boilerplate),
                "glossary": len(report.glossary),
            }
        )
