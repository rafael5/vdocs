"""Pure rendering of a :class:`DoctorReport` to/from its computable artifact shape (P2.1).

The soundness verdict used to exist only as stdout a human read. Here it becomes a value: a
deterministic mapping (``generated_at`` is the one non-reproducible field, mirroring ``manifest``)
that round-trips, so the CLI can render the *written report* instead of running a second
diagnosis. Zero I/O — the stage driver does the reading and writing.
"""

from __future__ import annotations

from typing import Any

from vdocs.server.doctor import Check, DoctorReport, Health


def report_payload(report: DoctorReport, *, tool_ver: str, generated_at: str) -> dict[str, Any]:
    """The ``reports/doctor/doctor.json`` payload: the verdict, the gold count, and every check
    in diagnosis order (the order carries meaning — coverage, then integrity, then contract)."""
    return {
        "verdict": report.verdict(),
        "gold_count": report.gold_count,
        "generated_at": generated_at,
        "tool_ver": tool_ver,
        "checks": [
            {"name": c.name, "health": c.health.value, "detail": c.detail} for c in report.checks
        ],
    }


def report_from_payload(payload: dict[str, Any]) -> DoctorReport:
    """Reconstruct the report from its artifact — the inverse of :func:`report_payload`, so a
    consumer (the ``vdocs doctor`` renderer) reads the gate's record rather than re-deriving it."""
    return DoctorReport(
        gold_count=int(payload.get("gold_count", 0)),
        checks=[
            Check(
                name=str(c.get("name", "")),
                health=Health(c.get("health", Health.PASS.value)),
                detail=str(c.get("detail", "")),
            )
            for c in payload.get("checks") or []
        ],
    )


def health_counts(report: DoctorReport) -> dict[str, int]:
    """Per-bucket check counts for the run summary (``pass``/``by_design``/``warn``/``fail``) —
    the operator sees the shape of the verdict in the stage line, not just GREEN/RED."""
    keys = {
        Health.PASS: "pass",
        Health.BY_DESIGN: "by_design",
        Health.WARN: "warn",
        Health.FAIL: "fail",
    }
    counts = dict.fromkeys(keys.values(), 0)
    for check in report.checks:
        counts[keys[check.health]] += 1
    return counts


__all__ = ["health_counts", "report_from_payload", "report_payload"]
