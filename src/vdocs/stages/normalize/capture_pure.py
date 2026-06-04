"""Pure typed capture-attempt classification → the per-bundle ``capture.yaml`` manifest (§6.4).

`normalize` lifts machine-owned structure out of the body into *conditional* sidecars
(``revisions.yaml``, ``tables/*.csv``, ``refs.yaml``, ``toc.yaml``) — written iff the structure was
present and captured. A **missing** sidecar is therefore ambiguous: "nothing to capture" and "a
detector silently failed" look identical on disk, and ``flags.yaml`` only fires when a strip step
*fires but cannot parse* — never when a detector **never fires** on a structure that was present.

This module closes that gap. For *every* bundle `normalize` writes a ``capture.yaml`` recording each
capture attempt's typed outcome:

  * ``captured`` — detector ran, structure present, sidecar written (with the row/file count);
  * ``failed`` — structure *recognised* but unparseable (the existing ``flags.yaml`` cases);
  * ``absent-expected`` — detector ran, nothing present, **and** the residue re-scan agrees;
  * ``absent-unexpected`` — detector found nothing **but** the residue re-scan still sees the
    structure (a per-document silent miss — the case corpus aggregates cannot see).

The **residue re-scan** is a *second, detector-independent* look at the normalized body (the
fidelity framework's "independent reference" principle, ``fidelity-framework.md`` §2.2): cheap
pure predicates deliberately **broader** than the detectors, so a structure a detector missed is
seen (e.g. ``_LOOSE_REVISION_RE`` matches ``Change History`` though it is not in the curated
``REVISION_HEADING_TEXTS`` the strict detector keys on). ``flags.yaml`` stays the *sparse* attention
signal; ``capture.yaml`` is the *dense*, always-written completeness manifest — opposite lifecycles,
deliberately separate files (vdocs-design §6.4).

Pure: plain values in, a serialisable manifest dict out; the ``stage.py`` driver writes the sidecar.
The corpus-level reconciliation (whole-detector failure, count drop vs. the prior run) is the
complementary net, enforced by the ``validate`` gate (§8) — this module is the per-document half.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from vdocs.kernel.markdown import heading_furniture_text, iter_headings, strip_tags
from vdocs.stages.normalize import tables_pure

CAPTURED = "captured"
FAILED = "failed"
ABSENT_EXPECTED = "absent-expected"
ABSENT_UNEXPECTED = "absent-unexpected"

# The five capture attempts `normalize` records, in manifest order.
KINDS = ("revisions", "tables", "refs", "toc", "title_date")

# Residue: recognise a revision-history *section heading* in a form broader than
# ``kernel.is_revision_heading`` (which keys on the exact curated ``REVISION_HEADING_TEXTS``) — so a
# real missed variant (``Change History``, ``Revision Log``…) still trips ``absent-unexpected`` —
# WITHOUT the bare-substring false positives the real corpus exposed: ``Package Revision Data`` (a
# routine section), ``…Change Logical Links`` (``change log`` inside ``logical``), prose paragraphs
# promoted to headings, ``Revision History Archive`` (an appendix). The rule: the heading's text
# (leading section numbering stripped) **ends with** a curated revision-history phrase, and the
# heading is short enough to be a section title — a prose line promoted to a heading is not.
_REVISION_TAILS = (
    "revision history",
    "revisions",
    "revision log",
    "revision record",
    "revision summary",
    "change history",
    "change log",
    "version history",
    "document history",
    "modification history",
    "record of changes",
    "history of changes",
)
_LEADING_NUMBER_RE = re.compile(r"^[\d.\s]+")  # a leading "3 " / "3. " / "3.1 " section number
_MAX_REVISION_HEADING_LEN = 60  # a section title, not a paragraph promoted to a heading


def _is_revision_heading_residue(bare: str) -> bool:
    if not bare or len(bare) > _MAX_REVISION_HEADING_LEN:
        return False
    stripped = _LEADING_NUMBER_RE.sub("", bare).strip()
    return any(stripped == t or stripped.endswith(" " + t) for t in _REVISION_TAILS)


@dataclass(frozen=True)
class Residue:
    """The independent second-signal re-scan of the *normalized* body (§6.4)."""

    revision_heading_present: bool
    legacy_toc_heading_present: bool
    heading_present: bool
    qualifying_table_count: int


@dataclass(frozen=True)
class CaptureOutcome:
    """One capture attempt's verdict — the outcome and, for captured kinds, the count."""

    outcome: str
    count: int | None = None


def scan_residue(body: str, toc_titles: frozenset[str]) -> Residue:
    """Re-scan the *normalized* body for structure that should have been captured (§6.4).

    Heading signals use the shared fence-/Contents-aware ``iter_headings`` (so the generated
    ``## Contents`` never counts as residue); the table signal reuses ``tables_pure``'s own
    qualifying-table detector as a post-condition (a qualifying table left in the body = a miss)."""
    revision = legacy_toc = heading = False
    for _idx, _level, text in iter_headings(body):
        if not strip_tags(text).strip():
            # An empty ``# `` title or a bookmark-only heading (``## <span id="_Toc…"></span>``)
            # mints no anchor — ``parse_headings`` skips it identically — so it is NOT heading
            # structure that should have produced a ``refs.yaml``. Counting it makes refs a false
            # ``absent-unexpected`` that blocks the validate gate (§6.4/§6.7).
            continue
        heading = True
        bare = heading_furniture_text(text)
        if _is_revision_heading_residue(bare):
            revision = True
        if bare in toc_titles:
            legacy_toc = True
    return Residue(
        revision_heading_present=revision,
        legacy_toc_heading_present=legacy_toc,
        heading_present=heading,
        qualifying_table_count=tables_pure.count_qualifying_tables(body),
    )


