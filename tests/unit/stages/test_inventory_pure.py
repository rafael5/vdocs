"""The inventory rows the index stage publishes (inventory browser step 1).

Real objects, no mocks: a small inventory planting the shapes the 2026-11-05 ``inventory.json``
holds (13 MB, too big to commit) — a file listed twice on one page with every field identical,
and one manual (``DVBA_UM``, DOCX and PDF) listed three times under three titles and two doc
codes. Uniqueness over the real inventory is checked on the lake after the rebuild.
"""

from __future__ import annotations

import hashlib
from collections import Counter

from vdocs.kernel.ids import doc_id
from vdocs.kernel.personas import PROFILE_TAGS, ProfileMaps
from vdocs.models.catalog import EnrichedRecord
from vdocs.stages.enrich.enrich_pure import profile_frontmatter
from vdocs.stages.fetch.fetch_pure import GatePolicy, sole_survivors
from vdocs.stages.index.inventory_pure import (
    INVENTORY_COLUMNS,
    InventoryRow,
    canonical,
    inventory_hash,
    inventory_rows,
    row_keys,
    same_code_app_names,
)
from vdocs.stages.serve_inventory.completeness_pure import DISPOSITIONS, completeness_report

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


# --- the rows -------------------------------------------------------------------------------

POLICY = GatePolicy(
    allowed_system_prefixes=("VistA",),
    denied_app_status=frozenset({"decommissioned"}),
    omitted_doc_codes=frozenset({"RN", "DIBR"}),
)
MAPS = ProfileMaps(
    app_user={"CAPRI": "clinical-admin", "XU": "sysadmin"},
    software_class={"CAPRI": "I", "XU": "I"},
    function_category={"CAPRI": "Benefits"},
    doc_user={"UM": "operator", "UG": "operator", "TM": "developer"},
)
PAGE_XU = "https://www.va.gov/vdl/application.asp?appid=3"
PAGE_WEB = "https://www.va.gov/vdl/application.asp?appid=4"
FORM_URL = "http://www.vba.va.gov/pubs/forms/VBA-21-526-ARE"


def mixed_inventory() -> list[EnrichedRecord]:
    """The two key shapes plus a record down every disposition."""
    xu = "https://www.va.gov/vdl/documents/Infrastructure/Kernel/"

    def xu_rec(slug: str, fmt: str = "docx", **kw: str) -> EnrichedRecord:
        return _rec("XU", slug, fmt, page=PAGE_XU, url=xu + slug, **kw).model_copy(
            update={
                "app_status": kw.get("app_status", "active"),
                "anchor_key": f"XU:XU:{kw.get('doc_code', 'UM')}:{slug}",
            }
        )

    archived_rn = xu_rec("xu_old_rn", doc_code="RN").model_copy(update={"app_status": "archive"})
    unclassified = xu_rec("xu_new_um").model_copy(update={"system_type": "unclassified"})
    web = _rec("WEBP", "webp_ug", page=PAGE_WEB, url=xu + "webp_ug").model_copy(
        update={"system_type": "Web client"}
    )
    form = _rec("VBA", "vba_21_526", "pdf", page=PAGE_XU, url=FORM_URL).model_copy(
        update={"noise_type": "vba_form"}
    )
    return [
        *inventory(),
        xu_rec("xu_tm", doc_code="TM"),
        xu_rec("xu_tm", "pdf", doc_code="TM"),  # covered by its DOCX twin
        xu_rec("xu_only_pdf", "pdf"),  # held, sole format
        xu_rec("xu_legacy", "doc"),  # unreachable
        xu_rec("xu_rn", doc_code="RN"),  # excluded
        archived_rn,  # held, sole survivor
        unclassified,  # undecided
        web,  # not VistA
        form,  # not VistA, noise
    ]


def _rows() -> tuple[list[EnrichedRecord], list[InventoryRow]]:
    recs = mixed_inventory()
    return recs, inventory_rows(recs, POLICY, MAPS)


