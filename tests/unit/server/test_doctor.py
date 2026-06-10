"""Unit tests for the pure doctor check builders + verdict (the GOLD LIBRARY: GREEN|RED logic)."""

from __future__ import annotations

from vdocs.server.doctor import Check, DoctorReport, Health, coverage_check, integrity_check


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
