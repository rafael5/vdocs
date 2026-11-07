"""Unit tests for the pure doctor check builders + verdict (the GOLD LIBRARY: GREEN|RED logic)."""

from __future__ import annotations

from vdocs.server.doctor import (
    Check,
    DoctorReport,
    Health,
    coverage_check,
    integrity_check,
    inventory_freshness_check,
    load_doctor_policy,
    refiled_exceptions_check,
)


def test_coverage_full_is_pass():
    c = coverage_check("app_user", 615, 615, min_pct=100)
    assert c.health is Health.PASS and "100.0%" in c.detail


def test_coverage_below_min_is_fail_and_lists_offenders():
    c = coverage_check("doc_type", 612, 615, min_pct=100, offenders=["SD:a", "SD:b", "SD:c"])
    assert c.health is Health.FAIL
    assert "612/615" in c.detail and "SD:a" in c.detail


def test_coverage_by_design_gap_is_not_a_failure():
    # function_category at 94.3% with a documented by-design floor → BY-DESIGN, never RED (F6).
    c = coverage_check(
        "function_category",
        580,
        615,
        min_pct=90,
        by_design="fallback-profile apps have no SPM line",
    )
    assert c.health is Health.BY_DESIGN
    assert "fallback-profile" in c.detail


def test_coverage_below_by_design_floor_is_still_fail():
    c = coverage_check("function_category", 100, 615, min_pct=90, by_design="x")
    assert c.health is Health.FAIL


def test_integrity_check_clean_vs_violations():
    ok = integrity_check("anchor integrity", 0, detail_ok="one is_latest per anchor")
    assert ok.health is Health.PASS
    bad = integrity_check(
        "anchor integrity", 3, detail_bad="{n} anchors over-marked", offenders=["x"]
    )
    assert bad.health is Health.FAIL and "3 anchors over-marked" in bad.detail and "x" in bad.detail


def test_integrity_check_warn_severity():
    w = integrity_check(
        "anchor form",
        1,
        detail_bad="{n} malformed",
        health_bad=Health.WARN,
        offenders=["AR/WS:p13"],
    )
    assert w.health is Health.WARN


def test_verdict_green_unless_a_failure():
    green = DoctorReport(
        gold_count=615,
        checks=[
            Check("a", Health.PASS, ""),
            Check("b", Health.BY_DESIGN, ""),
            Check("c", Health.WARN, ""),
        ],
    )
    assert green.verdict() == "GREEN" and not green.failures()
    red = DoctorReport(gold_count=615, checks=[Check("a", Health.FAIL, "boom")])
    assert red.verdict() == "RED" and red.failures()[0].name == "a"


# --- P1: read-contract validation (the producer gate that emitted DB == spec) -------------------

_CONTRACT_SPEC = {
    "read_schema_version": "1.0",
    "views": {"v_documents": {"source": "documents", "columns": {"doc_key": {}, "title": {}}}},
}


def test_contract_check_passes_when_views_and_version_match():
    from vdocs.server.doctor import contract_check

    c = contract_check({"v_documents": ["doc_key", "title"]}, "1.0", _CONTRACT_SPEC)
    assert c.health is Health.PASS


def test_contract_check_fails_on_missing_view():
    from vdocs.server.doctor import contract_check

    c = contract_check({}, "1.0", _CONTRACT_SPEC)
    assert c.health is Health.FAIL and "v_documents" in c.detail


def test_contract_check_fails_on_column_drift():
    from vdocs.server.doctor import contract_check

    c = contract_check({"v_documents": ["doc_key"]}, "1.0", _CONTRACT_SPEC)
    assert c.health is Health.FAIL


def test_contract_check_fails_on_version_mismatch():
    from vdocs.server.doctor import contract_check

    c = contract_check({"v_documents": ["doc_key", "title"]}, "0.9", _CONTRACT_SPEC)
    assert c.health is Health.FAIL and "version" in c.detail.lower()


# --- P2: enum-coverage gate (every facet value present in gold is defined in vocab) -------------


def test_enum_coverage_passes_when_no_undefined_values():
    from vdocs.server.doctor import enum_coverage_check

    c = enum_coverage_check("function_category", [])
    assert c.health is Health.PASS


def test_enum_coverage_fails_and_names_the_undefined_values():
    from vdocs.server.doctor import enum_coverage_check

    c = enum_coverage_check("function_category", ["Health Informatics", "Mystery Domain"])
    assert c.health is Health.FAIL
    assert "Health Informatics" in c.detail


def test_policy_loads_accepted_anchorless_groups(tmp_path):
    # D2: known anchorless version groups (upstream grouping drift) are declared in
    # the policy registry — doctor WARNs on these, FAILs on any new one.
    (tmp_path / "doctor-policy.yaml").write_text(
        "coverage:\n  doc_type: {min_pct: 100}\n"
        "accepted_anchorless_groups:\n  - 'PSO:PSO:UG:pso_um'\n",
        encoding="utf-8",
    )
    pol = load_doctor_policy(tmp_path)
    assert "PSO:PSO:UG:pso_um" in pol.accepted_anchorless_groups


