"""`vdocs completeness` — the definition, made checkable (VO.9).

The five problems this effort fixes are symptoms of one root cause: the corpus had no definition of
completeness, so "we hold all VistA documentation" could not be verified and exclusions never
needed a stated reason. A definition nobody can run is the same as no definition, so it ships as a
command with an exit code.
"""

import json

from typer.testing import CliRunner

from vdocs.cli.app import app
from vdocs.models.catalog import EnrichedInventory, EnrichedRecord

runner = CliRunner()


def _rec(slug: str, **kw) -> EnrichedRecord:
    base = dict(
        app_name_abbrev="XU",
        doc_slug=slug,
        doc_code="UM",
        doc_format="docx",
        system_type="VistA",
        app_status="active",
        anchor_key=f"XU:XU:{slug}",
        doc_title=slug,
    )
    return EnrichedRecord(**{**base, **kw})


def _seed(tmp_path, records) -> dict[str, str]:
    lake = tmp_path / "lake"
    (lake / "inventory" / "gold").mkdir(parents=True)
    (lake / "inventory" / "gold" / "inventory.json").write_text(
        EnrichedInventory(records=records).model_dump_json(), encoding="utf-8"
    )
    return {"DATA_DIR": str(lake)}


def test_a_clean_library_is_complete(tmp_path, monkeypatch):
    for k, v in _seed(tmp_path, [_rec("um"), _rec("rn", doc_code="RN")]).items():
        monkeypatch.setenv(k, v)
    res = runner.invoke(app, ["completeness"])
    assert res.exit_code == 0, res.output
    assert "COMPLETE" in res.output and "INCOMPLETE" not in res.output


def test_an_unreadable_format_makes_it_incomplete_and_exits_nonzero(tmp_path, monkeypatch):
    """The gate that stops a converter limitation hardening into scope. A document no converter
    can read is a hole in the library however the registries are set. Legacy `.doc` is the live
    example — PDF stopped being one when VO.8 routed it to Docling."""
    for k, v in _seed(tmp_path, [_rec("scan", doc_format="doc")]).items():
        monkeypatch.setenv(k, v)
    res = runner.invoke(app, ["completeness"])
    assert res.exit_code == 1
    assert "INCOMPLETE" in res.output
    assert "format:doc-only" in res.output


def test_a_pdf_duplicate_does_not_make_it_incomplete(tmp_path, monkeypatch):
    for k, v in _seed(tmp_path, [_rec("m"), _rec("m", doc_format="pdf")]).items():
        monkeypatch.setenv(k, v)
    res = runner.invoke(app, ["completeness"])
    assert res.exit_code == 0
    assert "COMPLETE" in res.output


def test_every_exclusion_reason_is_reported(tmp_path, monkeypatch):
    """No silent exclusions — the operator can enumerate what is missing and why."""
    records = [
        _rec("um"),
        _rec("form", noise_type="vba_form"),
        _rec("web", system_type="Web client"),
        _rec("rn", doc_code="RN"),
    ]
    for k, v in _seed(tmp_path, records).items():
        monkeypatch.setenv(k, v)
    res = runner.invoke(app, ["completeness"])
    assert res.exit_code == 0
    for reason in ("not-vista:vba-form", "not-vista:system-type=Web client", "doctype-omitted:RN"):
        assert reason in res.output


def test_json_output_is_machine_readable(tmp_path, monkeypatch):
    for k, v in _seed(tmp_path, [_rec("um"), _rec("form", noise_type="vba_form")]).items():
        monkeypatch.setenv(k, v)
    res = runner.invoke(app, ["completeness", "--json"])
    assert res.exit_code == 0
    payload = json.loads(res.output)
    assert payload["verdict"] == "COMPLETE"
    assert payload["held"] == 1
    assert payload["by_reason"]["not-vista:vba-form"] == 1


def test_it_says_so_when_there_is_no_inventory_yet(tmp_path, monkeypatch):
    lake = tmp_path / "empty"
    lake.mkdir()
    monkeypatch.setenv("DATA_DIR", str(lake))
    res = runner.invoke(app, ["completeness"])
    assert res.exit_code == 1
    assert "no gold inventory" in res.output.lower()
