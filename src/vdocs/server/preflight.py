"""Pre-run environment checks — the ``vdocs preflight`` GO/NO-GO gate.

The single highest-leverage zero-AI investment: most operator stranding happens *before* stage 1
(a missing `pandoc`, an unwritable data dir, an offline crawl). This checks the environment up
front and reports each as OK / WARN / FAIL with a remediation, plus a final ``PREFLIGHT: GO|NO-GO``
+ exit code — so a no-AI operator learns what to fix in one command instead of mid-run.

Pure: the builders here take *already-probed* inputs (binary availability, free bytes, writability,
reachability); the I/O probes live in the CLI command. ``verdict`` is GO unless a check FAILs —
WARN (e.g. the network is for crawl/fetch only; post-fetch runs offline) never blocks.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from vdocs.stages.convert.convert_pure import missing_converters

#: Free-space floor under DATA_DIR below which preflight WARNs (the corpus + intermediate artifacts
#: are multi-GB; this is advisory, not a hard block — the exact need varies with the gold set).
MIN_FREE_BYTES = 2 * 1024**3


class Outcome(StrEnum):
    OK = "OK"
    WARN = "WARN"  # worth the operator's eye, but does not block
    FAIL = "FAIL"  # blocks — NO-GO


@dataclass(frozen=True)
class PreflightCheck:
    """One environment check. ``remediation`` is the operator's next action (FAIL/WARN)."""

    name: str
    outcome: Outcome
    detail: str
    remediation: str = ""


def converter_checks(
    need_pandoc: bool, need_docling: bool, available: Callable[[str], bool]
) -> list[PreflightCheck]:
    """A check per required converter binary (reuses the same ``missing_converters`` the ``convert``
    stage preflights with, so the two never disagree). Present → OK; required-but-absent → FAIL."""
    missing = dict(missing_converters(need_pandoc, need_docling, available))
    checks: list[PreflightCheck] = []
    for tool, needed in (("pandoc", need_pandoc), ("docling", need_docling)):
        if not needed:
            continue
        if tool in missing:
            checks.append(
                PreflightCheck(f"converter:{tool}", Outcome.FAIL, "not found", missing[tool])
            )
        else:
            checks.append(PreflightCheck(f"converter:{tool}", Outcome.OK, "on PATH"))
    return checks


def data_dir_check(writable: bool, path: str) -> PreflightCheck:
    """The lake (``$DATA_DIR``) must be writable — every stage persists there."""
    if writable:
        return PreflightCheck("data-dir", Outcome.OK, f"writable: {path}")
    return PreflightCheck(
        "data-dir", Outcome.FAIL, f"not writable: {path}", "set $DATA_DIR to a writable directory"
    )


def disk_check(free_bytes: int, min_bytes: int = MIN_FREE_BYTES) -> PreflightCheck:
    """Advisory free-space check under the lake (the corpus + intermediates are multi-GB)."""
    free_gb = free_bytes / 1024**3
    if free_bytes >= min_bytes:
        return PreflightCheck("disk", Outcome.OK, f"{free_gb:.1f} GB free")
    return PreflightCheck(
        "disk",
        Outcome.WARN,
        f"only {free_gb:.1f} GB free (corpus + intermediates are multi-GB)",
        "free up disk or point $DATA_DIR at a larger volume",
    )


def network_check(reachable: bool, url: str) -> PreflightCheck:
    """VDL reachability — needed by ``crawl``/``fetch`` only; post-fetch stages run offline, so an
    unreachable network is a WARN, never a NO-GO."""
    if reachable:
        return PreflightCheck("network", Outcome.OK, f"reachable: {url}")
    return PreflightCheck(
        "network",
        Outcome.WARN,
        f"unreachable: {url} (only crawl/fetch need it; post-fetch runs offline)",
        "connect to the network before `vdocs crawl`/`fetch`",
    )


def verdict(checks: list[PreflightCheck]) -> str:
    """``GO`` unless any check FAILs — WARN never flips it (mirrors doctor's GREEN/RED rule)."""
    return "NO-GO" if any(c.outcome is Outcome.FAIL for c in checks) else "GO"


def render(checks: list[PreflightCheck], echo: Callable[[str], None]) -> str:
    """Print each check + the final ``PREFLIGHT: GO|NO-GO``; return the verdict."""
    echo("=== vdocs preflight — environment readiness ===")
    for c in checks:
        echo(f"  {c.name}: {c.outcome.value} — {c.detail}")
        if c.remediation and c.outcome is not Outcome.OK:
            echo(f"      → {c.remediation}")
    v = verdict(checks)
    echo("")
    echo(f"PREFLIGHT: {v}")
    return v
