"""The `serve-inventory` stage — promote silver → the GOLD INVENTORY + the fetch gate (§8).

Reads the conformed ``catalog.enriched`` and writes the inv-gold selection surface: a
portable ``inventory.json`` and a queryable ``inventory.db`` (one indexed ``inventory``
table). Its **postflight is a HARD GATE** (``deep_gate``): the gold inventory is blessed
``ok`` only when it is complete vs. the crawl, noise-classified, system-classified, and
structurally sound (spec §7). **That `ok` is the fetch gate** — the document medallion's
``fetch`` requires it via the generic consumer-preflight (§7.3), so nothing downstream runs
until the gate is green.
"""

from __future__ import annotations

import os

from vdocs.contracts.registry import CATALOG_ENRICHED, GOLD_INVENTORY, GOLD_INVENTORY_DB
from vdocs.kernel import cas, db
from vdocs.kernel import csv as kcsv
from vdocs.models.catalog import ENRICHED_COLUMNS, EnrichedInventory, EnrichedRecord
from vdocs.models.stage import Idempotency, PostflightResult, RunResult
from vdocs.orchestrator.stage import Stage, StageContext
from vdocs.stages.serve_inventory import serve_pure as sp

# columns indexed for the common selection queries (by app/section/type/group/noise/id)
_INDEXED = ("doc_id", "app_name_abbrev", "section_code", "doc_code", "group_key", "noise_type")
# the published CSV table leads with the stable doc_id join key, then the §5 columns
_CSV_COLUMNS = ["doc_id", *ENRICHED_COLUMNS]


class ServeInventoryStage(Stage):
    name = "serve-inventory"
    description = "promote the enriched inventory to the gold selection surface + the fetch gate"
    requires = [CATALOG_ENRICHED]
    produces = [GOLD_INVENTORY, GOLD_INVENTORY_DB]
    idempotency = Idempotency.SKIP_IF_UNCHANGED

    def run(self, ctx: StageContext, force: bool) -> RunResult:
        inventory = EnrichedInventory.model_validate_json(
            ctx.cfg.catalog_enriched.read_text(encoding="utf-8")
        )
        records = inventory.records

        # portable JSON view (the gold inventory, browsable/selectable)
        cas.atomic_write(
            ctx.cfg.gold_inventory_json, inventory.model_dump_json(indent=2).encode("utf-8")
        )
        # published flat CSV table (human-browsable / spreadsheet-friendly)
        rows = ({"doc_id": sp.doc_id(r), **r.model_dump()} for r in records)
        cas.atomic_write(
            ctx.cfg.gold_inventory_csv, kcsv.to_csv(_CSV_COLUMNS, rows).encode("utf-8")
        )
        # queryable SQLite, built atomically (temp + rename, §7.4)
        _build_db(ctx.cfg.gold_inventory_db, records)

        counts = {"records": len(records), "genuine": sum(1 for r in records if not r.noise_type)}
        return RunResult(counts=counts)

    def deep_gate(self, ctx: StageContext) -> PostflightResult:
        inventory = EnrichedInventory.model_validate_json(
            ctx.cfg.gold_inventory_json.read_text(encoding="utf-8")
        )
        crawl = ctx.state.get("crawl", ctx.scope)
        crawl_documents = crawl.counts.get("documents") if crawl is not None else None
        verdict = sp.evaluate_gate(inventory.records, crawl_documents)
        if verdict.unclassified:
            import structlog

            structlog.get_logger(__name__).warning(
                "inventory-unclassified-apps", count=verdict.unclassified
            )
        return PostflightResult(ok=verdict.ok, reason=verdict.reason)


def _build_db(path, records: list[EnrichedRecord]) -> None:  # type: ignore[no-untyped-def]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    if tmp.exists():
        tmp.unlink()
    col_defs = ", ".join(
        f"{c} INTEGER" if c == "cots_dependent" else f"{c} TEXT" for c in _CSV_COLUMNS
    )
    conn = db.connect(tmp)
    try:
        conn.execute(f"CREATE TABLE inventory ({col_defs})")
        placeholders = ", ".join("?" for _ in _CSV_COLUMNS)
        conn.executemany(
            f"INSERT INTO inventory ({', '.join(_CSV_COLUMNS)}) VALUES ({placeholders})",
            [[sp.doc_id(r), *[_cell(getattr(r, c)) for c in ENRICHED_COLUMNS]] for r in records],
        )
        for col in _INDEXED:
            conn.execute(f"CREATE INDEX idx_inventory_{col} ON inventory ({col})")
        conn.commit()
    finally:
        conn.close()
    os.replace(tmp, path)


def _cell(value: object) -> object:
    """SQLite cell: bool → 0/1, everything else as-is (all enriched fields are str/bool)."""
    return int(value) if isinstance(value, bool) else value