def test_policy_file_is_required(tmp_path):
    # the policy registry ships in the repo; a missing file is a broken install — fail loud
    # (tenet #7), never silently fall back to hardcoded floors that can drift from the YAML
    import pytest

    with pytest.raises(FileNotFoundError, match="doctor-policy.yaml"):
        load_doctor_policy(tmp_path)


def test_policy_requires_a_coverage_block(tmp_path):
    (tmp_path / "doctor-policy.yaml").write_text("accepted_anchor_edge_cases: []\n")
    import pytest

    with pytest.raises(ValueError, match="coverage"):
        load_doctor_policy(tmp_path)


def test_policy_rejects_unknown_top_level_keys(tmp_path):
    # operator typos (e.g. `coverge:`) must fail loud, not silently revert to defaults
    (tmp_path / "doctor-policy.yaml").write_text("coverge:\n  app_user: {min_pct: 100}\n")
    import pytest

    with pytest.raises(ValueError, match="coverge"):
        load_doctor_policy(tmp_path)


# --- inventory freshness (inventory browser step 1, D3: WARN, never RED) -------------------------


def test_inventory_freshness_passes_when_the_stamp_matches():
    c = inventory_freshness_check("abc", "abc")
    assert c.health is Health.PASS and c.name == "inventory freshness"


def test_a_different_inventory_warns_and_names_the_fix():
    c = inventory_freshness_check("abc", "def")
    assert c.health is Health.WARN
    assert "vdocs index" in c.detail


def test_an_unstamped_index_warns_rather_than_passing():
    """An index.db built before read contract 1.7 has no stamp: not a match, so not a PASS."""
    c = inventory_freshness_check(None, "def")
    assert c.health is Health.WARN and "vdocs index" in c.detail


def test_a_missing_inventory_says_it_was_skipped():
    c = inventory_freshness_check("abc", None)
    assert c.health is Health.WARN and "skipped" in c.detail


# --- D1's stopgap: the re-filing exception list and its expiry ---------------------------------

_LISTED = {"SD:iss_ug": "ADT:iss_ug"}


def test_listed_refilings_that_still_need_the_file_pass():
    c = refiled_exceptions_check(_LISTED, inventory_ids={"SD:iss_ug"}, gold_ids={"ADT:iss_ug"})
    assert c.health is Health.PASS and c.name == "refiled exceptions"


def test_the_stopgap_expires_red_once_gold_carries_the_inventory_id():
    """The testable expiry: identity continuity landed and the id joins without the file."""
    c = refiled_exceptions_check(
        _LISTED, inventory_ids={"SD:iss_ug"}, gold_ids={"ADT:iss_ug", "SD:iss_ug"}
    )
    assert c.health is Health.FAIL
    assert "SD:iss_ug" in c.detail and "refiled.yaml" in c.detail


def test_the_stopgap_expires_red_once_the_inventory_carries_the_gold_id():
    """The other way continuity can land: the inventory keeps the id the document already had."""
    c = refiled_exceptions_check(_LISTED, inventory_ids={"ADT:iss_ug"}, gold_ids={"ADT:iss_ug"})
    assert c.health is Health.FAIL


def test_a_listed_refiling_that_matches_nothing_warns():
    """A smaller lake (a dev subset) need not hold the document: say so, do not pass silently."""
    c = refiled_exceptions_check(_LISTED, inventory_ids={"SD:iss_ug"}, gold_ids=set())
    assert c.health is Health.WARN and "SD:iss_ug" in c.detail


def test_no_exception_file_is_the_expired_state_and_passes_out_loud():
    c = refiled_exceptions_check({}, inventory_ids=set(), gold_ids=set())
    assert c.health is Health.PASS and "none listed" in c.detail


# --- body coverage gate (end-to-end review A2, decision D2) --------------------------------------
# Per latest document: body word tokens (gold body.md minus the generated TOC) present in its
# non-table chunks; FAIL below the floor unless the document is a named exception, and the
# exception list is printed on every run, even when empty.

from vdocs.server.doctor import (  # noqa: E402
    BodyCoverageRow,
    body_coverage_checks,
    body_tokens,
    indexed_tokens,
)


def _row(key, body, indexed):
    return BodyCoverageRow(doc_key=key, body_tokens=body, indexed_tokens=indexed)


def test_body_coverage_passes_above_the_floor_and_prints_an_empty_exception_list():
    checks = body_coverage_checks([_row("A/a", 1000, 990), _row("B/b", 10, 10)], floor=95.0,
                                  exceptions={})  # fmt: skip
    gate, listed = checks
    assert gate.name == "body coverage" and gate.health is Health.PASS
    assert "2/2" in gate.detail and "95" in gate.detail
    assert listed.name == "body coverage exceptions" and listed.health is Health.PASS
    assert "none" in listed.detail


