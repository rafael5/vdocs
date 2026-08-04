"""VO.8 — a document is not excluded for being unreadable by our converter.

The pipeline is DOCX-only (§1) because the VDL publishes nearly everything twice and DOCX converts
better: 2,866 of the 2,885 PDF-excluded records have a DOCX twin, so the rule costs nothing there.
For the remaining 19 it costs the document entirely — among them **both CPRS Technical Manuals**
and **both Kernel 8.0 binders**, absent from the corpus not by any decision but because of the
format they happen to be published in.

That is an implementation limitation acting as a scope decision, which is exactly what the
completeness definition forbids. So: admit a non-DOCX record when no DOCX representation of that
document exists anywhere and policy would otherwise admit it. A rule, not an allowlist — it stays
correct as the VDL changes, and it can never re-admit a duplicate.
"""

from vdocs.models.catalog import EnrichedRecord
from vdocs.stages.fetch.fetch_pure import GatePolicy, Selection, select_fetch_targets

POLICY = GatePolicy(
    allowed_system_prefixes=("VistA",),
    denied_app_status=frozenset({"decommissioned"}),
    omitted_doc_codes=frozenset({"RN"}),
)


def rec(slug: str, **kw) -> EnrichedRecord:
    base = dict(
        app_name_abbrev="XU",
        doc_slug=slug,
        doc_code="UM",
        doc_format="docx",
        system_type="VistA",
        app_status="active",
        anchor_key="XU:XU:UM",
    )
    return EnrichedRecord(**{**base, **kw})


def test_a_pdf_only_document_is_admitted() -> None:
    targets = select_fetch_targets([rec("m", doc_format="pdf")], Selection(all_=True), POLICY)
    assert [t.doc_slug for t in targets] == ["m"]


def test_a_pdf_with_a_docx_twin_is_still_excluded() -> None:
    """The 2,866-record case. Admitting these would double the corpus with worse conversions."""
    records = [rec("m-docx"), rec("m-pdf", doc_format="pdf")]
    targets = select_fetch_targets(records, Selection(all_=True), POLICY)
    assert [t.doc_slug for t in targets] == ["m-docx"]


def test_the_docx_wins_when_both_share_a_slug() -> None:
    records = [rec("m", doc_format="pdf"), rec("m")]
    targets = select_fetch_targets(records, Selection(all_=True), POLICY)
    assert [t.doc_format for t in targets] == ["docx"]


def test_format_admission_does_not_bypass_the_doctype_policy() -> None:
    records = [rec("rn", doc_code="RN", doc_format="pdf", anchor_key="XU:XU:RN")]
    assert select_fetch_targets(records, Selection(all_=True), POLICY) == []


def test_format_admission_does_not_bypass_app_scope() -> None:
    records = [rec("m", doc_format="pdf", system_type="COTS product")]
    assert select_fetch_targets(records, Selection(all_=True), POLICY) == []


def test_format_admission_does_not_bypass_noise() -> None:
    records = [rec("f", doc_format="pdf", noise_type="vba_form")]
    assert select_fetch_targets(records, Selection(all_=True), POLICY) == []


def test_a_pdf_only_sole_survivor_is_admitted() -> None:
    """VO.7 and VO.8 compose: an archived, omitted-type, PDF-only document with nothing newer."""
    records = [
        rec("vdd", doc_code="VDD", doc_format="pdf", app_status="archive", anchor_key="XU:XU:VDD")
    ]
    policy = GatePolicy(
        allowed_system_prefixes=("VistA",),
        denied_app_status=frozenset(),
        omitted_doc_codes=frozenset({"VDD"}),
    )
    assert [t.doc_slug for t in select_fetch_targets(records, Selection(all_=True), policy)] == [
        "vdd"
    ]


def test_pandoc_cannot_read_pdf_so_routing_must_be_format_aware() -> None:
    """VO.8's other half: admitting a PDF is useless if `convert` hands it to Pandoc, which
    cannot read one. The Docling allowlist is keyed by document; the format rule is universal."""
    from vdocs.stages.convert.convert_pure import needs_docling

    assert needs_docling("pdf", key="XU/m", routing=frozenset()) is True
    assert needs_docling("docx", key="XU/m", routing=frozenset()) is False
    # the existing ADR-010 allowlist still forces Docling for a DOCX
    assert (
        needs_docling("docx", key="CPRS/cprsguium", routing=frozenset({"CPRS/cprsguium"})) is True
    )


def test_docling_post_processing_is_docx_only() -> None:
    """VO.8 defect caught by the conversion assessment: `_docling_convert` recovered images by
    reading the source as a DOCX zip. Routing a PDF there raises `BadZipFile` — the document
    would fail to convert entirely. The image-recovery step is a DOCX affordance (Docling parses
    no alt-text from DOCX XML); PDFs keep Docling's own output."""
    from vdocs.stages.convert.convert_pure import recovers_docx_images

    assert recovers_docx_images("docx") is True
    assert recovers_docx_images("pdf") is False
    assert recovers_docx_images("PDF") is False


class TestDoclingImageMode:
    """VO.8d — figures from a PDF must reach the shared asset CAS, as DOCX figures do.

    The two formats need opposite Docling settings. For DOCX we ask for `placeholder` and recover
    the images from the source zip ourselves, because Docling parses no alt-text from DOCX XML and
    the alt-text is worth more than the pixels. A PDF has no zip and no alt-text to recover, so
    Docling has to export the images itself or they are lost — which is why the Kernel Developer's
    Guide carried 539 `<!-- image -->` placeholders and no figures.
    """

    def test_docx_keeps_placeholders_so_alt_text_can_be_recovered(self) -> None:
        from vdocs.stages.convert.convert_pure import docling_image_mode

        assert docling_image_mode("docx") == "placeholder"

    def test_pdf_asks_docling_to_export_the_images(self) -> None:
        from vdocs.stages.convert.convert_pure import docling_image_mode

        assert docling_image_mode("pdf") == "referenced"
        assert docling_image_mode("PDF") == "referenced"
