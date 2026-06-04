"""Pure outbound-reference resolution — the validate gate's severed-conref check (§5.5, FF C5).

`normalize` records, per bundle, the live anchor set + an outbound cross-ref map in ``refs.yaml``
(``anchors_pure.anchor_sidecar``). DITA migrations report the most common silent-loss mode is a
**severed cross-reference**: a link whose target id changed, broken silently. This module resolves
every outbound ref against that bundle's *own* live anchor set and classifies each as:

  * resolved — the target slug is a live anchor (no finding);
  * **severed** — the target slug is **absent** from the live set (a true dead anchor — the
    generalised C5 TOC round-trip applied to all cross-refs; the validate hard floor is **zero**);
  * **unmapped** — an ``UNRESOLVED`` marker on a ``_Toc…`` bookmark: a Word **TOC-field** bookmark,
    which targets a *heading*, that ``normalize`` did not map to a slug. This is the recoverable,
    C5-bounded resolvability class — the mapping is lost (Pandoc drops some heading bookmark spans)
    but reconstructible from the legacy TOC (a tracked ``normalize`` follow-up), so it is the rate
    C5 should bound.
  * **expected-unmapped** — an ``UNRESOLVED`` marker on any other bookmark (a ``_Ref…`` Word
    cross-reference, etc.): these target **non-heading** objects (figures, tables, numbered items,
    page spans), so they are unmappable to a GitHub heading anchor *by construction*. They are
    reported but sit **outside** the C5 heading-resolvability rate (corpus triage 2026-06-03: 0 of
    844 ``_Ref`` refs ever resolve, vs ``_Toc`` which resolves 27% — conflating them miscalibrated
    the C5 target; §6.7/§8, FF C5).

Keeping these apart is the point: *severed* was good and now points nowhere (a silent loss → hard
zero); *unmapped* is a recoverable ``_Toc``→heading miss (a measured, C5-bounded rate); and
*expected-unmapped* can never resolve to a heading and is informational only. Pure: dicts in,
findings out.
"""

from __future__ import annotations

from dataclasses import dataclass

UNRESOLVED = "UNRESOLVED"  # the marker anchors_pure writes for an unmappable Word bookmark
TOC_BOOKMARK_PREFIX = "_Toc"  # Word TOC-field bookmarks target headings → C5-bounded resolvability

SEVERED = "severed"
UNMAPPED = "unmapped"
EXPECTED_UNMAPPED = "expected-unmapped"


@dataclass(frozen=True)
class RefFinding:
    """One non-resolved outbound ref: the bundle, the source bookmark, its target, and the class."""

    doc_id: str
    bookmark: str
    target: str
    kind: str  # SEVERED | UNMAPPED | EXPECTED_UNMAPPED


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
        bm = str(bookmark)
        if t == UNRESOLVED:
            kind = UNMAPPED if bm.startswith(TOC_BOOKMARK_PREFIX) else EXPECTED_UNMAPPED
            findings.append(RefFinding(doc_id, bm, t, kind))
        elif t not in live:
            findings.append(RefFinding(doc_id, bm, t, SEVERED))
    return findings
