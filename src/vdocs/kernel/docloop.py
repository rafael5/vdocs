"""Per-document error isolation, shared across the per-doc stages (R6, §9.2 anti-duplication).

``convert``, ``normalize``, and ``consolidate`` each iterate a corpus document-by-document and must
**isolate** a single bad document — log it, count it, skip it — so one failure never abandons the
batch, while a *systemic* failure rate still fails the stage (``Stage.doc_error_gate``). That shape
was copy-pasted across three stages; this is the one implementation.

Wrap each document's work in :meth:`DocLoop.guard`::

    loop = DocLoop("convert", log)
    for key, item in items:
        with loop.guard(key):
            ...do the per-document work...        # an exception here is isolated
    return RunResult(counts={..., "errors": loop.errors},
                     warnings=loop.warnings(action="convert"))

The guard **suppresses** the exception so the enclosing ``for`` continues to the next document.
``loop.errors``/``loop.total`` feed ``doc_error_gate``; ``loop.warnings()`` renders the operator's
"N document(s) failed to <action>: …" WARN line in the run summary.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DocLoop:
    """Accumulates per-document outcomes for one stage run. ``log`` is the stage's structlog
    logger; ``stage`` names the event (``"<stage>-doc-failed"``) and the operator messaging."""

    stage: str
    log: Any
    ok: int = 0
    errors: int = 0
    failed: list[str] = field(default_factory=list)

    @contextlib.contextmanager
    def guard(self, key: str) -> Iterator[None]:
        """Run one document's work; isolate a failure (log + count + collect ``key``) and suppress
        it so the loop continues. A clean pass increments :attr:`ok`."""
        try:
            yield
        except Exception as exc:  # noqa: BLE001 — isolating one bad document is the whole point (R6)
            self.errors += 1
            self.failed.append(key)
            self.log.warning(f"{self.stage}-doc-failed", doc=key, error=str(exc))
        else:
            self.ok += 1

    @property
    def total(self) -> int:
        """Documents seen (ok + failed) — the denominator for ``doc_error_gate``."""
        return self.ok + self.errors

    def warnings(self, *, action: str, sample: int = 5) -> list[str]:
        """The operator-facing WARN line(s): one summary of the isolated failures, or ``[]`` when
        every document succeeded. ``action`` is the verb (``"convert"``/``"normalize"``/…)."""
        if not self.errors:
            return []
        shown = ", ".join(self.failed[:sample])
        more = f" (+{self.errors - sample} more)" if self.errors > sample else ""
        return [f"{self.errors} document(s) failed to {action}: {shown}{more}"]


__all__ = ["DocLoop"]
