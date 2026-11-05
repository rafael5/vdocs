"""Build the published **vocabulary** (ADR-0001 P2): the controlled vocabularies — function
domains, doc types, VDL sections, personas — assembled from the curated ``registries/`` (the SSOT)
into ``(kind, code, label, description)`` rows. The ``index`` stage writes these to ``index.db``'s
``vocab`` table (surfaced as ``v_vocab``) so consumers read definitions **as data** instead of
hardcoding them, and ``doctor`` can gate that every facet value present in the corpus is defined.

Adding a new function domain / doc type / section / persona is therefore a registry edit — no code
or consumer change (tenet #13, extended across the producer/consumer boundary).
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from vdocs.kernel.registry import load_mapping

# (kind, code, label, description)
VocabRow = tuple[str, str, str, str]


def _load(path: Path) -> dict:
    data = load_mapping(path, missing_ok=True)
    return data if isinstance(data, dict) else {}


def _oneline(s: str) -> str:
    """Collapse a folded multi-line YAML scalar to a single line."""
    return " ".join(str(s).split())


def vocab_rows(
    registries_dir: Path, *, namespaces: Mapping[str, str] | None = None
) -> list[VocabRow]:
    """Assemble the published vocabulary rows from the registries, sorted (deterministic).

    ``namespaces`` maps each inventory namespace to the same-code application's name (empty when
    there is none); only those namespaces get a ``namespace`` row (:func:`namespace_rows`)."""
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

    # inventory dispositions and reason kinds — dispositions.yaml (the closed sets are in code,
    # beside classify(); a test holds the two equal)
    dispositions = _load(inv / "dispositions.yaml")
    for code, body in (dispositions.get("dispositions") or {}).items():
        rows.append(("disposition", str(code), *_label_desc(code, body)))
    for code, body in (dispositions.get("reason_kinds") or {}).items():
        rows.append(("reason_kind", str(code), *_label_desc(code, body)))

    rows += doc_type_family_rows(_load(inv / "doctype-families.yaml"))
    rows += namespace_rows(_load(inv / "namespace-names.yaml"), namespaces or {})
    return sorted(rows)


def doc_type_family_rows(families: dict) -> list[VocabRow]:
    """One ``doc_type_family`` row per member doc type, labelled with its family; a type in no
    family is "Other". A type listed in two families is refused — its family would depend on
    which row a consumer happened to read."""
    family_of: dict[str, str] = {}
    for family, codes in (families.get("families") or {}).items():
        for code in codes or []:
            if str(code) in family_of:
                raise ValueError(
                    f"doc type {code} is in two families: {family_of[str(code)]}, {family}"
                )
            family_of[str(code)] = str(family)
    return [("doc_type_family", code, family, "") for code, family in family_of.items()]


def namespace_rows(names: dict, namespaces: Mapping[str, str]) -> list[VocabRow]:
    """``namespace`` rows for the given namespaces (read by the Inventory mode only, D4): the
    PACKAGE-file (#9.4) name copied into ``namespace-names.yaml``, an operator override applied
    after it, else the same-code application's name — the description says which. A namespace
    named nowhere gets no row."""
    package = {str(k): str(v) for k, v in (names.get("package_file") or {}).items()}
    overrides = {str(k): str(v) for k, v in (names.get("overrides") or {}).items()}
    rows: list[VocabRow] = []
    for ns, app_name in namespaces.items():
        if ns in overrides:
            desc = f"the operator's name; PACKAGE file (#9.4): {package.get(ns, '')}"
            rows.append(("namespace", ns, overrides[ns], desc))
        elif ns in package:
            rows.append(("namespace", ns, package[ns], "PACKAGE file (#9.4)"))
        elif app_name:
            desc = "not in the PACKAGE file (#9.4): the same-code application's name"
            rows.append(("namespace", ns, app_name, desc))
    return rows


def _label_desc(code: object, body: object) -> tuple[str, str]:
    """``(label, description)`` from a ``{label, description}`` entry (label falls back to code)."""
    b = body if isinstance(body, dict) else {}
    return str(b.get("label", code)), str(b.get("description", ""))
