"""Phase C10 — the conformed inventory: §7 fidelity gate + CatalogStage driver wiring.

Two complementary checks:

1. ``test_section7_distributions`` runs the pure engine over a **pinned** capture of the v1
   raw ``vdl_inventory.csv`` (8,834 rows, gzipped under tests/fixtures) and asserts the §7
   reference distributions **exactly** — the no-information-loss / replication-grade gate.
2. ``test_catalog_stage_*`` drive the real ``CatalogStage`` over a small synthetic
   ``catalog.raw`` to prove the driver flattens → enriches → writes the inv-silver
   ``catalog.enriched.{json,csv}`` + schema with the right shape.
"""

from __future__ import annotations

import csv
import gzip
import json
from collections import Counter
from pathlib import Path

import pytest

from vdocs.config import Settings
from vdocs.models.catalog import (
    ENRICHED_COLUMNS,
    Catalog,
    CatalogApplication,
    CatalogDocument,
    CatalogSection,
    EnrichedInventory,
)
from vdocs.orchestrator.engine import Orchestrator
from vdocs.stages.catalog import enrich_pure as ep
from vdocs.stages.catalog import registries as rg
from vdocs.stages.catalog.stage import CatalogStage

_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "vdl_inventory_raw.csv.gz"


@pytest.fixture(scope="module")
def reg():
    return rg.load_registries(Settings().registries)


def _raw_rows():
    with gzip.open(_FIXTURE, "rt", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_section7_distributions(reg):
    """Replication-grade: the enriched corpus reproduces the §7 reference figures exactly."""
    out = ep.enrich_rows(_raw_rows(), reg)

    # 1:1 rows — enrichment never adds or drops a row
    assert len(out) == 8834

    def counts(key):
        return Counter(r[key] for r in out)

    assert counts("noise_type") == {"": 7491, "vba_form": 1192, "va_ref": 149, "test_document": 2}
    assert counts("doc_layer") == {"anchor": 3466, "patch": 3584, "plain": 1784}
    assert counts("doc_format") == {"pdf": 5097, "docx": 3730, "doc": 7}
    assert counts("doc_labelling") == {"code": 8526, "manual": 308}
    assert counts("section_code") == {"CLI": 5790, "FIN": 1485, "GUI": 780, "INF": 777, "MON": 2}
    assert sum(1 for r in out if r["patch_id"]) == 6902
    assert sum(1 for r in out if r["companion_url"]) == 7422

    dc = counts("doc_code")
    for code, n in {
        "RN": 1598, "DIBR": 1342, "FORM": 1192, "UG": 884, "UM": 880,
        "IG": 821, "TM": 723, "CRU": 336, "": 151, "VDD": 145,
    }.items():  # fmt: skip
        assert dc[code] == n, f"{code}: {dc[code]} != {n}"

    # Stage C: 100% system_type coverage, zero unclassified; COTS only on the 6 known apps
    assert all(r["system_type"] for r in out)
    assert counts("system_type")["unclassified"] == 0
    cots_apps = {r["app_name_abbrev"] for r in out if r["cots_dependent"]}
    assert cots_apps == {"MD", "YS", "ROI", "CPT", "DRG", "PREM"}


# --- CatalogStage driver wiring -------------------------------------------
def _catalog():
    docx = CatalogDocument(
        title="DG*5.3*1057 Deployment, Installation, Back-Out, and Rollback Guide",
        url="https://www.va.gov/vdl/documents/Clinical/ADT/dg_5_3_1057_dibr.docx",
        filename="dg_5_3_1057_dibr.docx",
        file_ext=".docx",
    )
    pdf = docx.model_copy(
        update={
            "url": docx.url.replace(".docx", ".pdf"),
            "filename": "dg_5_3_1057_dibr.pdf",
            "file_ext": ".pdf",
        }
    )
    app = CatalogApplication(
        name="Admission Discharge Transfer",
        app_code="ADT",
        url="https://www.va.gov/vdl/application.asp?appid=55",
        documents=[docx, pdf],
    )
    return Catalog(sections=[CatalogSection(name="Clinical", url="u", applications=[app])])


def _seed_and_run(ctx):
    from vdocs.kernel import cas

    cas.atomic_write(ctx.cfg.catalog_raw, _catalog().model_dump_json().encode("utf-8"))
    # record a crawl completion so catalog's preflight sees a clean upstream
    from vdocs.contracts.registry import CATALOG_RAW
    from vdocs.models.stage import StageRun

    ctx.state.record(
        StageRun(
            stage="crawl",
            scope="",
            status="ok",
            started_at="t",
            finished_at="t",
            inputs_fp={},
            outputs_fp={CATALOG_RAW.key: CATALOG_RAW.fingerprint(ctx.cfg)},
            counts={},
            contract_ver=1,
            tool_ver=ctx.cfg.tool_ver,
        )
    )
    return Orchestrator([CatalogStage()]).run(ctx)


def test_catalog_stage_writes_enriched_inventory(ctx):
    (result,) = _seed_and_run(ctx)
    assert result.status == "ok"
    assert result.counts["records"] == 2
    assert result.counts["noise:clean"] == 2

    inv = EnrichedInventory.model_validate_json(ctx.cfg.catalog_enriched.read_text())
    assert len(inv.records) == 2
    d = next(r for r in inv.records if r.doc_format == "docx")
    assert d.patch_id == "DG*5.3*1057" and d.doc_code == "DIBR"
    assert d.section_code == "CLI" and d.canonical_pkg == "ADT"
    assert d.group_key == "ADT:DG:5.3" and d.anchor_key == "ADT:DG:DIBR"
    assert d.system_type == "VistA" and d.cots_dependent is False
    # companion pairing across the DOCX/PDF pair
    assert d.companion_url.endswith(".pdf")


def test_catalog_stage_writes_csv_and_schema(ctx):
    _seed_and_run(ctx)
    csv_path = ctx.cfg.catalog_enriched.with_suffix(".csv")
    schema_path = ctx.cfg.catalog_enriched.with_suffix(".schema.json")
    assert csv_path.exists() and schema_path.exists()

    header = csv_path.read_text().splitlines()[0]
    assert header.split(",")[:3] == ["section_name", "section_code", "app_name_full"]
    assert "anchor_key" in header and "system_type" in header

    schema = json.loads(schema_path.read_text())
    assert schema["row_count"] == 2
    assert schema["columns"] == ENRICHED_COLUMNS
    assert schema["fields"]["cots_dependent"]["type"] == "boolean"
