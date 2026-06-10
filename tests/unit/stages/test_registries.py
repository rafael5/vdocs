"""Unit tests for the registries loader (A3) — curated v1 vocabularies as in-repo data.

These assert the loader reads every registry into typed structures and preserves the
load-bearing invariants from the v1 corpus (§6, §7, §10): the 196-app system map, the 154
manually-reviewed slugs, the COTS set, the three package consolidations, ordered doc-type
patterns. Counts that the spec gives exactly are asserted exactly; "~N" spec figures are
sanity-bounded.
"""

from __future__ import annotations

from vdocs.config import Settings
from vdocs.stages.catalog import registries as rg


def _load():
    return rg.load_registries(Settings().registries)


def test_section_codes():
    reg = _load()
    assert reg.section_code["Clinical"] == "CLI"
    assert reg.section_code["Infrastructure"] == "INF"
    assert set(reg.section_code.values()) == {"CLI", "FIN", "GUI", "INF", "MON"}


def test_doc_type_patterns_are_ordered_and_specific_first():
    reg = _load()
    codes = [p.code for p in reg.doc_type_patterns]
    assert len(reg.doc_type_patterns) == 58  # 57 from v1 + bare "TM" abbreviation (last-resort)
    # DIBR must precede the generic Installation Guide; User Manual before User Guide.
    assert codes.index("DIBR") < codes.index("IG")
    assert codes.index("UM") < codes.index("UG")
    # first entry is the full DIBR phrase
    assert reg.doc_type_patterns[0].code == "DIBR"


def test_slug_suffix_map_known_traps():
    reg = _load()
    # _tg means Training Guide (TRG), NOT Technical Guide — 100% of corpus (spec §6.4)
    assert reg.slug_suffix_map["tg"] == ("TRG", "Training Guide")
    assert reg.slug_suffix_map["manual"][0] == "TM"
    assert reg.slug_suffix_map["pm"][0] == "API"
    assert 50 <= len(reg.slug_suffix_map) <= 60


def test_app_specific_suffix_overrides():
    reg = _load()
    assert reg.app_specific_suffix[("PRC", "signed")] == ("POM", "Production Operations Manual")
    assert reg.app_specific_suffix[("TMP", "signed")] == ("RS", "Requirements Specification")


def test_manual_review_layer():
    reg = _load()
    assert len(reg.manual_slugs) == 154  # the 154 human-reviewed slugs (spec §6.5)
    assert reg.manual_noise == frozenset({"archive_placeholder", "test_document_vdl"})
    # overrides ∪ noise ⊆ manual_slugs
    assert set(reg.manual_overrides) <= reg.manual_slugs
    assert reg.manual_noise <= reg.manual_slugs
    assert reg.manual_overrides["fb_pm"] == ("POM", "Production Operations Manual")


def test_noise_domains():
    reg = _load()
    assert "vba.va.gov" in reg.vba_form_hosts
    assert "benefits.va.gov" in reg.vba_form_hosts


def test_system_types_full_coverage_and_cots():
    reg = _load()
    assert len(reg.system_type) == 196  # the 196-app map (spec §7)
    assert reg.system_type["CPRS"] == "VistA + GUI"
    assert reg.system_type["MD"] == "VistA + COTS"
    assert reg.system_type["JLV"] == "Web client"
    assert set(reg.cots_dependency) == {"MD", "YS", "ROI", "CPT", "DRG", "PREM"}


def test_doc_labels_canonical():
    reg = _load()
    assert len(reg.doc_labels) == 31
    assert reg.doc_labels["RN"] == "Release Notes"
    assert reg.doc_labels["DIBR"].startswith("Deployment, Installation")


def test_typo_corrections():
    reg = _load()
    sources = {c.source for c in reg.typo_corrections}
    assert "Staph Aurerus" in sources
    aurerus = next(c for c in reg.typo_corrections if c.source == "Staph Aurerus")
    assert aurerus.corrected == "Staph Aureus"
    assert "doc_title" in aurerus.fields


def test_package_master_aliases_and_consolidations():
    reg = _load()
    # aliases register as their own keys, resolving to the surviving abbrev (spec §10.2)
    assert reg.packages["RUM"].canonical_pkg == "KMPR"
    assert reg.packages["SAGG"].canonical_pkg == "KMPS"
    assert reg.packages["SSO/UC"].canonical_pkg == "SSO"
    # app_name_abbrev (VDL display) ≠ pkg_ns (M namespace): ADT↔DG, CPRS↔OR
    assert reg.packages["ADT"].pkg_ns == "DG"
    assert reg.packages["CPRS"].pkg_ns == "OR"


def test_alias_collision_with_package_key_raises():
    bad = "packages:\n  A: {canonical_name: X, aliases: [B]}\n  B: {canonical_name: Y}\n"
    import pytest

    with pytest.raises(ValueError, match="collides with a package key"):
        rg.parse_package_master(bad)


def test_alias_claimed_twice_raises():
    bad = (
        "packages:\n"
        "  A: {canonical_name: X, aliases: [Z]}\n"
        "  B: {canonical_name: Y, aliases: [Z]}\n"
    )
    import pytest

    with pytest.raises(ValueError, match="claimed by"):
        rg.parse_package_master(bad)


def test_package_missing_canonical_name_raises():
    import pytest

    with pytest.raises(ValueError, match="missing 'canonical_name'"):
        rg.parse_package_master("packages:\n  A: {pkg_ns: XX}\n")


def test_doc_labels_empty_label_raises():
    import pytest

    with pytest.raises(ValueError, match="empty canonical label"):
        rg.parse_doc_labels("labels:\n  RN: ''\n")


def test_typo_corrections_missing_field_raises():
    import pytest

    with pytest.raises(ValueError, match="missing"):
        rg.parse_typo_corrections("corrections:\n  - {source: foo}\n")


def test_registries_dir_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("REGISTRIES_DIR", str(tmp_path))
    assert Settings().registries == tmp_path


def test_subdir_layout_matches_design_section_11():
    """§11/§9.7: the curated tree is subdirectories, not flat files. The six pattern
    registries are present-but-may-be-empty dirs; inventory vocabularies live under
    ``inventory/`` (the §9.7-amended home for the catalog-track config)."""
    root = Settings().registries
    for pattern_dir in (
        "boilerplate",
        "templates",
        "phrases",
        "glossary",
        "structures",
        "converter-routing",
    ):
        assert (root / pattern_dir).is_dir(), f"missing pattern-registry dir {pattern_dir!r}"
    assert (root / "inventory").is_dir()
    # the inventory-track configs moved under inventory/ (not at the registries root)
    for name in ("package-master", "doc-types", "section-codes"):
        assert (root / "inventory" / f"{name}.yaml").is_file()
        assert not (root / f"{name}.yaml").exists(), f"{name}.yaml must move under inventory/"
    # the curated pattern registries keep their own named file inside their subdir
    assert (root / "phrases" / "phrases.yaml").is_file()
    assert (root / "converter-routing" / "converter-routing.yaml").is_file()


def test_load_registries_reads_subdir_layout():
    """The loader resolves the inventory vocabularies from the reshaped tree with the
    same load-bearing values (the reshape is a move, not a content change)."""
    reg = _load()
    assert reg.section_code["Clinical"] == "CLI"
    assert len(reg.doc_type_patterns) == 58  # +1: bare "TM" abbreviation (last-resort)
    assert reg.packages  # package-master resolved from inventory/