def _revisions(count: int, failed: bool, residue: Residue) -> CaptureOutcome:
    if count > 0:
        return CaptureOutcome(CAPTURED, count)
    # a recognised-but-unparseable apparatus is already a flags.yaml signal — loud, not silent
    if failed:
        return CaptureOutcome(FAILED, 0)
    # a revision heading survived but nothing was captured + no parse flag → a silent miss
    if residue.revision_heading_present:
        return CaptureOutcome(ABSENT_UNEXPECTED, 0)
    return CaptureOutcome(ABSENT_EXPECTED, 0)


def _tables(count: int, residue: Residue) -> CaptureOutcome:
    if count > 0:
        return CaptureOutcome(CAPTURED, count)
    if residue.qualifying_table_count > 0:  # a qualifying table remains in the body → silent miss
        return CaptureOutcome(ABSENT_UNEXPECTED, 0)
    return CaptureOutcome(ABSENT_EXPECTED, 0)


def _refs(count: int, residue: Residue) -> CaptureOutcome:
    if count > 0:
        return CaptureOutcome(CAPTURED, count)
    if residue.heading_present:  # headings exist but no anchor map was written → silent miss
        return CaptureOutcome(ABSENT_UNEXPECTED, 0)
    return CaptureOutcome(ABSENT_EXPECTED, 0)


def _toc(count: int, residue: Residue) -> CaptureOutcome:
    if count > 0:
        return CaptureOutcome(CAPTURED, count)
    if residue.legacy_toc_heading_present:  # a legacy contents heading survived the strip → miss
        return CaptureOutcome(ABSENT_UNEXPECTED, 0)
    return CaptureOutcome(ABSENT_EXPECTED, 0)


def classify(
    *,
    revisions_count: int,
    revision_failed: bool,
    tables_count: int,
    refs_count: int,
    toc_count: int,
    title_date_captured: bool,
    residue: Residue,
) -> dict[str, CaptureOutcome]:
    """Classify every capture attempt's typed outcome from the detector results + the residue scan.

    ``title_date`` is recorded for completeness but is never gated: an uncaptured title-page date is
    already a ``flags.yaml`` signal (``title-page-uncaptured-date``) and a legitimate ~3% of the
    corpus has no cover date, so it is benign-by-default (``absent-expected``) here, not a miss."""
    return {
        "revisions": _revisions(revisions_count, revision_failed, residue),
        "tables": _tables(tables_count, residue),
        "refs": _refs(refs_count, residue),
        "toc": _toc(toc_count, residue),
        "title_date": CaptureOutcome(CAPTURED if title_date_captured else ABSENT_EXPECTED),
    }


def manifest_dict(doc_id: str, outcomes: dict[str, CaptureOutcome], residue: Residue) -> dict:
    """Serialise the classified outcomes + residue into the ``capture.yaml`` mapping (§6.4)."""
    captures: dict[str, dict] = {}
    for kind, outcome in outcomes.items():
        entry: dict[str, object] = {"outcome": outcome.outcome}
        if outcome.count is not None:
            entry["count"] = outcome.count
        captures[kind] = entry
    return {
        "doc_id": doc_id,
        "captures": captures,
        "residue": {
            "revision_heading_present": residue.revision_heading_present,
            "legacy_toc_heading_present": residue.legacy_toc_heading_present,
            "heading_present": residue.heading_present,
            "qualifying_table_count": residue.qualifying_table_count,
        },
    }


def build_manifest(
    doc_id: str,
    body: str,
    toc_titles: frozenset[str],
    *,
    revisions_count: int,
    revision_failed: bool,
    tables_count: int,
    refs_count: int,
    toc_count: int,
    title_date_captured: bool,
) -> dict:
    """Scan the residue, classify each attempt, and return the serialisable ``capture.yaml`` dict —
    the one call the ``stage.py`` driver makes (§6.4)."""
    residue = scan_residue(body, toc_titles)
    outcomes = classify(
        revisions_count=revisions_count,
        revision_failed=revision_failed,
        tables_count=tables_count,
        refs_count=refs_count,
        toc_count=toc_count,
        title_date_captured=title_date_captured,
        residue=residue,
    )
    return manifest_dict(doc_id, outcomes, residue)


def has_unexpected_absence(manifest: dict) -> bool:
    """True if any capture attempt in ``manifest`` is ``absent-unexpected`` — the per-document
    silent-miss signal the ``validate`` gate trips on (§8). Reads the serialised mapping so both the
    driver (counting) and the verifier (gating) share one definition."""
    return any(c.get("outcome") == ABSENT_UNEXPECTED for c in manifest.get("captures", {}).values())
