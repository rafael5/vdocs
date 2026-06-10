"""Unit tests for the run reporter — the operator-facing status/verdict/exit-code surface.

Commit-2 scaffold: the data model (GREEN/WARN/ERROR/SKIPPED), the verdict + exit-code contract,
and a plain-text summary. The Rich console + per-stage banners arrive in commit 3, so these tests
target the reporter through an injected sink (a list) rather than real stdout.
"""

from __future__ import annotations

from vdocs.orchestrator.report import RunReporter, Status


def _reporter() -> tuple[list[str], RunReporter]:
    lines: list[str] = []
    return lines, RunReporter(echo=lines.append)


def test_verdict_green_when_all_stages_green():
    _, r = _reporter()
    r.stage_done(1, 2, "crawl", Status.GREEN, {"docs": 8907}, [], 1.0)
    r.stage_done(2, 2, "catalog", Status.GREEN, {"records": 1044}, [], 0.5)
    assert r.verdict() is Status.GREEN
    assert r.exit_code(strict=False) == 0
    assert r.exit_code(strict=True) == 0


def test_verdict_warn_does_not_block_unless_strict():
    _, r = _reporter()
    r.stage_done(1, 1, "fetch", Status.WARN, {"fetched": 1040}, ["2 docs permanently missing"], 6.0)
    assert r.verdict() is Status.WARN
    assert r.exit_code(strict=False) == 0  # WARN proceeds by default
    assert r.exit_code(strict=True) == 10  # --strict turns WARN into a non-zero (but distinct) exit


def test_verdict_error_blocks_with_exit_one():
    _, r = _reporter()
    r.stage_done(1, 2, "index", Status.GREEN, {}, [], 0.1)
    r.stage_error(2, 2, "validate", "1 severed cross-ref", "fix refs.yaml then re-run validate")
    assert r.verdict() is Status.ERROR
    assert r.exit_code(strict=False) == 1
    assert r.exit_code(strict=True) == 1  # ERROR is 1 regardless of strict


def test_error_dominates_warn():
    _, r = _reporter()
    r.stage_done(1, 2, "fetch", Status.WARN, {}, ["something"], 0.0)
    r.stage_error(2, 2, "validate", "boom", "")
    assert r.verdict() is Status.ERROR
    assert r.exit_code(strict=False) == 1


def test_skipped_stage_is_neither_warn_nor_error():
    _, r = _reporter()
    r.stage_skipped(1, 1, "manifest", "inputs unchanged")
    assert r.verdict() is Status.GREEN
    assert r.exit_code(strict=False) == 0


def test_summary_lists_each_stage_with_status_and_verdict():
    lines, r = _reporter()
    r.stage_done(1, 3, "crawl", Status.GREEN, {"docs": 8907}, [], 1.0)
    r.stage_skipped(2, 3, "catalog", "inputs unchanged")
    r.stage_error(3, 3, "fetch", "gold inventory missing", "run: vdocs serve-inventory")
    r.render_summary()
    out = "\n".join(lines)
    assert "crawl" in out and "catalog" in out and "fetch" in out
    assert "GREEN" in out and "ERROR" in out
    assert "VERDICT" in out.upper()
    # the remediation for the failing stage is shown so the operator knows the next action
    assert "serve-inventory" in out


def test_summary_renders_warning_lines_human_readably():
    lines, r = _reporter()
    r.stage_done(
        1, 1, "fetch", Status.WARN, {"fetched": 1040},
        ["2 docs permanently unavailable (HTTP 500): DGBT:dgbt_1_40_um, ROEB:hreg_bcrv2"], 6.0,
    )  # fmt: skip
    r.render_summary()
    out = "\n".join(lines)
    assert "permanently unavailable" in out
    assert "DGBT:dgbt_1_40_um" in out
