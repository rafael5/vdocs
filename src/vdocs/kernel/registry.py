"""Curated-registry YAML loader — the single shared reader (§9.2/§11).

Every stage that consumes a ``registries/*.yaml`` config (``catalog`` vocabularies,
``convert`` routing, ``normalize`` phrases/boilerplate/templates/structures) read it with
the same ``exists?→read_text→yaml.safe_load or {}`` dance. A primitive used by ≥2 stages
lives in the kernel, not copy-pasted per stage — so the open/guard/parse boilerplate lives
here once. Each stage keeps only its own *shape* extraction over the returned mapping.

Pure-ish I/O boundary: it reads one file and returns a plain ``dict``. ``missing_ok=True``
turns an absent file into an empty mapping (a curated registry not yet populated → a no-op);
``missing_ok=False`` (the default) lets the absent-file ``FileNotFoundError`` surface loud
(a *required* vocabulary must exist — fail-loud, tenet #7).
"""

from __future__ import annotations

from pathlib import Path

import yaml


def load_mapping(path: Path, *, missing_ok: bool = False) -> dict:
    """Read a curated YAML file into a mapping (``{}`` for an empty or — when ``missing_ok`` —
    an absent file)."""
    if missing_ok and not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
