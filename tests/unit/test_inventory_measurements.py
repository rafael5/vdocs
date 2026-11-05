"""Inventory browser step 0 — the committed measurements behind the proposal's §1, §3 and §4.

Real objects, no mocks: a few hand-written inventory records, a minimal lake (``inventory.json``,
the raw crawl, an ``index.db`` with ``v_documents`` and ``meta``, ``history.yaml`` files and a
``state.db`` written by the real ``StateStore``), minimal policy and profile registries, and a
one-file vista-meta export. Each test plants the case its figure exists to catch.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from vdocs.models.catalog import EnrichedInventory, EnrichedRecord
from vdocs.models.stage import Acquisition
from vdocs.orchestrator.state import StateStore

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.inventory_measurements import (  # noqa: E402
    fold_name,
    load_lake,
    main,
    measure,
    measured,
)

PAGE_SD = "https://www.va.gov/vdl/application.asp?appid=1"
PAGE_XU = "https://www.va.gov/vdl/application.asp?appid=2"
PAGE_DG = "https://www.va.gov/vdl/application.asp?appid=3"
PAGE_WEB = "https://www.va.gov/vdl/application.asp?appid=4"
PAGE_OLD = "https://www.va.gov/vdl/application.asp?appid=5"
FORM_URL = "http://www.vba.va.gov/pubs/forms/VBA-21-526-ARE.pdf"


def _rec(
    app: str,
    slug: str,
    fmt: str = "docx",
    *,
    page: str = PAGE_SD,
    doc_code: str = "UM",
    system_type: str = "VistA",
    app_status: str = "active",
    pkg_ns: str = "",
    title: str = "",
    noise_type: str = "",
    url: str = "",
) -> EnrichedRecord:
    return EnrichedRecord(
        section_name="Clinical",
        section_code="CLI",
        app_name_full=f"{app} application",
        app_name_abbrev=app,
        app_status=app_status,
        system_type=system_type,
        pkg_ns=pkg_ns or app,
        patch_id=f"{app}*1",
        anchor_key=f"{app}:{pkg_ns or app}:{doc_code}:{slug}" if doc_code else "",
        doc_code=doc_code,
        doc_title=title or f"{slug} title",
        doc_filename=f"{slug}.{fmt}",
        doc_slug=slug,
        doc_format=fmt,
        noise_type=noise_type,
        app_url=page,
        doc_url=url or f"https://www.va.gov/vdl/documents/{app}/{slug}.{fmt}",
    )


def _records() -> list[EnrichedRecord]:
    return [
        # VA re-filed the ISS guide from ADT to SD: the inventory lists it under SD only, while
        # gold still holds it as ADT:iss_release_ug.
        _rec("SD", "iss_release_ug", page=PAGE_SD),
        # The RPC Broker supplement: in gold, with a PDF twin; its newest revision (2022-08) is
        # later than its title page (2005-01).
        _rec("XWB", "xwb_sup_um", page=PAGE_XU),
        _rec("XWB", "xwb_sup_um", "pdf", page=PAGE_XU),
        # The same Kernel manual listed twice on one page with every field identical.
        _rec("XU", "xu_tm", page=PAGE_XU, doc_code="TM"),
        _rec("XU", "xu_tm", page=PAGE_XU, doc_code="TM"),
        # One file listed twice on one page under two titles (the DVBA_UM shape).
        _rec("XU", "xu_um", page=PAGE_XU, title="Kernel User Manual"),
        _rec("XU", "xu_um", page=PAGE_XU, title="Kernel Systems Manual", doc_code="SM"),
        # Admitted, never in gold: the fetch failed.
        _rec("DGBT", "dgbt_um", page=PAGE_DG),
        # A decommissioned VistA application: the gate denies it, a system-type prefix does not.
        _rec("OLD", "old_um", page=PAGE_OLD, app_status="decommissioned"),
        # Not VistA: a web client, and one benefits form listed on two application pages.
        _rec("WEBP", "webp_ug", page=PAGE_WEB, system_type="Web client"),
        _rec("VBA", "vba_21_526", "pdf", page=PAGE_SD, noise_type="vba_form", url=FORM_URL),
        _rec("VBA", "vba_21_526", "pdf", page=PAGE_DG, noise_type="vba_form", url=FORM_URL),
    ]


def _write_registries(root: Path) -> Path:
    inv = root / "registries" / "inventory"
    inv.mkdir(parents=True)
    (inv / "scope-policy.yaml").write_text(
        yaml.safe_dump(
            {
                "app_scope": {
                    "allowed_system_type_prefixes": ["VistA"],
                    "denied_app_status": ["decommissioned"],
                }
            }
        )
    )
    (inv / "doctype-policy.yaml").write_text(
        yaml.safe_dump(
            {
                "default": "keep",
                "doctypes": {
                    "UM": {"decision": "keep"},
                    "TM": {"decision": "keep"},
                    "SM": {"decision": "keep"},
                    "RN": {"decision": "omit"},
                },
            }
        )
    )
    profiles = {
        app: {
            "name": f"{app} application",
            "app_user_primary": "clinical",
            "software_class": "I",
        }
        for app in ("SD", "XWB", "XU", "DGBT", "ADT")
    }
    (inv / "app-profiles.yaml").write_text(yaml.safe_dump({"profiles": profiles}))
    (inv / "doc-user.yaml").write_text(
        yaml.safe_dump({"doc_user": {"UM": "operator", "TM": "developer", "SM": "sysadmin"}})
    )
    (inv / "function-domains.yaml").write_text(
        yaml.safe_dump({"apps": {a: "Infrastructure" for a in ("SD", "XWB", "XU", "DGBT", "ADT")}})
    )
    return root / "registries"


GOLD_COLS = (
    "doc_id",
    "app_code",
    "doc_type",
    "pkg_ns",
    "app_name",
    "app_user",
    "doc_user",
    "software_class",
    "function_category",
    "is_latest",
    "published",
)


def _gold_row(app: str, slug: str, published: str) -> dict[str, Any]:
    return {
        "doc_id": f"{app}:{slug}",
        "app_code": app,
        "doc_type": "UM",
        "pkg_ns": app,
        "app_name": f"{app} application",
        "app_user": "clinical",
        "doc_user": "clinical",
        "software_class": "I",
        "function_category": "Infrastructure",
        "is_latest": 1,
        "published": published,
    }


def _history(doc_id: str, official_date: str, revision_dates: list[str]) -> dict[str, Any]:
    return {
        "anchor_key": doc_id,
        "member_count": 1,
        "members": [
            {
                "doc_id": doc_id,
                "doc_slug": doc_id.split(":", 1)[1],
                "official_date": official_date,
                "is_latest": True,
                "revisions": [{"date": d, "change": "edit"} for d in revision_dates],
            }
        ],
    }


def _mk_lake(tmp_path: Path, records: list[EnrichedRecord]) -> tuple[Path, Path, Path]:
    """Write the fixture lake, registries and vista-meta export; return their three paths."""
    lake = tmp_path / "lake"
    gold_inv = lake / "inventory" / "gold"
    gold_inv.mkdir(parents=True)
    (gold_inv / "inventory.json").write_text(
        EnrichedInventory(records=records).model_dump_json(), encoding="utf-8"
    )
    bronze = lake / "inventory" / "bronze"
    bronze.mkdir(parents=True)
    raw_docs = [
        {"url": r.doc_url, "file_date": "2020-01-01" if i == 0 else ""}
        for i, r in enumerate(records)
    ]
    (bronze / "catalog.raw.json").write_text(
        json.dumps({"sections": [{"applications": [{"documents": raw_docs}]}]}), encoding="utf-8"
    )

    conn = sqlite3.connect(lake / "index.db")
    conn.execute(f"CREATE TABLE v_documents ({', '.join(GOLD_COLS)})")
    conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    for row in (
        _gold_row("ADT", "iss_release_ug", "2019-03"),
        _gold_row("XWB", "xwb_sup_um", "2005-01"),
    ):
        conn.execute(
            f"INSERT INTO v_documents VALUES ({', '.join('?' for _ in GOLD_COLS)})",
            [row[c] for c in GOLD_COLS],
        )
    conn.executemany(
        "INSERT INTO meta VALUES (?, ?)",
        [("read_schema_version", "1.6"), ("corpus_content_hash", "fixturehash")],
    )
    conn.commit()
    conn.close()

    consolidated = lake / "documents" / "gold" / "consolidated"
    for rel, hist in (
        ("ADT/iss_release_ug", _history("ADT:iss_release_ug", "2019-03", [])),
        ("XWB/xwb_sup_um", _history("XWB:xwb_sup_um", "2022-08", ["2022-08", "2005-01"])),
    ):
        (consolidated / rel).mkdir(parents=True)
        (consolidated / rel / "history.yaml").write_text(yaml.safe_dump(hist), encoding="utf-8")

    store = StateStore.open(lake / "state.db")
    store.record_acquisition(
        Acquisition(doc_id="XWB:xwb_sup_um", source_url="u", status="fetched", tool_ver="t")
    )
    store.record_acquisition(
        Acquisition(doc_id="DGBT:dgbt_um", source_url="u", status="failed", tool_ver="t")
    )
    store.close()

    registries = _write_registries(tmp_path)
    tsv = tmp_path / "package-namespace.tsv"
    tsv.write_text(
        "package\tpackage_name\tnamespace\tprefixes\tapp_code\tvdl_id\n"
        "Scheduling\tSCHEDULING\tSD\tSD,SC\tSD\t\n"
        "Kernel\tKERNEL\tXU\tXU,XQ\tXU\t\n",
        encoding="utf-8",
    )
    return lake, registries, tsv


@pytest.fixture
def result(tmp_path: Path) -> dict[str, Any]:
    lake, registries, tsv = _mk_lake(tmp_path, _records())
    return measure(load_lake(lake, registries, tsv))


def test_refiled_slug_counts_once_as_gold_only_and_once_as_held_not_in_gold(
    result: dict[str, Any],
) -> None:
    m = measured(result)
    assert m["s1.gold_only"] == 1
    assert m["s1.gold_only_refiled"] == 1
    assert m["s1.gold_only_departed"] == 0
    assert m["s1.refiled_held_not_in_gold"] == 1
    # SD:iss_release_ug, the failed DGBT manual, and the Kernel TM and UM listings: held, no gold
    assert m["s1.held_not_in_gold"] == 6


def test_a_document_is_dated_by_its_newest_revision_not_its_title_page(
    result: dict[str, Any],
) -> None:
    m = measured(result)
    assert m["s4.gold_dated"] == 2
    assert m["s4.dated_revision"] == 1
    assert m["s4.dated_title_page"] == 1
    assert m["s4.revision_later_than_title"] == 1
    # the DOCX and its PDF twin both take the revision date through doc_id
    assert m["s4.records_dated"] == 2
    assert result["details"]["revision_later_than_title"] == [
        {"doc_id": "XWB:xwb_sup_um", "title_page": "2005-01", "newest_revision": "2022-08"}
    ]


def test_a_failed_fetch_is_not_counted_as_never_fetched(result: dict[str, Any]) -> None:
    m = measured(result)
    assert m["s1.hng_failed"] == 1
    split = result["details"]["undated_vista_no_gold_by_fetch"]
    assert split["failed"] == 1
    assert split["never-attempted"] == 5  # SD iss guide, the Kernel TM pair and UM pair
    assert sum(split.values()) == m["s4.undated_vista_no_gold"]


def test_vista_is_what_the_gate_admits_not_a_system_type_prefix(result: dict[str, Any]) -> None:
    m = measured(result)
    # the decommissioned application's document is not VistA to the gate
    assert m["s1.status_vista"] == 5
    assert m["s1.status_vista_prefix_only"] == 6
    assert m["s4.undated_not_vista"] == 4  # OLD, WEBP and the two form listings
    assert m["s4.undated_vista"] == 6


def test_repeated_links_are_counted_as_links_and_listings(result: dict[str, Any]) -> None:
    m = measured(result)
    assert m["s3.multi_page_links"] == 1
    assert m["s3.multi_page_link_records"] == 2
    assert m["s3.four_field_distinct"] == len(_records()) - 2
    assert m["s3.four_field_surplus"] == 2


def test_name_agreement_folds_case_and_punctuation_only() -> None:
    assert fold_name("VA FILEMAN") == fold_name("VA FileMan")
    assert fold_name("WOMEN'S HEALTH") == fold_name("Womens Health")
    assert fold_name("ACCOUNTS RECEIVABLE") != fold_name("Accounts Receivable (AR)")


def test_report_names_its_inputs_and_repeats_byte_for_byte(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lake, registries, tsv = _mk_lake(tmp_path, _records())
    outputs = []
    for n in (1, 2):
        out = tmp_path / f"run{n}" / "report.md"
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "inventory_measurements.py",
                "--data-dir",
                str(lake),
                "--registries",
                str(registries),
                "--package-namespace",
                str(tsv),
                "--out",
                str(out),
            ],
        )
        main()
        outputs.append(json.loads(out.with_suffix(".json").read_text()))
        assert "inventory.json" in out.read_text()
    first, second = outputs
    prov = first["provenance"]
    assert prov["inventory_json"]["records"] == len(_records())
    assert len(prov["inventory_json"]["sha256"]) == 64
    assert prov["index_db"] == {
        "read_schema_version": "1.6",
        "corpus_content_hash": "fixturehash",
    }
    for run in outputs:
        run["provenance"].pop("run_date")
    assert first == second
