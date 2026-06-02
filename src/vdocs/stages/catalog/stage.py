"""The `catalog` stage driver — enrich ``catalog.raw`` into the conformed inventory (§8, §4).

Thin I/O around the pure engine (``enrich_pure``): it flattens the crawled ``catalog.raw``
into raw rows, loads the curated ``registries/`` vocabularies, runs the 5-pass + system
classification pipeline, and writes the inv-silver ``catalog.enriched.{json,csv}`` + a
per-field schema manifest. Deterministic — a pure function of ``catalog.raw`` + the
registries (drift is decided later, at ``fetch``/``acquisitions``, §7.6).
"""

from __future__ import annotations

import json

from vdocs.contracts.registry import CATALOG_ENRICHED, CATALOG_RAW
from vdocs.kernel import cas
from vdocs.kernel import csv as kcsv
from vdocs.models.catalog import ENRICHED_COLUMNS, Catalog, EnrichedInventory, EnrichedRecord
from vdocs.models.stage import Idempotency, RunResult
from vdocs.orchestrator.stage import Stage, StageContext


class CatalogStage(Stage):
    name = "catalog"
    description = "enrich catalog.raw into the conformed inventory (identity, doc-type, noise)"
    requires = [CATALOG_RAW]
    produces = [CATALOG_ENRICHED]
    idempotency = Idempotency.SKIP_IF_UNCHANGED

    def run(self, ctx: StageContext, force: bool) -> RunResult:
        from vdocs.stages.catalog import enrich_pure as ep
        from vdocs.stages.catalog import registries as rg

        catalog = Catalog.model_validate_json(ctx.cfg.catalog_raw.read_text(encoding="utf-8"))
        reg = rg.load_registries(ctx.cfg.registries)

        raw_rows = [_raw_row(s, a, d) for s, a, d in catalog.walk()]
        enriched = ep.enrich_rows(raw_rows, reg)
        records = [EnrichedRecord(**row) for row in enriched]

        inventory = EnrichedInventory(records=records)
        cas.atomic_write(
            ctx.cfg.catalog_enriched, inventory.model_dump_json(indent=2).encode("utf-8")
        )
        cas.atomic_write(
            ctx.cfg.catalog_enriched.with_suffix(".csv"),
            kcsv.to_csv(ENRICHED_COLUMNS, (r.model_dump() for r in records)).encode("utf-8"),
        )
        cas.atomic_write(
            ctx.cfg.catalog_enriched.with_suffix(".schema.json"),
            json.dumps(_schema(records), indent=2).encode("utf-8"),
        )

        counts: dict[str, int] = {"records": len(records)}
        for r in records:
            counts[f"noise:{r.noise_type or 'clean'}"] = (
                counts.get(f"noise:{r.noise_type or 'clean'}", 0) + 1
            )
        return RunResult(counts=counts)


def _raw_row(section, app, doc) -> dict:  # type: ignore[no-untyped-def]
    """Flatten a (section, application, document) triple into a raw enrichment row.

    Reconstructs ``app_name`` with its parenthetical code so the pure pass-1 abbrev
    extraction reproduces v1's behaviour exactly (crawl split name/app_code apart).
    """
    app_name = f"{app.name} ({app.app_code})" if app.app_code else app.name
    return {
        "section_name": section.name,
        "app_name": app_name,
        "app_status": app.status,
        "decommission_date": app.decommission_date,
        "doc_title": doc.title,
        "filename": doc.filename,
        "file_ext": doc.file_ext,
        "doc_url": doc.url,
        "app_url": app.url,
    }


def _schema(records: list[EnrichedRecord]) -> dict:
    """A light per-field type manifest (the spec's ``vdl_inventory_schema.json`` analogue)."""
    fields = {
        name: {"type": "boolean" if name == "cots_dependent" else "string"}
        for name in ENRICHED_COLUMNS
    }
    return {
        "description": "Field type manifest for catalog.enriched (inventory medallion silver)",
        "row_count": len(records),
        "columns": ENRICHED_COLUMNS,
        "fields": fields,
    }
