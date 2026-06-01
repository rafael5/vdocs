"""Provenance stamping — the single lineage primitive (§9.2, §9.4, tenet #10).

Every derived silver/gold artifact records where it came from: the ``source_sha256``
of the bronze document, the ``tool_ver`` that produced it, and ``at`` (the timestamp).
Pure: the caller supplies ``at`` so the stamp is deterministic and testable — time is
never read here.
"""

from __future__ import annotations

from typing import Any


def stamp(
    *,
    source_sha256: str,
    tool_ver: str,
    at: str,
    converter: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a provenance record. ``source_sha256`` must be non-empty (tenet #10)."""
    if not source_sha256:
        raise ValueError("lineage requires a non-empty source_sha256")
    record: dict[str, Any] = {
        "source_sha256": source_sha256,
        "tool_ver": tool_ver,
        "at": at,
    }
    if converter is not None:
        record["converter"] = converter
    if extra:
        record.update(extra)
    return record