class TestInventoryRows:
    def test_one_row_per_record_in_record_order_with_unique_keys(self) -> None:
        recs, rows = _rows()
        assert len(rows) == len(recs)
        assert [r.row_key for r in rows] == row_keys(recs)
        assert len({r.row_key for r in rows}) == len(rows)

    def test_disposition_counts_equal_the_completeness_report(self) -> None:
        recs, rows = _rows()
        report = completeness_report(recs, POLICY, sole_survivors=sole_survivors(recs, POLICY))
        counts = Counter(r.disposition for r in rows)
        assert counts == Counter(
            {
                "held": report.held,
                "not-vista": report.not_vista,
                "excluded": report.excluded_by_policy,
                "covered-by-other-format": report.covered_by_other_format,
                "unreachable": report.unreachable,
                "undecided": report.undecided,
            }
        )
        assert set(counts) == DISPOSITIONS  # the fixture reaches every disposition
        not_held = Counter(r.reason for r in rows if r.disposition != "held")
        assert not_held == Counter(report.by_reason)

    def test_the_sole_survivor_rule_reaches_the_rows(self) -> None:
        _, rows = _rows()
        survivor = next(r for r in rows if r.doc_id == "XU:xu_old_rn")
        assert (survivor.disposition, survivor.reason_kind, survivor.reason_value) == (
            "held",
            "sole-survivor",
            "RN",
        )

    def test_doc_id_is_the_kernel_join_key(self) -> None:
        recs, rows = _rows()
        assert [r.doc_id for r in rows] == [doc_id(r) for r in recs]

    def test_profile_tags_equal_the_ones_baked_into_gold(self) -> None:
        """The gold documents' tags are what enrich bakes into the body frontmatter; a record
        must carry the same four, with an absent tag published as empty."""
        recs, rows = _rows()
        for rec, row in zip(recs, rows, strict=True):
            baked = profile_frontmatter(rec, MAPS)
            assert {t: getattr(row, t) for t in PROFILE_TAGS} == {
                t: baked.get(t, "") for t in PROFILE_TAGS
            }
        capri = next(r for r in rows if r.app_code == "CAPRI" and r.doc_type == "UG")
        assert (capri.app_user, capri.doc_user, capri.function_category) == (
            "clinical-admin",
            "clinical-admin",
            "Benefits",
        )

    def test_a_row_carries_the_listing_as_the_vdl_shows_it(self) -> None:
        recs, rows = _rows()
        rec, row = recs[2], rows[2]
        assert row.as_tuple() == (
            row.row_key,
            "CAPRI:dvba_um",
            "CAPRI",
            rec.app_name_full,
            "FIN",
            "UM",
            "CAPRI User Manual",
            "dvba_um.docx",
            "docx",
            rec.patch_id,
            "active",
            "VistA",
            DVBA + ".docx",
            PAGE_CAPRI,
            "clinical-admin",
            "clinical-admin",
            "I",
            "Benefits",
            "CAPRI",
            "held",
            "",
            "doctype-kept",
            "UM",
        )
        assert INVENTORY_COLUMNS[0] == "row_key" and len(INVENTORY_COLUMNS) == len(row.as_tuple())


class TestInventoryHash:
    """Stamped into meta so doctor can tell when the table no longer matches inventory.json."""

    def test_it_ignores_the_order_va_lists_the_records_in(self) -> None:
        recs = mixed_inventory()
        assert inventory_hash(recs) == inventory_hash(list(reversed(recs)))

    def test_it_is_the_canonical_hash_of_the_sorted_canonical_records(self) -> None:
        recs = inventory()
        lines = sorted(canonical(r) for r in recs)
        assert inventory_hash(recs) == hashlib.sha256("\n".join(lines).encode()).hexdigest()

    def test_any_change_to_a_record_changes_it(self) -> None:
        recs = inventory()
        edited = [recs[0].model_copy(update={"doc_title": "renamed"}), *recs[1:]]
        assert inventory_hash(edited) != inventory_hash(recs)


def test_namespaces_map_to_the_same_code_applications_name() -> None:
    recs = [
        *inventory(),
        _rec("XU", "xu_um", page=PAGE_XU, url="u").model_copy(update={"pkg_ns": "XUSC"}),
    ]
    recs = [r.model_copy(update={"app_name_full": f"{r.app_name_abbrev} app"}) for r in recs]
    assert same_code_app_names(recs) == {"PRCA": "PRCA app", "CAPRI": "CAPRI app", "XUSC": ""}
