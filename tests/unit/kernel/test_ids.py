"""Unit tests for kernel.ids — the one inventory stable-id builder (§5.5, §9.2)."""

from dataclasses import dataclass

from vdocs.kernel.ids import bundle_key, bundle_path, doc_id


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


def test_bundle_key_is_the_sanitised_convert_layout_identity():
    # The (safe app, safe slug) tuple that enrich/discover/normalize all join against the convert
    # bundle layout — a sanitised app code (AR/WS → AR_WS) still matches the on-disk dir.
    assert bundle_key("RA", "ra_um") == ("RA", "ra_um")
    assert bundle_key("AR/WS", "x") == ("AR_WS", "x")


def test_bundle_path_is_the_slash_joined_key():
    assert bundle_path("AR/WS", "x") == "AR_WS/x"
    assert bundle_path("RA", "ra_um") == "/".join(bundle_key("RA", "ra_um"))
