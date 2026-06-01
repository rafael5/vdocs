"""Loader for the curated inventory vocabularies (A3, §6, §9.3, §9.7).

The registries are *data, not code* (tenet #13): version-controlled YAML in the repo's
``registries/`` tree, ported verbatim from the v1 vista-docs corpus. This module is the
thin I/O boundary that reads them into typed structures; the ``catalog`` enrichment
(``catalog_pure``) consumes the loaded :class:`Registries` and stays pure. Parsers that
take YAML text (``parse_*``) are themselves pure and unit-tested directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

import yaml


@dataclass(frozen=True)
class TypoCorrection:
    """A field-scoped spelling fix; the original spelling feeds ``doc_search_aliases``."""

    source: str
    corrected: str
    fields: tuple[str, ...]


@dataclass(frozen=True)
class PackageEntry:
    """A resolved package-master row. For an alias key, ``abbrev`` is the alias itself
    and ``canonical_pkg`` points at the surviving abbrev."""

    abbrev: str
    canonical_name: str
    pkg_ns: str
    canonical_pkg: str
    aliases: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class DocTypePattern:
    """One ordered title-classifier rule; ``pattern`` is a raw regex (compiled by the
    pure classifier, kept uncompiled here so the registry stays plain data)."""

    pattern: str
    code: str
    label: str


SuffixMap = dict[str, tuple[str, str]]
AppSpecificMap = dict[tuple[str, str], tuple[str, str]]


@dataclass(frozen=True)
class Registries:
    """All curated inventory vocabularies, loaded once and passed into enrichment."""

    section_code: dict[str, str]
    abbrev_fallback: dict[str, str]
    doc_type_patterns: tuple[DocTypePattern, ...]
    slug_suffix_map: dict[str, tuple[str, str]]
    app_specific_suffix: dict[tuple[str, str], tuple[str, str]]
    manual_overrides: dict[str, tuple[str, str]]
    manual_noise: frozenset[str]
    manual_slugs: frozenset[str]
    vba_form_hosts: frozenset[str]
    system_type: dict[str, str]
    cots_dependency: dict[str, str]
    doc_labels: dict[str, str]
    typo_corrections: tuple[TypoCorrection, ...]
    packages: dict[str, PackageEntry] = field(default_factory=dict)


# --- pure parsers (YAML text → structures) ---------------------------------


def parse_doc_labels(text: str) -> dict[str, str]:
    raw = yaml.safe_load(text) or {}
    labels = raw.get("labels") or {}
    for code, label in labels.items():
        if not label:
            raise ValueError(f"doc_labels: '{code}' has empty canonical label")
    return dict(labels)


def parse_typo_corrections(text: str) -> tuple[TypoCorrection, ...]:
    raw = yaml.safe_load(text) or {}
    out: list[TypoCorrection] = []
    for i, item in enumerate(raw.get("corrections") or []):
        if "source" not in item or "corrected" not in item:
            raise ValueError(f"typo_corrections[{i}]: missing 'source'/'corrected'")
        out.append(
            TypoCorrection(
                source=item["source"],
                corrected=item["corrected"],
                fields=tuple(item.get("fields") or ()),
            )
        )
    return tuple(out)


def parse_package_master(text: str) -> dict[str, PackageEntry]:
    """Parse package-master YAML into a by-abbrev map; aliases register as their own keys."""
    raw = yaml.safe_load(text) or {}
    packages = raw.get("packages") or {}
    by_abbrev: dict[str, PackageEntry] = {}
    seen_aliases: dict[str, str] = {}
    for abbrev, fields in packages.items():
        if not fields or "canonical_name" not in fields:
            raise ValueError(f"package_master: '{abbrev}' missing 'canonical_name'")
        aliases = tuple(fields.get("aliases") or ())
        entry = PackageEntry(
            abbrev=abbrev,
            canonical_name=fields["canonical_name"],
            pkg_ns=fields.get("pkg_ns", ""),
            canonical_pkg=fields.get("canonical_pkg", abbrev),
            aliases=aliases,
            notes=fields.get("notes", ""),
        )
        by_abbrev[abbrev] = entry
        for alias in aliases:
            if alias in packages:
                raise ValueError(f"package_master: alias '{alias}' collides with a package key")
            if alias in seen_aliases:
                prior = seen_aliases[alias]
                raise ValueError(
                    f"package_master: alias '{alias}' claimed by '{prior}' and '{abbrev}'"
                )
            seen_aliases[alias] = abbrev
            by_abbrev[alias] = replace(entry, abbrev=alias)
    return by_abbrev


def parse_doc_types(
    text: str,
) -> tuple[tuple[DocTypePattern, ...], SuffixMap, AppSpecificMap]:
    raw = yaml.safe_load(text) or {}
    patterns = tuple(
        DocTypePattern(pattern=p["pattern"], code=p["code"], label=p["label"])
        for p in raw.get("doc_type_patterns") or []
    )
    suffix_map = {k: (v["code"], v["label"]) for k, v in (raw.get("slug_suffix_map") or {}).items()}
    app_specific = {
        (e["app"], e["suffix"]): (e["code"], e["label"])
        for e in raw.get("app_specific_suffix") or []
    }
    return patterns, suffix_map, app_specific


# --- I/O loader ------------------------------------------------------------


def _read(d: Path, name: str) -> dict:
    return yaml.safe_load((d / f"{name}.yaml").read_text(encoding="utf-8")) or {}


def load_registries(d: Path) -> Registries:
    """Read every registry YAML from directory ``d`` into a :class:`Registries`."""
    doc_types_text = (d / "doc-types.yaml").read_text(encoding="utf-8")
    patterns, suffix_map, app_specific = parse_doc_types(doc_types_text)
    manual = _read(d, "manual-labels")
    noise = _read(d, "noise-domains")
    systypes = _read(d, "system-types")
    return Registries(
        section_code=dict(_read(d, "section-codes").get("section_code", {})),
        abbrev_fallback=dict(_read(d, "abbrev-fallback").get("abbrev_fallback", {})),
        doc_type_patterns=patterns,
        slug_suffix_map=suffix_map,
        app_specific_suffix=app_specific,
        manual_overrides={
            k: (v["code"], v["label"]) for k, v in (manual.get("overrides") or {}).items()
        },
        manual_noise=frozenset(manual.get("noise") or []),
        manual_slugs=frozenset(manual.get("manual_slugs") or []),
        vba_form_hosts=frozenset(noise.get("vba_form_hosts") or []),
        system_type=dict(systypes.get("system_type", {})),
        cots_dependency=dict(systypes.get("cots_dependency", {})),
        doc_labels=parse_doc_labels((d / "doc-labels.yaml").read_text(encoding="utf-8")),
        typo_corrections=parse_typo_corrections(
            (d / "typo-corrections.yaml").read_text(encoding="utf-8")
        ),
        packages=parse_package_master((d / "package-master.yaml").read_text(encoding="utf-8")),
    )
