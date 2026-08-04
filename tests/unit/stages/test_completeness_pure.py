"""Completeness accounting (VO.6/VO.9) — every genuine record's disposition, from a closed set.

The corpus had no definition of *complete*, so nothing could check the claim that it holds all
VistA documentation. Four mechanisms excluded records and only one wrote a reason down. These are
the pure functions behind the definition: classify every record's disposition, then partition the
library by it and rule on whether the result is complete.

The load-bearing distinction is **policy vs implementation**. A document omitted because its type
is version-bound ephemera is a decision we made; a document missing because the converter only
reads DOCX is a limitation wearing a decision's clothes. Only the first is compatible with
completeness.
"""

from vdocs.models.catalog import EnrichedRecord
from vdocs.stages.fetch.fetch_pure import GatePolicy
from vdocs.stages.serve_inventory.completeness_pure import (
    Disposition,
    classify,
    completeness_report,
)

POLICY = GatePolicy(
    allowed_system_prefixes=("VistA",),
    denied_app_status=frozenset({"decommissioned"}),
    omitted_doc_codes=frozenset({"RN"}),
)


def rec(**kw) -> EnrichedRecord:
    base = dict(
        app_name_abbrev="XU",
        doc_slug="s",
        doc_code="UM",
        doc_format="docx",
        system_type="VistA",
        app_status="active",
        anchor_key="XU:XU:UM",
    )
    return EnrichedRecord(**{**base, **kw})


class TestClassify:
    def test_held_when_the_gate_admits_it(self) -> None:
        assert classify(rec(), POLICY, docx_anchors=set(), sole_survivors=set()) == Disposition(
            "held", ""
        )

    def test_vba_form_is_named_not_vista(self) -> None:
        """The operator's ask: a benefits form should say why it is not fetched, not just that
        it is 'noise'."""
        d = classify(rec(noise_type="vba_form"), POLICY, docx_anchors=set(), sole_survivors=set())
        assert d == Disposition("not-vista", "not-vista:vba-form")

    def test_va_reference_is_named_not_vista(self) -> None:
        d = classify(rec(noise_type="va_ref"), POLICY, docx_anchors=set(), sole_survivors=set())
        assert d.reason == "not-vista:va-reference"

    def test_out_of_scope_system_type_names_the_value(self) -> None:
        """App-scope exclusions recorded nothing at all before this."""
        d = classify(
            rec(system_type="Web client"), POLICY, docx_anchors=set(), sole_survivors=set()
        )
        assert d.reason == "not-vista:system-type=Web client"

    def test_decommissioned_app_is_named(self) -> None:
        d = classify(
            rec(app_status="decommissioned"), POLICY, docx_anchors=set(), sole_survivors=set()
        )
        assert d.reason == "not-vista:app-status=decommissioned"

    def test_pdf_with_a_docx_twin_is_a_harmless_duplicate(self) -> None:
        """2,866 of 2,885 PDF exclusions are this. Lumping them with the real losses under one
        `pdf` reason is what made the format barrier look like half the library."""
        d = classify(
            rec(doc_format="pdf"),
            POLICY,
            docx_anchors={"XU:XU:UM"},
            sole_survivors=set(),
        )
        assert d == Disposition("covered-by-other-format", "format:pdf-duplicate")

    def test_pdf_with_no_docx_anywhere_is_held_via_docling(self) -> None:
        """VO.8 and VO.9 must agree: once the gate admits a PDF-only document and Docling can
        read it, calling it "unreachable" would report a hole that no longer exists."""
        d = classify(rec(doc_format="pdf"), POLICY, docx_anchors=set(), sole_survivors=set())
        assert d == Disposition("held", "sole-format")

    def test_a_format_no_converter_reads_is_a_real_loss(self) -> None:
        """The definition's teeth: legacy `.doc` has no converter, so a document published only
        that way is genuinely missing — a limitation, not a decision."""
        d = classify(rec(doc_format="doc"), POLICY, docx_anchors=set(), sole_survivors=set())
        assert d == Disposition("unreachable", "format:doc-only")

    def test_omitted_doctype_names_the_code(self) -> None:
        d = classify(rec(doc_code="RN"), POLICY, docx_anchors=set(), sole_survivors=set())
        assert d == Disposition("excluded", "doctype-omitted:RN")

    def test_sole_survivor_overrides_the_doctype_omission(self) -> None:
        """VO.7 — the last surviving document of its kind for code still running in VistA is the
        historical record, not ephemera."""
        r = rec(doc_code="RN", app_status="archive", anchor_key="XU:XU:RN")
        d = classify(r, POLICY, docx_anchors=set(), sole_survivors={"XU:XU:RN"})
        assert d == Disposition("held", "sole-survivor")

    def test_noise_is_judged_before_scope(self) -> None:
        """A VBA form on a web-client app is a form first — the reason must be stable regardless
        of which gate would also have caught it."""
        d = classify(
            rec(noise_type="vba_form", system_type="Web client"),
            POLICY,
            docx_anchors=set(),
            sole_survivors=set(),
        )
        assert d.reason == "not-vista:vba-form"

    def test_every_record_gets_a_reason(self) -> None:
        """The definition's core requirement: no silent exclusions."""
        for r in (
            rec(),
            rec(noise_type="vba_form"),
            rec(system_type="COTS product"),
            rec(doc_format="pdf"),
            rec(doc_code="RN"),
        ):
            d = classify(r, POLICY, docx_anchors=set(), sole_survivors=set())
            assert d.status == "held" or d.reason, f"silent exclusion: {r.doc_code}"


class TestCompletenessReport:
    def test_complete_when_every_document_is_held_or_excluded_by_policy(self) -> None:
        report = completeness_report([rec(), rec(doc_slug="t", doc_code="RN")], POLICY)
        assert report.complete is True
        assert report.held == 1 and report.excluded_by_policy == 1
        assert report.unreachable == 0

    def test_incomplete_when_a_document_is_lost_to_an_implementation_limit(self) -> None:
        """A document in a format no converter reads is not a decision anyone made."""
        report = completeness_report([rec(doc_format="doc")], POLICY)
        assert report.complete is False
        assert report.unreachable == 1
        assert "format:doc-only" in report.unreachable_by_reason

    def test_a_pdf_duplicate_does_not_make_the_corpus_incomplete(self) -> None:
        report = completeness_report([rec(), rec(doc_slug="t", doc_format="pdf")], POLICY)
        assert report.complete is True
        assert report.covered_by_other_format == 1

    def test_noise_is_outside_the_library_and_does_not_count_against_it(self) -> None:
        report = completeness_report([rec(), rec(doc_slug="t", noise_type="vba_form")], POLICY)
        assert report.complete is True
        assert report.not_vista == 1

    def test_every_reason_is_counted(self) -> None:
        report = completeness_report(
            [rec(), rec(doc_slug="b", doc_code="RN"), rec(doc_slug="c", noise_type="vba_form")],
            POLICY,
        )
        assert report.by_reason["doctype-omitted:RN"] == 1
        assert report.by_reason["not-vista:vba-form"] == 1
        assert sum(report.by_reason.values()) + report.held == report.total
