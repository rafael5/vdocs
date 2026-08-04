"""The crawl completeness floor (CI.1) — pure verdict logic.

A crawl finding materially less than the last good one must red instead of becoming the new
truth; a whole section going dark must red even when the total stays within tolerance (the
live sections are skewed: Monograph holds 2 documents, Infrastructure 8.7% — a 10% total
floor alone would miss either vanishing).
"""

from __future__ import annotations

from vdocs.models.catalog import (
    Catalog,
    CatalogApplication,
    CatalogDocument,
    CatalogSection,
)
from vdocs.stages.crawl.floor_pure import CrawlYield, check_floor, yield_of


def _catalog(section_docs: dict[str, int]) -> Catalog:
    sections = []
    for name, n in section_docs.items():
        docs = [
            CatalogDocument(
                title=f"{name}-{i}",
                url=f"http://x/{name}/{i}.docx",
                filename=f"{i}.docx",
                file_ext=".docx",
            )
            for i in range(n)
        ]
        sections.append(
            CatalogSection(
                name=name,
                url=f"http://x/{name}",
                applications=[
                    CatalogApplication(
                        name="App", app_code="APP", url=f"http://x/{name}/app", documents=docs
                    )
                ],
            )
        )
    return Catalog(sections=sections)


def test_yield_of_counts_documents_per_section() -> None:
    y = yield_of(_catalog({"Clinical": 3, "Infra": 2, "Empty": 0}))
    assert y.documents == 5
    assert y.section_docs == {"Clinical": 3, "Infra": 2, "Empty": 0}


def test_first_crawl_with_no_baseline_passes() -> None:
    verdict = check_floor(None, CrawlYield(documents=10, section_docs={"A": 10}), floor_ratio=0.9)
    assert verdict.ok


def test_empty_baseline_defends_nothing() -> None:
    prior = CrawlYield(documents=0, section_docs={})
    verdict = check_floor(prior, CrawlYield(documents=0, section_docs={}), floor_ratio=0.9)
    assert verdict.ok


def test_within_tolerance_passes() -> None:
    prior = CrawlYield(documents=100, section_docs={"A": 100})
    verdict = check_floor(prior, CrawlYield(documents=95, section_docs={"A": 95}), floor_ratio=0.9)
    assert verdict.ok


def test_growth_passes() -> None:
    prior = CrawlYield(documents=100, section_docs={"A": 100})
    verdict = check_floor(
        prior, CrawlYield(documents=120, section_docs={"A": 120}), floor_ratio=0.9
    )
    assert verdict.ok


def test_materially_smaller_reds_with_counts_in_reason() -> None:
    prior = CrawlYield(documents=100, section_docs={"A": 100})
    verdict = check_floor(prior, CrawlYield(documents=50, section_docs={"A": 50}), floor_ratio=0.9)
    assert not verdict.ok
    assert "100" in verdict.reason and "50" in verdict.reason


def test_empty_crawl_against_real_baseline_reds() -> None:
    prior = CrawlYield(documents=100, section_docs={"A": 100})
    verdict = check_floor(prior, CrawlYield(documents=0, section_docs={}), floor_ratio=0.9)
    assert not verdict.ok


def test_vanished_section_reds_even_when_total_is_within_tolerance() -> None:
    # Monograph-shaped: the tiny section disappears, the total barely moves.
    prior = CrawlYield(documents=100, section_docs={"Big": 98, "Monograph": 2})
    current = CrawlYield(documents=98, section_docs={"Big": 98})
    verdict = check_floor(prior, current, floor_ratio=0.9)
    assert not verdict.ok
    assert "Monograph" in verdict.reason


def test_section_present_but_emptied_reds() -> None:
    prior = CrawlYield(documents=100, section_docs={"Big": 98, "Infra": 2})
    current = CrawlYield(documents=99, section_docs={"Big": 99, "Infra": 0})
    verdict = check_floor(prior, current, floor_ratio=0.9)
    assert not verdict.ok
    assert "Infra" in verdict.reason


def test_section_empty_in_baseline_may_stay_empty() -> None:
    prior = CrawlYield(documents=10, section_docs={"A": 10, "Empty": 0})
    verdict = check_floor(
        prior, CrawlYield(documents=10, section_docs={"A": 10, "Empty": 0}), floor_ratio=0.9
    )
    assert verdict.ok


def test_both_failures_are_named_together() -> None:
    prior = CrawlYield(documents=100, section_docs={"A": 50, "B": 50})
    verdict = check_floor(prior, CrawlYield(documents=40, section_docs={"A": 40}), floor_ratio=0.9)
    assert not verdict.ok
    assert "B" in verdict.reason  # the vanished section is named
    assert "40" in verdict.reason  # and the shrink is quantified
