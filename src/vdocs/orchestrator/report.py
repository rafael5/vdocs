"""The run reporter — the operator-facing status / verdict / exit-code surface (§4 operability).

The orchestrator drives a :class:`RunReporter` through per-stage hooks; the reporter collects a
:class:`StageReport` per stage, renders live progress + an end-of-run summary, and computes the
verdict + process exit code. This is the one place that decides what GREEN/WARN/ERROR means and
what exit code the operator/script sees:

- **GREEN** — the stage did its work, no caveats.
- **WARN**  — completed, but the operator should know (a stage returned ``RunResult.warnings``);
  WARN never blocks. Exit 0 by default; ``--strict`` makes a run with WARNs exit 10 (distinct,
  non-zero, but not an error) so CI can choose to treat WARNs as failures.
- **ERROR** — a preflight FAIL or a postflight/deep-gate failure stopped the run. Exit 1.
- **SKIPPED** — a stage the orchestrator skipped (inputs unchanged / force-only); neutral.

**Rendering is gated behind a single :class:`Renderer` seam** (the findings' "swap is one place"
rule): :class:`RichRenderer` for a real terminal (banners + a summary table), :class:`PlainRenderer`
for non-TTY / tests / airgapped plain stdout. The data model + verdict/exit-code logic are
renderer-independent, so swapping presentation never touches the orchestrator wiring. Per-stage
progress heartbeats for long stages (``fetch``/``convert``) arrive in commit 4 behind these hooks.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    from rich.console import Console

#: process exit code for a run that completed with WARNs under ``--strict`` (non-zero but distinct
#: from an ERROR, so a caller can tell "proceeded with caveats" apart from "stopped").
STRICT_WARN_EXIT = 10


class Status(StrEnum):
    """A stage's operator-facing outcome (distinct from the persisted ``ok``/``failed`` status)."""

    GREEN = "GREEN"
    WARN = "WARN"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"


#: Rich styles + plain glyphs per status (one table both renderers read).
_STYLE = {
    Status.GREEN: "green",
    Status.WARN: "yellow",
    Status.ERROR: "bold red",
    Status.SKIPPED: "dim",
}


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


