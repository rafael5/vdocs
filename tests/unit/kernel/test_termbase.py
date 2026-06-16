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
}


def _arts() -> dict[str, str]:
    return t.build_artifacts(products=_PRODUCTS, corrections=_CORRECTIONS, expansions=_EXPANSIONS)


# --- the artifact set --------------------------------------------------------------------------
def test_emits_the_three_expected_artifacts():
    arts = _arts()
    assert set(arts) == {"accept.txt", "VistA.yml", "typos-extend.toml"}


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
    arts = t.build_artifacts(products={}, corrections=[], expansions={})
    assert set(arts) == {"accept.txt", "VistA.yml", "typos-extend.toml"}
    assert yaml.safe_load(arts["VistA.yml"])["swap"] == {}


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

    arts = t.termbase_artifacts(tmp_path)
    assert "PIMS" in arts["accept.txt"]
    assert yaml.safe_load(arts["VistA.yml"])["swap"]["DIBORG"] == "DIBRG"


def test_termbase_artifacts_tolerates_absent_registries(tmp_path):
    # No registry files at all → empty-but-well-formed artifacts (fail-soft on the optional inputs).
    arts = t.termbase_artifacts(tmp_path)
    assert set(arts) == {"accept.txt", "VistA.yml", "typos-extend.toml"}
