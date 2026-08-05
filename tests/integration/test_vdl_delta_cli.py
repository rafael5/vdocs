"""`vdocs vdl-delta` — two consecutive crawls compared without re-crawling (VO.3/VO.4a).

The acceptance criterion this command exists for: what changed on the VDL between two snapshots is
a query, not an archaeology project. It reads only preserved bronze snapshots, so it can be run
long after the crawls that produced them.
"""

from __future__ import annotations

from typer.testing import CliRunner

from vdocs.cli.app import app
from vdocs.models.catalog import (
    Catalog,
    CatalogApplication,
    CatalogDocument,
    CatalogSection,
)

runner = CliRunner()


def _catalog(*apps: CatalogApplication) -> Catalog:
    return Catalog(
        sections=[
            CatalogSection(
                name="Clinical",
                url="https://www.va.gov/vdl/section.asp?secid=1",
                applications=list(apps),
            )
        ]
    )


def _app(appid: int, name: str, *, status: str = "active", docs: int = 1) -> CatalogApplication:
    return CatalogApplication(
        name=name,
        app_code=name[:3].upper(),
        url=f"https://www.va.gov/vdl/application.asp?appid={appid}",
        status=status,
        documents=[
            CatalogDocument(
                title=f"Doc {i}",
                url=f"http://x/{appid}-{i}.docx",
                filename=f"{appid}-{i}.docx",
                file_ext=".docx",
            )
            for i in range(docs)
        ],
    )


def _seed(tmp_path, snapshots: dict[str, Catalog]) -> dict[str, str]:
    lake = tmp_path / "lake"
    for name, catalog in snapshots.items():
        d = lake / "inventory" / "snapshots" / name
        d.mkdir(parents=True)
        (d / "catalog.raw.json").write_text(catalog.model_dump_json(), encoding="utf-8")
    return {"DATA_DIR": str(lake)}


def test_delta_between_two_named_snapshots(tmp_path, monkeypatch):
    env = _seed(
        tmp_path,
        {
            "2026-06-10": _catalog(_app(10, "Nursing"), _app(11, "Lab")),
            "2026-09-01": _catalog(_app(10, "Nursing Service"), _app(12, "Pharmacy", docs=3)),
        },
    )
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    res = runner.invoke(app, ["vdl-delta", "2026-06-10", "2026-09-01"])

    assert res.exit_code == 0, res.output
    assert "2026-06-10 → 2026-09-01" in res.output
    assert "appid=10" in res.output  # the rename, keyed on the VDL's own id
    assert "appid=12" in res.output  # the arrival
    assert "appid=11" in res.output  # the departure
    assert "2 → 4 documents (+2)" in res.output


def test_no_arguments_compares_the_two_newest_snapshots(tmp_path, monkeypatch):
    env = _seed(
        tmp_path,
        {
            "2026-01-01": _catalog(_app(10, "Nursing")),
            "2026-06-10": _catalog(_app(10, "Nursing")),
            "2026-09-01": _catalog(_app(10, "Nursing", status="archive")),
        },
    )
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    res = runner.invoke(app, ["vdl-delta"])

    assert res.exit_code == 0, res.output
    assert "2026-06-10 → 2026-09-01" in res.output
    assert "active → archive" in res.output


def test_one_snapshot_is_not_a_timeline_yet(tmp_path, monkeypatch):
    for k, v in _seed(tmp_path, {"2026-06-10": _catalog(_app(10, "Nursing"))}).items():
        monkeypatch.setenv(k, v)

    res = runner.invoke(app, ["vdl-delta"])

    assert res.exit_code == 1
    assert "two snapshots" in res.output


def test_an_unknown_snapshot_name_lists_what_is_available(tmp_path, monkeypatch):
    env = _seed(
        tmp_path,
        {
            "2026-06-10": _catalog(_app(10, "Nursing")),
            "2026-09-01": _catalog(_app(10, "Nursing")),
        },
    )
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    res = runner.invoke(app, ["vdl-delta", "2026-06-10", "2099-01-01"])

    assert res.exit_code == 1
    assert "2026-06-10" in res.output
