"""Product registry loader — `app_code → [product, …]` from function-domains'
sibling ``registries/inventory/product-names.yaml`` (see
``docs/title-normalization-proposal.md`` / the product-naming work).

A VistA namespace (app_code) hosts one or more named products/modules; this maps
each to a dense ``abbr`` (the faceted-browser label + display-title prefix), a
``full`` name (the explainer-bar expansion), and ``match`` aliases (the
title-leading strings that resolve a document to the product). Pure-ish I/O: it
reads one YAML and returns plain dicts; resolution itself lives in
``kernel.titles`` (pure).

Each entry also carries the SKL **Term-classification facets** (``docs/skl-proposal.md`` §5,
``docs/skl-implementation-plan.md`` S1.1) — the per-term meaning the flat termbase lacked:

* ``term_class`` (YAML ``class``) — what the term *is* (``brand``/``product``/``acronym``/…);
  informational, ``None`` when unset.
* ``enforce_case`` (default ``True``) — whether the gate force-cases this surface. The
  collision auto-derivation (``kernel.casing_pure``) still vetoes English-colliding acronyms, so
  this is the rarely-needed *opt-out* for a non-colliding term we deliberately don't enforce.
* ``canonical_casing`` (default = ``abbr``) — the one correct capitalization.
* ``expand_on_first_use`` (default ``False``) — reserved for the glossary projection (later phase).

Facets are validated on load (fail-loud on a wrong-typed facet — tenet #7 — so a typo'd flag
can't silently mis-gate), additive to the existing ``abbr``/``full``/``match`` contract.
"""

from __future__ import annotations

from pathlib import Path

from vdocs.kernel import registry as kregistry


def _bool_facet(entry: dict, key: str, default: bool) -> bool:
    val = entry.get(key, default)
    if not isinstance(val, bool):
        raise ValueError(
            f"product-names.yaml entry {entry.get('abbr')!r}: facet {key!r} must be a bool, "
            f"got {val!r}"
        )
    return val


def load_products(registries_dir: Path) -> dict[str, list[dict]]:
    """``app_code → list of {abbr, full, match, term_class, enforce_case, canonical_casing,
    expand_on_first_use}`` (empty if the file is absent)."""
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
            abbr = str(e["abbr"])
            term_class = e.get("class")
            if term_class is not None and not isinstance(term_class, str):
                raise ValueError(
                    f"product-names.yaml entry {abbr!r}: facet 'class' must be a string"
                )
            norm.append(
                {
                    "abbr": abbr,
                    "full": str(e.get("full", e["abbr"])),
                    "match": [str(m) for m in (e.get("match") or [e["abbr"]])],
                    "term_class": term_class,
                    "enforce_case": _bool_facet(e, "enforce_case", True),
                    "canonical_casing": str(e.get("canonical_casing", abbr)),
                    "expand_on_first_use": _bool_facet(e, "expand_on_first_use", False),
                }
            )
        if norm:
            out[str(app)] = norm
    return out
