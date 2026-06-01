"""Catalog drift across two runs — the §7.6 always-current mechanism through the driver."""

import json

from vdocs.contracts.registry import CATALOG_RAW
from vdocs.kernel import cas
from vdocs.models.catalog import DriftStatus, EnrichedCatalog
from vdocs.models.stage import StageRun
from vdocs.orchestrator.engine import Orchestrator
from vdocs.stages.catalog.stage import CatalogStage


def _raw(*patch_nums: int) -> dict:
    docs = [
        {
            "title": f"DG*5.3*{n} Installation Guide",
            "url": f"https://va.gov/d/dg_5_3_{n}_dibr.docx",
            "filename": f"dg_5_3_{n}_dibr.docx",
            "file_ext": ".docx",
        }
        for n in patch_nums
    ]
    return {
        "sections": [
            {
                "name": "Clinical",
                "url": "u",
                "applications": [{"name": "ADT", "app_code": "ADT", "url": "u", "documents": docs}],
            }
        ]
    }


def _write_raw(ctx, raw: dict) -> None:
    """Write catalog.raw and record the matching `crawl` completion (as a real crawl would)."""
    cas.atomic_write(ctx.cfg.catalog_raw, json.dumps(raw).encode())
    ctx.state.record(
        StageRun(
            stage="crawl",
            status="ok",
            started_at="t",
            finished_at="t",
            inputs_fp={"vdl": "external:vdl"},
            outputs_fp={CATALOG_RAW.key: CATALOG_RAW.fingerprint(ctx.cfg)},
            counts={},
            contract_ver=1,
            tool_ver=ctx.cfg.tool_ver,
        )
    )


def test_catalog_drift_supersede_and_withdraw(ctx):
    stage = CatalogStage()
    orch = Orchestrator([stage])

    # first run: two patches, both NEW
    _write_raw(ctx, _raw(1000, 1057))
    orch.run(ctx, only="catalog", force=True)
    first = EnrichedCatalog.model_validate_json(ctx.cfg.catalog_enriched.read_text())
    assert {d.drift_status for d in first.documents} == {DriftStatus.NEW}

    # second crawl: 1057 stays, 1000 vanished, 1099 appeared → re-run catalog (force)
    _write_raw(ctx, _raw(1057, 1099))
    orch.run(ctx, only="catalog", force=True)
    second = EnrichedCatalog.model_validate_json(ctx.cfg.catalog_enriched.read_text())

    by_id = {d.patch_id: d.drift_status for d in second.documents}
    assert by_id["DG*5.3*1057"] is DriftStatus.UNCHANGED
    assert by_id["DG*5.3*1099"] is DriftStatus.SUPERSEDED  # group already existed
    # 1000 dropped out upstream → flagged WITHDRAWN, never deleted (bronze immutable)
    assert [w.patch_id for w in second.withdrawn] == ["DG*5.3*1000"]
