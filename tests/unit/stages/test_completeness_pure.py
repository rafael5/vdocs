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
    DISPOSITIONS,
    REASON_KINDS,
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
        assert classify(
            rec(), POLICY, docx_ids=set(), docx_anchors=set(), sole_survivors=set()
        ) == Disposition("held", "", "doctype-kept", "UM")

    def test_vba_form_is_named_not_vista(self) -> None:
        """The operator's ask: a benefits form should say why it is not fetched, not just that
        it is 'noise'."""
        d = classify(
            rec(noise_type="vba_form"),
            POLICY,
            docx_ids=set(),
            docx_anchors=set(),
            sole_survivors=set(),
        )
        assert d == Disposition("not-vista", "not-vista:vba-form", "noise", "vba_form")

    def test_va_reference_is_named_not_vista(self) -> None:
        d = classify(
            rec(noise_type="va_ref"),
            POLICY,
            docx_ids=set(),
            docx_anchors=set(),
            sole_survivors=set(),
        )
        assert d.reason == "not-vista:va-reference"

    def test_out_of_scope_system_type_names_the_value(self) -> None:
        """App-scope exclusions recorded nothing at all before this."""
        d = classify(
            rec(system_type="Web client"),
            POLICY,
            docx_ids=set(),
            docx_anchors=set(),
            sole_survivors=set(),
        )
        assert d.reason == "not-vista:system-type=Web client"

    def test_an_unclassified_application_is_undecided_not_excluded(self) -> None:
        """`unclassified` is the ABSENCE of a decision, so it must not read as one.

        RMPV (Prosthetics 4-Sight II) arrived on the VDL in no registry, so it classified as
        `unclassified`, was treated as not-VistA, and all 15 of its records were dropped — while
        `completeness` still reported COMPLETE. A genuinely new VistA application vanished from the
        corpus without anyone ruling on it.
        """
        d = classify(
            rec(system_type="unclassified"),
            POLICY,
            docx_ids=set(),
            docx_anchors=set(),
            sole_survivors=set(),
        )
        assert d == Disposition(
            "undecided",
            "undecided:system-type-unclassified",
            "system-type-unclassified",
            "unclassified",
        )

    def test_an_unmapped_application_is_also_undecided(self) -> None:
        """An empty system_type is the same absence, reached a different way."""
        d = classify(
            rec(system_type=""), POLICY, docx_ids=set(), docx_anchors=set(), sole_survivors=set()
        )
        assert d.status == "undecided"

    def test_decommissioned_app_is_named(self) -> None:
        d = classify(
            rec(app_status="decommissioned"),
            POLICY,
            docx_ids=set(),
            docx_anchors=set(),
            sole_survivors=set(),
        )
        assert d.reason == "not-vista:app-status=decommissioned"

    def test_pdf_with_a_docx_twin_is_a_harmless_duplicate(self) -> None:
        """2,866 of 2,885 PDF exclusions are this. Lumping them with the real losses under one
        `pdf` reason is what made the format barrier look like half the library."""
        d = classify(
            rec(doc_format="pdf"),
            POLICY,
            docx_ids=set(),
            docx_anchors={"XU:XU:UM"},
            sole_survivors=set(),
        )
        assert d == Disposition(
            "covered-by-other-format", "format:pdf-duplicate", "format-duplicate", "pdf"
        )

    def test_pdf_twin_with_no_anchor_key_is_paired_by_doc_id(self) -> None:
        """Measured 2026-11-05 (inventory browser step 0): three PDFs whose rows carry no anchor
        key were held as *sole-format* beside a DOCX with the same doc_id. fetch never takes a PDF
        without an anchor key — it takes the DOCX — so "held" claimed a copy nobody downloads."""
        d = classify(
            rec(doc_format="pdf", anchor_key=""),
            POLICY,
            docx_ids={"XU:s"},
            docx_anchors=set(),
            sole_survivors=set(),
        )
        assert d == Disposition(
            "covered-by-other-format", "format:pdf-duplicate", "format-duplicate", "pdf"
        )

    def test_pdf_with_no_docx_anywhere_is_held_via_docling(self) -> None:
        """VO.8 and VO.9 must agree: once the gate admits a PDF-only document and Docling can
        read it, calling it "unreachable" would report a hole that no longer exists."""
        d = classify(
            rec(doc_format="pdf"), POLICY, docx_ids=set(), docx_anchors=set(), sole_survivors=set()
        )
        assert d == Disposition("held", "sole-format", "sole-format", "pdf")

    def test_a_format_no_converter_reads_is_a_real_loss(self) -> None:
        """The definition's teeth: legacy `.doc` has no converter, so a document published only
        that way is genuinely missing — a limitation, not a decision."""
        d = classify(
            rec(doc_format="doc"), POLICY, docx_ids=set(), docx_anchors=set(), sole_survivors=set()
        )
        assert d == Disposition("unreachable", "format:doc-only", "format-only", "doc")

    def test_omitted_doctype_names_the_code(self) -> None:
        d = classify(
            rec(doc_code="RN"), POLICY, docx_ids=set(), docx_anchors=set(), sole_survivors=set()
        )
        assert d == Disposition("excluded", "doctype-omitted:RN", "doctype-omitted", "RN")

    def test_sole_survivor_overrides_the_doctype_omission(self) -> None:
        """VO.7 — the last surviving document of its kind for code still running in VistA is the
        historical record, not ephemera."""
        r = rec(doc_code="RN", app_status="archive", anchor_key="XU:XU:RN")
        d = classify(r, POLICY, docx_ids=set(), docx_anchors=set(), sole_survivors={"XU:XU:RN"})
        assert d == Disposition("held", "sole-survivor", "sole-survivor", "RN")

    def test_noise_is_judged_before_scope(self) -> None:
        """A VBA form on a web-client app is a form first — the reason must be stable regardless
        of which gate would also have caught it."""
        d = classify(
            rec(noise_type="vba_form", system_type="Web client"),
            POLICY,
            docx_ids=set(),
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
            d = classify(r, POLICY, docx_ids=set(), docx_anchors=set(), sole_survivors=set())
            assert d.status == "held" or d.reason, f"silent exclusion: {r.doc_code}"


def _every_branch() -> list[Disposition]:
    """One record down each of classify()'s return paths."""
    none: set[str] = set()
    return [
        classify(r, POLICY, docx_ids=none, docx_anchors=anchors, sole_survivors=soles)
        for r, anchors, soles in (
            (rec(), none, none),
            (rec(noise_type="va_ref"), none, none),
            (rec(app_status="decommissioned"), none, none),
            (rec(system_type=""), none, none),
            (rec(system_type="Web client"), none, none),
            (rec(doc_format="pdf"), {"XU:XU:UM"}, none),
            (rec(doc_format="pdf", doc_code="RN"), none, none),
            (rec(doc_format="pdf"), none, none),
            (rec(doc_format="doc"), none, none),
            (rec(doc_code="RN"), none, none),
            (rec(doc_code="RN", anchor_key="XU:XU:RN"), none, {"XU:XU:RN"}),
        )
    ]


class TestReasonKind:
    """The reason as a structured kind plus value (inventory browser step 1). The string stays as
    it was — the `completeness` CLI prints it — and the kind is what the published vocabulary
    explains, one sentence per kind."""

    def test_the_disqualifying_value_rides_beside_its_kind(self) -> None:
        none: set[str] = set()
        got = [
            (d.kind, d.value)
            for d in (
                classify(rec(app_status="decommissioned"), POLICY, docx_ids=none,
                         docx_anchors=none, sole_survivors=none),
                classify(rec(system_type="Web client"), POLICY, docx_ids=none,
                         docx_anchors=none, sole_survivors=none),
                classify(rec(system_type=""), POLICY, docx_ids=none,
                         docx_anchors=none, sole_survivors=none),
                classify(rec(doc_format="pdf", doc_code="RN"), POLICY, docx_ids=none,
                         docx_anchors=none, sole_survivors=none),
            )
        ]  # fmt: skip
        assert got == [
            ("app-status", "decommissioned"),
            ("system-type", "Web client"),
            ("system-type-unclassified", ""),
            ("doctype-omitted", "RN"),
        ]

    def test_every_record_gets_a_kind_even_when_held_with_no_reason_string(self) -> None:
        assert all(d.kind for d in _every_branch())

    def test_the_kinds_classify_emits_are_exactly_the_closed_set(self) -> None:
        """Both directions: no path emits a kind outside REASON_KINDS, and no kind in the set is
        unreachable — a kind nothing emits would be an explanation describing nothing."""
        assert {d.kind for d in _every_branch()} == REASON_KINDS

    def test_each_kind_belongs_to_one_disposition(self) -> None:
        by_kind: dict[str, set[str]] = {}
        for d in _every_branch():
            by_kind.setdefault(d.kind, set()).add(d.status)
        assert all(len(statuses) == 1 for statuses in by_kind.values())
        assert {s for ss in by_kind.values() for s in ss} == DISPOSITIONS


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

    def test_an_undecided_application_makes_the_corpus_incomplete(self) -> None:
        """The whole point: an unclassified application must force a ruling, not pass silently.

        `complete` means nothing is missing for a reason we did not choose — and nobody chose to
        drop an application that simply arrived after the registries were last curated.
        """
        report = completeness_report([rec(), rec(doc_slug="t", system_type="unclassified")], POLICY)
        assert report.undecided == 1
        assert report.complete is False
        assert report.verdict == "INCOMPLETE"
        assert report.undecided_by_reason == {"undecided:system-type-unclassified": 1}

    def test_the_undecided_applications_are_named(self) -> None:
        """A count is not actionable — the operator needs to know which app_code to classify."""
        report = completeness_report(
            [
                rec(app_name_abbrev="RMPV", system_type="unclassified"),
                rec(app_name_abbrev="RMPV", doc_slug="t", system_type="unclassified"),
                rec(app_name_abbrev="NEW", doc_slug="u", system_type=""),
                rec(),
            ],
            POLICY,
        )
        assert report.undecided == 3
        assert report.undecided_apps == {"NEW", "RMPV"}  # deduplicated, not one entry per record

    def test_undecided_is_reported_separately_from_a_real_hole(self) -> None:
        """Two different problems: one needs a ruling, the other needs a converter."""
        report = completeness_report(
            [
                rec(system_type="unclassified"),
                # a distinct anchor_key, or the first record's DOCX would make this one read as a
                # harmless duplicate instead of the unreadable-format hole the test is about
                rec(doc_slug="t", doc_format="doc", anchor_key="XU:XU:TM"),
            ],
            POLICY,
        )
        assert report.undecided == 1 and report.unreachable == 1
        assert report.undecided_by_reason and report.unreachable_by_reason

    def test_a_pdf_duplicate_does_not_make_the_corpus_incomplete(self) -> None:
        report = completeness_report([rec(), rec(doc_slug="t", doc_format="pdf")], POLICY)
        assert report.complete is True
        assert report.covered_by_other_format == 1

    def test_a_pdf_twin_with_no_anchor_key_is_covered_by_its_docx(self) -> None:
        r = completeness_report([rec(anchor_key=""), rec(doc_format="pdf", anchor_key="")], POLICY)
        assert (r.held, r.covered_by_other_format) == (1, 1)

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
