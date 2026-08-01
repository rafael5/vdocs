"""Unit: the doctor report payload — the computable artifact shape + its round trip (P2.1).

The verdict stops being stdout a human read and becomes ``reports/doctor/doctor.json``. The
payload must be deterministic (so a re-run is byte-identical apart from the timestamp) and
round-trippable (the CLI renders the *artifact*, not a second diagnosis).
"""

from __future__ import annotations

from vdocs.server.doctor import Check, DoctorReport, Health
from vdocs.stages.doctor import doctor_pure as dp


def _report() -> DoctorReport:
    return DoctorReport(
        gold_count=615,
        checks=[
            Check("gold documents present", Health.PASS, "1040 is_latest documents"),
            Check("coverage:function_category", Health.BY_DESIGN, "600/615 — fallback profile"),
            Check("anchor form", Health.WARN, "1 non-4-part anchor_key: AR/WS:p13"),
        ],
    )


def test_payload_carries_the_verdict_counts_and_every_check():
    payload = dp.report_payload(_report(), tool_ver="0.1.0", generated_at="2026-08-01T00:00:00Z")
    assert payload["verdict"] == "GREEN"  # WARN / BY-DESIGN never flip the verdict (F6)
    assert payload["gold_count"] == 615
    assert payload["generated_at"] == "2026-08-01T00:00:00Z"
    assert payload["tool_ver"] == "0.1.0"
    assert [c["name"] for c in payload["checks"]] == [
        "gold documents present",
        "coverage:function_category",
        "anchor form",
    ]
    assert payload["checks"][2] == {
        "name": "anchor form",
        "health": "WARN",
        "detail": "1 non-4-part anchor_key: AR/WS:p13",
    }


def test_payload_verdict_is_red_when_any_check_failed():
    report = DoctorReport(gold_count=2, checks=[Check("search surface", Health.FAIL, "empty")])
    payload = dp.report_payload(report, tool_ver="0.1.0", generated_at="t")
    assert payload["verdict"] == "RED"


def test_payload_is_deterministic_apart_from_the_timestamp():
    a = dp.report_payload(_report(), tool_ver="0.1.0", generated_at="t1")
    b = dp.report_payload(_report(), tool_ver="0.1.0", generated_at="t2")
    assert {k: v for k, v in a.items() if k != "generated_at"} == {
        k: v for k, v in b.items() if k != "generated_at"
    }


def test_report_round_trips_through_the_payload():
    # the CLI renders the written artifact rather than re-diagnosing — so the artifact must
    # reconstruct the report the renderer takes, check order and health included.
    original = _report()
    restored = dp.report_from_payload(
        dp.report_payload(original, tool_ver="0.1.0", generated_at="t")
    )
    assert restored.gold_count == original.gold_count
    assert restored.verdict() == original.verdict()
    assert restored.checks == original.checks
