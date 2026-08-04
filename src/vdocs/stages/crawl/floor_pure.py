"""The crawl completeness floor (CI.1, audit R‑4) — pure verdict logic, no I/O.

Nothing watched the front door: a degraded VDL page made the crawl find less, and the smaller
result silently became the new truth. The floor compares this crawl's yield against the last
*good* one (the catalog already on disk — on a red the driver refuses the overwrite, so the
artifact on disk is always the last good crawl) and reds when the yield is materially smaller
or a previously-populated section comes back empty.

Two rules, because the live sections are skewed (Monograph: 2 documents; Infrastructure: 8.7%
of the corpus — measured at CI.0):

* **total floor** — fewer than ``floor_ratio`` of the baseline's documents is a red;
* **per-section non-zero** — a section that had documents and now has none is a red even when
  the total stays within tolerance (a whole section going dark is the R‑4 failure shape, and
  no defensible total ratio can see the small sections).
"""

from __future__ import annotations

from dataclasses import dataclass

from vdocs.models.catalog import Catalog


@dataclass(frozen=True)
class CrawlYield:
    """What one crawl found — the comparable summary of a raw catalog."""

    documents: int
    section_docs: dict[str, int]  # section name → document count


@dataclass(frozen=True)
class FloorVerdict:
    """The floor's decision; ``reason`` names every failed rule (empty when ok)."""

    ok: bool
    reason: str = ""


def yield_of(catalog: Catalog) -> CrawlYield:
    """Summarize a catalog into the numbers the floor compares."""
    section_docs = {s.name: sum(len(a.documents) for a in s.applications) for s in catalog.sections}
    return CrawlYield(documents=sum(section_docs.values()), section_docs=section_docs)


def check_floor(
    prior: CrawlYield | None, current: CrawlYield, *, floor_ratio: float
) -> FloorVerdict:
    """Compare ``current`` against the last good crawl ``prior``.

    ``prior=None`` (first-ever crawl) and an empty baseline both pass — there is nothing to
    defend yet; the floor only ever protects a real prior yield.
    """
    if prior is None or prior.documents == 0:
        return FloorVerdict(ok=True)
    problems: list[str] = []
    floor = prior.documents * floor_ratio
    if current.documents < floor:
        problems.append(
            f"yield {current.documents} documents < {floor_ratio:.0%} of the last good "
            f"crawl ({prior.documents})"
        )
    dark = [
        name
        for name, had in sorted(prior.section_docs.items())
        if had > 0 and current.section_docs.get(name, 0) == 0
    ]
    if dark:
        problems.append(
            "section(s) went dark: "
            + ", ".join(f"{name} (had {prior.section_docs[name]})" for name in dark)
        )
    if problems:
        return FloorVerdict(ok=False, reason="; ".join(problems))
    return FloorVerdict(ok=True)
