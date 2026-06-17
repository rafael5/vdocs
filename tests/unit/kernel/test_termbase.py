"""Unit tests for kernel.termbase — compile the curated registries into docs-as-code
quality-gate config (Vale + typos), the `vdocs build-termbase` substrate.

The controlled vocabulary already lives as curated data: `product-names.yaml` (canonical
abbr/full/match), `typo-corrections.yaml` (wrong→right), and `glossary/expansions.yaml`
(approved acronyms). termbase compiles them into the artifacts the fileman-docs gate consumes:
an `accept.txt` (approved terms), a Vale `substitution` style (forbidden→preferred), and a
`typos` extend-words snippet — single-sourced, deterministic, no copy-paste into the docs repo.
"""

from __future__ import annotations

import yaml

from vdocs.kernel import termbase as t

_PRODUCTS = {
    "ADT": [{"abbr": "PIMS", "full": "Patient Information Management System", "match": ["PIMS"]}],
    "SD": [
        {"abbr": "VSE", "full": "VistA Scheduling Enhancement", "match": ["VSE", "VSECS"]},
    ],
}
_CORRECTIONS = [
    {"source": "Staph Aurerus", "corrected": "Staph Aureus", "fields": ["doc_title"]},
    {"source": "DIBORG", "corrected": "DIBRG", "fields": ["doc_title"]},
]
_EXPANSIONS = {
    "ADPAC": "Automated Data Processing Application Coordinator",
    "ACL": "Access Control List",
    "CAN": "Care Assessment Need",  # collides with English "can"
    "KIDS": "Kernel Installation and Distribution System",
}
# Synthetic stand-in for registries/glossary/english-words.txt.
_WORDS = frozenset({"can", "site", "an", "or", "is", "vista", "map"})


def _arts() -> dict[str, str]:
    return t.build_artifacts(
        products=_PRODUCTS,
        corrections=_CORRECTIONS,
        expansions=_EXPANSIONS,
        english_words=_WORDS,
    )


# --- the artifact set --------------------------------------------------------------------------
def test_emits_the_four_expected_artifacts():
    arts = _arts()
    assert set(arts) == {"accept.txt", "VistA.yml", "Casing.yml", "typos-extend.toml"}


# --- Casing.yml (selective case-enforcement, SKL S1.3) -----------------------------------------
def test_casing_enforces_safe_terms_and_skips_colliding_acronyms():
    doc = yaml.safe_load(_arts()["Casing.yml"])
    assert doc["extends"] == "substitution"
    assert doc["level"] == "error"
    assert doc["ignorecase"] is True  # catch any miscasing, force canonical
    swap = doc["swap"]
    assert swap["PIMS"] == "PIMS"  # product abbr, non-colliding → enforced
    assert swap["VSE"] == "VSE"  # product abbr → enforced
    assert swap["KIDS"] == "KIDS"  # acronym not in the English dict → enforced
    assert "CAN" not in swap  # collides with "can" → spelling-accept only, never force-cased
    assert "Patient Information Management System" not in swap  # multiword skipped


def test_casing_respects_enforce_case_opt_out():
    products = {"DI": [{"abbr": "FileMan", "match": ["FileMan"], "enforce_case": False}]}
    doc = yaml.safe_load(
        t.build_artifacts(products=products, corrections=[], expansions={}, english_words=_WORDS)[
            "Casing.yml"
        ]
    )
    assert "FileMan" not in doc["swap"]


# --- accept.txt --------------------------------------------------------------------------------
def test_accept_lists_abbrs_acronyms_and_full_names_sorted_unique():
    lines = [ln for ln in _arts()["accept.txt"].splitlines() if ln and not ln.startswith("#")]
    assert "PIMS" in lines  # product abbr
    assert "VSE" in lines  # product abbr
    assert "ADPAC" in lines  # glossary acronym
    assert "VistA Scheduling Enhancement" in lines  # product full name
    assert lines == sorted(lines)  # deterministic order
    assert len(lines) == len(set(lines))  # no duplicates


def test_accept_dedupes_a_term_present_in_multiple_sources():
    # VSE appears as both abbr and a match alias — must collapse to one line.
    lines = _arts()["accept.txt"].splitlines()
    assert lines.count("VSE") == 1


