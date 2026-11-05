"""The inventory rows the index stage publishes (inventory browser step 1).

Real objects, no mocks: a small inventory planting the shapes the 2026-11-05 ``inventory.json``
holds (13 MB, too big to commit) — a file listed twice on one page with every field identical,
and one manual (``DVBA_UM``, DOCX and PDF) listed three times under three titles and two doc
codes. Uniqueness over the real inventory is checked on the lake after the rebuild.
"""

from __future__ import annotations

from vdocs.models.catalog import EnrichedRecord
from vdocs.stages.index.inventory_pure import row_keys

PAGE_CAPRI = "https://www.va.gov/vdl/application.asp?appid=133"
PAGE_PRCA = "https://www.va.gov/vdl/application.asp?appid=21"
DVBA = "https://www.va.gov/vdl/documents/Financial_Admin/CAPRI/DVBA_UM"
PRCA = (
    "https://www.va.gov/vdl/documents/Financial_Admin/Accounts_Receivable_(AR)/prca_4_5_p455_dibr"
)


def _rec(
    app: str,
    slug: str,
    fmt: str = "docx",
    *,
    page: str,
    url: str,
    doc_code: str = "UM",
    title: str = "",
) -> EnrichedRecord:
    return EnrichedRecord(
        section_name="Financial-Administrative",
        section_code="FIN",
        app_name_abbrev=app,
        system_type="VistA",
        pkg_ns=app,
        doc_code=doc_code,
        doc_title=title or f"{slug} title",
        doc_filename=f"{slug}.{fmt}",
        doc_slug=slug,
        doc_format=fmt,
        app_url=page,
        doc_url=f"{url}.{fmt}",
    )


def inventory() -> list[EnrichedRecord]:
    """The two shapes no combination of listing fields tells apart."""
    dvba = [
        ("CAPRI User Manual", "UM"),
        ("CAPRI DVBA User Manual", "UM"),
        ("CAPRI Compensation and Pension Worksheet Module", "UG"),
    ]
    return [
        # one file listed twice on one page, every field identical
        _rec("PRCA", "prca_4_5_p455_dibr", page=PAGE_PRCA, url=PRCA, doc_code="DIBR"),
        _rec("PRCA", "prca_4_5_p455_dibr", page=PAGE_PRCA, url=PRCA, doc_code="DIBR"),
        # DVBA_UM: three listings of each format, three titles, two doc codes
        *(
            _rec("CAPRI", "dvba_um", page=PAGE_CAPRI, url=DVBA, doc_code=c, title=t)
            for t, c in dvba
        ),
        *(
            _rec("CAPRI", "dvba_um", "pdf", page=PAGE_CAPRI, url=DVBA, doc_code=c, title=t)
            for t, c in dvba
        ),
    ]


class TestRowKeys:
    def test_every_listing_gets_its_own_key(self) -> None:
        recs = inventory()
        assert len(set(row_keys(recs))) == len(recs)

    def test_identical_listings_differ_only_by_their_ordinal(self) -> None:
        keys = row_keys(inventory())
        assert keys[0] != keys[1]
        assert keys[0].rsplit(":", 1)[0] == keys[1].rsplit(":", 1)[0]

    def test_a_key_follows_the_listings_content_not_the_page_order(self) -> None:
        recs = inventory()
        keys = row_keys(recs)
        rev = list(reversed(recs))
        by_content = {r.model_dump_json(): k for r, k in zip(rev, row_keys(rev), strict=True)}
        assert sorted(row_keys(rev)) == sorted(keys)
        for r, k in zip(recs[2:], keys[2:], strict=True):  # the DVBA_UM listings are all distinct
            assert by_content[r.model_dump_json()] == k
