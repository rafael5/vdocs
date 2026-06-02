"""Pure fetch logic — target selection + index entries (§8 fetch, §16).

The pipeline is **DOCX-only** (§1): DOCX is the richer, structure-preserving source and the
only format converted/normalized/published. PDF is out of scope — there is no format fallback,
and a document published only as PDF is never a fetch target. No I/O: the ``stage.py`` driver
does the downloading and content-addressed storage; these functions only decide *what* to fetch
and *how* to address it.
"""

import hashlib
from dataclasses import dataclass
from urllib.parse import urlparse

from vdocs.models.catalog import EnrichedRecord


def url_ext(url: str) -> str:
    """The lowercased file extension of a URL (without the dot), or '' if none."""
    name = urlparse(url).path.rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def _doc_id(rec: EnrichedRecord) -> str:
    """The inventory stable id — ``app_code:doc_slug`` (§5.5)."""
    return f"{rec.app_name_abbrev}:{rec.doc_slug}"


@dataclass(frozen=True)
class Selection:
    """A fetch selection — the §5.6 selection surface, as a pure predicate.

    A selection is the conjunction (AND) of zero or more **dimension filters**, each matching one
    field of :class:`EnrichedRecord`; within a single dimension multiple values are a disjunction
    (OR). ``all_=True`` is the explicit "whole genuine inventory" selector. An otherwise-empty
    selection (no dimensions, not ``all_``) matches **nothing** — there is no blind/full download
    (§5.6 tenet): the operator opts into breadth, never backs into it.

    The selection only ever *narrows*; the two always-on invariants (noise gate §9.5, DOCX scope
    §1) are enforced by :func:`select_fetch_targets` regardless of what a dimension would match.
    """

    apps: frozenset[str] = frozenset()  # --app: app_name_abbrev exact | app_name_full substring
    sections: frozenset[str] = frozenset()  # --section: section_code (exact)
    statuses: frozenset[str] = frozenset()  # --status: app_status (exact)
    doc_types: frozenset[str] = frozenset()  # --doc-type: doc_code (exact)
    groups: frozenset[str] = frozenset()  # --group: group_key | anchor_key (exact)
    ids: frozenset[str] = frozenset()  # --select: doc_id membership (app_code:doc_slug)
    all_: bool = False  # --all: every genuine in-scope row

    @property
    def is_empty(self) -> bool:
        """No dimension set and not ``all_`` ⇒ matches nothing (the no-arguments default)."""
        return not self.all_ and not (
            self.apps or self.sections or self.statuses or self.doc_types or self.groups or self.ids
        )

    def matches(self, rec: EnrichedRecord) -> bool:
        """Does ``rec`` satisfy the predicate? (AND across set dimensions, OR within each.)"""
        if self.all_:
            return True
        if self.is_empty:
            return False
        if self.apps and not (
            rec.app_name_abbrev in self.apps
            or any(v.lower() in rec.app_name_full.lower() for v in self.apps)
        ):
            return False
        if self.sections and rec.section_code not in self.sections:
            return False
        if self.statuses and rec.app_status not in self.statuses:
            return False
        if self.doc_types and rec.doc_code not in self.doc_types:
            return False
        if self.groups and not (rec.group_key in self.groups or rec.anchor_key in self.groups):
            return False
        if self.ids and _doc_id(rec) not in self.ids:
            return False
        return True

    def fingerprint(self) -> str:
        """Canonical, order-independent signature of the normalized predicate (§5.6/§7.3).

        Recorded as part of ``fetch``'s input fingerprint so the selection participates in
        ``SKIP_IF_UNCHANGED``: re-running with the same selection is a no-op; changing it re-runs.
        (The *expanded* doc-id set the selection resolves to need not be hashed here — the gold
        inventory is itself a required ``fetch`` input, so any inventory change that would grow the
        set already trips the gate via ``GOLD_INVENTORY``'s fingerprint.)
        """
        payload = "\n".join(
            [
                f"all={int(self.all_)}",
                "apps=" + ",".join(sorted(self.apps)),
                "sections=" + ",".join(sorted(self.sections)),
                "statuses=" + ",".join(sorted(self.statuses)),
                "doc_types=" + ",".join(sorted(self.doc_types)),
                "groups=" + ",".join(sorted(self.groups)),
                "ids=" + ",".join(sorted(self.ids)),
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def select_fetch_targets(
    records: list[EnrichedRecord], selection: Selection
) -> list[EnrichedRecord]:
    """The documents ``fetch`` will download for ``selection`` — one target per logical document
    version (same ``doc_slug``), the DOCX representation.

    Pipeline (each step only narrows or completes, never widens past the invariants):

    1. **Always-on narrowing** (§5.6 invariants, independent of the selection): genuine rows only
       (``noise_type`` set ⇒ chrome/forms, excluded §9.5) and in-scope only (``out_of_scope_reason``
       set ⇒ a non-DOCX representation, §1 — a PDF-only logical document yields no target).
    2. **Selection predicate**: keep the genuine in-scope rows the selection matches.
    3. **Version completeness** (§5.6 invariant 2): pull in every genuine in-scope row sharing an
       ``anchor_key`` with a matched row, so a filter can never silently drop patches of a selected
       logical document — the historical bodies are what ``push`` replays. (Rows with no resolved
       ``anchor_key`` are matched as singletons.)
    4. **DOCX dedup**: one target per ``doc_slug`` (a PDF/DOCX pair shares it; only the in-scope
       DOCX survives step 1, and distinct versions keep distinct slugs → every version is a target).
    """
    genuine = [r for r in records if not r.noise_type and not r.out_of_scope_reason]
    matched_ids = {id(r) for r in genuine if selection.matches(r)}
    anchors = {r.anchor_key for r in genuine if id(r) in matched_ids and r.anchor_key}
    best: dict[str, EnrichedRecord] = {}
    for rec in genuine:
        if id(rec) in matched_ids or (rec.anchor_key and rec.anchor_key in anchors):
            best.setdefault(rec.doc_slug, rec)
    return list(best.values())


def index_entry(
    *, app_code: str, doc_slug: str, title: str, source_url: str, ext: str
) -> dict[str, str]:
    """A ``raw/index.json`` entry: sha256 → provenance. ``app_code``/``doc_slug`` give the
    downstream bundle path (``<app>/<slug>/`` in ``text@converted``)."""
    return {
        "app_code": app_code,
        "doc_slug": doc_slug,
        "title": title,
        "source_url": source_url,
        "ext": ext,
    }
