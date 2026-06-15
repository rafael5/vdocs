"""Unit tests for server.preflight — the pre-run environment GO/NO-GO checks.

Pure builders: each takes already-probed inputs (binary availability, free bytes, writability,
reachability) and returns a PreflightCheck; `verdict` is GO unless a check FAILs. The I/O probes
live in the CLI command; here we test the decision logic with no filesystem/network.
"""

from vdocs.server import preflight as pf


def test_converter_checks_fail_when_pandoc_missing():
    checks = pf.converter_checks(need_pandoc=True, need_docling=False, available=lambda _t: False)
    pandoc = next(c for c in checks if "pandoc" in c.name)
    assert pandoc.outcome is pf.Outcome.FAIL
    assert pandoc.remediation  # tells the operator how to install it


def test_converter_checks_pass_when_present_and_skip_unneeded_docling():
    only_pandoc = lambda t: t == "pandoc"  # noqa: E731
    checks = pf.converter_checks(need_pandoc=True, need_docling=False, available=only_pandoc)
    assert all(c.outcome is pf.Outcome.OK for c in checks)
    assert not any("docling" in c.name for c in checks)  # not needed → not checked


def test_converter_checks_flag_docling_when_routed_and_absent():
    only_pandoc = lambda t: t == "pandoc"  # noqa: E731
    checks = pf.converter_checks(need_pandoc=True, need_docling=True, available=only_pandoc)
    docling = next(c for c in checks if "docling" in c.name)
    assert docling.outcome is pf.Outcome.FAIL


def test_data_dir_check_fails_when_not_writable():
    assert pf.data_dir_check(writable=False, path="/x").outcome is pf.Outcome.FAIL
    assert pf.data_dir_check(writable=True, path="/x").outcome is pf.Outcome.OK


def test_disk_check_warns_below_floor():
    assert pf.disk_check(free_bytes=1 * 1024**3, min_bytes=2 * 1024**3).outcome is pf.Outcome.WARN
    assert pf.disk_check(free_bytes=9 * 1024**3, min_bytes=2 * 1024**3).outcome is pf.Outcome.OK


def test_network_check_warns_when_unreachable_never_fails():
    # crawl/fetch need the network, but post-fetch stages run offline — so unreachable is a WARN,
    # never a NO-GO.
    assert pf.network_check(reachable=False, url="https://x").outcome is pf.Outcome.WARN
    assert pf.network_check(reachable=True, url="https://x").outcome is pf.Outcome.OK


def test_verdict_is_no_go_only_on_a_fail():
    ok = pf.PreflightCheck("a", pf.Outcome.OK, "")
    warn = pf.PreflightCheck("b", pf.Outcome.WARN, "")
    fail = pf.PreflightCheck("c", pf.Outcome.FAIL, "")
    assert pf.verdict([ok, warn]) == "GO"  # WARN never blocks
    assert pf.verdict([ok, warn, fail]) == "NO-GO"


def test_render_emits_each_check_and_the_verdict():
    lines: list[str] = []
    v = pf.render(
        [pf.PreflightCheck("converter:pandoc", pf.Outcome.FAIL, "not found", remediation="apt …")],
        lines.append,
    )
    assert v == "NO-GO"
    blob = "\n".join(lines)
    assert "converter:pandoc" in blob and "FAIL" in blob and "apt" in blob
    assert "PREFLIGHT: NO-GO" in blob
