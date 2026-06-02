"""Pure logic for `serve-inventory` — the stable doc_id + the HARD GATE (§7.3, §8, spec §7).

No I/O: the gate is a pure function of the enriched records (plus the crawl's document
count), so "is the gold inventory fit to bless?" is decided deterministically and tested
offline. The driver (`stage.py`) reads/writes the artifacts and calls these.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from vdocs.models.catalog import EnrichedRecord
from vdocs.models.stage import Acquisition

# The inventory is the gatekeeper: nothing outside these noise classes is a valid value.
VALID_NOISE = frozenset({"", "vba_form", "va_ref", "test_document"})


def doc_id(record: EnrichedRecord) -> str:
    """The inventory's stable join key — ``app_code:doc_slug`` (§5.5). PDF/DOCX of one
    logical document share it (they share ``doc_slug``)."""
    return f"{record.app_name_abbrev}:{record.doc_slug}"


@dataclass(frozen=True)
class GateResult:
    """The HARD GATE verdict: green ⇒ the gold inventory is blessed (the fetch gate)."""

    ok: bool
    reason: str = ""
    unclassified: int = 0  # apps with no system_type mapping — a soft data-quality signal


def evaluate_gate(records: list[EnrichedRecord], crawl_documents: int | None) -> GateResult:
    """The serve-inventory postflight gate (§8): the gold inventory is blessed ``ok`` only when
    it is **complete vs. the crawl**, **noise-classified**, **system-classified**, and
    structurally sound — no information loss (spec §7). Returns the first hard failure.

    ``crawl_documents`` is the crawl's reported document count (1:1 check); ``None`` skips it.
    """
    if not records:
        return GateResult(ok=False, reason="gold inventory is empty")

    # 1:1 with the crawl — enrichment must neither add nor drop a row.
    if crawl_documents is not None and len(records) != crawl_documents:
        return GateResult(
            ok=False,
            reason=f"inventory has {len(records)} records but crawl found {crawl_documents}",
        )

    for r in records:
        if r.noise_type not in VALID_NOISE:
            return GateResult(
                ok=False, reason=f"unclassified noise_type {r.noise_type!r} for {doc_id(r)}"
            )
        if not r.system_type:
            return GateResult(ok=False, reason=f"missing system_type for {doc_id(r)}")
        if not r.section_code:
            return GateResult(
                ok=False, reason=f"missing section_code for {doc_id(r)} ({r.section_name!r})"
            )
        if not r.doc_format:
            return GateResult(ok=False, reason=f"missing doc_format for {doc_id(r)}")

    # Soft signal: every app should map to a system_type; surface (don't block on) any gaps.
    unclassified = sum(1 for r in records if r.system_type == "unclassified")
    return GateResult(ok=True, unclassified=unclassified)


# --- inventory_status = enriched ⋈ acquisitions (the operator view, §5.5, §9.5) ---

_STATUS_ORDER = ("fetched", "pending", "failed", "withdrawn", "not_acquired")


@dataclass(frozen=True)
class InventoryStatus:
    """One genuine logical document, annotated with its fetch status (the join, per doc_id)."""

    doc_id: str
    app_name_abbrev: str
    section_code: str
    doc_code: str
    doc_title: str
    status: str  # fetched | pending | failed | withdrawn | not_acquired
    sha256: str = ""
    fetched_at: str = ""


def inventory_status(
    records: list[EnrichedRecord], acquisitions: dict[str, Acquisition]
) -> list[InventoryStatus]:
    """Join the genuine inventory rows (``noise_type==''``) with their acquisition status by
    ``doc_id`` — one entry per logical document (PDF/DOCX collapse). Status is ``not_acquired``
    when no acquisition exists yet. The inventory stays the gatekeeper; status is joined *to* it."""
    seen: dict[str, InventoryStatus] = {}
    for r in records:
        if r.noise_type:
            continue
        did = doc_id(r)
        if did in seen:
            continue
        acq = acquisitions.get(did)
        seen[did] = InventoryStatus(
            doc_id=did,
            app_name_abbrev=r.app_name_abbrev,
            section_code=r.section_code,
            doc_code=r.doc_code,
            doc_title=r.doc_title,
            status=acq.status if acq is not None else "not_acquired",
            sha256=(acq.sha256 or "") if acq is not None else "",
            fetched_at=(acq.fetched_at or "") if acq is not None else "",
        )
    return list(seen.values())


def status_summary(statuses: list[InventoryStatus]) -> dict[str, int]:
    """Counts by fetch status (+ ``total``) for the ``vdocs inventory --status`` report."""
    counts = Counter(s.status for s in statuses)
    out = {"total": len(statuses)}
    out.update({k: counts[k] for k in _STATUS_ORDER if counts[k]})
    return out
