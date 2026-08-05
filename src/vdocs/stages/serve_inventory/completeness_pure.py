"""What "complete" means for this corpus, and whether it currently is (VO.6/VO.9).

The library had no definition of completeness. Without one, "we hold all VistA documentation" was
an assertion nobody could check, and four independent exclusion mechanisms — noise classification,
app scope, file format, doc-type policy — could drop a document while only one of them wrote down
a reason. Silent exclusion is the failure mode this module exists to make impossible.

**The definition.** The corpus is complete when every genuine VistA document is either *held*, or
carries an explicit reason from the closed vocabulary below — and no document is lost to an
**implementation limitation**. That last clause is the load-bearing one:

* a document we chose not to keep (its type is version-bound ephemera) is **policy** — a decision,
  reversible by editing a registry, and compatible with completeness;
* a document we *cannot read* (it exists only as a PDF and the converter takes DOCX) is a
  **limitation** wearing a decision's clothes. It is a hole in the library, and it makes the corpus
  incomplete no matter how the registries are set.

Keeping those two apart is what stops a temporary technical constraint from silently hardening into
scope. Pure functions only — no I/O (§9.2).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from vdocs.models.catalog import EnrichedRecord
from vdocs.stages.fetch.fetch_pure import GatePolicy

# --- the closed vocabulary -------------------------------------------------------------------
# `status` is what became of the document; `reason` is why, and is empty only when it is held.
# A new exclusion mechanism MUST add a reason here — that is the whole point of the closed set.
NOISE_REASONS = {
    "vba_form": "not-vista:vba-form",  # VA benefits forms listed on VistA app pages
    "va_ref": "not-vista:va-reference",
    "test_document": "not-vista:test-document",
}

# Formats the pipeline can actually turn into a body: DOCX via Pandoc, PDF via Docling (VO.8).
# **This set is the boundary between a decision and a limitation** — a document published only in a
# format outside it is unreachable, and that is what makes a library incomplete. Widening the set
# (a converter for legacy `.doc`) is how a hole gets closed; nothing else here needs to change.
CONVERTIBLE_FORMATS = frozenset({"docx", "pdf"})

# `system_type` values meaning "nobody has looked at this application yet". They are **not**
# exclusions: `classify_system` returns "unclassified" for any app_code absent from
# `registries/inventory/system-types.yaml`, so a brand-new VDL application lands here by default.
# Reporting that as not-VistA would record an accident as a decision — the RMPV case, where a
# genuinely new VistA application was dropped in full while the verdict still read COMPLETE.
UNDECIDED_SYSTEM_TYPES = frozenset({"", "unclassified", "unknown"})


@dataclass(frozen=True)
class Disposition:
    """What became of one inventory record, and why.

    ``status`` is one of:
      * ``held`` — in the corpus (or admitted to it);
      * ``not-vista`` — outside the library's subject entirely (forms, non-VistA systems);
      * ``excluded`` — a genuine VistA document we **decided** not to keep (policy);
      * ``covered-by-other-format`` — not fetched, but we hold the same document in another format;
      * ``unreachable`` — a genuine VistA document we **cannot** currently read (a real hole);
      * ``undecided`` — its application has never been classified, so no one has ruled on it.
    """

    status: str
    reason: str


def classify(
    rec: EnrichedRecord,
    policy: GatePolicy,
    *,
    docx_anchors: set[str],
    sole_survivors: set[str],
) -> Disposition:
    """One record's disposition. ``docx_anchors`` is every ``anchor_key`` for which a DOCX
    representation exists somewhere in the library (so a PDF row can tell "duplicate" from "only
    copy"); ``sole_survivors`` is the VO.7 set — archived documents nothing newer supersedes.

    Order matters and is deliberate: **noise first**, so a benefits form on a web-client
    application is reported as a form rather than as a scope miss. The reason a record carries
    must not depend on which of several applicable gates happened to run first.
    """
    if rec.noise_type:
        return Disposition(
            "not-vista", NOISE_REASONS.get(rec.noise_type, f"not-vista:{rec.noise_type}")
        )
    if not policy.app_in_scope(rec):
        # name the disqualifying value, not just the fact — an operator needs to see *what* it was
        if rec.app_status in policy.denied_app_status:
            return Disposition("not-vista", f"not-vista:app-status={rec.app_status}")
        if rec.system_type.strip().lower() in UNDECIDED_SYSTEM_TYPES:
            # an absence of classification, not a classification of absence
            return Disposition("undecided", "undecided:system-type-unclassified")
        return Disposition("not-vista", f"not-vista:system-type={rec.system_type or 'unknown'}")

    admitted = policy.doctype_kept(rec) or rec.anchor_key in sole_survivors
    if rec.out_of_scope_reason:  # a non-DOCX representation
        if rec.anchor_key and rec.anchor_key in docx_anchors:
            # we hold the same document as DOCX and fetch that one — nothing is missing
            return Disposition(
                "covered-by-other-format", f"format:{rec.out_of_scope_reason}-duplicate"
            )
        if not admitted:
            # policy did not want it anyway — the format is not what is keeping it out, and
            # reporting it as a format problem would overstate the hole
            return Disposition("excluded", f"doctype-omitted:{rec.doc_code}")
        if rec.doc_format in CONVERTIBLE_FORMATS:
            return Disposition("held", "sole-format")  # VO.8 admits it and Docling reads it
        return Disposition("unreachable", f"format:{rec.out_of_scope_reason}-only")

    if not policy.doctype_kept(rec):
        if rec.anchor_key in sole_survivors:
            return Disposition("held", "sole-survivor")
        return Disposition("excluded", f"doctype-omitted:{rec.doc_code}")
    return Disposition("held", "")


@dataclass(frozen=True)
class CompletenessReport:
    """The library partitioned by disposition, and the verdict.

    ``complete`` is **not** "we hold everything" — it is "nothing is missing for a reason we did
    not choose". A corpus that deliberately omits release notes is complete; one that silently
    drops a manual because it is a PDF is not.
    """

    total: int
    held: int
    not_vista: int
    excluded_by_policy: int
    covered_by_other_format: int
    unreachable: int
    undecided: int = 0
    by_reason: dict[str, int] = field(default_factory=dict)
    unreachable_by_reason: dict[str, int] = field(default_factory=dict)
    undecided_by_reason: dict[str, int] = field(default_factory=dict)
    # the app codes to classify — a count alone tells an operator nothing they can act on
    undecided_apps: set[str] = field(default_factory=set)

    @property
    def complete(self) -> bool:
        """Nothing missing for a reason we did not choose — so an **unruled** application counts
        against it exactly as a real hole does. The two are reported separately because the
        remedies differ: ``undecided`` needs a registry line, ``unreachable`` needs a converter."""
        return self.unreachable == 0 and self.undecided == 0

    @property
    def verdict(self) -> str:
        return "COMPLETE" if self.complete else "INCOMPLETE"


def docx_anchor_keys(records: list[EnrichedRecord]) -> set[str]:
    """Every ``anchor_key`` with a DOCX representation — the "do we hold this document in a
    readable format at all?" lookup behind the duplicate/only-copy split."""
    return {r.anchor_key for r in records if r.doc_format == "docx" and r.anchor_key}


def completeness_report(
    records: list[EnrichedRecord],
    policy: GatePolicy,
    *,
    sole_survivors: set[str] | None = None,
) -> CompletenessReport:
    """Partition the whole inventory by disposition and rule on completeness."""
    anchors = docx_anchor_keys(records)
    soles = sole_survivors or set()
    counts: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    unreachable: Counter[str] = Counter()
    undecided: Counter[str] = Counter()
    undecided_apps: set[str] = set()
    for rec in records:
        d = classify(rec, policy, docx_anchors=anchors, sole_survivors=soles)
        counts[d.status] += 1
        if d.status != "held":
            reasons[d.reason] += 1
        if d.status == "unreachable":
            unreachable[d.reason] += 1
        if d.status == "undecided":
            undecided[d.reason] += 1
            undecided_apps.add(rec.app_name_abbrev)
    return CompletenessReport(
        total=len(records),
        held=counts["held"],
        not_vista=counts["not-vista"],
        excluded_by_policy=counts["excluded"],
        covered_by_other_format=counts["covered-by-other-format"],
        unreachable=counts["unreachable"],
        undecided=counts["undecided"],
        by_reason=dict(reasons),
        unreachable_by_reason=dict(unreachable),
        undecided_by_reason=dict(undecided),
        undecided_apps=undecided_apps,
    )
