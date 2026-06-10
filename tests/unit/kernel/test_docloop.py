"""Unit tests for the shared per-document loop guard (R6 error isolation, §9.2 anti-duplication)."""

from __future__ import annotations

from vdocs.kernel.docloop import DocLoop


class _Log:
    """A fake structlog logger that records ``warning`` calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def warning(self, event: str, **kw: object) -> None:
        self.calls.append((event, dict(kw)))


def test_guard_counts_success():
    loop = DocLoop("convert", _Log())
    with loop.guard("APP/doc-a"):
        pass  # work succeeded
    assert loop.ok == 1 and loop.errors == 0 and loop.failed == []


def test_guard_isolates_and_records_a_failure():
    log = _Log()
    loop = DocLoop("normalize", log)
    with loop.guard("APP/doc-b"):
        raise ValueError("boom")  # one bad doc — must be suppressed, counted, logged
    # the exception did NOT propagate (we reached here)
    assert loop.errors == 1 and loop.ok == 0
    assert loop.failed == ["APP/doc-b"]
    assert log.calls == [("normalize-doc-failed", {"doc": "APP/doc-b", "error": "boom"})]


def test_guard_lets_the_loop_continue_after_a_failure():
    loop = DocLoop("consolidate", _Log())
    seen = []
    for key in ("a", "b", "c"):
        with loop.guard(key):
            seen.append(key)
            if key == "b":
                raise RuntimeError("bad b")
    assert seen == ["a", "b", "c"]  # the loop kept going past the bad doc
    assert loop.ok == 2 and loop.errors == 1 and loop.failed == ["b"]


def test_warnings_empty_when_no_errors():
    loop = DocLoop("convert", _Log())
    with loop.guard("a"):
        pass
    assert loop.warnings(action="convert") == []


def test_warnings_summarize_failures_with_a_sample():
    loop = DocLoop("convert", _Log())
    for key in ("d1", "d2", "d3"):
        with loop.guard(key):
            raise ValueError("x")
    (line,) = loop.warnings(action="convert")
    assert line == "3 document(s) failed to convert: d1, d2, d3"


def test_warnings_truncate_long_failure_lists():
    loop = DocLoop("normalize", _Log())
    for i in range(8):
        with loop.guard(f"d{i}"):
            raise ValueError("x")
    (line,) = loop.warnings(action="normalize", sample=5)
    assert line.startswith("8 document(s) failed to normalize: d0, d1, d2, d3, d4")
    assert line.endswith("(+3 more)")
