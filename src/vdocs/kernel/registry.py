"""YAML-mapping loader — the single shared reader for any curated/sidecar mapping (§9.2/§11).

Every stage that reads a YAML *mapping* off disk — a ``registries/*.yaml`` config (``catalog``
vocabularies, ``convert`` routing, ``normalize`` phrases/boilerplate/templates/structures/entities)
**or** a per-bundle sidecar (``history.yaml``, ``refs.yaml``, ``bundle.yaml`` …) — does the same
``exists?→read_text→yaml.safe_load or {}`` dance. A primitive used by ≥2 stages lives in the kernel,
not copy-pasted per stage — so the open/guard/parse boilerplate lives here once. Each caller keeps
only its own *shape* extraction over the returned mapping (and composes ``or None`` itself when it
needs to distinguish an empty/absent file from a populated one).

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


def load_entity_vocabularies(entities_dir: Path, entries: list) -> dict[str, frozenset[str]]:
    """Load each vocabulary an entity rule names (``vocab: <name>`` → ``<name>.txt``, one
    member per line, ``#`` comments) — the membership filter behind vocab-validated
    recognizers. Shared by every stage that compiles `registries/entities` rules (§9.2)."""
    out: dict[str, frozenset[str]] = {}
    for name in {e["vocab"] for e in entries if "vocab" in e}:
        lines = (entities_dir / f"{name}.txt").read_text(encoding="utf-8").split("\n")
        out[name] = frozenset(x for x in lines if x and not x.startswith("#"))
    return out


def load_anchor_aliases(registries_dir: Path) -> dict[str, str]:
    """The curated computed→canonical anchor_key map (``anchor-aliases.yaml``;
    empty if absent) — consumed by every anchor_key derivation site."""
    raw = load_mapping(registries_dir / "anchor-aliases.yaml", missing_ok=True)
    return {str(k): str(v) for k, v in (raw.get("aliases") or {}).items()}
