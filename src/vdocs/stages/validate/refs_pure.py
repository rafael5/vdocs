"""Pure outbound-reference resolution — the validate gate's severed-conref check (§5.5, FF C5).

`normalize` records, per bundle, the live anchor set + an outbound cross-ref map in ``refs.yaml``
(``anchors_pure.anchor_sidecar``). DITA migrations report the most common silent-loss mode is a
**severed cross-reference**: a link whose target id changed, broken silently. This module resolves
every outbound ref against that bundle's *own* live anchor set and classifies each as:

  * resolved — the target slug is a live anchor (no finding);
  * **severed** — the target slug is **absent** from the live set (a true dead anchor — the
    generalised C5 TOC round-trip applied to all cross-refs; the validate hard floor is **zero**);
  * **unmapped** — the ``UNRESOLVED`` marker ``anchors_pure`` wrote for a Word bookmark it never
    mapped to a heading (an already-flagged class, bounded by the C5 cross-ref dead-anchor rate, not
    a silent regression).

Keeping the two apart is the point: *severed* is a ref that **was** good and now points nowhere (a
silent loss → hard zero); *unmapped* never resolved and is already recorded by `normalize` (a
measured rate, not a new silent loss). Pure: plain dicts in, findings out.
"""

from __future__ import annotations

from dataclasses import dataclass

UNRESOLVED = "UNRESOLVED"  # the marker anchors_pure writes for an unmappable Word bookmark

SEVERED = "severed"
UNMAPPED = "unmapped"


@dataclass(frozen=True)
class RefFinding:
    """One non-resolved outbound ref: the bundle, the source bookmark, its target, and the class."""

    doc_id: str
    bookmark: str
    target: str
    kind: str  # SEVERED | UNMAPPED


def live_anchor_slugs(refs: dict) -> set[str]:
    """The set of slugs a bundle's headings actually mint — the live anchor set (§6.7).

    Includes a slug recorded as the empty string: a punctuation-only heading (e.g. titled ``;``)
    slugifies to ``""``, a degenerate-but-real anchor row. A ref targeting it *resolves* (the
    heading exists) — filtering empty slugs out would mis-flag it as severed. (The empty slug itself
    is a separate `normalize` slug-fallback quality issue, not a severed cross-ref.)"""
    return {str(a["slug"]) for a in (refs.get("anchors") or []) if "slug" in a}


def resolve_refs(refs: dict) -> list[RefFinding]:
    """Classify every outbound ref in one bundle's ``refs.yaml``; return the non-resolved findings.

    A resolved target is a live anchor slug (by construction `normalize` mints them together), so
    a severed finding is a genuine inconsistency — a ref pointing at a slug no heading carries."""
    doc_id = str(refs.get("doc_id", ""))
    live = live_anchor_slugs(refs)
    findings: list[RefFinding] = []
    for bookmark, target in (refs.get("outbound") or {}).items():
        t = str(target)
        if t == UNRESOLVED:
            findings.append(RefFinding(doc_id, str(bookmark), t, UNMAPPED))
        elif t not in live:
            findings.append(RefFinding(doc_id, str(bookmark), t, SEVERED))
    return findings
