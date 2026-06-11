"""Unit tests for kernel.products — the product-names.yaml loader."""

from vdocs.config import Settings
from vdocs.kernel import products


def test_load_products_from_real_registry():
    p = products.load_products(Settings().registries)
    assert "PSO" in p and any(e["abbr"] == "IEP" for e in p["PSO"])
    bcma = p["PSB"][0]
    assert bcma["abbr"] == "BCMA" and "BCMA" in bcma["match"]


def test_load_products_missing_is_empty(tmp_path):
    assert products.load_products(tmp_path) == {}
