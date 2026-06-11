"""Build the published **vocabulary** (ADR-0001 P2): the controlled vocabularies — function
domains, doc types, VDL sections, personas — assembled from the curated ``registries/`` (the SSOT)
into ``(kind, code, label, description)`` rows. The ``index`` stage writes these to ``index.db``'s
``vocab`` table (surfaced as ``v_vocab``) so consumers read definitions **as data** instead of
hardcoding them, and ``doctor`` can gate that every facet value present in the corpus is defined.

Adding a new function domain / doc type / section / persona is therefore a registry edit — no code
or consumer change (tenet #13, extended across the producer/consumer boundary).
"""

from __future__ import annotations

from pathlib import Path

import yaml

# (kind, code, label, description)
VocabRow = tuple[str, str, str, str]


def _load(path: Path) -> dict:
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _oneline(s: str) -> str:
    """Collapse a folded multi-line YAML scalar to a single line."""
    return " ".join(str(s).split())


def vocab_rows(registries_dir: Path) -> list[VocabRow]:
    """Assemble the published vocabulary rows from the registries, sorted (deterministic)."""
    inv = registries_dir / "inventory"
    rows: list[VocabRow] = []

    # function domains — function-domains.yaml `domains:` carries the definition
    for name, body in (_load(inv / "function-domains.yaml").get("domains") or {}).items():
        desc = _oneline((body or {}).get("definition", "")) if isinstance(body, dict) else ""
        rows.append(("function_category", str(name), str(name), desc))

    # doc types — doc-labels.yaml `labels:` (code → canonical label)
    for code, label in (_load(inv / "doc-labels.yaml").get("labels") or {}).items():
        rows.append(("doc_type", str(code), str(label), ""))

    # VDL sections — section-codes.yaml `descriptions:` (code → {label, description})
    for code, body in (_load(inv / "section-codes.yaml").get("descriptions") or {}).items():
        rows.append(("section", str(code), *_label_desc(code, body)))

    # personas — personas.yaml (the shared 5-persona vocabulary)
    for code, body in (_load(inv / "personas.yaml").get("personas") or {}).items():
        rows.append(("persona", str(code), *_label_desc(code, body)))

    return sorted(rows)


def _label_desc(code: object, body: object) -> tuple[str, str]:
    """``(label, description)`` from a ``{label, description}`` entry (label falls back to code)."""
    b = body if isinstance(body, dict) else {}
    return str(b.get("label", code)), str(b.get("description", ""))