# --- Vale substitution style -------------------------------------------------------------------
def test_substitution_style_is_valid_vale_and_maps_source_to_corrected():
    doc = yaml.safe_load(_arts()["VistA.yml"])
    assert doc["extends"] == "substitution"
    assert doc["level"] == "error"
    assert doc["swap"]["Staph Aurerus"] == "Staph Aureus"
    assert doc["swap"]["DIBORG"] == "DIBRG"


# --- typos extend-words ------------------------------------------------------------------------
def test_typos_snippet_has_identity_entries_for_single_token_terms():
    toml = _arts()["typos-extend.toml"]
    assert "[default.extend-words]" in toml
    assert '"PIMS" = "PIMS"' in toml
    assert '"ADPAC" = "ADPAC"' in toml
    # multiword full names are not single tokens → not in extend-words
    assert "Patient Information Management System" not in toml


# --- determinism + degenerate input ------------------------------------------------------------
def test_deterministic_across_calls():
    assert _arts() == _arts()


def test_empty_inputs_yield_well_formed_empty_artifacts():
    arts = t.build_artifacts(products={}, corrections=[], expansions={}, english_words=frozenset())
    assert set(arts) == {"accept.txt", "VistA.yml", "Casing.yml", "typos-extend.toml"}
    assert yaml.safe_load(arts["VistA.yml"])["swap"] == {}
    assert yaml.safe_load(arts["Casing.yml"])["swap"] == {}


# --- the loader (I/O boundary) -----------------------------------------------------------------
def test_termbase_artifacts_reads_registries_dir(tmp_path):
    inv = tmp_path / "inventory"
    inv.mkdir()
    (inv / "product-names.yaml").write_text(
        yaml.safe_dump({"products": _PRODUCTS}), encoding="utf-8"
    )
    (inv / "typo-corrections.yaml").write_text(
        yaml.safe_dump({"corrections": _CORRECTIONS}), encoding="utf-8"
    )
    glo = tmp_path / "glossary"
    glo.mkdir()
    (glo / "expansions.yaml").write_text(
        yaml.safe_dump({"expansions": _EXPANSIONS}), encoding="utf-8"
    )
    (glo / "english-words.txt").write_text("can\nsite\nvista\n", encoding="utf-8")

    arts = t.termbase_artifacts(tmp_path)
    assert "PIMS" in arts["accept.txt"]
    assert yaml.safe_load(arts["VistA.yml"])["swap"]["DIBORG"] == "DIBRG"
    casing = yaml.safe_load(arts["Casing.yml"])["swap"]
    assert casing["PIMS"] == "PIMS"  # enforced from the loaded wordlist
    assert "CAN" not in casing  # colliding acronym vetoed by the loaded wordlist


def test_termbase_artifacts_tolerates_absent_registries(tmp_path):
    # No registry files at all → empty-but-well-formed artifacts (fail-soft on the optional inputs).
    arts = t.termbase_artifacts(tmp_path)
    assert set(arts) == {"accept.txt", "VistA.yml", "Casing.yml", "typos-extend.toml"}


def test_termbase_projects_from_skl_identically_to_registries(tmp_path):
    """S3.1 no-regression guarantee: projecting the gate artifacts from the SKL Term catalog
    (knowledge.db, the full superset `classify` emits) is **byte-identical** to projecting from the
    raw registries — and carries the full controlled vocab (≥600 terms), not just the ~23 in DI
    gold. This is what lets `build-termbase` single-source the SKL with no coverage regression."""
    from pathlib import Path

    from vdocs.kernel import knowledge_db
    from vdocs.kernel import products as kproducts
    from vdocs.models.knowledge import Provenance
    from vdocs.stages.resolve import resolve_pure as rp

    reg = Path(__file__).resolve().parents[3] / "registries"
    products = kproducts.load_products(reg)
    english = t.load_english_words(reg)
    terms = rp.classify_terms(
        products, english_words=english, registry_provenance=Provenance(source_sha256="")
    )
    kdb = tmp_path / "knowledge.db"
    knowledge_db.write_atomic(kdb, entities=[], terms=terms, relationships=[])

    from_registry = t.termbase_artifacts(reg)
    from_skl = t.termbase_artifacts(reg, knowledge_db=kdb)
    for name in ("accept.txt", "Casing.yml", "VistA.yml", "typos-extend.toml"):
        assert from_skl[name] == from_registry[name], f"{name} drifted: SKL vs registry projection"
    n = sum(1 for ln in from_skl["accept.txt"].splitlines() if ln and not ln.startswith("#"))
    assert n >= 600  # the full controlled vocab, not the ~23 corpus-seen terms
