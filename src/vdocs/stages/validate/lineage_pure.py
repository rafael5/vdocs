"""Pure lineage check for the `validate` bundle gate — Step 4 extension (§8, §6.6, P5.2).

`bundle.yaml` proves a bundle is *internally* consistent: its part hashes are recomputed from the
parts on disk. That is exactly why it cannot see a lying lineage — `history.yaml` is one of those
parts, so a member entry describing a body the bundle no longer holds hashes fine and verifies
green (audit [S9]a; measured 2026-08-01 at 615 of 615 gold anchors before P5.1).

The invariant this module gates is the one `bundle.yaml` structurally cannot: the member flagged
``is_latest`` — the head of the replay chain, the one §6.6 designates as the anchor's own body —
must record the ``sha256`` of the ``body.md`` beside it. Everything else in ``history.yaml`` is
lineage *about other* bodies (retained in the CAS) and is not checkable against this bundle.

Absence is UNKNOWN, never OK (the P3.3 lesson): a bundle with no history, no ``is_latest`` member,
two of them, or a member with no recorded sha is **unverifiable** and reported, not skipped.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

# Finding kinds (both blocking — a lineage the gate cannot verify is not a lineage it can trust).
STALE_LINEAGE = "stale-lineage"  # the latest member's recorded sha ≠ the body on disk
UNVERIFIABLE_LINEAGE = "unverifiable-lineage"  # no single latest member / no recorded sha to check


@dataclass(frozen=True)
class LineageFinding:
    """One lineage finding (empty list ⇒ the bundle's replay head describes its own body)."""

    kind: str
    doc_id: str  # the offending member's stable id ("" when the lineage names none)
    detail: str


def check_lineage(history: dict[str, Any] | None, body: bytes) -> list[LineageFinding]:
    """Check one gold bundle's ``history.yaml`` against its ``body.md`` bytes.

    ``history`` is the parsed sidecar (``None``/empty when the bundle carries none); ``body`` is the
    bundle's ``body.md`` as written. Returns the findings — empty means the lineage's ``is_latest``
    member records exactly this body."""
    members = (history or {}).get("members") or []
    if not members:
        return [LineageFinding(UNVERIFIABLE_LINEAGE, "", "no history.yaml members to verify")]
    latest = [m for m in members if m.get("is_latest")]
    if len(latest) != 1:
        return [
            LineageFinding(
                UNVERIFIABLE_LINEAGE,
                "",
                f"no member flagged is_latest among {len(members)}"
                if not latest
                else f"{len(latest)} members flagged is_latest (the replay head must be one)",
            )
        ]
    recorded = str(latest[0].get("body_sha256") or "")
    doc_id = str(latest[0].get("doc_id") or "")
    if not recorded:
        detail = "latest member records no body_sha256"
        return [LineageFinding(UNVERIFIABLE_LINEAGE, doc_id, detail)]
    actual = hashlib.sha256(body).hexdigest()
    if recorded != actual:
        return [
            LineageFinding(
                STALE_LINEAGE,
                doc_id,
                f"latest member records body_sha256 {recorded[:12]} "
                f"but body.md hashes to {actual[:12]}",
            )
        ]
    return []