def test_body_coverage_fails_below_the_floor_and_names_the_document_with_its_share():
    (gate, _) = body_coverage_checks([_row("RMPR/x", 11340, 1198), _row("B/b", 10, 10)],
                                     floor=95.0, exceptions={})  # fmt: skip
    assert gate.health is Health.FAIL
    assert "RMPR/x" in gate.detail and "10.6%" in gate.detail and "1/2" in gate.detail


def test_body_coverage_exception_turns_a_failure_into_by_design_and_is_printed():
    gate, listed = body_coverage_checks(
        [_row("LR/labbbumf", 17996, 14408)], floor=95.0,
        exceptions={"LR/labbbumf": "TOC entries are whole paragraphs"},
    )  # fmt: skip
    assert gate.health is Health.BY_DESIGN
    assert listed.health is Health.BY_DESIGN
    assert "LR/labbbumf" in listed.detail and "whole paragraphs" in listed.detail


def test_body_coverage_exception_that_is_not_needed_is_still_printed_and_not_a_failure():
    gate, listed = body_coverage_checks([_row("A/a", 100, 100)], floor=95.0,
                                        exceptions={"A/a": "was low once"})  # fmt: skip
    assert gate.health is Health.PASS and "A/a" in listed.detail


def test_body_coverage_with_no_rows_is_a_warning_not_a_pass():
    # fail closed: a gate that measured nothing says so instead of going green
    gate, _ = body_coverage_checks([], floor=95.0, exceptions={})
    assert gate.health is Health.WARN and "not measured" in gate.detail


def test_body_tokens_drop_the_frontmatter_identity_header_and_generated_toc_only():
    # the identity header (`**title**`, `_Version · Patch · Published_`, `Source: <url>`) and the
    # `## Contents` list are normalize's own text; on a 148-token change page they were 20% of the
    # "body" (PRCA/icd_10_um_tp_4_5_281 read 80% covered with every word of its text indexed)
    text = (
        "---\ntitle: X\n---\n**X Manual**\n\n_Version 4.5 · Published 1995-03_\n\n"
        "Source: <https://x.gov/a.docx>\n\n## Contents\n\n- [Intro](#intro)\n  - [Sub](#sub)\n\n"
        "Preamble words here.\n\n# Intro\n\nbody words\n"
    )
    assert body_tokens(text) == 3 + 1 + 2  # Preamble words here · Intro · body words


def test_indexed_tokens_count_part_zero_whole_and_drop_the_overlap_block_of_later_parts():
    # split_oversized repeats the last block of a window at the start of the next; a line-split
    # giant block has no overlap and loses one line — the safe direction for a floor
    chunks = [("S/a", 0, "one two\n\nthree four"), ("S/a", 1, "three four\n\nfive six"),
              ("S/a#table-01.csv", 0, "cap | a | b")]  # fmt: skip
    assert indexed_tokens(chunks) == 6


def test_policy_loads_the_body_coverage_block(tmp_path):
    (tmp_path / "doctor-policy.yaml").write_text(
        "coverage:\n  doc_type: {min_pct: 100}\n"
        "body_coverage:\n  min_pct: 95\n  exceptions:\n"
        "    LR/labbbumf: TOC entries are paragraphs\n",
        encoding="utf-8",
    )
    pol = load_doctor_policy(tmp_path)
    assert pol.body_coverage.min_pct == 95.0
    assert pol.body_coverage.exceptions == {"LR/labbbumf": "TOC entries are paragraphs"}


def test_policy_body_coverage_defaults_when_absent(tmp_path):
    (tmp_path / "doctor-policy.yaml").write_text("coverage:\n  doc_type: {min_pct: 100}\n")
    pol = load_doctor_policy(tmp_path)
    assert pol.body_coverage.min_pct == 95.0 and pol.body_coverage.exceptions == {}


def test_policy_rejects_an_exception_without_a_reason(tmp_path):
    import pytest

    (tmp_path / "doctor-policy.yaml").write_text(
        "coverage:\n  doc_type: {min_pct: 100}\nbody_coverage:\n  exceptions:\n    A/a: ''\n"
    )
    with pytest.raises(ValueError, match="reason"):
        load_doctor_policy(tmp_path)


def test_body_coverage_exception_naming_no_latest_document_is_a_failure():
    # fail closed: a vanished document must not keep an exception alive
    gate, listed = body_coverage_checks([_row("A/a", 100, 100)], floor=95.0,
                                        exceptions={"GONE/x": "was low"})  # fmt: skip
    assert gate.health is Health.FAIL and "GONE/x" in gate.detail
    assert listed.health is Health.WARN and "not in the index" in listed.detail