def _fmt_elapsed(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m{secs:02d}s"


# --- the rendering seam -------------------------------------------------------------------------


class Renderer:
    """How run progress + the summary reach the operator. Two implementations: plain and Rich."""

    def stage_start(self, index: int, total: int, name: str, description: str) -> None: ...
    def stage_progress(self, index: int, total: int, name: str, message: str) -> None: ...
    def stage_result(self, report: StageReport) -> None: ...
    def summary(self, reports: Sequence[StageReport], verdict: Status) -> None: ...


class PlainRenderer(Renderer):
    """Plain-stdout rendering — non-TTY, tests, and the zero-dep airgapped fallback."""

    def __init__(self, echo: Callable[[str], None] = typer.echo) -> None:
        self.echo = echo

    def stage_start(self, index: int, total: int, name: str, description: str) -> None:
        self.echo(f"[{index}/{total}] {name} — {description}")

    def stage_progress(self, index: int, total: int, name: str, message: str) -> None:
        self.echo(f"      … {name}: {message}")

    def stage_result(self, r: StageReport) -> None:
        if r.status is Status.SKIPPED:
            self.echo(f"   {r.name}: SKIPPED ({r.reason})" if r.reason else f"   {r.name}: SKIPPED")
            return
        if r.status is Status.ERROR:
            self.echo(f"   {r.name}: ERROR {r.reason}".rstrip())
            if r.remediation:
                self.echo(f"      → {r.remediation}")
            return
        counts = _counts_str(r.counts)
        self.echo(f"   {r.name}: {r.status.value} {counts}  ({_fmt_elapsed(r.elapsed_s)})".rstrip())
        for w in r.warnings:
            self.echo(f"      WARN  {w}")

    def summary(self, reports: Sequence[StageReport], verdict: Status) -> None:
        self.echo("")
        self.echo("=== vdocs run summary ===")
        for r in reports:
            counts = _counts_str(r.counts)
            self.echo(f"  [{r.index}/{r.total}] {r.name:<16} {r.status.value:<7} {counts}".rstrip())
            for w in r.warnings:
                self.echo(f"        WARN  {w}")
            if r.status is Status.SKIPPED and r.reason:
                self.echo(f"        ({r.reason})")
            if r.status is Status.ERROR:
                if r.reason:
                    self.echo(f"        ERROR {r.reason}")
                if r.remediation:
                    self.echo(f"        → {r.remediation}")
        n_warn = sum(1 for r in reports if r.status is Status.WARN)
        n_err = sum(1 for r in reports if r.status is Status.ERROR)
        self.echo(
            f"VERDICT: {verdict.value}  ({len(reports)} stages, {n_warn} warn, {n_err} error)"
        )


class RichRenderer(Renderer):
    """Rich rendering for a real terminal — styled banners + a summary table."""

    def __init__(self, console: Console | None = None) -> None:
        from rich.console import Console

        self.console: Console = console or Console()

    def _print(self, markup: str) -> None:
        # highlight=False so Rich's repr-highlighter doesn't split counts/elapsed numbers.
        self.console.print(markup, highlight=False)

    def stage_start(self, index: int, total: int, name: str, description: str) -> None:
        self._print(f"[bold cyan]\\[{index}/{total}][/] [bold]{name}[/] [dim]— {description}[/]")

    def stage_progress(self, index: int, total: int, name: str, message: str) -> None:
        self._print(f"      [dim]… {name}: {message}[/]")

    def stage_result(self, r: StageReport) -> None:
        style = _STYLE[r.status]
        if r.status is Status.SKIPPED:
            self._print(f"   [dim]{r.name}: SKIPPED ({r.reason})[/]")
            return
        if r.status is Status.ERROR:
            self._print(f"   [{style}]{r.name}: ERROR[/] {r.reason}")
            if r.remediation:
                self._print(f"      [dim]→ {r.remediation}[/]")
            return
        counts = _counts_str(r.counts)
        self._print(
            f"   [{style}]{r.name}: {r.status.value}[/] {counts}  "
            f"[dim]({_fmt_elapsed(r.elapsed_s)})[/]"
        )
        for w in r.warnings:
            self._print(f"      [yellow]WARN[/]  {w}")

    def summary(self, reports: Sequence[StageReport], verdict: Status) -> None:
        from rich.table import Table

        table = Table(title="vdocs run summary", title_style="bold", expand=False)
        table.add_column("#", justify="right")
        table.add_column("stage")
        table.add_column("status")
        table.add_column("counts")
        table.add_column("warn", justify="right")
        table.add_column("elapsed", justify="right")
        for r in reports:
            table.add_row(
                f"{r.index}/{r.total}",
                r.name,
                f"[{_STYLE[r.status]}]{r.status.value}[/]",
                _counts_str(r.counts) or ("—" if r.status is not Status.SKIPPED else r.reason),
                str(len(r.warnings)) if r.warnings else "",
                _fmt_elapsed(r.elapsed_s) if r.status not in (Status.SKIPPED, Status.ERROR) else "",
            )
        self.console.print(table)
        # warnings + error remediation below the table — the operator's "what to do next"
        for r in reports:
            for w in r.warnings:
                self._print(f"  [yellow]WARN[/] \\[{r.name}] {w}")
            if r.status is Status.ERROR:
                self._print(f"  [bold red]ERROR[/] \\[{r.name}] {r.reason}")
                if r.remediation:
                    self._print(f"        [dim]→ {r.remediation}[/]")
        n_warn = sum(1 for r in reports if r.status is Status.WARN)
        n_err = sum(1 for r in reports if r.status is Status.ERROR)
        self._print(
            f"[{_STYLE[verdict]}]VERDICT: {verdict.value}[/]  "
            f"({len(reports)} stages, {n_warn} warn, {n_err} error)"
        )


def _default_renderer() -> Renderer:
    """Rich on a real terminal, plain otherwise (CI, pipes, the airgapped plain stdout)."""
    if sys.stdout.isatty():
        return RichRenderer()
    return PlainRenderer()


class RunReporter:
    """Collects per-stage outcomes and drives a :class:`Renderer` for live progress + the summary.

    ``RunReporter(echo=...)`` is the plain path tests use (a list appender); ``RunReporter()`` picks
    Rich-or-plain by TTY; ``RunReporter(renderer=...)`` injects either explicitly.
    """

    def __init__(
        self,
        echo: Callable[[str], None] | None = None,
        renderer: Renderer | None = None,
    ) -> None:
        if renderer is None:
            renderer = PlainRenderer(echo) if echo is not None else _default_renderer()
        self.renderer = renderer
        self.reports: list[StageReport] = []

    # --- hooks the orchestrator calls, one per stage ---
    def stage_start(self, index: int, total: int, name: str, description: str) -> None:
        self.renderer.stage_start(index, total, name, description)

    def stage_progress(self, index: int, total: int, name: str, message: str) -> None:
        self.renderer.stage_progress(index, total, name, message)

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
        report = StageReport(
            index=index,
            total=total,
            name=name,
            status=status,
            counts=dict(counts),
            warnings=list(warnings),
            elapsed_s=elapsed_s,
        )
        self.reports.append(report)
        self.renderer.stage_result(report)

    def stage_skipped(self, index: int, total: int, name: str, reason: str) -> None:
        report = StageReport(
            index=index, total=total, name=name, status=Status.SKIPPED, reason=reason
        )
        self.reports.append(report)
        self.renderer.stage_result(report)

    def stage_error(self, index: int, total: int, name: str, reason: str, remediation: str) -> None:
        report = StageReport(
            index=index,
            total=total,
            name=name,
            status=Status.ERROR,
            reason=reason,
            remediation=remediation,
        )
        self.reports.append(report)
        self.renderer.stage_result(report)

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
        """Emit the end-of-run summary + overall verdict line."""
        self.renderer.summary(self.reports, self.verdict())


__all__ = [
    "PlainRenderer",
    "Renderer",
    "RichRenderer",
    "RunReporter",
    "STRICT_WARN_EXIT",
    "StageReport",
    "Status",
]
