"""Snapshot identity and naming (VO.2) — pure, no I/O.

A snapshot is evidence: it is never rewritten, and a crawl that found the same thing must not
manufacture a second one. Identity is therefore the *canonical content* of the catalog — a hash
over sorted rows — not the file's bytes, whose order follows the order VA happened to list pages
in. Two crawls on one day must still produce two distinct directories, or the second would
overwrite the first and break immutability.
"""

from __future__ import annotations

from vdocs.models.catalog import (
    Catalog,
    CatalogApplication,
    CatalogDocument,
    CatalogSection,
)
from vdocs.stages.crawl.snapshot_pure import canonical_hash, snapshot_name, snapshot_order


def _doc(n: int) -> CatalogDocument:
    return CatalogDocument(
        title=f"Doc {n}", url=f"http://x/d{n}.docx", filename=f"d{n}.docx", file_ext=".docx"
    )


def _catalog(*, reverse: bool = False, status: str = "active") -> Catalog:
    apps = [
        CatalogApplication(
            name="Nursing",
            app_code="NUR",
            url="http://x/application.asp?appid=10",
            status=status,
            documents=[_doc(1), _doc(2)],
        ),
        CatalogApplication(
            name="Lab",
            app_code="LR",
            url="http://x/application.asp?appid=11",
            documents=[_doc(3)],
        ),
    ]
    if reverse:
        apps = list(reversed(apps))
        for app in apps:
            app.documents = list(reversed(app.documents))
    return Catalog(
        sections=[
            CatalogSection(name="Clinical", url="http://x/section.asp?secid=1", applications=apps)
        ]
    )


def test_hash_is_stable_across_page_ordering() -> None:
    """A VDL list reorder is not a change — else every reorder fabricates a snapshot."""
    assert canonical_hash(_catalog()) == canonical_hash(_catalog(reverse=True))


def test_hash_changes_when_a_lifecycle_label_changes() -> None:
    assert canonical_hash(_catalog()) != canonical_hash(_catalog(status="archive"))


def test_hash_changes_when_a_document_is_added() -> None:
    more = _catalog()
    more.sections[0].applications[0].documents.append(_doc(9))
    assert canonical_hash(_catalog()) != canonical_hash(more)


def test_hash_sees_an_application_that_has_no_documents() -> None:
    """``Catalog.walk`` yields nothing for an empty application; the hash must still see it."""
    with_empty = _catalog()
    with_empty.sections[0].applications.append(
        CatalogApplication(name="New", app_code="NEW", url="http://x/application.asp?appid=12")
    )
    assert canonical_hash(_catalog()) != canonical_hash(with_empty)


def test_snapshot_name_is_the_crawl_date() -> None:
    assert snapshot_name("2026-06-10", taken=()) == "2026-06-10"


def test_snapshot_name_never_reuses_a_taken_directory() -> None:
    """Two crawls in one day must not collide — an overwritten snapshot is not evidence."""
    assert snapshot_name("2026-06-10", taken=("2026-06-10",)) == "2026-06-10-2"
    assert snapshot_name("2026-06-10", taken=("2026-06-10", "2026-06-10-2")) == "2026-06-10-3"


def test_snapshots_order_by_day_then_by_same_day_sequence() -> None:
    """A new crawl is deduplicated against the *newest* snapshot, so 'newest' must be right —
    lexically '2026-06-10-10' sorts before '-2', which would compare against the wrong one."""
    names = ["2026-06-10-10", "2026-06-10", "2026-07-01", "2026-06-10-2"]
    assert sorted(names, key=snapshot_order) == [
        "2026-06-10",
        "2026-06-10-2",
        "2026-06-10-10",
        "2026-07-01",
    ]
