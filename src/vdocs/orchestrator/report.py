"""The run reporter — the operator-facing status / verdict / exit-code surface (§4 operability).

The orchestrator drives a :class:`RunReporter` through per-stage hooks; the reporter collects a
:class:`StageReport` per stage and, at the end of a run, renders a summary and computes the
verdict + process exit code. This is the one place that decides what GREEN/WARN/ERROR means and
what exit code the operator/script sees:

- **GREEN** — the stage did its work, no caveats.
- **WARN**  — completed, but the operator should know (a stage returned ``RunResult.warnings``);
  WARN never blocks. Exit 0 by default; ``--strict`` makes a run with WARNs exit 10 (distinct,
  non-zero, but not an error) so CI can choose to treat WARNs as failures.
- **ERROR** — a preflight FAIL or a postflight/deep-gate failure stopped the run. Exit 1.
- **SKIPPED** — a stage the orchestrator skipped (inputs unchanged / force-only); neutral.

Commit-2 scaffold: the data model + verdict/exit-code contract + a plain-text summary. The Rich
console, per-stage start banners, and progress heartbeats arrive in commit 3 — they slot in behind
the same hooks, so the orchestrator wiring does not change.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

import typer

#: process exit code for a run that completed with WARNs under ``--strict`` (non-zero but distinct
#: from an ERROR, so a caller can tell "proceeded with caveats" apart from "stopped").
STRICT_WARN_EXIT = 10


class Status(StrEnum):
    """A stage's operator-facing outcome (distinct from the persisted ``ok``/``failed`` status)."""

    GREEN = "GREEN"
    WARN = "WARN"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"


@dataclass
class StageReport:
    """One stage's outcome in the run summary."""

    index: int
    total: int
    name: str
    status: Status
    counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    reason: str = ""  # the FAIL reason (ERROR) or skip reason (SKIPPED)
    remediation: str = ""  # the operator's next action (ERROR only)
    elapsed_s: float = 0.0


def _counts_str(counts: dict[str, int]) -> str:
    return " ".join(f"{k}={v}" for k, v in counts.items())


@dataclass
class RunReporter:
    """Collects per-stage outcomes and renders the operator-facing summary.

    ``echo`` is the output sink (defaults to ``typer.echo``); tests inject a list appender so the
    rendering is asserted without touching real stdout.
    """

    echo: Callable[[str], None] = typer.echo
    reports: list[StageReport] = field(default_factory=list)

    # --- hooks the orchestrator calls, one per stage ---
    def stage_done(
        self,
        index: int,
        total: int,
        name: str,
        status: Status,
        counts: dict[str, int],
        warnings: list[str],
        elapsed_s: float,
    ) -> None:
        self.reports.append(
            StageReport(
                index=index,
                total=total,
                name=name,
                status=status,
                counts=dict(counts),
                warnings=list(warnings),
                elapsed_s=elapsed_s,
            )
        )

    def stage_skipped(self, index: int, total: int, name: str, reason: str) -> None:
        self.reports.append(
            StageReport(index=index, total=total, name=name, status=Status.SKIPPED, reason=reason)
        )

    def stage_error(self, index: int, total: int, name: str, reason: str, remediation: str) -> None:
        self.reports.append(
            StageReport(
                index=index,
                total=total,
                name=name,
                status=Status.ERROR,
                reason=reason,
                remediation=remediation,
            )
        )

    # --- verdict + exit code ---
    def verdict(self) -> Status:
        """ERROR if any stage errored, else WARN if any stage warned, else GREEN."""
        statuses = {r.status for r in self.reports}
        if Status.ERROR in statuses:
            return Status.ERROR
        if Status.WARN in statuses:
            return Status.WARN
        return Status.GREEN

    def exit_code(self, *, strict: bool) -> int:
        """The documented exit-code contract: 1 on ERROR, ``STRICT_WARN_EXIT`` on WARN under
        ``--strict`` (else 0 on WARN), 0 when all GREEN/SKIPPED."""
        verdict = self.verdict()
        if verdict is Status.ERROR:
            return 1
        if verdict is Status.WARN and strict:
            return STRICT_WARN_EXIT
        return 0

    # --- summary ---
    def render_summary(self) -> None:
        """Emit the end-of-run summary: one line per stage + an overall verdict line. (The Rich
        table is commit 3; this plain rendering is what the scaffold ships.)"""
        self.echo("")
        self.echo("=== vdocs run summary ===")
        for r in self.reports:
            counts = _counts_str(r.counts)
            line = f"  [{r.index}/{r.total}] {r.name:<16} {r.status.value:<7} {counts}".rstrip()
            self.echo(line)
            for w in r.warnings:
                self.echo(f"        WARN  {w}")
            if r.status is Status.SKIPPED and r.reason:
                self.echo(f"        ({r.reason})")
            if r.status is Status.ERROR:
                if r.reason:
                    self.echo(f"        ERROR {r.reason}")
                if r.remediation:
                    self.echo(f"        → {r.remediation}")
        verdict = self.verdict()
        n_warn = sum(1 for r in self.reports if r.status is Status.WARN)
        n_err = sum(1 for r in self.reports if r.status is Status.ERROR)
        self.echo(
            f"VERDICT: {verdict.value}  ({len(self.reports)} stages, {n_warn} warn, {n_err} error)"
        )


__all__ = ["RunReporter", "StageReport", "Status", "STRICT_WARN_EXIT"]
