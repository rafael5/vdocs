"""Product registry loader — `app_code → [product, …]` from function-domains'
sibling ``registries/inventory/product-names.yaml`` (see
``docs/title-normalization-proposal.md`` / the product-naming work).

A VistA namespace (app_code) hosts one or more named products/modules; this maps
each to a dense ``abbr`` (the faceted-browser label + display-title prefix), a
``full`` name (the explainer-bar expansion), and ``match`` aliases (the
title-leading strings that resolve a document to the product). Pure-ish I/O: it
reads one YAML and returns plain dicts; resolution itself lives in
``kernel.titles`` (pure).
"""

from __future__ import annotations

from pathlib import Path

from vdocs.kernel import registry as kregistry


def load_products(registries_dir: Path) -> dict[str, list[dict]]:
    """``app_code → list of {abbr, full, match:[…]}`` (empty if the file is absent)."""
    data = kregistry.load_mapping(
        registries_dir / "inventory" / "product-names.yaml", missing_ok=True
    )
    out: dict[str, list[dict]] = {}
    for app, entries in (data.get("products") or {}).items():
        if not isinstance(entries, list):
            continue
        norm: list[dict] = []
        for e in entries:
            if not isinstance(e, dict) or not e.get("abbr"):
                continue
            norm.append(
                {
                    "abbr": str(e["abbr"]),
                    "full": str(e.get("full", e["abbr"])),
                    "match": [str(m) for m in (e.get("match") or [e["abbr"]])],
                }
            )
        if norm:
            out[str(app)] = norm
    return out
