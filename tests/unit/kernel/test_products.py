"""Unit tests for kernel.products — the product-names.yaml loader."""

import pytest
import yaml

from vdocs.config import Settings
from vdocs.kernel import products


def test_load_products_from_real_registry():
    p = products.load_products(Settings().registries)
    assert "PSO" in p and any(e["abbr"] == "IEP" for e in p["PSO"])
    bcma = p["PSB"][0]
    assert bcma["abbr"] == "BCMA" and "BCMA" in bcma["match"]


def test_load_products_missing_is_empty(tmp_path):
    assert products.load_products(tmp_path) == {}


# --- Term-classification facets (SKL S1.1) ------------------------------------------------------
def _write(tmp_path, products_block):
    inv = tmp_path / "inventory"
    inv.mkdir(exist_ok=True)
    (inv / "product-names.yaml").write_text(
        yaml.safe_dump({"products": products_block}), encoding="utf-8"
    )


def test_facets_default_when_absent(tmp_path):
    # A bare entry gets the conservative defaults: casing enforced, no first-use expansion.
    _write(tmp_path, {"DI": [{"abbr": "FileMan", "full": "VA FileMan", "match": ["FileMan"]}]})
    e = products.load_products(tmp_path)["DI"][0]
    assert e["enforce_case"] is True
    assert e["expand_on_first_use"] is False
    assert e["canonical_casing"] == "FileMan"  # defaults to abbr
    assert e["term_class"] is None


def test_facets_passed_through_when_present(tmp_path):
    _write(
        tmp_path,
        {
            "SD": [
                {
                    "abbr": "VSE",
                    "full": "VistA Scheduling Enhancement",
                    "match": ["VSE"],
                    "class": "product",
                    "enforce_case": False,
                    "expand_on_first_use": True,
                    "canonical_casing": "VSE",
                }
            ]
        },
    )
    e = products.load_products(tmp_path)["SD"][0]
    assert e["term_class"] == "product"
    assert e["enforce_case"] is False
    assert e["expand_on_first_use"] is True
    assert e["canonical_casing"] == "VSE"


def test_bad_facet_type_fails_loud(tmp_path):
    # A typo'd facet (string where a bool is expected) must fail loud, not silently mis-gate.
    _write(tmp_path, {"DI": [{"abbr": "FileMan", "enforce_case": "yes"}]})
    with pytest.raises(ValueError, match="enforce_case"):
        products.load_products(tmp_path)


def test_bad_expand_facet_type_fails_loud(tmp_path):
    _write(tmp_path, {"DI": [{"abbr": "FileMan", "expand_on_first_use": "no"}]})
    with pytest.raises(ValueError, match="expand_on_first_use"):
        products.load_products(tmp_path)


def test_bad_class_facet_type_fails_loud(tmp_path):
    _write(tmp_path, {"DI": [{"abbr": "FileMan", "class": ["brand"]}]})
    with pytest.raises(ValueError, match="class"):
        products.load_products(tmp_path)
