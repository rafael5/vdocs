"""The `catalog` stage driver — enrich + drift-classify into ``catalog.enriched`` (§8, §7.6).

Reads ``catalog.raw``, derives identity/classification per document (pure), diffs against the
prior ``catalog.enriched`` for drift, and writes the enriched catalog as JSON + CSV.
"""

from __future__ import annotations

import csv
import io

from vdocs.contracts.registry import CATALOG_ENRICHED, CATALOG_RAW
from vdocs.kernel import cas
from vdocs.models.catalog import Catalog, EnrichedCatalog, EnrichedDocument
from vdocs.models.stage import Idempotency, RunResult
from vdocs.orchestrator.stage import Stage, StageContext

_CSV_COLUMNS = [
    "section_code",
    "app_code",
    "pkg_ns",
    "patch_id",
    "patch_ver",
    "patch_num",
    "doc_type",
    "doc_label",
    "doc_slug",
    "group_key",
    "drift_status",
    "url",
]


class CatalogStage(Stage):
    name = "catalog"
    description = "enrich catalog.raw with patch identity, doc-type, version groups, and drift"
    requires = [CATALOG_RAW]
    produces = [CATALOG_ENRICHED]
    idempotency = Idempotency.SKIP_IF_UNCHANGED

    def run(self, ctx: StageContext, force: bool) -> RunResult:
        from vdocs.stages.catalog import catalog_pure as cp

        catalog = Catalog.model_validate_json(ctx.cfg.catalog_raw.read_text(encoding="utf-8"))
        enriched = [cp.enrich_document(s, a, d) for s, a, d in catalog.walk()]

        prior: list[EnrichedDocument] = []
        if ctx.cfg.catalog_enriched.exists():
            prior = EnrichedCatalog.model_validate_json(
                ctx.cfg.catalog_enriched.read_text(encoding="utf-8")
            ).documents

        report = cp.diff_catalog(enriched, prior)
        out = EnrichedCatalog(documents=report.documents, withdrawn=report.withdrawn)
        cas.atomic_write(ctx.cfg.catalog_enriched, out.model_dump_json(indent=2).encode("utf-8"))
        cas.atomic_write(
            ctx.cfg.catalog_enriched.with_suffix(".csv"), _to_csv(report.documents).encode("utf-8")
        )

        counts: dict[str, int] = {
            "documents": len(report.documents),
            "withdrawn": len(report.withdrawn),
        }
        for doc in report.documents:
            counts[doc.drift_status.value] = counts.get(doc.drift_status.value, 0) + 1
        return RunResult(counts=counts)


def _to_csv(docs: list[EnrichedDocument]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_CSV_COLUMNS)
    writer.writeheader()
    for d in docs:
        writer.writerow(
            {
                "section_code": d.section_code,
                "app_code": d.app_code,
                "pkg_ns": d.pkg_ns,
                "patch_id": d.patch_id,
                "patch_ver": d.patch_ver,
                "patch_num": d.patch_num,
                "doc_type": d.doc_type.value,
                "doc_label": d.doc_label,
                "doc_slug": d.doc_slug,
                "group_key": d.group_key,
                "drift_status": d.drift_status.value,
                "url": d.url,
            }
        )
    return buf.getvalue()
