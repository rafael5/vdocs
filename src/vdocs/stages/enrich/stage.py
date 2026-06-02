"""The `enrich` stage — bake identity frontmatter + stage doc metadata (§8, §6.3).

Joins each ``text@converted`` bundle with its inventory record (by the bundle's ``<app>/<slug>``
path) and writes a ``text@enriched`` bundle with the **identity frontmatter** baked into
``body.md`` (§6.3); in parallel it stages per-document metadata (identity + computed
``word_count``) into ``index.db:doc_meta_staged`` for the `index` stage. Computed fields never
enter the body — they live only in the staged table (so a body diff stays a real content diff).
"""

from __future__ import annotations

import structlog

from vdocs.contracts.registry import (
    CATALOG_ENRICHED,
    DOC_META_STAGED,
    TEXT_CONVERTED,
    TEXT_ENRICHED,
)
from vdocs.kernel import cas, db, frontmatter
from vdocs.kernel.text import safe_component
from vdocs.models.catalog import EnrichedInventory, EnrichedRecord
from vdocs.models.stage import Idempotency, RunResult
from vdocs.orchestrator.stage import Stage, StageContext

log = structlog.get_logger(__name__)


class EnrichStage(Stage):
    name = "enrich"
    description = "bake identity frontmatter onto converted bundles + stage doc metadata for index"
    requires = [TEXT_CONVERTED, CATALOG_ENRICHED]
    produces = [TEXT_ENRICHED, DOC_META_STAGED]
    idempotency = Idempotency.SKIP_IF_UNCHANGED

    def run(self, ctx: StageContext, force: bool) -> RunResult:
        from vdocs.stages.enrich import enrich_pure as ep

        records = EnrichedInventory.model_validate_json(
            ctx.cfg.catalog_enriched.read_text(encoding="utf-8")
        ).records
        by_path = _index_by_bundle_path(records)

        converted_root = ctx.cfg.silver_converted
        enriched_root = ctx.cfg.silver_enriched
        staged: list[dict[str, object]] = []
        kept: set[str] = set()  # <app>/<slug> bundles in this run's input set (R5 pruning)
        n_docs = n_missing = 0
        for body_path in sorted(converted_root.rglob("body.md")):
            rel = body_path.parent.relative_to(converted_root)  # <app>/<slug>
            kept.add(rel.as_posix())
            record = by_path.get((rel.parts[0], rel.parts[1]))
            if record is None:
                log.warning("enrich-no-inventory-record", bundle=str(rel))
                n_missing += 1
                continue
            body = body_path.read_text(encoding="utf-8")
            fm = ep.identity_frontmatter(record, tool_ver=ctx.cfg.tool_ver)
            cas.atomic_write(
                enriched_root / rel / "body.md", frontmatter.emit(fm, body).encode("utf-8")
            )
            staged.append(ep.staged_row(record, body=body, bundle_path=str(rel)))
            n_docs += 1

        n_pruned = cas.prune_bundles(enriched_root, kept)
        _write_staged(ctx.cfg.index_db, staged)
        return RunResult(
            counts={"documents": n_docs, "missing_record": n_missing, "pruned": n_pruned}
        )


def _index_by_bundle_path(
    records: list[EnrichedRecord],
) -> dict[tuple[str, str], EnrichedRecord]:
    """Map ``(safe app, doc_slug)`` → record (genuine only, DOCX preferred), matching the
    convert bundle layout so a sanitised app code (AR/WS→AR_WS) still joins."""
    by_path: dict[tuple[str, str], EnrichedRecord] = {}
    for r in records:
        if r.noise_type:
            continue
        key = (safe_component(r.app_name_abbrev), safe_component(r.doc_slug))
        current = by_path.get(key)
        if current is None or (r.doc_format == "docx" and current.doc_format != "docx"):
            by_path[key] = r
    return by_path


def _write_staged(index_db, staged: list[dict[str, object]]) -> None:  # type: ignore[no-untyped-def]
    from vdocs.stages.enrich import enrich_pure as ep

    index_db.parent.mkdir(parents=True, exist_ok=True)
    cols = ", ".join(
        f"{c} TEXT" if c != "word_count" else f"{c} INTEGER" for c in ep.STAGED_COLUMNS
    )
    placeholders = ", ".join("?" for _ in ep.STAGED_COLUMNS)
    rows = [[row[c] for c in ep.STAGED_COLUMNS] for row in staged]
    conn = db.connect(index_db)
    try:
        # Atomic rebuild (§7.4): build the replacement in a side table — the live
        # doc_meta_staged is untouched until the swap — then drop-old + rename-new inside one
        # transaction, so a crash never exposes a missing or half-written table.
        conn.execute("DROP TABLE IF EXISTS doc_meta_staged__new")
        conn.execute(f"CREATE TABLE doc_meta_staged__new ({cols}, PRIMARY KEY (doc_id))")
        conn.executemany(
            f"INSERT OR REPLACE INTO doc_meta_staged__new ({', '.join(ep.STAGED_COLUMNS)}) "
            f"VALUES ({placeholders})",
            rows,
        )
        conn.commit()
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DROP TABLE IF EXISTS doc_meta_staged")
        conn.execute("ALTER TABLE doc_meta_staged__new RENAME TO doc_meta_staged")
        conn.commit()
    finally:
        conn.close()
