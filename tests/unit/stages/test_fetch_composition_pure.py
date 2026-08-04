"""CI.4 — the admitted-set composition baseline, pure verdict logic.

Departures are reported by document identifier AND application (a count can hide a swap — the
P1 lesson), an acknowledged application passes, and an unchanged or growing set is silent.
"""

from __future__ import annotations

from vdocs.stages.fetch.composition_pure import check_composition, diff_admitted

OLD = {
    "XOBW:xobw_um": "XOBW",
    "XOBW:xobw_tm": "XOBW",
    "ADT:dg_um": "ADT",
}


def test_first_run_with_no_baseline_passes() -> None:
    verdict = check_composition(None, OLD, acknowledged_apps=frozenset())
    assert verdict.ok and verdict.departures == {}


def test_unchanged_set_passes_silently() -> None:
    verdict = check_composition(OLD, dict(OLD), acknowledged_apps=frozenset())
    assert verdict.ok


def test_growth_passes() -> None:
    bigger = OLD | {"LR:lr_um": "LR"}
    assert check_composition(OLD, bigger, acknowledged_apps=frozenset()).ok


def test_departure_reds_naming_application_and_documents() -> None:
    current = {"ADT:dg_um": "ADT"}
    verdict = check_composition(OLD, current, acknowledged_apps=frozenset())
    assert not verdict.ok
    assert verdict.departures == {"XOBW": ["XOBW:xobw_tm", "XOBW:xobw_um"]}
    assert "XOBW" in verdict.reason and "XOBW:xobw_um" in verdict.reason
    assert "scope-changes.yaml" in verdict.reason  # the remediation is in the message


def test_equal_size_swap_reds() -> None:
    # lose XOBW's two docs, gain two LR docs — the total is unchanged and the set is not
    current = {"ADT:dg_um": "ADT", "LR:lr_um": "LR", "LR:lr_tm": "LR"}
    verdict = check_composition(OLD, current, acknowledged_apps=frozenset())
    assert not verdict.ok
    assert "XOBW" in verdict.reason


def test_acknowledged_application_passes() -> None:
    current = {"ADT:dg_um": "ADT"}
    verdict = check_composition(OLD, current, acknowledged_apps=frozenset({"XOBW"}))
    assert verdict.ok
    assert verdict.departures == {"XOBW": ["XOBW:xobw_tm", "XOBW:xobw_um"]}  # reported, not fatal


def test_partial_acknowledgement_still_reds_the_unacknowledged_app() -> None:
    current: dict[str, str] = {}
    verdict = check_composition(OLD, current, acknowledged_apps=frozenset({"XOBW"}))
    assert not verdict.ok
    assert "ADT" in verdict.reason and "XOBW" not in verdict.reason


def test_diff_groups_departures_by_application_sorted() -> None:
    assert diff_admitted(OLD, {}) == {
        "ADT": ["ADT:dg_um"],
        "XOBW": ["XOBW:xobw_tm", "XOBW:xobw_um"],
    }
    assert diff_admitted(OLD, dict(OLD)) == {}
    assert diff_admitted(None, {}) == {}
