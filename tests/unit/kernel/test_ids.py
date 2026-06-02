"""Unit tests for kernel.ids — the one inventory stable-id builder (§5.5, §9.2)."""

from dataclasses import dataclass

from vdocs.kernel.ids import doc_id


@dataclass
class _Rec:
    app_name_abbrev: str
    doc_slug: str


def test_doc_id_joins_app_code_and_slug():
    assert doc_id(_Rec("CPRS", "cprsguium")) == "CPRS:cprsguium"


def test_doc_id_is_pure_plain_values():
    # Any object exposing app_name_abbrev + doc_slug works (structural typing; kernel stays
    # model-free).
    assert doc_id(_Rec("ADT", "dg_5_3_1057_dibr")) == "ADT:dg_5_3_1057_dibr"
